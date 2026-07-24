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
mixin keeps the base answer (``None``). The login seam is not a server method:
a handler attaches the identity through the request facade
(``request.session.attach_avatar(avatar)``) — the session id never changes at
login, so the cookie already held by the client stays valid.
"""

from __future__ import annotations

from typing import Any

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



if __name__ == "__main__":
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
    # login seam via the request facade: attach the avatar to the session in place
    anonymous.attach_avatar(Avatar("alice", ["admin"]))
    assert anonymous.avatar is not None and anonymous.avatar.identity == "alice"
    assert anonymous.data["cart"] == "kept"  # same session, same id — the cart survives
