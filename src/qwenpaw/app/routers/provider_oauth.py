# -*- coding: utf-8 -*-
"""OAuth endpoints for provider one-click authentication."""

from __future__ import annotations

import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from ...providers.oauth import (
    OAuthSessionStore,
    OpenRouterOAuthFlow,
    OpenAICodexOAuthFlow,
)
from ...providers.oauth.base import OAuthFlow, OAuthTokenResult
from ...providers.provider_manager import ProviderManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/providers",
    tags=["provider-oauth"],
)

# Singleton session store (lives in process memory)
_session_store = OAuthSessionStore()

# Registry of OAuth flows by provider_id
_OAUTH_FLOWS: dict[str, OAuthFlow] = {
    "openrouter": OpenRouterOAuthFlow(),
    "openai": OpenAICodexOAuthFlow(),
}


async def _get_provider_manager(
    request: Request,
) -> ProviderManager:
    """Get provider manager from app state."""
    return request.app.state.provider_manager


def _get_flow(provider_id: str) -> OAuthFlow:
    """Get OAuth flow for a provider or raise 404."""
    flow = _OAUTH_FLOWS.get(provider_id)
    if not flow:
        raise HTTPException(
            status_code=404,
            detail=(f"Provider '{provider_id}' does not support OAuth"),
        )
    return flow


def _build_callback_url(
    request: Request,
    provider_id: str,
) -> str:
    """Build the OAuth callback URL for this request."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/providers/{provider_id}/oauth/callback"


# ----- Request/Response models -----


class OAuthStartResponse(BaseModel):
    """Response for OAuth start endpoint."""

    authorize_url: str = Field(
        ...,
        description="URL to open in browser popup",
    )
    state: str = Field(
        ...,
        description="State token for status polling",
    )
    flow_type: str = Field(
        default="browser_redirect",
        description="browser_redirect or device_code",
    )
    user_code: Optional[str] = Field(
        default=None,
        description="Device-code user code",
    )
    verification_url: Optional[str] = Field(
        default=None,
        description="Device-code verification URL",
    )
    expires_in: Optional[int] = Field(
        default=None,
        description="Device-code expiration in seconds",
    )
    poll_interval: Optional[int] = Field(
        default=None,
        description="Suggested polling interval in seconds",
    )


class OAuthStatusResponse(BaseModel):
    """Response for OAuth status endpoint."""

    status: str = Field(
        ...,
        description="pending, completed, failed, or expired",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if failed",
    )


# ----- Endpoints -----


@router.post(
    "/{provider_id}/oauth/start",
    response_model=OAuthStartResponse,
    summary="Start OAuth flow for a provider",
)
async def start_oauth(
    provider_id: str,
    request: Request,
    manager: ProviderManager = Depends(_get_provider_manager),
) -> OAuthStartResponse:
    """Start OAuth flow. Returns authorize_url for browser popup."""
    flow = _get_flow(provider_id)
    callback_url = _build_callback_url(request, provider_id)
    try:
        result = flow.start(callback_url)
    except Exception as exc:
        logger.exception("OAuth start failed for %s", provider_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _session_store.create(
        provider_id=provider_id,
        state=result.state,
        code_verifier="",
        callback_url=callback_url,
        data={
            "device_auth_id": result.device_auth_id,
            "user_code": result.user_code,
            "poll_interval": result.poll_interval,
        },
        expires_in=result.expires_in,
    )

    if result.flow_type == "device_code":
        asyncio.create_task(
            _complete_device_code_flow(
                provider_id=provider_id,
                state=result.state,
                flow=flow,
                manager=manager,
                expires_in=result.expires_in or 15 * 60,
                poll_interval=result.poll_interval or 5,
            ),
            name=f"provider-oauth-{provider_id}-{result.state[:8]}",
        )

    return OAuthStartResponse(
        authorize_url=result.authorize_url,
        state=result.state,
        flow_type=result.flow_type,
        user_code=result.user_code,
        verification_url=result.verification_url,
        expires_in=result.expires_in,
        poll_interval=result.poll_interval,
    )


async def _save_oauth_credentials(
    *,
    provider_id: str,
    flow: OAuthFlow,
    token_result: OAuthTokenResult,
    manager: ProviderManager,
    session_state: str,
) -> bool:
    """Persist OAuth credentials and discover models."""
    credential = flow.get_credential_dict(token_result)
    if not credential:
        _session_store.fail(session_state, "No credentials returned")
        return False

    if not manager.update_provider(provider_id, credential):
        _session_store.fail(session_state, "Provider not found")
        return False

    try:
        await manager.fetch_provider_models(provider_id)
    except Exception:
        logger.warning(
            "Model discovery failed for %s after OAuth, will retry on next list",
            provider_id,
        )
    _session_store.complete(session_state, credential)
    return True


async def _complete_device_code_flow(
    *,
    provider_id: str,
    state: str,
    flow: OAuthFlow,
    manager: ProviderManager,
    expires_in: int,
    poll_interval: int,
) -> None:
    """Background worker for provider device-code OAuth flows."""
    session = _session_store.get(state)
    if not session:
        return
    device_auth_id = str(session.data.get("device_auth_id") or "")
    user_code = str(session.data.get("user_code") or "")
    if not device_auth_id or not user_code:
        _session_store.fail(state, "Missing device-code session data")
        return

    try:
        poller = getattr(flow, "poll_device_authorization", None)
        if not poller:
            raise RuntimeError("OAuth flow does not support device polling")
        code, code_verifier = await poller(
            device_auth_id=device_auth_id,
            user_code=user_code,
            poll_interval=poll_interval,
            expires_in=expires_in,
        )
        token_result = await flow.exchange(
            code=code,
            state=state,
            code_verifier=code_verifier,
            callback_url=session.callback_url,
        )
        await _save_oauth_credentials(
            provider_id=provider_id,
            flow=flow,
            token_result=token_result,
            manager=manager,
            session_state=state,
        )
    except TimeoutError as exc:
        _session_store.expire(state, str(exc))
    except Exception as exc:
        logger.exception("Device-code OAuth failed for %s", provider_id)
        _session_store.fail(state, str(exc))


@router.get(
    "/{provider_id}/oauth/callback",
    response_class=HTMLResponse,
    summary="OAuth callback (redirect target)",
)
async def oauth_callback(
    provider_id: str,
    code: str,
    state: str = "",
    manager: ProviderManager = Depends(_get_provider_manager),
) -> HTMLResponse:
    """OAuth callback. Exchanges code, saves key, closes popup."""
    session = _session_store.get(state) if state else None
    if not session:
        # Fallback: providers like OpenRouter don't relay state
        session = _session_store.get_by_provider(provider_id)
    if not session:
        return HTMLResponse(
            content=_error_html("Session expired or invalid."),
            status_code=400,
        )

    if session.provider_id != provider_id:
        return HTMLResponse(
            content=_error_html("Provider mismatch."),
            status_code=400,
        )

    flow = _get_flow(provider_id)
    session_state = session.state

    try:
        token_result = await flow.exchange(
            code=code,
            state=session_state,
            code_verifier=session.code_verifier,
            callback_url=session.callback_url,
        )
    except Exception as exc:
        logger.exception(
            f"OAuth exchange failed for {provider_id}",
        )
        _session_store.fail(session_state, str(exc))
        return HTMLResponse(
            content=_error_html("Authorization failed. Please retry."),
            status_code=500,
        )

    if not await _save_oauth_credentials(
        provider_id=provider_id,
        flow=flow,
        token_result=token_result,
        manager=manager,
        session_state=session_state,
    ):
        return HTMLResponse(
            content=_error_html("No credentials received."),
            status_code=500,
        )

    return HTMLResponse(content=_success_html(provider_id))


@router.get(
    "/{provider_id}/oauth/status",
    response_model=OAuthStatusResponse,
    summary="Poll OAuth flow status",
)
async def oauth_status(
    provider_id: str,
    state: str,
) -> OAuthStatusResponse:
    """Poll current OAuth flow status."""
    session = _session_store.get(state)
    if not session:
        return OAuthStatusResponse(
            status="failed",
            error="Session expired",
        )
    if session.provider_id != provider_id:
        return OAuthStatusResponse(
            status="failed",
            error="Provider mismatch",
        )
    return OAuthStatusResponse(
        status=session.status,
        error=session.error,
    )


# ----- HTML templates for popup -----


def _success_html(provider_id: str) -> str:
    """HTML that notifies opener and closes the popup."""
    return f"""<!DOCTYPE html>
<html><head><title>Authorization Successful</title></head>
<body style="font-family:system-ui;text-align:center;padding:60px">
<h2>Connected!</h2>
<p>You can close this window.</p>
<script>
if (window.opener) {{
  window.opener.postMessage(
    {{type: "oauth_complete", provider: "{provider_id}"}},
    window.location.origin
  );
}}
setTimeout(function() {{ window.close(); }}, 1500);
</script>
</body></html>"""


def _error_html(message: str) -> str:
    """HTML for error display in popup."""
    import html

    safe_msg = html.escape(message)
    return f"""<!DOCTYPE html>
<html><head><title>Authorization Failed</title></head>
<body style="font-family:system-ui;text-align:center;padding:60px">
<h2>Authorization Failed</h2>
<p>{safe_msg}</p>
<p><a href="javascript:window.close()">Close this window</a></p>
</body></html>"""
