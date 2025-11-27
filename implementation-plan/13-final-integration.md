# Block 13: Final Integration & __init__.py

**Status**: DA REVISIONARE
**Dependencies**: All previous blocks (01-12)
**Commit message**: `feat: complete genro-asgi with full public API`

---

## Purpose

Final integration of all components and complete public API exports.

## File: `src/genro_asgi/__init__.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
genro-asgi - Minimal ASGI foundation with WebSocket support.

A lightweight, framework-agnostic ASGI toolkit featuring:
- HTTP Request/Response handling
- WebSocket support with WSX protocol
- Lifespan management
- Composable middleware

Example - Simple HTTP:
    from genro_asgi import App, Request, JSONResponse

    async def handler(request: Request) -> JSONResponse:
        return JSONResponse({"hello": "world"})

    app = App(handler=handler)

Example - WebSocket with WSX:
    from genro_asgi import App, WebSocket
    from genro_asgi.wsx import WSXDispatcher, WSXHandler

    dispatcher = WSXDispatcher()

    @dispatcher.method("echo")
    async def echo(message: str):
        return {"echo": message}

    async def ws_handler(websocket: WebSocket):
        handler = WSXHandler(websocket, dispatcher)
        await handler.run()

    app = App(websocket_handler=ws_handler)
"""

__version__ = "0.1.0"

# Core application
from .applications import App

# Request/Response
from .requests import Request
from .responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

# WebSocket
from .websockets import WebSocket, WebSocketState

# Lifespan
from .lifespan import Lifespan

# Data structures
from .datastructures import Address, Headers, QueryParams, State, URL

# Exceptions
from .exceptions import HTTPException, WebSocketDisconnect, WebSocketException

# Types
from .types import ASGIApp, Message, Receive, Scope, Send

# Middleware
from .middleware import BaseHTTPMiddleware, CORSMiddleware, ErrorMiddleware

__all__ = [
    # Version
    "__version__",
    # Core
    "App",
    # Request/Response
    "Request",
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "StreamingResponse",
    "RedirectResponse",
    "FileResponse",
    # WebSocket
    "WebSocket",
    "WebSocketState",
    # Lifespan
    "Lifespan",
    # Data structures
    "Headers",
    "QueryParams",
    "State",
    "URL",
    "Address",
    # Exceptions
    "HTTPException",
    "WebSocketException",
    "WebSocketDisconnect",
    # Types
    "ASGIApp",
    "Scope",
    "Receive",
    "Send",
    "Message",
    # Middleware
    "BaseHTTPMiddleware",
    "CORSMiddleware",
    "ErrorMiddleware",
]
```

## Integration Test: `tests/test_integration.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Integration tests for genro-asgi."""

import json

import pytest
from genro_asgi import (
    App,
    HTTPException,
    JSONResponse,
    Lifespan,
    Request,
    WebSocket,
)
from genro_asgi.middleware import CORSMiddleware, ErrorMiddleware
from genro_asgi.wsx import WSXDispatcher, WSXHandler


class MockTransport:
    """Mock ASGI transport for testing."""

    def __init__(self, messages: list[dict] | None = None):
        self.incoming = messages or []
        self.outgoing: list[dict] = []

    async def receive(self) -> dict:
        if not self.incoming:
            if self.outgoing and self.outgoing[-1].get("type") == "websocket.accept":
                return {"type": "websocket.disconnect", "code": 1000}
            return {"type": "http.request", "body": b"", "more_body": False}
        return self.incoming.pop(0)

    async def send(self, message: dict) -> None:
        self.outgoing.append(message)


def http_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
    }


def ws_scope(path: str = "/ws") -> dict:
    return {
        "type": "websocket",
        "path": path,
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "subprotocols": [],
    }


class TestFullHTTPFlow:
    """Test complete HTTP request/response flow."""

    @pytest.mark.asyncio
    async def test_json_api(self):
        """Test JSON API endpoint."""
        async def handler(request: Request):
            data = await request.json()
            return JSONResponse({
                "received": data,
                "method": request.method,
            })

        app = App(handler=handler)
        transport = MockTransport([
            {"type": "http.request", "body": b'{"key": "value"}', "more_body": False}
        ])

        await app(http_scope(method="POST"), transport.receive, transport.send)

        body = json.loads(transport.outgoing[1]["body"])
        assert body["received"] == {"key": "value"}
        assert body["method"] == "POST"

    @pytest.mark.asyncio
    async def test_query_params(self):
        """Test query parameter parsing."""
        async def handler(request: Request):
            name = request.query_params.get("name", "World")
            return JSONResponse({"hello": name})

        app = App(handler=handler)
        transport = MockTransport()

        await app(
            http_scope(query_string=b"name=John"),
            transport.receive,
            transport.send,
        )

        body = json.loads(transport.outgoing[1]["body"])
        assert body["hello"] == "John"

    @pytest.mark.asyncio
    async def test_http_exception(self):
        """Test HTTP exception handling."""
        async def handler(request: Request):
            raise HTTPException(404, detail="Not found")

        app = App(handler=handler)
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["status"] == 404


class TestFullWSXFlow:
    """Test complete WSX WebSocket flow."""

    @pytest.mark.asyncio
    async def test_wsx_rpc(self):
        """Test WSX RPC call."""
        dispatcher = WSXDispatcher()

        @dispatcher.method("greet")
        async def greet(name: str):
            return f"Hello, {name}!"

        async def ws_handler(websocket: WebSocket):
            handler = WSXHandler(websocket, dispatcher, ping_interval=None)
            await handler.run()

        app = App(websocket_handler=ws_handler)
        transport = MockTransport([
            {"type": "websocket.receive", "text": json.dumps({
                "type": "rpc.request",
                "id": "1",
                "method": "greet",
                "params": {"name": "World"},
            })},
        ])

        await app(ws_scope(), transport.receive, transport.send)

        # Find the response
        responses = [
            msg for msg in transport.outgoing
            if msg.get("type") == "websocket.send"
        ]
        assert len(responses) >= 1

        response = json.loads(responses[0]["text"])
        assert response["type"] == "rpc.response"
        assert response["result"] == "Hello, World!"


class TestMiddlewareIntegration:
    """Test middleware integration."""

    @pytest.mark.asyncio
    async def test_cors_middleware(self):
        """Test CORS middleware."""
        async def handler(request: Request):
            return JSONResponse({"status": "ok"})

        app = App(
            handler=handler,
            middleware=[(CORSMiddleware, {"allow_origins": ["*"]})],
        )
        transport = MockTransport()

        await app(
            http_scope(headers=[(b"origin", b"http://example.com")]),
            transport.receive,
            transport.send,
        )

        headers = dict(transport.outgoing[0]["headers"])
        assert b"access-control-allow-origin" in headers

    @pytest.mark.asyncio
    async def test_error_middleware(self):
        """Test error middleware."""
        async def handler(request: Request):
            raise ValueError("Test error")

        app = App(
            handler=handler,
            middleware=[(ErrorMiddleware, {"debug": True})],
        )
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["status"] == 500
        body = transport.outgoing[1]["body"]
        assert b"Test error" in body


class TestLifespanIntegration:
    """Test lifespan integration."""

    @pytest.mark.asyncio
    async def test_lifespan_events(self):
        """Test startup and shutdown events."""
        events = []

        lifespan = Lifespan()

        @lifespan.on_startup
        async def startup():
            events.append("startup")

        @lifespan.on_shutdown
        async def shutdown():
            events.append("shutdown")

        app = App(lifespan=lifespan)
        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        await app({"type": "lifespan"}, transport.receive, transport.send)

        assert events == ["startup", "shutdown"]
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"


class TestSmartPublisherPattern:
    """Test the pattern used by SmartPublisher."""

    @pytest.mark.asyncio
    async def test_smartpublisher_style_handler(self):
        """
        Test handler pattern similar to SmartPublisher http_channel.

        This simulates how SmartPublisher would use genro-asgi
        instead of FastAPI.
        """
        # Mock SmartRoute-like router
        class MockRouter:
            def __init__(self):
                self.handlers = {
                    "service.list": self._list,
                    "service.create": self._create,
                }

            async def _list(self):
                return ["item1", "item2"]

            async def _create(self, name: str):
                return {"id": 1, "name": name}

            def get(self, method, use_smartasync=False):
                if method in self.handlers:
                    return self.handlers[method]
                raise KeyError(method)

        router = MockRouter()

        async def handler(request: Request):
            # Parse path to method name
            path = request.path.strip("/")
            segments = path.split("/")
            method_name = ".".join(segments)

            try:
                method_callable = router.get(method_name, use_smartasync=True)
            except KeyError:
                raise HTTPException(404, detail=f"Method not found: {method_name}")

            # Get params from query (GET) or body (POST)
            if request.method == "GET":
                params = {k: v for k, v in request.query_params.items()}
            else:
                try:
                    params = await request.json()
                except Exception:
                    params = {}

            # Call the method
            result = await method_callable(**params)

            return JSONResponse({"result": result})

        app = App(handler=handler)

        # Test list
        transport = MockTransport()
        await app(http_scope(path="/service/list"), transport.receive, transport.send)

        body = json.loads(transport.outgoing[1]["body"])
        assert body["result"] == ["item1", "item2"]

        # Test create
        transport = MockTransport([
            {"type": "http.request", "body": b'{"name": "test"}', "more_body": False}
        ])
        await app(
            http_scope(method="POST", path="/service/create"),
            transport.receive,
            transport.send,
        )

        body = json.loads(transport.outgoing[1]["body"])
        assert body["result"] == {"id": 1, "name": "test"}
```

## Checklist

- [ ] Update `src/genro_asgi/__init__.py` with full exports
- [ ] Create `tests/test_integration.py`
- [ ] Run full test suite: `pytest tests/`
- [ ] Run mypy: `mypy src/genro_asgi/`
- [ ] Run ruff: `ruff check src/`
- [ ] Verify all imports work: `python -c "from genro_asgi import *"`
- [ ] Update README.md with examples
- [ ] Final commit
