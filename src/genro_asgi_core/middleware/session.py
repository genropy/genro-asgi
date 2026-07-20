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

"""Session middleware — session lifecycle driven by the request cookie.

Reads the session token from the request ``Cookie`` header (via the shared
``headers_dict`` scope cache, not a request object), reconnects an existing
session or creates a new ANONYMOUS one through ``server.session_store``
(``store.create()`` with no avatar — capturing an identity into a session is
an explicit act of the login surface, core 1d), attaches it to
``scope["session"]``, and — for a NEW session — wraps ``send`` to add a
``Set-Cookie`` header (HttpOnly, ``Max-Age`` = the session TTL). Armed by
``SessionMixin``; order 400 (OUTSIDE ``AuthMiddleware`` at 450, so the session
is on the scope before the §5.5 fallback runs), default OFF. The chain only
carries ``http`` scopes, so no scope filtering happens here.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any

from .base import BaseMiddleware, headers_dict

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send

__all__ = ["SessionMiddleware"]


class SessionMiddleware(BaseMiddleware):
    """Per-server session middleware: cookie in, session on the scope, cookie out."""

    middleware_order = 400
    middleware_default = False

    def __init__(
        self,
        app: ASGIApp,
        server: Any,
        cookie_name: str = "session_id",
        secure: bool = False,
        samesite: str = "lax",
        **options: Any,
    ) -> None:
        """Store the cookie configuration; ``server`` supplies ``session_store``."""
        super().__init__(app, server, **options)
        self._cookie_name = cookie_name
        self._secure = secure
        self._samesite = samesite

    def _cookie_value(self, scope: Scope) -> str | None:
        """The session cookie value carried by the request, or ``None``."""
        cookie_header = headers_dict(scope).get("cookie")
        if not cookie_header:
            return None
        jar: SimpleCookie = SimpleCookie()
        jar.load(cookie_header)
        morsel = jar.get(self._cookie_name)
        return morsel.value if morsel is not None else None

    def _set_cookie(self, session: Any) -> tuple[bytes, bytes]:
        """Build the ``Set-Cookie`` header tuple for a newly created session."""
        parts = [
            f"{self._cookie_name}={session.id}",
            f"Max-Age={session.meta['ttl']}",
            "Path=/",
            "HttpOnly",
            f"SameSite={self._samesite.capitalize()}",
        ]
        if self._secure:
            parts.append("Secure")
        return (b"set-cookie", "; ".join(parts).encode("latin-1"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach the session to the scope; emit ``Set-Cookie`` for a new session."""
        store = self.server.session_store
        session_id = self._cookie_value(scope)
        session = store.get(session_id) if session_id else None
        is_new = session is None
        if is_new:
            session = store.create()
        scope["session"] = session

        if not is_new:
            await self.app(scope, receive, send)
            return

        cookie = self._set_cookie(session)

        async def send_with_cookie(message: MutableMapping[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(cookie)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_cookie)


if __name__ == "__main__":
    import asyncio

    from ..session.store import MemorySessionStore

    class _Server:
        def __init__(self) -> None:
            self.session_store = MemorySessionStore()

    async def demo() -> None:
        async def inner(scope: Scope, receive: Receive, send: Send) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        async def receive() -> Any:
            return {"type": "http.request"}

        sent: list[Any] = []

        async def send(message: Any) -> None:
            sent.append(message)

        middleware = SessionMiddleware(inner, _Server())
        scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        await middleware(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        cookies = [value for name, value in start["headers"] if name == b"set-cookie"]
        assert cookies and cookies[0].startswith(b"session_id=")
        assert "session" in scope

    asyncio.run(demo())
