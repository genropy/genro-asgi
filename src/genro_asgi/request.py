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

"""
Transport-agnostic request system.

This module provides the complete request handling infrastructure:
- BaseRequest: Abstract interface for all request types
- HttpRequest: ASGI HTTP request adapter
- MsgRequest: Message-based request adapter (WSX over WebSocket, NATS)
- RequestRegistry: Factory and tracking for active requests

Architecture:
    BaseRequest (ABC)
        ├── HttpRequest     # ASGI HTTP scope
        └── MsgRequest      # WSX message (WebSocket, NATS)

Every request:
1. Gets a unique `id` (correlation ID)
2. Is registered in RequestRegistry
3. Has `app_name` for per-app metrics
4. Has `created_at` for age tracking
5. Is unregistered on completion

Example:
    registry = RequestRegistry()
    request = await registry.create(scope, receive, send)
    try:
        result = await handler(request)
    finally:
        registry.unregister(request.id)
"""

from __future__ import annotations

import json as stdlib_json
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from .datastructures import (
    Address,
    Headers,
    QueryParams,
    State,
    URL,
    headers_from_scope,
    query_params_from_scope,
)
from .types import Receive, Scope, Send

if TYPE_CHECKING:
    from .websocket import WebSocket

__all__ = [
    "BaseRequest",
    "HttpRequest",
    "MsgRequest",
    "RequestRegistry",
    "REQUEST_FACTORIES",
    "get_current_request",
    "set_current_request",
]

# ContextVar for current request - allows any code to access the current request
_current_request: ContextVar["BaseRequest | None"] = ContextVar("current_request", default=None)


def get_current_request() -> "BaseRequest | None":
    """Get the current request from context. Returns None if not in request context."""
    return _current_request.get()


def set_current_request(request: "BaseRequest | None") -> Any:
    """Set the current request in context. Returns token for reset."""
    return _current_request.set(request)


class BaseRequest(ABC):
    """
    Abstract base class for transport-agnostic requests.

    All request implementations (HTTP, Message-based) must implement
    this interface, allowing handlers to work uniformly across transports.

    Properties:
        id: Server-generated correlation ID (internal)
        external_id: Client-provided ID for correlation (optional)
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        path: Request path (e.g., '/users/42')
        headers: Request headers as dict
        cookies: Request cookies as dict
        query: Query parameters
        data: Request body/payload
        transport: Transport type ('http', 'websocket', 'nats')
        app_name: Name of the app handling this request (for metrics)
        created_at: Timestamp when request was created (for age tracking)
        tytx_mode: True if request uses TYTX serialization
        tytx_transport: TYTX transport type ('json', 'msgpack') or None
    """

    __slots__ = ("_app_name", "_created_at", "_external_id", "_tytx_mode", "_tytx_transport", "response")

    def __init__(self) -> None:
        from .response import Response
        self._app_name: str | None = None
        self._created_at: float = time.time()
        self._external_id: str | None = None
        self._tytx_mode: bool = False
        self._tytx_transport: str | None = None
        self.response: Response = Response(request=self)

    @property
    @abstractmethod
    def id(self) -> str:
        """Correlation ID for request/response matching."""

    @property
    @abstractmethod
    def method(self) -> str:
        """HTTP method: GET, POST, PUT, DELETE, PATCH."""

    @property
    @abstractmethod
    def path(self) -> str:
        """Request path (e.g., '/users/42')."""

    @property
    @abstractmethod
    def headers(self) -> dict[str, str]:
        """Request headers (lowercase keys)."""

    @property
    @abstractmethod
    def cookies(self) -> dict[str, str]:
        """Request cookies."""

    @property
    @abstractmethod
    def query(self) -> dict[str, Any]:
        """Query parameters."""

    @property
    @abstractmethod
    def data(self) -> Any:
        """Request body/payload."""

    @property
    @abstractmethod
    def transport(self) -> str:
        """Transport type: 'http', 'websocket', 'nats'."""

    @property
    def external_id(self) -> str | None:
        """Client-provided ID for correlation (e.g., WSX message id)."""
        return self._external_id

    @external_id.setter
    def external_id(self, value: str | None) -> None:
        self._external_id = value

    @property
    def tytx_mode(self) -> bool:
        """True if request uses TYTX serialization."""
        return self._tytx_mode

    @tytx_mode.setter
    def tytx_mode(self, value: bool) -> None:
        self._tytx_mode = value

    @property
    def tytx_transport(self) -> str | None:
        """TYTX transport type ('json', 'msgpack') or None."""
        return self._tytx_transport

    @tytx_transport.setter
    def tytx_transport(self, value: str | None) -> None:
        self._tytx_transport = value

    @property
    def app_name(self) -> str | None:
        """Name of the app handling this request (set after routing)."""
        return self._app_name

    @app_name.setter
    def app_name(self, value: str | None) -> None:
        self._app_name = value

    @property
    def created_at(self) -> float:
        """Timestamp when request was created."""
        return self._created_at

    @property
    def age(self) -> float:
        """Seconds since request was created."""
        return time.time() - self._created_at

    @abstractmethod
    async def init(
        self,
        scope: Scope,
        receive: Receive,
        send: Send | None = None,
        **kwargs: Any,
    ) -> None:
        """Async initialization - subclasses must override."""

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"id={self.id!r} method={self.method} path={self.path!r} "
            f"transport={self.transport}>"
        )


class HttpRequest(BaseRequest):
    """HTTP request adapter wrapping ASGI scope."""

    __slots__ = (
        "_scope",
        "_body",
        "_headers",
        "_headers_obj",
        "_cookies",
        "_query",
        "_query_obj",
        "_data",
        "_id",
        "_url",
        "_state",
    )

    def __init__(self) -> None:
        super().__init__()
        # Slots initialized to None, populated by init()
        self._scope: Scope = {}
        self._body: bytes = b""
        self._headers: dict[str, str] = {}
        self._cookies: dict[str, str] = {}
        self._query: dict[str, Any] = {}
        self._data: Any = None
        self._id: str = ""
        self._url: URL | None = None
        self._state: State | None = None
        self._headers_obj: Headers | None = None
        self._query_obj: QueryParams | None = None

    async def init(
        self,
        scope: Scope,
        receive: Receive,
        send: Send | None = None,
        **kwargs: Any,
    ) -> None:
        """Async initialization - reads body and parses request data."""
        from genro_tytx import asgi_data

        self._scope = scope

        # Parse headers first (needed for TYTX detection)
        self._headers = {}
        for name, value in scope.get("headers", []):
            self._headers[name.decode("latin-1").lower()] = value.decode("latin-1")

        # Check for TYTX mode via X-TYTX-Transport header
        tytx_transport = self._headers.get("x-tytx-transport")
        if tytx_transport:
            self._tytx_mode = True
            self._tytx_transport = tytx_transport.lower()

        # Use asgi_data for parsing (handles both TYTX and normal requests)
        data = await asgi_data(dict(scope), receive)
        self._body = b""
        self._headers = data.get("headers", self._headers)
        self._cookies = data.get("cookies", {})
        self._query = data.get("query", {})
        self._data = data.get("body")

        # Generate or extract request ID
        self._id = self._headers.get("x-request-id", str(uuid.uuid4()))
        self._external_id = self._headers.get("x-external-id")

    @property
    def id(self) -> str:
        return self._id

    @property
    def method(self) -> str:
        return str(self._scope.get("method", "GET")).upper()

    @property
    def path(self) -> str:
        return str(self._scope.get("path", "/"))

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def cookies(self) -> dict[str, str]:
        return self._cookies

    @property
    def query(self) -> dict[str, Any]:
        return self._query

    @property
    def data(self) -> Any:
        return self._data

    @property
    def transport(self) -> str:
        return "http"

    @property
    def scope(self) -> Scope:
        """Raw ASGI scope dict."""
        return self._scope

    @property
    def body(self) -> bytes:
        """Raw body bytes."""
        return self._body

    @property
    def scheme(self) -> str:
        """URL scheme: http or https."""
        return str(self._scope.get("scheme", "http"))

    @property
    def url(self) -> URL:
        """Full request URL."""
        if self._url is None:
            scheme = self.scheme
            server = self._scope.get("server")
            path = self._scope.get("root_path", "") + self.path
            query_string = self._scope.get("query_string", b"")

            if server:
                host, port = server
                if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                    netloc = host
                else:
                    netloc = f"{host}:{port}"
            else:
                netloc = self._headers.get("host", "localhost")

            url_str = f"{scheme}://{netloc}{path}"
            if query_string:
                url_str += f"?{query_string.decode('latin-1')}"

            self._url = URL(url_str)
        return self._url

    @property
    def headers_obj(self) -> Headers:
        """Request headers as Headers object (case-insensitive)."""
        if self._headers_obj is None:
            self._headers_obj = headers_from_scope(self._scope)
        return self._headers_obj

    @property
    def query_params(self) -> QueryParams:
        """Query string parameters as QueryParams object."""
        if self._query_obj is None:
            self._query_obj = query_params_from_scope(self._scope)
        return self._query_obj

    @property
    def client(self) -> Address | None:
        """Client address (host, port) if available."""
        client = self._scope.get("client")
        if client:
            return Address(host=client[0], port=client[1])
        return None

    @property
    def state(self) -> State:
        """Request-scoped state container."""
        if self._state is None:
            self._state = State()
        return self._state

    @property
    def content_type(self) -> str | None:
        """Content-Type header value."""
        return self._headers.get("content-type")

    def make_response(self, result: Any) -> Any:
        """Convert handler result to Response object."""
        from .response import HTMLResponse, JSONResponse, PlainTextResponse, Response

        if isinstance(result, Response):
            return result
        if isinstance(result, dict):
            return JSONResponse(result)
        if isinstance(result, list):
            return JSONResponse(result)
        if isinstance(result, str):
            # Auto-detect HTML content by checking for HTML-like structure
            stripped = result.strip()
            if stripped.startswith("<") and stripped.endswith(">"):
                return HTMLResponse(result)
            return PlainTextResponse(result)
        if result is None:
            return PlainTextResponse("")
        return PlainTextResponse(str(result))


class MsgRequest(BaseRequest):
    """
    Message-based request adapter (WSX over WebSocket, NATS, etc.).

    Parses WSX:// formatted messages into BaseRequest interface.
    Transport-agnostic: works with any message-based protocol.
    """

    __slots__ = (
        "_scope",
        "_send",
        "_id",
        "_method",
        "_path",
        "_headers",
        "_cookies",
        "_query",
        "_data",
        "_transport_type",
        "_websocket",
    )

    def __init__(self) -> None:
        super().__init__()
        # Slots initialized to defaults, populated by init()
        self._scope: Scope = {}
        self._send: Send | None = None
        self._id: str = ""
        self._method: str = "GET"
        self._path: str = "/"
        self._headers: dict[str, str] = {}
        self._cookies: dict[str, str] = {}
        self._query: dict[str, Any] = {}
        self._data: Any = None
        self._transport_type: str = "websocket"
        self._websocket: "WebSocket | None" = None

    async def init(
        self,
        scope: Scope,
        receive: Receive,
        send: Send | None = None,
        **kwargs: Any,
    ) -> None:
        """Async initialization - parses WSX message."""
        self._scope = scope
        self._send = send
        self._transport_type = kwargs.get("transport_type", "websocket")
        self._websocket = kwargs.get("websocket")

        # Get message from kwargs
        message = kwargs.get("message")
        if message is None:
            raise ValueError("MsgRequest requires 'message' kwarg")

        # Parse WSX message
        parsed = self._parse_wsx_message(message)

        # Required fields
        if "id" not in parsed:
            raise ValueError("WSX message missing required 'id' field")
        if "method" not in parsed:
            raise ValueError("WSX message missing required 'method' field")

        # The WSX message 'id' is the client's external_id
        self._external_id = parsed["id"]
        # Generate internal server id
        self._id = str(uuid.uuid4())

        self._method = parsed["method"].upper()
        self._path = parsed.get("path", "/")
        self._headers = parsed.get("headers", {})
        self._cookies = parsed.get("cookies", {})
        self._query = parsed.get("query", {})
        self._data = parsed.get("data")

        # Detect TYTX mode from message marker or header
        self._tytx_mode = (
            parsed.get("tytx", False) or "tytx" in self._headers.get("content-type", "").lower()
        )

    def _parse_wsx_message(self, data: str | bytes) -> dict[str, Any]:
        """Parse WSX:// message into dict, with TYTX hydration if applicable."""
        if isinstance(data, bytes):
            # Binary data - try msgpack via from_tytx
            try:
                from genro_tytx import from_tytx

                return dict(from_tytx(data, transport="msgpack"))
            except ImportError:
                data = data.decode("utf-8")

        # String data
        if data.startswith("WSX://"):
            data = data[6:]

        # Check for TYTX JSON marker
        if data.endswith("::JS"):
            try:
                from genro_tytx import from_tytx

                return dict(from_tytx(data))
            except ImportError:
                data = data[:-4]  # Strip marker, parse as regular JSON

        return dict(stdlib_json.loads(data))

    @property
    def id(self) -> str:
        return self._id

    @property
    def method(self) -> str:
        return self._method

    @property
    def path(self) -> str:
        return self._path

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def cookies(self) -> dict[str, str]:
        return self._cookies

    @property
    def query(self) -> dict[str, Any]:
        return self._query

    @property
    def data(self) -> Any:
        return self._data

    @property
    def transport(self) -> str:
        return self._transport_type

    @property
    def scope(self) -> Scope:
        """Access to raw ASGI scope."""
        return self._scope

    @property
    def websocket(self) -> "WebSocket | None":
        """Access to underlying WebSocket connection (if available)."""
        return self._websocket

    @property
    def client(self) -> tuple[str, int] | None:
        """Client address as (host, port) tuple."""
        return self._scope.get("client")


class RequestRegistry:
    """
    Registry for creating and tracking active requests.

    Responsibilities:
    - Creates appropriate request based on scope["type"] using factories dict
    - Calls async init() on the created request
    - Tracks active requests for monitoring and metrics
    - Provides iteration and lookup by request ID

    Example:
        registry = RequestRegistry()
        request = await registry.create(scope, receive, send)
        print(f"Active: {len(registry)}")
        registry.unregister()
    """

    __slots__ = ("_requests", "factories", "_ctx_request")

    def __init__(
        self,
        factories: dict[str, type[BaseRequest]] | None = None,
    ) -> None:
        self._requests: dict[str, BaseRequest] = {}
        self.factories = factories if factories is not None else REQUEST_FACTORIES.copy()
        self._ctx_request: ContextVar[BaseRequest | None] = ContextVar('current_request', default=None)

    @property
    def current(self) -> BaseRequest | None:
        """Current request from ContextVar."""
        return self._ctx_request.get()

    async def create(
        self,
        scope: Scope,
        receive: Receive,
        send: Send | None = None,
        **kwargs: Any,
    ) -> BaseRequest:
        """Create and register a request from ASGI scope."""
        scope_type = scope.get("type", "")
        factory = self.factories.get(scope_type)
        if factory is None:
            raise ValueError(f"No factory for scope type: {scope_type!r}")

        request = factory()
        await request.init(scope, receive, send, **kwargs)
        self._requests[request.id] = request
        self._ctx_request.set(request)
        return request

    def register_factory(self, scope_type: str, factory: type[BaseRequest]) -> None:
        """Register a factory for a scope type."""
        self.factories[scope_type] = factory

    def unregister(self) -> BaseRequest | None:
        """Unregister current request."""
        request = self._ctx_request.get()
        if request is not None:
            self._requests.pop(request.id, None)
            self._ctx_request.set(None)
        return request

    def get(self, request_id: str) -> BaseRequest | None:
        """Get a request by id."""
        return self._requests.get(request_id)

    def count_by_app(self, app_name: str) -> int:
        """Count active requests for a specific app."""
        return sum(1 for req in self._requests.values() if req.app_name == app_name)

    def __len__(self) -> int:
        """Return number of active requests."""
        return len(self._requests)

    def __iter__(self) -> Iterator[BaseRequest]:
        """Iterate over active requests."""
        return iter(self._requests.values())

    def __contains__(self, request_id: str) -> bool:
        """Check if a request is registered."""
        return request_id in self._requests

    def __repr__(self) -> str:
        return f"RequestRegistry(active={len(self._requests)})"


# Default factories for request creation
REQUEST_FACTORIES: dict[str, type[BaseRequest]] = {
    "http": HttpRequest,
    "websocket": MsgRequest,
}
