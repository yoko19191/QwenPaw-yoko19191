# -*- coding: utf-8 -*-
"""In-memory OAuth session store with TTL expiration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional


_TTL_SECONDS = 600  # 10 minutes


@dataclass
class OAuthSession:
    """Transient state for a single OAuth round-trip."""

    provider_id: str
    state: str
    code_verifier: str
    callback_url: str
    created_at: float = field(default_factory=time.monotonic)
    expires_at: Optional[float] = None
    status: str = "pending"  # pending | completed | failed | expired
    error: Optional[str] = None
    data: dict = field(default_factory=dict)
    # Stored after successful exchange
    credential: Optional[dict] = None

    def is_expired(self) -> bool:
        """Return True if session exceeded TTL."""
        if self.expires_at is not None:
            return time.monotonic() > self.expires_at
        return (time.monotonic() - self.created_at) > _TTL_SECONDS

    def can_purge(self) -> bool:
        """Return True when an old terminal session can be discarded."""
        return (time.monotonic() - self.created_at) > (_TTL_SECONDS * 2)


class OAuthSessionStore:
    """Process-local in-memory store for OAuth sessions."""

    def __init__(self) -> None:
        """Initialise session store."""
        self._sessions: Dict[str, OAuthSession] = {}

    def _purge_expired(self) -> None:
        """Mark expired sessions and remove old terminal sessions."""
        expired = []
        for key, session in self._sessions.items():
            if session.is_expired() and session.status == "pending":
                session.status = "expired"
                session.error = "Session expired"
            if session.status != "pending" and session.can_purge():
                expired.append(key)
        for k in expired:
            del self._sessions[k]

    def create(
        self,
        provider_id: str,
        state: str,
        code_verifier: str,
        callback_url: str,
        data: Optional[dict] = None,
        expires_in: Optional[int] = None,
    ) -> OAuthSession:
        """Create and store a new OAuth session."""
        self._purge_expired()
        expires_at = (
            time.monotonic() + expires_in
            if isinstance(expires_in, int) and expires_in > 0
            else None
        )
        session = OAuthSession(
            provider_id=provider_id,
            state=state,
            code_verifier=code_verifier,
            callback_url=callback_url,
            expires_at=expires_at,
            data=data or {},
        )
        self._sessions[state] = session
        return session

    def get(self, state: str) -> Optional[OAuthSession]:
        """Get a session by state token."""
        self._purge_expired()
        session = self._sessions.get(state)
        if session and session.is_expired():
            del self._sessions[state]
            return None
        return session

    def get_by_provider(
        self,
        provider_id: str,
    ) -> Optional[OAuthSession]:
        """Get the most recent pending session for a provider.

        Fallback for OAuth providers (e.g. OpenRouter) that do
        not relay the state parameter back in the callback URL.
        """
        self._purge_expired()
        candidates = [
            s
            for s in self._sessions.values()
            if s.provider_id == provider_id
            and s.status == "pending"
            and not s.is_expired()
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.created_at)

    def complete(
        self,
        state: str,
        credential: dict,
    ) -> None:
        """Mark session as completed with credentials."""
        session = self._sessions.get(state)
        if session:
            session.status = "completed"
            session.credential = credential

    def fail(self, state: str, error: str) -> None:
        """Mark session as failed."""
        session = self._sessions.get(state)
        if session:
            session.status = "failed"
            session.error = error

    def expire(self, state: str, error: str = "Session expired") -> None:
        """Mark session as expired."""
        session = self._sessions.get(state)
        if session:
            session.status = "expired"
            session.error = error

    def remove(self, state: str) -> None:
        """Remove a session."""
        self._sessions.pop(state, None)
