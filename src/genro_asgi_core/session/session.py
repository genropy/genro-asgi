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

"""Server-managed session: id, meta, Bag data, and an optional Avatar.

A ``Session`` groups request-scoped state under a unique id with expiry
tracking. ``SessionMiddleware`` creates or reconnects sessions via the request
cookie and attaches them to ``scope["session"]``. Each session carries an
``Avatar | None`` — ``None`` is an anonymous session; capturing an identity is
an explicit ``avatar=`` at creation — and a ``Bag`` for arbitrary application
data. ``touch()`` refreshes ``last_access``; ``is_expired()`` measures the TTL
from it.

Write-back is explicit (D24): a session persists at request end ONLY when
``dirty`` is set. ``attach_avatar`` marks it dirty (a login must survive), and a
handler mutating ``data`` marks it dirty with ``mark_dirty()`` — there is no
write-through. ``touch()`` is NOT a mutation for this purpose: the ``last_access``
refresh happens on every ``get`` (including read-only requests), so making it
dirty would save on every request and defeat the zero-I/O read path. The
middleware clears the flag with ``clear_dirty()`` after a successful save.
"""

from __future__ import annotations

import time
from typing import Any

from genro_bag import Bag

from .avatar import Avatar

__all__ = ["Session"]


class Session:
    """Server-managed session with meta, Bag data, and an optional Avatar."""

    __slots__ = ("_id", "_meta", "_data", "_avatar", "_dirty")

    def __init__(self, session_id: str, avatar: Avatar | None, ttl: int) -> None:
        """Initialize the session with its token, an identity avatar, and a TTL."""
        now = time.time()
        self._id = session_id
        self._meta: dict[str, Any] = {"created_at": now, "last_access": now, "ttl": ttl}
        self._data = Bag()
        self._avatar = avatar
        self._dirty = False

    @property
    def id(self) -> str:
        """Unique session token."""
        return self._id

    @property
    def meta(self) -> dict[str, Any]:
        """Server-managed metadata: created_at, last_access, ttl."""
        return self._meta

    @property
    def data(self) -> Bag:
        """Application data as a Bag."""
        return self._data

    @property
    def avatar(self) -> Avatar | None:
        """Identity avatar; ``None`` = anonymous session."""
        return self._avatar

    @property
    def dirty(self) -> bool:
        """Whether the session has unsaved changes to persist at request end."""
        return self._dirty

    def attach_avatar(self, avatar: Avatar) -> None:
        """Attach the identity avatar — the login event (marks the session dirty).

        The session stays the same object: id, ``data`` and ``meta`` are
        untouched, so whatever an anonymous visitor accumulated survives
        the login. The change is marked dirty so the login persists.
        """
        self._avatar = avatar
        self.mark_dirty()

    def mark_dirty(self) -> None:
        """Flag the session as changed — a handler mutating ``data`` calls this."""
        self._dirty = True

    def clear_dirty(self) -> None:
        """Reset the dirty flag (the middleware calls this after a successful save)."""
        self._dirty = False

    def touch(self) -> None:
        """Refresh ``last_access`` to now (NOT a dirty-making change; see module doc)."""
        self.meta["last_access"] = time.time()

    def is_expired(self) -> bool:
        """Whether the session has exceeded its TTL (non-positive TTL = expired)."""
        ttl: int = self.meta["ttl"]
        if ttl <= 0:
            return True
        last_access: float = self.meta["last_access"]
        return bool((time.time() - last_access) > ttl)


if __name__ == "__main__":
    session = Session("tok", avatar=Avatar("alice"), ttl=3600)
    assert session.id == "tok"
    assert session.avatar is not None and session.avatar.identity == "alice"
    assert not session.is_expired()
    session.meta["last_access"] = time.time() - 10_000
    assert session.is_expired()
    anonymous = Session("t2", avatar=None, ttl=0)
    assert anonymous.avatar is None
    assert anonymous.is_expired()

    fresh = Session("t3", avatar=None, ttl=3600)
    assert fresh.dirty is False
    fresh.touch()  # a read refreshes last_access but does NOT mark dirty
    assert fresh.dirty is False
    fresh.data["cart"] = "x"
    fresh.mark_dirty()  # a data mutation is dirty only when the handler says so
    assert fresh.dirty is True
    fresh.clear_dirty()
    assert fresh.dirty is False
    fresh.attach_avatar(Avatar("bob"))  # login marks dirty automatically
    assert fresh.dirty is True
