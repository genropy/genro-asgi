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

"""HTTP request: one flat class over the ASGI scope, eager body parsing.

``Request`` is HTTP-only — no transport abstraction (the WSX/message transport
is orchestration, out of the core). It wraps the ASGI ``scope`` and, in the
async ``init()``, parses headers/cookies/query/body once via
``genro_tytx.asgi_data`` (which hydrates JSON/XML/msgpack bodies and hands back
the raw bytes for anything else). TYTX mode is detected from the
``X-TYTX-Transport`` header; the paired ``Response`` reads ``tytx_mode`` /
``tytx_transport`` to serialize the reply in the same transport.

The owning application creates it (``Request(scope, receive, application=app)``,
or ``server=`` directly) and holds the response seam: ``self.response`` is a
``Response`` bound back to this request (the TYTX path).

``handler_kwargs()`` builds the kwargs a route handler receives: the query is
the base; a form body (``x-www-form-urlencoded``) is decoded and merged (body
wins on a clash), a hydrated body is passed whole as ``body_data``, opaque bytes
as ``body_raw``, an empty body adds nothing.

``db`` is the deferred preparation layer (no ORM yet): on first access it
resolves the server's registered handler for the owning app's ``db_name`` (else
``"default"``) and registers its ``closeConnection`` as a request cleanup (drained
by the server at end of request). ``get_db(name)`` is a plain lookup with no
cleanup registration. Auth and session ride the scope (``scope["auth"]`` — an
``Avatar`` or ``None`` — and ``scope["session"]``), set by the middleware chain.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any

from genro_tytx import asgi_data

from .response import Response

if TYPE_CHECKING:
    from .application import BaseApplication
    from .server import BaseServer
    from .types import Receive, Scope

__all__ = ["Request"]


class Request:
    """An ASGI HTTP request: scope wrapper with eager, TYTX-aware body parsing."""

    __slots__ = (
        "_scope",
        "_receive",
        "_server",
        "_application",
        "_db",
        "_headers",
        "_cookies",
        "_query",
        "_data",
        "_id",
        "_external_id",
        "_tytx_mode",
        "_tytx_transport",
        "_created_at",
        "response",
    )

    def __init__(
        self,
        scope: Scope,
        receive: Receive,
        *,
        server: BaseServer | None = None,
        application: BaseApplication | None = None,
    ) -> None:
        self._scope = scope
        self._receive = receive
        self._server = server
        self._application = application
        self._db: Any = None
        self._headers: dict[str, Any] = {}
        self._cookies: dict[str, str] = {}
        self._query: dict[str, Any] = {}
        self._data: Any = None
        self._id: str = ""
        self._external_id: str | None = None
        self._tytx_mode: bool = False
        self._tytx_transport: str | None = None
        self._created_at: float = time.time()
        self.response: Response = Response(request=self)

    async def init(self) -> None:
        """Parse headers, cookies, query and body from the scope (once).

        Delegates to ``genro_tytx.asgi_data`` and then derives TYTX mode, the
        request id (``x-request-id`` header or a fresh uuid4) and the optional
        client correlation id (``x-external-id``).
        """
        data = await asgi_data(dict(self._scope), self._receive)
        self._headers = data["headers"]
        self._cookies = data["cookies"]
        self._query = data["query"]
        self._data = data["body"]
        transport = self._headers.get("x-tytx-transport")
        if transport:
            self._tytx_mode = True
            self._tytx_transport = str(transport).lower()
        request_id = self._headers.get("x-request-id")
        self._id = str(request_id) if request_id else str(uuid.uuid4())
        external_id = self._headers.get("x-external-id")
        self._external_id = str(external_id) if external_id is not None else None

    @property
    def id(self) -> str:
        """Correlation id: the ``x-request-id`` header, or a generated uuid4."""
        return self._id

    @property
    def method(self) -> str:
        """HTTP method (uppercased)."""
        return str(self._scope.get("method", "GET")).upper()

    @property
    def path(self) -> str:
        """Request path."""
        return str(self._scope.get("path", "/"))

    @property
    def headers(self) -> dict[str, Any]:
        """Request headers (lowercase keys), values hydrated by TYTX."""
        return self._headers

    @property
    def cookies(self) -> dict[str, str]:
        """Request cookies parsed from the ``Cookie`` header."""
        return self._cookies

    @property
    def query(self) -> dict[str, Any]:
        """Query parameters (typed via TYTX)."""
        return self._query

    @property
    def data(self) -> Any:
        """Parsed body: hydrated value, raw bytes, or ``None`` when empty."""
        return self._data

    @property
    def content_type(self) -> str | None:
        """``Content-Type`` header value, or ``None``."""
        return self._headers.get("content-type")

    @property
    def external_id(self) -> str | None:
        """Client-provided correlation id (``x-external-id`` header)."""
        return self._external_id

    @property
    def tytx_mode(self) -> bool:
        """True when the request declared a TYTX transport."""
        return self._tytx_mode

    @property
    def tytx_transport(self) -> str | None:
        """TYTX transport (``json``/``xml``/``msgpack``), or ``None``."""
        return self._tytx_transport

    @property
    def created_at(self) -> float:
        """Wall-clock timestamp captured at construction."""
        return self._created_at

    @property
    def age(self) -> float:
        """Seconds elapsed since construction."""
        return time.time() - self._created_at

    @property
    def scope(self) -> Scope:
        """The raw ASGI scope."""
        return self._scope

    @property
    def server(self) -> BaseServer | None:
        """The owning server (passed directly, or via the owning application)."""
        if self._server is not None:
            return self._server
        return self._application.server if self._application is not None else None

    @property
    def application(self) -> BaseApplication | None:
        """The application that created this request (``None`` if unbound)."""
        return self._application

    @property
    def avatar(self) -> Any:
        """The identity acting on this request (an ``Avatar``) or ``None``.

        The effective identity the auth chain resolved for this request —
        header credentials or the session's avatar — read from the scope.
        """
        return self._scope.get("auth")

    @property
    def auth_tags(self) -> list[str]:
        """Authorization tags of the current identity (empty when anonymous)."""
        avatar = self.avatar
        return list(avatar.tags) if avatar is not None else []

    @property
    def session(self) -> Any:
        """The session object attached by ``SessionMiddleware``, or ``None``."""
        return self._scope.get("session")

    @property
    def db(self) -> Any:
        """The default db handler for the owning app, or ``None`` (lazy).

        Resolves ``server.databases[name]`` where ``name`` is the owning
        application's ``db_name`` attribute if set, else ``"default"``. On the
        first successful resolution it registers ``handler.closeConnection`` as a
        request cleanup (drained by the server at end of request). Returns
        ``None`` when there is no server or no handler under that name.

        Preparation layer only: no pooling, no transactions, no per-app registry.
        """
        if self._db is not None:
            return self._db
        server = self.server
        if server is None:
            return None
        name = getattr(self._application, "db_name", None) or "default"
        handler = server.databases.get(name)
        if handler is None:
            return None
        self._db = handler
        current = server.requests.current
        if current is not None:
            current.add_cleanup(handler.closeConnection)
        return handler

    def get_db(self, name: str) -> Any:
        """Look up a registered db handler by ``name`` (no cleanup registration)."""
        server = self.server
        if server is None:
            return None
        return server.databases.get(name)

    def handler_kwargs(self) -> dict[str, Any]:
        """Build the kwargs a route handler is called with (query + body).

        The query params are the base. The body adds to them by content-type,
        not by Python shape: an ``x-www-form-urlencoded`` body arrives already
        hydrated (``asgi_data`` decodes it, typed, via TYTX ``from_qs``) and is
        merged — the body wins on a name clash; a hydrated body (JSON/XML/msgpack)
        is passed whole as ``body_data``; opaque bytes are passed as ``body_raw``;
        an empty body adds nothing.
        """
        kwargs: dict[str, Any] = dict(self._query)
        data = self._data
        if data is None:
            return kwargs
        content_type = (self.content_type or "").lower()
        if "x-www-form-urlencoded" in content_type:
            if isinstance(data, dict):
                kwargs.update(data)
        elif isinstance(data, bytes):
            kwargs["body_raw"] = data
        else:
            kwargs["body_data"] = data
        return kwargs

    def __repr__(self) -> str:
        return f"<Request id={self._id!r} method={self.method} path={self.path!r}>"


if __name__ == "__main__":
    import asyncio

    async def demo() -> None:
        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b'{"n":1}', "more_body": False}

        scope: Scope = {
            "type": "http",
            "method": "POST",
            "path": "/items",
            "query_string": b"page=2",
            "headers": [(b"content-type", b"application/json")],
        }
        request = Request(scope, receive)
        await request.init()
        assert request.method == "POST"
        assert request.query == {"page": 2}
        assert request.data == {"n": 1}
        assert request.handler_kwargs() == {"page": 2, "body_data": {"n": 1}}
        assert isinstance(request.response, Response)
        print(request)

    asyncio.run(demo())
