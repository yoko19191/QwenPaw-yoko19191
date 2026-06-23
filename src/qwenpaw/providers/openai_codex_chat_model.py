# -*- coding: utf-8 -*-
"""AgentScope chat model adapter for ChatGPT Codex Responses."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncGenerator, Type

import httpx
from agentscope.message import TextBlock, ToolUseBlock
from agentscope.model import ChatModelBase
from agentscope.model._model_response import ChatResponse
from agentscope.model._model_usage import ChatUsage
from pydantic import BaseModel

from .openai_chat_model_compat import _sanitize_tool_schemas
from .openai_codex import (
    CODEX_RESPONSES_URL,
    codex_headers,
    refresh_codex_tokens,
    token_expires_soon,
)


def _json_dict(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif item.get("type") == "input_text" and isinstance(
                    item.get("text"),
                    str,
                ):
                    parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part)
    return str(content or "")


def _message_to_response_input(message: dict[str, Any]) -> dict[str, Any] | None:
    role = str(message.get("role") or "user")
    content = _content_to_text(message.get("content"))

    if role == "system":
        return None
    if role == "tool":
        call_id = str(
            message.get("tool_call_id")
            or message.get("call_id")
            or message.get("id")
            or "",
        )
        if not call_id:
            return None
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": content,
        }

    response_role = "assistant" if role == "assistant" else "user"
    text_type = "output_text" if response_role == "assistant" else "input_text"
    return {
        "role": response_role,
        "content": [{"type": text_type, "text": content}],
    }


def _messages_to_responses(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    instructions: list[str] = []
    response_input: list[dict[str, Any]] = []
    for message in messages:
        if str(message.get("role") or "") == "system":
            text = _content_to_text(message.get("content")).strip()
            if text:
                instructions.append(text)
            continue
        item = _message_to_response_input(message)
        if item is not None:
            response_input.append(item)
    return "\n\n".join(instructions), response_input


def _responses_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not tools:
        return []
    result: list[dict[str, Any]] = []
    for tool in _sanitize_tool_schemas(tools):
        if not isinstance(tool, dict):
            continue
        func = tool.get("function")
        if not isinstance(func, dict):
            continue
        name = str(func.get("name") or "").strip()
        if not name:
            continue
        payload = {
            "type": "function",
            "name": name,
            "description": str(func.get("description") or ""),
            "parameters": func.get("parameters") or {"type": "object"},
        }
        result.append(payload)
    return result


class CodexResponsesChatModelCompat(ChatModelBase):
    """ChatGPT Codex Responses adapter with token refresh support."""

    def __init__(
        self,
        *,
        model_name: str,
        provider_id: str,
        api_key: str,
        oauth_refresh_token: str = "",
        oauth_expires_at: float | None = None,
        stream: bool = True,
        generate_kwargs: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(model_name=model_name, stream=stream)
        self.provider_id = provider_id
        self.api_key = api_key
        self.oauth_refresh_token = oauth_refresh_token
        self.oauth_expires_at = oauth_expires_at
        self.generate_kwargs = generate_kwargs or {}

    async def _refresh_and_persist(self) -> bool:
        if not self.oauth_refresh_token:
            return False
        updates = await refresh_codex_tokens(self.oauth_refresh_token)
        access_token = str(updates.get("api_key") or "").strip()
        if not access_token:
            return False
        self.api_key = access_token
        self.oauth_refresh_token = str(
            updates.get("oauth_refresh_token") or self.oauth_refresh_token,
        )
        expires_at = updates.get("oauth_expires_at")
        self.oauth_expires_at = (
            float(expires_at) if isinstance(expires_at, (int, float)) else None
        )
        try:
            from .provider_manager import ProviderManager

            ProviderManager.get_instance().update_provider(
                self.provider_id,
                updates,
            )
        except Exception:
            pass
        return True

    async def _ensure_fresh_token(self) -> None:
        if token_expires_soon(self.oauth_expires_at):
            await self._refresh_and_persist()

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        kwargs: dict[str, Any],
    ) -> dict[str, Any]:
        instructions, response_input = _messages_to_responses(messages)
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": response_input,
            "store": False,
            "stream": True,
        }
        if instructions:
            payload["instructions"] = instructions

        response_tools = _responses_tools(tools)
        if response_tools:
            payload["tools"] = response_tools
            payload["tool_choice"] = "auto" if tool_choice != "none" else "none"
            payload["parallel_tool_calls"] = True

        extra_body = self.generate_kwargs.get("extra_body")
        if isinstance(extra_body, dict):
            for key in ("reasoning", "include", "prompt_cache_key"):
                if key in extra_body:
                    payload[key] = extra_body[key]
        for key in ("reasoning", "include", "prompt_cache_key"):
            if key in kwargs:
                payload[key] = kwargs[key]
        return payload

    async def __call__(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        structured_model: Type[BaseModel] | None = None,
        **kwargs: Any,
    ) -> ChatResponse | AsyncGenerator[ChatResponse, None]:
        if structured_model is not None:
            raise ValueError("Codex OAuth mode does not support structured_model")
        if not isinstance(messages, list):
            raise ValueError("Codex Responses `messages` must be a list")

        if self.stream:
            return self._stream_with_retry(messages, tools, tool_choice, kwargs)

        last: ChatResponse | None = None
        async for chunk in self._stream_with_retry(
            messages,
            tools,
            tool_choice,
            kwargs,
        ):
            last = chunk
        return last or ChatResponse(content=[])

    async def _stream_with_retry(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        kwargs: dict[str, Any],
    ) -> AsyncGenerator[ChatResponse, None]:
        try:
            await self._ensure_fresh_token()
            async for chunk in self._stream_once(
                messages,
                tools,
                tool_choice,
                kwargs,
            ):
                yield chunk
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 401:
                raise
            if not await self._refresh_and_persist():
                raise
            async for chunk in self._stream_once(
                messages,
                tools,
                tool_choice,
                kwargs,
            ):
                yield chunk

    async def _stream_once(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        kwargs: dict[str, Any],
    ) -> AsyncGenerator[ChatResponse, None]:
        payload = self._build_payload(messages, tools, tool_choice, kwargs)
        timeout = kwargs.get("timeout")
        timeout_value = float(timeout) if isinstance(timeout, (int, float)) else 120.0
        start = datetime.now()
        state = _CodexStreamState(start)

        async with httpx.AsyncClient(timeout=timeout_value) as client:
            async with client.stream(
                "POST",
                CODEX_RESPONSES_URL,
                headers=codex_headers(self.api_key),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for event_name, data in _iter_sse_events(response):
                    chunk = state.apply(event_name, data)
                    if chunk is not None:
                        yield chunk


class _CodexStreamState:
    def __init__(self, start: datetime) -> None:
        self.start = start
        self.response_id: str | None = None
        self.text = ""
        self.tool_calls: dict[str, dict[str, str]] = {}
        self.usage: ChatUsage | None = None

    def apply(self, event_name: str, data: dict[str, Any]) -> ChatResponse | None:
        changed = False
        if event_name == "response.created":
            response = data.get("response")
            if isinstance(response, dict):
                self.response_id = str(response.get("id") or "") or None
        elif event_name == "response.output_text.delta":
            delta = data.get("delta")
            if isinstance(delta, str) and delta:
                self.text += delta
                changed = True
        elif event_name == "response.output_item.added":
            item = data.get("item")
            changed = self._merge_tool_item(item) or changed
        elif event_name in {
            "response.function_call_arguments.delta",
            "response.function_call_arguments.done",
        }:
            item_id = str(data.get("item_id") or data.get("output_index") or "")
            if item_id:
                entry = self.tool_calls.setdefault(
                    item_id,
                    {"id": item_id, "name": "", "arguments": ""},
                )
                if event_name.endswith(".delta"):
                    delta = data.get("delta")
                    if isinstance(delta, str):
                        entry["arguments"] += delta
                        changed = True
                else:
                    arguments = data.get("arguments")
                    if isinstance(arguments, str):
                        entry["arguments"] = arguments
                        changed = True
        elif event_name == "response.output_item.done":
            item = data.get("item")
            changed = self._merge_tool_item(item) or changed
        elif event_name == "response.completed":
            response = data.get("response")
            if isinstance(response, dict):
                self.response_id = str(response.get("id") or "") or self.response_id
                self._merge_usage(response.get("usage"))
                for item in response.get("output") or []:
                    changed = self._merge_tool_item(item) or changed

        if changed:
            return self._response()
        return None

    def _merge_tool_item(self, item: Any) -> bool:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            return False
        item_id = str(item.get("id") or item.get("call_id") or "")
        if not item_id:
            return False
        entry = self.tool_calls.setdefault(
            item_id,
            {"id": item_id, "name": "", "arguments": ""},
        )
        changed = False
        call_id = str(item.get("call_id") or item_id)
        name = str(item.get("name") or "")
        arguments = item.get("arguments")
        if call_id and entry["id"] != call_id:
            entry["id"] = call_id
            changed = True
        if name and entry["name"] != name:
            entry["name"] = name
            changed = True
        if isinstance(arguments, str) and arguments != entry["arguments"]:
            entry["arguments"] = arguments
            changed = True
        return changed

    def _merge_usage(self, usage: Any) -> None:
        if not isinstance(usage, dict):
            return
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        self.usage = ChatUsage(
            input_tokens=int(input_tokens) if isinstance(input_tokens, int) else 0,
            output_tokens=int(output_tokens) if isinstance(output_tokens, int) else 0,
            time=(datetime.now() - self.start).total_seconds(),
            metadata=usage,
        )

    def _response(self) -> ChatResponse:
        content: list[Any] = []
        if self.text:
            content.append(TextBlock(type="text", text=self.text))
        for tool_call in self.tool_calls.values():
            name = tool_call["name"]
            if not name:
                continue
            raw_input = tool_call["arguments"]
            content.append(
                ToolUseBlock(
                    type="tool_use",
                    id=tool_call["id"],
                    name=name,
                    input=_json_dict(raw_input),
                    raw_input=raw_input,
                ),
            )
        kwargs: dict[str, Any] = {"content": content, "usage": self.usage}
        if self.response_id:
            kwargs["id"] = self.response_id
        return ChatResponse(**kwargs)


async def _iter_sse_events(
    response: httpx.Response,
) -> AsyncGenerator[tuple[str, dict[str, Any]], None]:
    event_name = "message"
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if not line:
            payload = "\n".join(data_lines).strip()
            if payload and payload != "[DONE]":
                try:
                    data = json.loads(payload)
                    if isinstance(data, dict):
                        yield event_name, data
                except json.JSONDecodeError:
                    pass
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
