# -*- coding: utf-8 -*-
from __future__ import annotations

from qwenpaw.providers.oauth import openai_codex_flow as flow_module
from qwenpaw.providers.oauth.openai_codex_flow import OpenAICodexOAuthFlow


class FakeResponse:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")


def test_codex_start_returns_device_code(monkeypatch) -> None:
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def post(self, url, **kwargs):
            assert url.endswith("/api/accounts/deviceauth/usercode")
            assert kwargs["json"]["client_id"] == flow_module.CODEX_OAUTH_CLIENT_ID
            return FakeResponse(
                200,
                {
                    "user_code": "ABCD-EFGH",
                    "device_auth_id": "device-1",
                    "interval": 4,
                    "expires_in": 600,
                },
            )

    monkeypatch.setattr(flow_module.httpx, "Client", FakeClient)

    result = OpenAICodexOAuthFlow().start()

    assert result.flow_type == "device_code"
    assert result.user_code == "ABCD-EFGH"
    assert result.verification_url == flow_module.CODEX_DEVICE_VERIFICATION_URL
    assert result.device_auth_id == "device-1"
    assert result.poll_interval == 4
    assert result.expires_in == 600


async def test_codex_poll_waits_until_authorized(monkeypatch) -> None:
    responses = [
        FakeResponse(403, {}),
        FakeResponse(
            200,
            {
                "authorization_code": "auth-code",
                "code_verifier": "verifier",
            },
        ),
    ]

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            assert url.endswith("/api/accounts/deviceauth/token")
            assert kwargs["json"] == {
                "device_auth_id": "device-1",
                "user_code": "ABCD-EFGH",
            }
            return responses.pop(0)

    async def no_sleep(seconds):
        assert seconds == 3

    flow = OpenAICodexOAuthFlow()
    monkeypatch.setattr(flow_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(flow, "_sleep", no_sleep)

    code, verifier = await flow.poll_device_authorization(
        device_auth_id="device-1",
        user_code="ABCD-EFGH",
        poll_interval=3,
        expires_in=30,
    )

    assert code == "auth-code"
    assert verifier == "verifier"
    assert responses == []


async def test_codex_exchange_returns_credentials(monkeypatch) -> None:
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            assert url == flow_module.CODEX_OAUTH_TOKEN_URL
            assert kwargs["data"]["grant_type"] == "authorization_code"
            assert kwargs["data"]["code"] == "auth-code"
            assert kwargs["data"]["code_verifier"] == "verifier"
            return FakeResponse(
                200,
                {
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_in": 3600,
                },
            )

    monkeypatch.setattr(flow_module.httpx, "AsyncClient", FakeAsyncClient)

    flow = OpenAICodexOAuthFlow()
    result = await flow.exchange(
        code="auth-code",
        code_verifier="verifier",
    )
    credential = flow.get_credential_dict(result)

    assert result.access_token == "access-token"
    assert result.refresh_token == "refresh-token"
    assert credential["api_key"] == "access-token"
    assert credential["oauth_refresh_token"] == "refresh-token"
    assert credential["auth_mode"] == "codex_oauth"
    assert credential["oauth_expires_at"] is not None
