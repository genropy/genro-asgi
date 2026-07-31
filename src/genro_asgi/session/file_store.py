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

"""FileSessionStore — one JSON file per session over a storage mount.

Like ``MemorySessionStore`` this store keeps live ``Session`` objects in memory
(so ``get`` returns the same instance and ``touch`` is honored) but mirrors each
to ``<mount>:<prefix>/<id>.json``, so a session survives a process restart or a
fresh store built on the SAME mount — the D22 survival line. The file carries
meta (created_at/last_access/ttl) and the avatar's identity/tags ONLY, keyed on
disk by the session id (the filename); the data Bag is VOLATILE — never
persisted — the SAME contract as ``dump``/``restore`` (full-data persistence is
a future decision). All I/O is synchronous through the Phase 1 storage nodes
(core 1b ratified: async callers wrap in ``server.run_sync()``).

``purge_expired`` reaps the sessions this process tracks in memory (removing
their files too) and is invoked opportunistically at ``create`` time — no
background task, those arrive in core 1e. An expired file the store has not
loaded is reaped lazily the next time ``get`` touches it (no plain-text
fallback, no silent skip on a corrupt file: a non-JSON payload raises).
"""

from __future__ import annotations

import json
import secrets
from typing import Any

from genro_storage import StorageManager, StorageNode
from .avatar import Avatar
from .session import Session

__all__ = ["FileSessionStore"]


class FileSessionStore:
    """Session store persisting one JSON file per session on a storage mount."""

    __slots__ = ("_storage", "_mount", "_prefix", "_default_ttl", "_sessions")

    def __init__(
        self,
        storage: StorageManager,
        mount: str = "site",
        prefix: str = "sessions",
        default_ttl: int = 3600,
    ) -> None:
        """Bind the store to a storage ``mount``/``prefix`` with a default TTL."""
        self._storage = storage
        self._mount = mount
        self._prefix = prefix
        self._default_ttl = default_ttl
        self._sessions: dict[str, Session] = {}

    # ── persistence helpers ────────────────────────────────────────────

    def _node(self, session_id: str) -> StorageNode:
        """The storage node backing ``session_id`` on the configured mount."""
        return self._storage.node(f"{self._mount}:{self._prefix}/{session_id}.json")

    def _entry(self, session: Session) -> dict[str, Any]:
        """Serialize a session to the dump/on-disk record (meta + avatar, no data)."""
        avatar = session.avatar
        return {
            "meta": dict(session.meta),
            "avatar": (
                {"identity": avatar.identity, "tags": list(avatar.tags)}
                if avatar is not None
                else None
            ),
        }

    def _session_from_entry(self, session_id: str, entry: dict[str, Any]) -> Session:
        """Rebuild a session from a dump/on-disk record (data Bag starts empty)."""
        meta = entry["meta"]
        avatar_data = entry.get("avatar")
        avatar = Avatar(avatar_data["identity"], avatar_data["tags"]) if avatar_data else None
        session = Session(session_id=session_id, avatar=avatar, ttl=meta["ttl"])
        session.meta["created_at"] = meta["created_at"]
        session.meta["last_access"] = meta["last_access"]
        return session

    def _write(self, session: Session) -> None:
        """Persist a session's record to its file (plain: a session is not a credential)."""
        self._node(session.id).write_text(json.dumps(self._entry(session)))

    def _remove_file(self, session_id: str) -> None:
        """Delete a session's file if it exists (a no-op otherwise)."""
        node = self._node(session_id)
        if node.exists():
            node.delete()

    def _load(self, session_id: str) -> Session | None:
        """Load a session from disk, or ``None`` if no file; a non-JSON file raises."""
        node = self._node(session_id)
        if not node.exists():
            return None
        return self._session_from_entry(session_id, json.loads(node.read_text()))

    # ── SessionStore contract ──────────────────────────────────────────

    def get(self, session_id: str) -> Session | None:
        """Retrieve a session (cache first, then disk); expired ones are reaped."""
        session = self._sessions.get(session_id)
        if session is None:
            session = self._load(session_id)
            if session is None:
                return None
            self._sessions[session_id] = session
        if session.is_expired():
            del self._sessions[session_id]
            self._remove_file(session_id)
            return None
        session.touch()
        return session

    def create(self, avatar: Avatar | None = None) -> Session:
        """Create and persist a session, purging expired ones opportunistically first."""
        self.purge_expired()
        session_id = secrets.token_urlsafe(32)
        session = Session(session_id=session_id, avatar=avatar, ttl=self._default_ttl)
        self._sessions[session_id] = session
        self._write(session)
        return session

    def save(self, session: Session) -> None:
        """Persist a session's current state to disk (the write-back seam)."""
        self._write(session)

    def delete(self, session_id: str) -> None:
        """Remove a session from the cache and disk (a no-op if absent)."""
        self._sessions.pop(session_id, None)
        self._remove_file(session_id)

    def purge_expired(self) -> int:
        """Drop every expired tracked session (and its file); return the count purged."""
        expired = [sid for sid, session in self._sessions.items() if session.is_expired()]
        for sid in expired:
            del self._sessions[sid]
            self._remove_file(sid)
        return len(expired)

    def dump(self) -> dict[str, Any]:
        """Serialize the tracked sessions (meta + avatar per session; never the data Bag)."""
        return {sid: self._entry(session) for sid, session in self._sessions.items()}

    def restore(self, data: dict[str, Any]) -> None:
        """Restore non-expired sessions from ``dump()`` output (cached and persisted)."""
        for session_id, entry in data.items():
            session = self._session_from_entry(session_id, entry)
            if not session.is_expired():
                self._sessions[session_id] = session
                self._write(session)
