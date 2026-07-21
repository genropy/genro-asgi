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

"""Session capability: HTTP sessions as a mixin over the base server (D16).

``SessionMixin`` is composed BEFORE ``MiddlewareMixin`` and ``BaseServer``
(``class S(SessionMixin, MiddlewareMixin, BaseServer)``). Its cooperative
``__init__`` peels ``session_store=`` (``None`` → a fresh ``MemorySessionStore``)
and ``session_ttl=`` (the default store's TTL), then ARMS ``SessionMiddleware``
by injecting ``{"session": True}`` into the ``middleware`` config it forwards
to ``MiddlewareMixin`` along the cooperative chain — composing the two mixins
arms sessions with no user action, while an explicit
``middleware={"session": False}`` still wins (``setdefault`` never overrides an
explicit switch). It overrides the §4 contract method ``session(request)`` to
return the session attached to the request scope; a composition WITHOUT the
mixin keeps the base answer (``None``). ``promote_session(request, avatar)``
is the login seam: it attaches the avatar to the request's EXISTING session —
the id never changes at login, so the cookie already held by the client stays
valid and no new ``Set-Cookie`` is involved.
"""

from __future__ import annotations

from typing import Any

from .session import Session
from .store import MemorySessionStore, SessionStore

__all__ = ["SessionMixin"]


class SessionMixin:
    """Session capability mixin, composed BEFORE the middleware/server classes.

    Constructor kwargs peeled here: ``session_store`` — an explicit store
    (``None`` builds a ``MemorySessionStore``); ``session_ttl`` — the default
    store's TTL when no explicit store is given.
    """

    def __init__(self, **kwargs: Any) -> None:
        store: SessionStore | None = kwargs.pop("session_store", None)
        ttl: int | None = kwargs.pop("session_ttl", None)
        middleware: dict[str, Any] = dict(kwargs.get("middleware") or {})
        middleware.setdefault("session", True)
        kwargs["middleware"] = middleware
        super().__init__(**kwargs)
        if store is None:
            store = MemorySessionStore() if ttl is None else MemorySessionStore(default_ttl=ttl)
        self._session_store = store

    @property
    def session_store(self) -> SessionStore:
        """The store backing this server's sessions."""
        return self._session_store

    def session(self, request: Any) -> Any:
        """The session attached to the request scope, or ``None`` if none."""
        return request.get("session") if request is not None else None

    def promote_session(self, request: Any, avatar: Any) -> Session:
        """Attach ``avatar`` to the request's session — the login event.

        The session keeps its id, ``data`` and ``meta``: whatever an anonymous
        visitor accumulated (a cart, a history) survives the login, and the
        cookie the client already holds stays valid — no new session, no new
        ``Set-Cookie``. Session-fixation defense is the upstream cookie
        hardening (HttpOnly, SameSite, token never read from the URL), not id
        rotation. Returns the session.
        """
        session: Session = request.scope["session"]
        session.attach_avatar(avatar)
        return session


if __name__ == "__main__":
    from types import SimpleNamespace

    from ..application import BaseApplication
    from ..middleware import MiddlewareMixin
    from ..server import BaseServer
    from .avatar import Avatar

    class DemoServer(SessionMixin, MiddlewareMixin, BaseServer):
        pass

    server = DemoServer(primary=BaseApplication())
    assert isinstance(server.session_store, SessionStore)
    assert server.session({"session": "S"}) == "S"
    assert server.session({}) is None
    assert BaseServer(primary=BaseApplication()).session({}) is None

    anonymous = server.session_store.create()
    anonymous.data["cart"] = "kept"
    request = SimpleNamespace(scope={"session": anonymous})
    promoted = server.promote_session(request, Avatar("alice", ["admin"]))
    assert promoted is anonymous  # same session, same id — login attaches in place
    assert promoted.avatar is not None and promoted.avatar.identity == "alice"
    assert promoted.data["cart"] == "kept"
