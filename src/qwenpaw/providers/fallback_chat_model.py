# -*- coding: utf-8 -*-
"""Fallback wrapper for ordered LLM model candidates."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator as AsyncGeneratorABC
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Literal, Type

from agentscope.model import ChatModelBase
from agentscope.model._model_response import ChatResponse
from agentscope_runtime.engine.schemas.exception import (
    ModelNotFoundException,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

FALLBACK_STATUS_CODES = {404, 429, 500, 502, 503, 504, 529}


@dataclass(frozen=True, slots=True)
class FallbackModelCandidate:
    """One configured fallback candidate."""

    provider_id: str
    model_id: str
    model: ChatModelBase

    @property
    def label(self) -> str:
        return f"{self.provider_id}:{self.model_id}"


def _get_status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _is_provider_transport_error(exc: Exception) -> bool:
    try:
        import httpx

        if isinstance(
            exc,
            (
                httpx.RemoteProtocolError,
                httpx.TimeoutException,
                httpx.NetworkError,
            ),
        ):
            return True
    except ImportError:
        pass
    try:
        import openai

        if isinstance(
            exc,
            (
                openai.APITimeoutError,
                openai.APIConnectionError,
                openai.RateLimitError,
            ),
        ):
            return True
    except ImportError:
        pass
    try:
        import anthropic

        if isinstance(
            exc,
            (
                anthropic.APITimeoutError,
                anthropic.APIConnectionError,
                anthropic.RateLimitError,
            ),
        ):
            return True
    except ImportError:
        pass
    return False


def _is_model_unavailable_400(exc: Exception) -> bool:
    if _get_status_code(exc) != 400:
        return False
    code = str(getattr(exc, "code", "") or "").lower()
    err_type = str(getattr(exc, "type", "") or "").lower()
    text = str(exc).lower()
    joined = " ".join((code, err_type, text))
    model_markers = (
        "model_not_found",
        "model not found",
        "model does not exist",
        "model unavailable",
        "model is unavailable",
        "model not available",
        "model is not available",
    )
    return any(marker in joined for marker in model_markers)


def is_fallbackable_llm_error(exc: Exception) -> bool:
    """Return whether an LLM error should move to the next candidate."""
    if isinstance(exc, ModelNotFoundException):
        return True
    status = _get_status_code(exc)
    if status in FALLBACK_STATUS_CODES:
        return True
    if status in {401, 403}:
        return False
    if _is_model_unavailable_400(exc):
        return True
    return _is_provider_transport_error(exc)


class FallbackChatModel(ChatModelBase):
    """Try ordered LLM candidates until one succeeds before output starts."""

    def __init__(self, candidates: list[FallbackModelCandidate]) -> None:
        if not candidates:
            raise ValueError("FallbackChatModel requires at least one candidate")
        primary = candidates[0]
        super().__init__(
            model_name=primary.model.model_name,
            stream=primary.model.stream,
        )
        self.candidates = candidates

    async def __call__(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: Literal["auto", "none", "required"] | str | None = None,
        structured_model: Type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        last_exc: Exception | None = None
        for index, candidate in enumerate(self.candidates):
            try:
                result = await candidate.model(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    structured_model=structured_model,
                    **kwargs,
                )
            except Exception as exc:
                last_exc = exc
                if not self._should_try_next(exc, index):
                    raise
                self._log_fallback(exc, candidate, index)
                continue

            if isinstance(result, AsyncGeneratorABC):
                return self._wrap_stream_candidate(
                    result,
                    candidate_index=index,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    structured_model=structured_model,
                    kwargs=kwargs,
                )
            return result

        assert last_exc is not None
        raise last_exc

    def _should_try_next(self, exc: Exception, candidate_index: int) -> bool:
        return (
            candidate_index < len(self.candidates) - 1
            and is_fallbackable_llm_error(exc)
        )

    def _log_fallback(
        self,
        exc: Exception,
        candidate: FallbackModelCandidate,
        candidate_index: int,
    ) -> None:
        next_candidate = self.candidates[candidate_index + 1]
        logger.warning(
            "LLM candidate %s failed with fallbackable error; trying %s: %s",
            candidate.label,
            next_candidate.label,
            exc,
        )

    async def _wrap_stream_candidate(
        self,
        stream: AsyncGenerator[ChatResponse, None],
        *,
        candidate_index: int,
        messages: list[dict],
        tools: list[dict] | None,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        structured_model: Type[BaseModel] | None,
        kwargs: dict[str, Any],
    ) -> AsyncGenerator[ChatResponse, None]:
        yielded = False
        try:
            async for chunk in stream:
                yielded = True
                yield chunk
            return
        except Exception as exc:
            if yielded or not self._should_try_next(exc, candidate_index):
                raise
            with suppress(Exception):
                await stream.aclose()
            self._log_fallback(
                exc,
                self.candidates[candidate_index],
                candidate_index,
            )
            async for chunk in self._stream_from_candidates(
                candidate_index + 1,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                structured_model=structured_model,
                kwargs=kwargs,
            ):
                yield chunk

    async def _stream_from_candidates(
        self,
        start_index: int,
        *,
        messages: list[dict],
        tools: list[dict] | None,
        tool_choice: Literal["auto", "none", "required"] | str | None,
        structured_model: Type[BaseModel] | None,
        kwargs: dict[str, Any],
    ) -> AsyncGenerator[ChatResponse, None]:
        last_exc: Exception | None = None
        for index in range(start_index, len(self.candidates)):
            candidate = self.candidates[index]
            try:
                result = await candidate.model(
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    structured_model=structured_model,
                    **kwargs,
                )
            except Exception as exc:
                last_exc = exc
                if not self._should_try_next(exc, index):
                    raise
                self._log_fallback(exc, candidate, index)
                continue

            if isinstance(result, AsyncGeneratorABC):
                async for chunk in self._wrap_stream_candidate(
                    result,
                    candidate_index=index,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    structured_model=structured_model,
                    kwargs=kwargs,
                ):
                    yield chunk
                return
            yield result
            return

        assert last_exc is not None
        raise last_exc
