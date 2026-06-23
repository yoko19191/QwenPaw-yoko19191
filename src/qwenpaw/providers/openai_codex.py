# -*- coding: utf-8 -*-
"""Utilities for the ChatGPT Codex OAuth backend."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Iterable

import httpx

from qwenpaw.providers.oauth.openai_codex_flow import OpenAICodexOAuthFlow
from qwenpaw.providers.provider import ModelInfo

CODEX_BASE_URL = "https://chatgpt.com/backend-api/codex"
CODEX_MODELS_URL = f"{CODEX_BASE_URL}/models"
CODEX_RESPONSES_URL = f"{CODEX_BASE_URL}/responses"
CODEX_CLIENT_VERSION = "1.0.0"
CODEX_REFRESH_SKEW_SECONDS = 120


def decode_jwt_claims(access_token: str | None) -> dict[str, Any]:
    """Best-effort JWT payload decoding without validation."""
    if not access_token:
        return {}
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return claims if isinstance(claims, dict) else {}
    except Exception:
        return {}


def codex_headers(access_token: str) -> dict[str, str]:
    """Headers expected by the ChatGPT Codex backend."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "codex_cli_rs/0.0.0 (QwenPaw)",
        "originator": "codex_cli_rs",
    }
    claims = decode_jwt_claims(access_token)
    auth_claims = claims.get("https://api.openai.com/auth")
    if isinstance(auth_claims, dict):
        account_id = auth_claims.get("chatgpt_account_id")
        if isinstance(account_id, str) and account_id.strip():
            headers["ChatGPT-Account-ID"] = account_id.strip()
    return headers


def token_expires_soon(
    expires_at: float | None,
    *,
    skew: int = CODEX_REFRESH_SKEW_SECONDS,
) -> bool:
    """Return True when the access token should be refreshed."""
    if expires_at is None:
        return False
    return expires_at <= time.time() + skew


async def refresh_codex_tokens(refresh_token: str) -> dict[str, Any]:
    """Refresh Codex OAuth tokens and return provider config fields."""
    result = await OpenAICodexOAuthFlow().refresh(refresh_token)
    return OpenAICodexOAuthFlow().get_credential_dict(result)


def normalize_codex_model_entries(entries: Iterable[Any]) -> list[ModelInfo]:
    """Parse ChatGPT Codex /models entries into ModelInfo rows."""
    sortable: list[tuple[int, str, ModelInfo]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        slug = str(item.get("slug") or "").strip()
        if not slug:
            continue
        visibility = item.get("visibility")
        if isinstance(visibility, str) and visibility.strip().lower() in {
            "hide",
            "hidden",
        }:
            continue
        priority = item.get("priority")
        rank = int(priority) if isinstance(priority, (int, float)) else 10_000
        payload: dict[str, Any] = {
            "id": slug,
            "name": slug,
            "probe_source": "codex",
        }
        context_window = item.get("context_window")
        if isinstance(context_window, int) and context_window >= 1000:
            payload["max_input_length"] = context_window
        max_output_tokens = item.get("max_output_tokens")
        if isinstance(max_output_tokens, int) and max_output_tokens > 0:
            payload["max_tokens"] = max_output_tokens
        sortable.append((rank, slug, ModelInfo(**payload)))

    sortable.sort(key=lambda row: (row[0], row[1]))
    deduped: list[ModelInfo] = []
    seen: set[str] = set()
    for _, _, model in sortable:
        if model.id in seen:
            continue
        seen.add(model.id)
        deduped.append(model)
    return deduped


async def fetch_codex_models(
    access_token: str,
    *,
    timeout: float = 5,
) -> list[ModelInfo]:
    """Fetch the live ChatGPT Codex model list."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            CODEX_MODELS_URL,
            params={"client_version": CODEX_CLIENT_VERSION},
            headers=codex_headers(access_token),
        )
        response.raise_for_status()
        data = response.json()
    entries = data.get("models", []) if isinstance(data, dict) else []
    return normalize_codex_model_entries(entries)
