# -*- coding: utf-8 -*-
"""OpenAI Codex OAuth flow using ChatGPT device authentication."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

import httpx

from .base import (
    OAuthFlow,
    OAuthStartResult,
    OAuthTokenResult,
    generate_state,
)

CODEX_OAUTH_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_OAUTH_ISSUER = "https://auth.openai.com"
CODEX_OAUTH_TOKEN_URL = f"{CODEX_OAUTH_ISSUER}/oauth/token"
CODEX_DEVICE_VERIFICATION_URL = f"{CODEX_OAUTH_ISSUER}/codex/device"
CODEX_DEVICE_CALLBACK_URL = f"{CODEX_OAUTH_ISSUER}/deviceauth/callback"


def _jwt_exp(access_token: str | None) -> float | None:
    """Best-effort decode of the JWT exp claim without validation."""
    if not access_token:
        return None
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        exp = claims.get("exp")
        if isinstance(exp, (int, float)) and exp > 0:
            return float(exp)
    except Exception:
        return None
    return None


def _expires_at(payload: dict[str, Any]) -> float | None:
    """Resolve token expiry from expires_in or JWT exp."""
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return time.time() + float(expires_in)
    return _jwt_exp(payload.get("access_token"))


class OpenAICodexOAuthFlow(OAuthFlow):
    """OpenAI Codex: device code -> authorization code -> OAuth tokens."""

    provider_id = "openai"

    def start(self, callback_url: str = "") -> OAuthStartResult:
        """Create a device-code session and return user-facing details."""
        del callback_url
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{CODEX_OAUTH_ISSUER}/api/accounts/deviceauth/usercode",
                json={"client_id": CODEX_OAUTH_CLIENT_ID},
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        user_code = str(data.get("user_code") or "").strip()
        device_auth_id = str(data.get("device_auth_id") or "").strip()
        if not user_code or not device_auth_id:
            raise RuntimeError(
                "Codex device-code response missing user_code or device_auth_id",
            )

        interval = data.get("interval")
        poll_interval = int(interval) if isinstance(interval, (int, float)) else 5
        poll_interval = max(3, poll_interval)
        expires_in = data.get("expires_in")
        if not isinstance(expires_in, (int, float)) or expires_in <= 0:
            expires_in = 15 * 60

        return OAuthStartResult(
            authorize_url=CODEX_DEVICE_VERIFICATION_URL,
            state=generate_state(),
            flow_type="device_code",
            user_code=user_code,
            verification_url=CODEX_DEVICE_VERIFICATION_URL,
            expires_in=int(expires_in),
            poll_interval=poll_interval,
            device_auth_id=device_auth_id,
        )

    async def poll_device_authorization(
        self,
        *,
        device_auth_id: str,
        user_code: str,
        poll_interval: int,
        expires_in: int,
    ) -> tuple[str, str]:
        """Poll OpenAI until the user approves the device code."""
        deadline = time.monotonic() + max(1, expires_in)
        async with httpx.AsyncClient(timeout=15) as client:
            while time.monotonic() < deadline:
                await self._sleep(poll_interval)
                response = await client.post(
                    f"{CODEX_OAUTH_ISSUER}/api/accounts/deviceauth/token",
                    json={
                        "device_auth_id": device_auth_id,
                        "user_code": user_code,
                    },
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code == 200:
                    data = response.json()
                    authorization_code = str(
                        data.get("authorization_code") or "",
                    ).strip()
                    code_verifier = str(data.get("code_verifier") or "").strip()
                    if not authorization_code or not code_verifier:
                        raise RuntimeError(
                            "Codex device-auth response missing "
                            "authorization_code or code_verifier",
                        )
                    return authorization_code, code_verifier
                if response.status_code in {403, 404}:
                    continue
                response.raise_for_status()
        raise TimeoutError("Codex device code expired before approval")

    async def _sleep(self, seconds: int) -> None:
        import asyncio

        await asyncio.sleep(max(1, seconds))

    async def exchange(
        self,
        code: str,
        state: str = "",
        code_verifier: str = "",
        callback_url: str = "",
    ) -> OAuthTokenResult:
        """Exchange authorization code for Codex OAuth tokens."""
        del state, callback_url
        if not code or not code_verifier:
            raise RuntimeError("Missing authorization code or code verifier")

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                CODEX_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": CODEX_DEVICE_CALLBACK_URL,
                    "client_id": CODEX_OAUTH_CLIENT_ID,
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Codex token exchange returned no access token")
        refresh_token = str(data.get("refresh_token") or "").strip() or None
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=_expires_at(data),
        )

    async def refresh(self, refresh_token: str) -> OAuthTokenResult:
        """Refresh Codex OAuth tokens."""
        if not refresh_token:
            raise RuntimeError("Missing Codex refresh token")
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                CODEX_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CODEX_OAUTH_CLIENT_ID,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

        access_token = str(data.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Codex token refresh returned no access token")
        next_refresh = str(data.get("refresh_token") or "").strip()
        return OAuthTokenResult(
            access_token=access_token,
            refresh_token=next_refresh or refresh_token,
            expires_at=_expires_at(data),
        )

    def get_credential_dict(self, result: OAuthTokenResult) -> dict:
        """Convert Codex OAuth tokens into OpenAI provider config."""
        if not result.access_token:
            return {}
        return {
            "api_key": result.access_token,
            "auth_mode": "codex_oauth",
            "oauth_refresh_token": result.refresh_token or "",
            "oauth_expires_at": result.expires_at,
        }
