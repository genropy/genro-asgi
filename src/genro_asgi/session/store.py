# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Session store — the storage Protocol and the in-memory default.

``SessionStore`` is a runtime-checkable ``Protocol`` (get/create/delete/
purge_expired/dump/restore). Its test suite is a shared CONTRACT suite
parametrized over implementations (§5.9), so the core 1b file/db backends plug
into the SAME tests. ``MemorySessionStore`` is the dict-backed default:
``secrets`` tokens, a ``default_ttl`` for new sessions, lazy expiry on ``get``,
opportunistic ``purge_expired`` at ``create`` time (no background task — those
arrive in core 1e), and a ``dump``/``restore`` that persists meta and the
avatar's identity/tags only — never the data Bag. ``create()`` is anonymous by
default (``avatar is None``); capturing an identity into a session is an
explicit ``create(avatar=...)``.
"""

from __future__ import annotations

import secrets
from typing import Any, Protocol, runtime_checkable

from .avatar import Avatar
from .session import Session

__all__ = ["SessionStore", "MemorySessionStore"]


@runtime_checkable
class SessionStore(Protocol):
    """Protocol for session storage backends."""

    def get(self, session_id: str) -> Session | None:
        """Retrieve a session by id, or ``None`` if unknown or expired."""
        ...

    def create(self, avatar: Avatar | None = None) -> Session:
        """Create a new session with a unique token (anonymous by default)."""
        ...

    def save(self, session: Session) -> None:
        """Persist a dirty session's state (the middleware calls this at request end)."""
        ...

    def delete(self, session_id: str) -> None:
        """Remove a session from the store."""
        ...

    def purge_expired(self) -> int:
        """Remove every expired session; return how many were purged."""
        ...

    def dump(self) -> dict[str, Any]:
        """Serialize the sessions for persistence."""
        ...

    def restore(self, data: dict[str, Any]) -> None:
        """Restore sessions from serialized data."""
        ...


class MemorySessionStore:
    """In-memory session store — the default implementation."""

    __slots__ = ("_sessions", "_default_ttl")

    def __init__(self, default_ttl: int = 3600) -> None:
        """Initialize an empty store with a default TTL for new sessions."""
        self._sessions: dict[str, Session] = {}
        self._default_ttl = default_ttl

    def get(self, session_id: str) -> Session | None:
        """Retrieve a session by id; drop and return ``None`` if it has expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            del self._sessions[session_id]
            return None
        session.touch()
        return session

    def create(self, avatar: Avatar | None = None) -> Session:
        """Create a session (default TTL), purging expired ones opportunistically first."""
        self.purge_expired()
        session_id = secrets.token_urlsafe(32)
        session = Session(session_id=session_id, avatar=avatar, ttl=self._default_ttl)
        self._sessions[session_id] = session
        return session

    def save(self, session: Session) -> None:
        """No-op: the in-memory store holds the live object, so it is already saved."""

    def delete(self, session_id: str) -> None:
        """Remove a session from the store (a no-op if absent)."""
        self._sessions.pop(session_id, None)

    def purge_expired(self) -> int:
        """Drop every expired session from the store; return the count purged."""
        expired = [sid for sid, session in self._sessions.items() if session.is_expired()]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

    def dump(self) -> dict[str, Any]:
        """Serialize meta and the avatar's identity/tags per session (never the data Bag)."""
        return {
            session_id: {
                "meta": dict(session.meta),
                "avatar": (
                    {"identity": session.avatar.identity, "tags": list(session.avatar.tags)}
                    if session.avatar is not None
                    else None
                ),
            }
            for session_id, session in self._sessions.items()
        }

    def restore(self, data: dict[str, Any]) -> None:
        """Restore non-expired sessions from ``dump()`` output (meta + rebuilt avatar)."""
        for session_id, session_data in data.items():
            meta = session_data["meta"]
            avatar_data = session_data.get("avatar")
            avatar = Avatar(avatar_data["identity"], avatar_data["tags"]) if avatar_data else None
            session = Session(session_id=session_id, avatar=avatar, ttl=meta["ttl"])
            session.meta["created_at"] = meta["created_at"]
            session.meta["last_access"] = meta["last_access"]
            if not session.is_expired():
                self._sessions[session_id] = session
