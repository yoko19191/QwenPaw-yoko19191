# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest
from agentscope.model import ChatModelBase

from qwenpaw.providers.fallback_chat_model import (
    FallbackChatModel,
    FallbackModelCandidate,
)
from qwenpaw.providers.retry_chat_model import (
    RateLimitConfig,
    RetryChatModel,
    RetryConfig,
)


class LLMStatusError(Exception):
    def __init__(self, status_code: int, message: str = "llm error") -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeModel(ChatModelBase):
    def __init__(self, name: str, result=None, exc: Exception | None = None):
        super().__init__(model_name=name, stream=True)
        self.result = result
        self.exc = exc
        self.calls = 0

    async def __call__(self, **kwargs):
        del kwargs
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.result


def _candidate(provider_id: str, model: FakeModel) -> FallbackModelCandidate:
    return FallbackModelCandidate(
        provider_id=provider_id,
        model_id=model.model_name,
        model=model,
    )


async def _collect(stream):
    return [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_fallbacks_after_model_not_found() -> None:
    primary = FakeModel("primary", exc=LLMStatusError(404))
    fallback = FakeModel("fallback", result=FakeResponse("ok"))
    wrapper = FallbackChatModel(
        [_candidate("a", primary), _candidate("b", fallback)],
    )

    result = await wrapper(messages=[])

    assert result.text == "ok"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_does_not_fallback_on_auth_error() -> None:
    primary = FakeModel("primary", exc=LLMStatusError(403))
    fallback = FakeModel("fallback", result=FakeResponse("ok"))
    wrapper = FallbackChatModel(
        [_candidate("a", primary), _candidate("b", fallback)],
    )

    with pytest.raises(LLMStatusError):
        await wrapper(messages=[])

    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_successful_fallback_is_not_sticky() -> None:
    primary = FakeModel("primary", exc=LLMStatusError(500))
    fallback = FakeModel("fallback", result=FakeResponse("ok"))
    wrapper = FallbackChatModel(
        [_candidate("a", primary), _candidate("b", fallback)],
    )

    await wrapper(messages=[])
    await wrapper(messages=[])

    assert [candidate.model_id for candidate in wrapper.candidates] == [
        "primary",
        "fallback",
    ]
    assert primary.calls == 2
    assert fallback.calls == 2


@pytest.mark.asyncio
async def test_fallback_runs_after_retry_exhaustion() -> None:
    primary = FakeModel("primary", exc=LLMStatusError(500))
    fallback = FakeModel("fallback", result=FakeResponse("ok"))
    retrying_primary = RetryChatModel(
        primary,
        retry_config=RetryConfig(
            enabled=True,
            max_retries=1,
            backoff_base=0.1,
            backoff_cap=0.5,
        ),
        rate_limit_config=RateLimitConfig(
            max_concurrent=1,
            max_qpm=0,
            pause_seconds=1.0,
            jitter_range=0.0,
            acquire_timeout=10.0,
        ),
    )
    wrapper = FallbackChatModel(
        [
            FallbackModelCandidate(
                provider_id="a",
                model_id=primary.model_name,
                model=retrying_primary,
            ),
            _candidate("b", fallback),
        ],
    )

    result = await wrapper(messages=[])

    assert result.text == "ok"
    assert primary.calls == 2
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_stream_fallback_before_first_chunk() -> None:
    async def failing_stream():
        if False:  # pragma: no cover - keeps function an async generator
            yield FakeResponse("never")
        raise LLMStatusError(500)

    async def ok_stream():
        yield FakeResponse("ok")

    primary = FakeModel("primary", result=failing_stream())
    fallback = FakeModel("fallback", result=ok_stream())
    wrapper = FallbackChatModel(
        [_candidate("a", primary), _candidate("b", fallback)],
    )

    result = await wrapper(messages=[])
    chunks = await _collect(result)

    assert [chunk.text for chunk in chunks] == ["ok"]
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_stream_does_not_fallback_after_first_chunk() -> None:
    async def failing_after_chunk():
        yield FakeResponse("partial")
        raise LLMStatusError(500)

    async def ok_stream():
        yield FakeResponse("ok")

    primary = FakeModel("primary", result=failing_after_chunk())
    fallback = FakeModel("fallback", result=ok_stream())
    wrapper = FallbackChatModel(
        [_candidate("a", primary), _candidate("b", fallback)],
    )

    result = await wrapper(messages=[])
    with pytest.raises(LLMStatusError):
        await _collect(result)

    assert primary.calls == 1
    assert fallback.calls == 0
