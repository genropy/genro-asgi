# Missing Documentation - 06_security_and_middleware

Paragraphs present in source documents but not in specifications.

## Source: initial_implementation_plan/archive/09-middleware.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types, 04-requests, 05-responses
**Commit message**: `feat(middleware): add BaseHTTPMiddleware, CORS, and Error middleware`

Middleware base class and essential middleware implementations.

```
src/genro_asgi/middleware/
├── __init__.py
├── base.py          # BaseHTTPMiddleware
├── cors.py          # CORSMiddleware
└── errors.py        # ErrorMiddleware
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

from .base import BaseHTTPMiddleware
from .cors import CORSMiddleware
from .errors import ErrorMiddleware

__all__ = [
    "BaseHTTPMiddleware",
    "CORSMiddleware",
    "ErrorMiddleware",
]
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Base HTTP middleware class."""

from typing import Awaitable, Callable

from ..requests import Request
from ..responses import Response
from ..types import ASGIApp, Receive, Scope, Send

CallNext = Callable[[Request], Awaitable[Response]]

class BaseHTTPMiddleware:
    """
    Base class for HTTP middleware.

Subclass and override dispatch() to implement custom middleware.

Example:
        class LoggingMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next: CallNext) -> Response:
                print(f"Request: {request.method} {request.path}")
                response = await call_next(request)
                print(f"Response: {response.status_code}")
                return response
    """

def __init__(self, app: ASGIApp) -> None:
        """
        Initialize middleware.

Args:
            app: The ASGI application to wrap
        """
        self.app = app

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            # Pass through non-HTTP requests
            await self.app(scope, receive, send)
            return

request = Request(scope, receive)

async def call_next(request: Request) -> Response:
            """Call the wrapped application."""
            response_started = False
            status_code = 200
            headers: list[tuple[bytes, bytes]] = []
            body_parts: list[bytes] = []

async def send_wrapper(message: dict) -> None:
                nonlocal response_started, status_code, headers

if message["type"] == "http.response.start":
                    response_started = True
                    status_code = message["status"]
                    headers = message.get("headers", [])
                elif message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    if body:
                        body_parts.append(body)

await self.app(scope, receive, send_wrapper)

# Reconstruct response
            body = b"".join(body_parts)
            return Response(
                content=body,
                status_code=status_code,
                headers={
                    k.decode("latin-1"): v.decode("latin-1")
                    for k, v in headers
                },
            )

response = await self.dispatch(request, call_next)
        await response(scope, receive, send)

async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        """
        Process the request.

Override this method in subclasses.

Args:
            request: The incoming request
            call_next: Callable to invoke the next middleware/handler

Returns:
            Response to send to client
        """
        return await call_next(request)
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

from ..responses import PlainTextResponse, Response
from ..types import ASGIApp, Receive, Scope, Send

class CORSMiddleware:
    """
    Cross-Origin Resource Sharing (CORS) middleware.

Adds appropriate CORS headers to responses and handles
    preflight OPTIONS requests.

Example:
        app = App(
            handler=my_handler,
            middleware=[
                (CORSMiddleware, {
                    "allow_origins": ["https://example.com"],
                    "allow_methods": ["GET", "POST"],
                    "allow_credentials": True,
                }),
            ],
        )
    """

def __init__(
        self,
        app: ASGIApp,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        allow_credentials: bool = False,
        expose_headers: list[str] | None = None,
        max_age: int = 600,
    ) -> None:
        """
        Initialize CORS middleware.

Args:
            app: ASGI application to wrap
            allow_origins: Allowed origins (default: ["*"])
            allow_methods: Allowed methods (default: ["*"])
            allow_headers: Allowed headers (default: ["*"])
            allow_credentials: Allow credentials (cookies, auth)
            expose_headers: Headers to expose to browser
            max_age: Preflight cache time in seconds
        """
        self.app = app
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
        self.allow_credentials = allow_credentials
        self.expose_headers = expose_headers or []
        self.max_age = max_age

# Pre-compute header values
        self._allow_all_origins = "*" in self.allow_origins
        self._allow_methods_str = ", ".join(self.allow_methods)
        self._allow_headers_str = ", ".join(self.allow_headers)
        self._expose_headers_str = ", ".join(self.expose_headers)

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

method = scope.get("method", "")
        headers = dict(
            (k.decode("latin-1").lower(), v.decode("latin-1"))
            for k, v in scope.get("headers", [])
        )
        origin = headers.get("origin", "")

# Check if origin is allowed
        if not self._is_origin_allowed(origin):
            await self.app(scope, receive, send)
            return

# Handle preflight OPTIONS request
        if method == "OPTIONS" and "access-control-request-method" in headers:
            response = self._preflight_response(origin, headers)
            await response(scope, receive, send)
            return

# Regular request - add CORS headers to response
        async def send_with_cors(message: dict) -> None:
            if message["type"] == "http.response.start":
                cors_headers = self._get_cors_headers(origin)
                existing_headers = list(message.get("headers", []))
                existing_headers.extend([
                    (k.encode("latin-1"), v.encode("latin-1"))
                    for k, v in cors_headers.items()
                ])
                message["headers"] = existing_headers
            await send(message)

await self.app(scope, receive, send_with_cors)

def _is_origin_allowed(self, origin: str) -> bool:
        """Check if origin is in allowed list."""
        if not origin:
            return False
        if self._allow_all_origins:
            return True
        return origin in self.allow_origins

def _get_cors_headers(self, origin: str) -> dict[str, str]:
        """Get CORS headers for regular response."""
        headers: dict[str, str] = {}

if self._allow_all_origins:
            headers["access-control-allow-origin"] = "*"
        else:
            headers["access-control-allow-origin"] = origin
            headers["vary"] = "Origin"

if self.allow_credentials:
            headers["access-control-allow-credentials"] = "true"

if self._expose_headers_str:
            headers["access-control-expose-headers"] = self._expose_headers_str

def _preflight_response(self, origin: str, headers: dict) -> Response:
        """Create preflight response."""
        response_headers: dict[str, str] = {}

# Origin
        if self._allow_all_origins:
            response_headers["access-control-allow-origin"] = "*"
        else:
            response_headers["access-control-allow-origin"] = origin
            response_headers["vary"] = "Origin"

# Methods
        response_headers["access-control-allow-methods"] = self._allow_methods_str

# Headers
        request_headers = headers.get("access-control-request-headers", "")
        if "*" in self.allow_headers:
            response_headers["access-control-allow-headers"] = request_headers or "*"
        else:
            response_headers["access-control-allow-headers"] = self._allow_headers_str

# Credentials
        if self.allow_credentials:
            response_headers["access-control-allow-credentials"] = "true"

# Max age
        response_headers["access-control-max-age"] = str(self.max_age)

return PlainTextResponse(
            content="",
            status_code=204,
            headers=response_headers,
        )
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Error handling middleware."""

import traceback
from typing import Callable

from ..exceptions import HTTPException
from ..responses import JSONResponse, Response
from ..types import ASGIApp, Receive, Scope, Send

class ErrorMiddleware:
    """
    Error handling middleware.

Catches exceptions and returns appropriate error responses.

Example:
        app = App(
            handler=my_handler,
            middleware=[
                (ErrorMiddleware, {"debug": True}),
            ],
        )
    """

def __init__(
        self,
        app: ASGIApp,
        debug: bool = False,
        handler: Callable[[Exception], Response] | None = None,
    ) -> None:
        """
        Initialize error middleware.

Args:
            app: ASGI application to wrap
            debug: Show detailed error messages
            handler: Custom error handler function
        """
        self.app = app
        self.debug = debug
        self.handler = handler

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

async def send_wrapper(message: dict) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if response_started:
                # Can't send error response if headers already sent
                raise

response = self._error_response(exc)
            await response(scope, receive, send)

def _error_response(self, exc: Exception) -> Response:
        """Create error response from exception."""
        if self.handler:
            return self.handler(exc)

if isinstance(exc, HTTPException):
            return JSONResponse(
                {"detail": exc.detail},
                status_code=exc.status_code,
                headers=exc.headers or {},
            )

if self.debug:
            detail = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        else:
            detail = "Internal Server Error"

return JSONResponse(
            {"detail": detail},
            status_code=500,
        )
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import pytest
from genro_asgi.exceptions import HTTPException
from genro_asgi.middleware import BaseHTTPMiddleware, CORSMiddleware, ErrorMiddleware
from genro_asgi.requests import Request
from genro_asgi.responses import JSONResponse, Response

class MockTransport:
    def __init__(self, messages: list[dict] | None = None):
        self.incoming = messages or []
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        if not self.incoming:
            return {"type": "http.request", "body": b"", "more_body": False}
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

def http_scope(
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers or [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
    }

async def simple_app(scope, receive, send):
    response = JSONResponse({"status": "ok"})
    await response(scope, receive, send)

async def error_app(scope, receive, send):
    raise ValueError("Test error")

async def http_error_app(scope, receive, send):
    raise HTTPException(400, detail="Bad request")

class TestBaseHTTPMiddleware:
    @pytest.mark.asyncio
    async def test_passthrough(self):
        class PassthroughMiddleware(BaseHTTPMiddleware):
            pass

middleware = PassthroughMiddleware(simple_app)
        transport = MockTransport()

await middleware(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 200

@pytest.mark.asyncio
    async def test_modify_response(self):
        class AddHeaderMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request, call_next):
                response = await call_next(request)
                response._headers["x-custom"] = "value"
                return response

middleware = AddHeaderMiddleware(simple_app)
        transport = MockTransport()

await middleware(http_scope(), transport.receive, transport.send)

headers = dict(transport.outgoing[0]["headers"])
        assert headers.get(b"x-custom") == b"value"

@pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        calls = []

async def ws_app(scope, receive, send):
            calls.append(scope["type"])

middleware = BaseHTTPMiddleware(ws_app)
        transport = MockTransport()

await middleware({"type": "websocket"}, transport.receive, transport.send)

class TestCORSMiddleware:
    @pytest.mark.asyncio
    async def test_cors_headers(self):
        middleware = CORSMiddleware(simple_app)
        transport = MockTransport()

await middleware(
            http_scope(headers=[(b"origin", b"http://example.com")]),
            transport.receive,
            transport.send,
        )

headers = dict(transport.outgoing[0]["headers"])
        assert b"access-control-allow-origin" in headers

@pytest.mark.asyncio
    async def test_preflight(self):
        middleware = CORSMiddleware(simple_app, allow_methods=["GET", "POST"])
        transport = MockTransport()

await middleware(
            http_scope(
                method="OPTIONS",
                headers=[
                    (b"origin", b"http://example.com"),
                    (b"access-control-request-method", b"POST"),
                ],
            ),
            transport.receive,
            transport.send,
        )

assert transport.outgoing[0]["status"] == 204
        headers = dict(transport.outgoing[0]["headers"])
        assert b"access-control-allow-methods" in headers

@pytest.mark.asyncio
    async def test_specific_origins(self):
        middleware = CORSMiddleware(
            simple_app, allow_origins=["http://allowed.com"]
        )
        transport = MockTransport()

# Allowed origin
        await middleware(
            http_scope(headers=[(b"origin", b"http://allowed.com")]),
            transport.receive,
            transport.send,
        )

headers = dict(transport.outgoing[0]["headers"])
        assert headers.get(b"access-control-allow-origin") == b"http://allowed.com"

@pytest.mark.asyncio
    async def test_credentials(self):
        middleware = CORSMiddleware(simple_app, allow_credentials=True)
        transport = MockTransport()

await middleware(
            http_scope(headers=[(b"origin", b"http://example.com")]),
            transport.receive,
            transport.send,
        )

headers = dict(transport.outgoing[0]["headers"])
        assert headers.get(b"access-control-allow-credentials") == b"true"

class TestErrorMiddleware:
    @pytest.mark.asyncio
    async def test_catch_exception(self):
        middleware = ErrorMiddleware(error_app)
        transport = MockTransport()

await middleware(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 500
        assert b"Internal Server Error" in transport.outgoing[1]["body"]

@pytest.mark.asyncio
    async def test_debug_mode(self):
        middleware = ErrorMiddleware(error_app, debug=True)
        transport = MockTransport()

await middleware(http_scope(), transport.receive, transport.send)

body = transport.outgoing[1]["body"]
        assert b"Test error" in body
        assert b"ValueError" in body

@pytest.mark.asyncio
    async def test_http_exception(self):
        middleware = ErrorMiddleware(http_error_app)
        transport = MockTransport()

await middleware(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 400
        assert b"Bad request" in transport.outgoing[1]["body"]

@pytest.mark.asyncio
    async def test_custom_handler(self):
        def custom_handler(exc):
            return JSONResponse({"custom": str(exc)}, status_code=418)

middleware = ErrorMiddleware(error_app, handler=custom_handler)
        transport = MockTransport()

await middleware(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 418

@pytest.mark.asyncio
    async def test_non_http_passthrough(self):
        middleware = ErrorMiddleware(error_app)
        transport = MockTransport()

with pytest.raises(ValueError):
            await middleware({"type": "websocket"}, transport.receive, transport.send)
```

```python
from .middleware import BaseHTTPMiddleware, CORSMiddleware, ErrorMiddleware
```

- [ ] Create `src/genro_asgi/middleware/__init__.py`
- [ ] Create `src/genro_asgi/middleware/base.py`
- [ ] Create `src/genro_asgi/middleware/cors.py`
- [ ] Create `src/genro_asgi/middleware/errors.py`
- [ ] Create `tests/test_middleware.py`
- [ ] Run `pytest tests/test_middleware.py`
- [ ] Run `mypy src/genro_asgi/middleware/`
- [ ] Update main `__init__.py` exports
- [ ] Commit

