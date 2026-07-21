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
is the login seam: it swaps the anonymous scope session for a fresh
identity-bearing one from the store; the ``Set-Cookie`` for the change is
emitted by ``SessionMiddleware`` at response time (option A), never here.
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
        """Replace the request's anonymous session with an identity-bearing one.

        Creates a fresh session carrying ``avatar`` through the store and sets
        it on ``request.scope["session"]`` (replacing the anonymous session the
        middleware put there). The promotion is also recorded in the shared
        ``session_state`` holder the middleware installed: the D3 demux hands a
        mounted app a shallow COPY of the scope, and the holder is the channel
        that survives the copy so ``SessionMiddleware`` sees the change and
        emits the ``Set-Cookie`` at response time (option A) — never here.
        Returns the session.
        """
        session = self.session_store.create(avatar=avatar)
        request.scope["session"] = session
        holder = request.scope.get("session_state")
        if holder is not None:
            holder["session"] = session
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
    request = SimpleNamespace(scope={"session": anonymous})
    promoted = server.promote_session(request, Avatar("alice", ["admin"]))
    assert request.scope["session"] is promoted
    assert promoted is not anonymous
    assert promoted.avatar is not None and promoted.avatar.identity == "alice"
