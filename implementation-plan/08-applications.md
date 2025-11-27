# Block 08: applications.py

**Status**: DA REVISIONARE
**Dependencies**: 01-07 (all previous blocks)
**Commit message**: `feat(applications): add App class with HTTP/WebSocket/Lifespan support`

---

## Purpose

Main ASGI Application class that composes all components.

## File: `src/genro_asgi/applications.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ASGI Application class."""

from typing import Awaitable, Callable

from .datastructures import State
from .exceptions import HTTPException
from .lifespan import Lifespan
from .requests import Request
from .responses import JSONResponse, PlainTextResponse, Response
from .types import ASGIApp, Receive, Scope, Send
from .websockets import WebSocket

# Handler type aliases
HTTPHandler = Callable[[Request], Awaitable[Response]]
WebSocketHandler = Callable[[WebSocket], Awaitable[None]]
RawASGIHandler = Callable[[Scope, Receive, Send], Awaitable[None]]


class App:
    """
    ASGI Application.

    Main entry point for genro-asgi applications.
    Composes HTTP handling, WebSocket support, lifespan events,
    and middleware chain.

    Example - Simple HTTP:
        async def handler(request: Request) -> Response:
            return JSONResponse({"hello": "world"})

        app = App(handler=handler)

    Example - With WebSocket:
        async def http_handler(request: Request) -> Response:
            return JSONResponse({"status": "ok"})

        async def ws_handler(websocket: WebSocket) -> None:
            await websocket.accept()
            async for msg in websocket:
                await websocket.send_text(f"Echo: {msg}")

        app = App(
            handler=http_handler,
            websocket_handler=ws_handler,
        )

    Example - With Lifespan:
        lifespan = Lifespan()

        @lifespan.on_startup
        async def startup():
            app.state.db = await connect_db()

        app = App(handler=handler, lifespan=lifespan)

    Example - With Middleware:
        from genro_asgi.middleware import CORSMiddleware

        app = App(
            handler=handler,
            middleware=[
                (CORSMiddleware, {"allow_origins": ["*"]}),
            ],
        )
    """

    __slots__ = (
        "_handler",
        "_websocket_handler",
        "_lifespan",
        "_middleware",
        "_debug",
        "_state",
        "_app",
    )

    def __init__(
        self,
        handler: HTTPHandler | RawASGIHandler | None = None,
        *,
        websocket_handler: WebSocketHandler | None = None,
        lifespan: Lifespan | bool = False,
        middleware: list[tuple[type, dict] | type] | None = None,
        debug: bool = False,
    ) -> None:
        """
        Initialize ASGI application.

        Args:
            handler: HTTP request handler (Request -> Response or raw ASGI)
            websocket_handler: WebSocket connection handler
            lifespan: Lifespan instance or True for empty Lifespan
            middleware: List of middleware classes (or tuples with kwargs)
            debug: Enable debug mode (detailed error messages)
        """
        self._handler = handler
        self._websocket_handler = websocket_handler
        self._debug = debug
        self._state = State()

        # Setup lifespan
        if lifespan is True:
            self._lifespan = Lifespan()
        elif lifespan is False:
            self._lifespan = None
        else:
            self._lifespan = lifespan

        # Setup middleware
        self._middleware = middleware or []

        # Build the middleware-wrapped app
        self._app = self._build_app()

    @property
    def state(self) -> State:
        """Application state for storing shared data."""
        return self._state

    @property
    def debug(self) -> bool:
        """Debug mode flag."""
        return self._debug

    def _build_app(self) -> ASGIApp:
        """Build the ASGI app with middleware chain."""
        app: ASGIApp = self._dispatch

        # Apply middleware in reverse order (last added = outermost)
        for mw in reversed(self._middleware):
            if isinstance(mw, tuple):
                mw_class, mw_kwargs = mw
                app = mw_class(app, **mw_kwargs)
            else:
                app = mw(app)

        return app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI interface.

        Routes to appropriate handler based on scope type.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        scope["app"] = self

        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            await self._app(scope, receive, send)

    async def _dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Dispatch to HTTP or WebSocket handler.

        Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)

    async def _handle_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Handle lifespan events."""
        if self._lifespan:
            await self._lifespan(scope, receive, send)
        else:
            # No lifespan handler - just acknowledge events
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

    async def _handle_http(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Handle HTTP requests."""
        if self._handler is None:
            response = PlainTextResponse("Not Found", status_code=404)
            await response(scope, receive, send)
            return

        request = Request(scope, receive)

        try:
            # Check if handler is raw ASGI or high-level
            response = await self._handler(request)  # type: ignore

            # If handler returned a Response, send it
            if isinstance(response, Response):
                await response(scope, receive, send)
            # If handler is raw ASGI (returned None), it handled send itself

        except HTTPException as exc:
            response = self._http_exception_response(exc)
            await response(scope, receive, send)

        except Exception as exc:
            response = self._error_response(exc)
            await response(scope, receive, send)

    async def _handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Handle WebSocket connections."""
        if self._websocket_handler is None:
            # No WebSocket handler - close connection
            await send({"type": "websocket.close", "code": 4000})
            return

        websocket = WebSocket(scope, receive, send)

        try:
            await self._websocket_handler(websocket)
        except Exception:
            # WebSocket errors - try to close gracefully
            try:
                await websocket.close(code=1011, reason="Internal error")
            except Exception:
                pass

    def _http_exception_response(self, exc: HTTPException) -> Response:
        """Create response from HTTPException."""
        if exc.headers:
            headers = exc.headers
        else:
            headers = {}

        return JSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
            headers=headers,
        )

    def _error_response(self, exc: Exception) -> Response:
        """Create response from unexpected exception."""
        if self._debug:
            import traceback
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        else:
            detail = "Internal Server Error"

        return JSONResponse(
            {"detail": detail},
            status_code=500,
        )

    # --- Convenience methods ---

    def on_startup(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """
        Register startup handler (shortcut for lifespan.on_startup).

        Creates lifespan if not exists.
        """
        if self._lifespan is None:
            self._lifespan = Lifespan()
        return self._lifespan.on_startup(func)

    def on_shutdown(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """
        Register shutdown handler (shortcut for lifespan.on_shutdown).

        Creates lifespan if not exists.
        """
        if self._lifespan is None:
            self._lifespan = Lifespan()
        return self._lifespan.on_shutdown(func)
```

## Tests: `tests/test_applications.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for App class."""

import pytest
from genro_asgi.applications import App
from genro_asgi.exceptions import HTTPException
from genro_asgi.requests import Request
from genro_asgi.responses import JSONResponse, Response
from genro_asgi.websockets import WebSocket


class MockTransport:
    """Mock ASGI transport for testing."""

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


def lifespan_scope() -> dict:
    return {"type": "lifespan"}


class TestAppHTTP:
    @pytest.mark.asyncio
    async def test_simple_handler(self):
        async def handler(request: Request) -> Response:
            return JSONResponse({"message": "hello"})

        app = App(handler=handler)
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["status"] == 200
        assert b"hello" in transport.outgoing[1]["body"]

    @pytest.mark.asyncio
    async def test_no_handler_404(self):
        app = App()
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["status"] == 404

    @pytest.mark.asyncio
    async def test_http_exception(self):
        async def handler(request: Request) -> Response:
            raise HTTPException(403, detail="Forbidden")

        app = App(handler=handler)
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["status"] == 403
        assert b"Forbidden" in transport.outgoing[1]["body"]

    @pytest.mark.asyncio
    async def test_unhandled_exception(self):
        async def handler(request: Request) -> Response:
            raise ValueError("Unexpected error")

        app = App(handler=handler)
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["status"] == 500

    @pytest.mark.asyncio
    async def test_debug_mode_shows_traceback(self):
        async def handler(request: Request) -> Response:
            raise ValueError("Debug error")

        app = App(handler=handler, debug=True)
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        body = transport.outgoing[1]["body"]
        assert b"Debug error" in body
        assert b"Traceback" in body or b"ValueError" in body

    @pytest.mark.asyncio
    async def test_app_in_scope(self):
        captured_app = None

        async def handler(request: Request) -> Response:
            nonlocal captured_app
            captured_app = request.scope.get("app")
            return JSONResponse({})

        app = App(handler=handler)
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert captured_app is app


class TestAppWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_handler(self):
        messages_received = []

        async def ws_handler(websocket: WebSocket) -> None:
            await websocket.accept()
            msg = await websocket.receive_text()
            messages_received.append(msg)
            await websocket.send_text(f"Echo: {msg}")

        app = App(websocket_handler=ws_handler)
        transport = MockTransport([
            {"type": "websocket.receive", "text": "hello"},
            {"type": "websocket.disconnect", "code": 1000},
        ])

        await app(ws_scope(), transport.receive, transport.send)

        assert messages_received == ["hello"]
        assert transport.outgoing[0]["type"] == "websocket.accept"
        assert transport.outgoing[1]["text"] == "Echo: hello"

    @pytest.mark.asyncio
    async def test_no_websocket_handler(self):
        app = App()
        transport = MockTransport()

        await app(ws_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["type"] == "websocket.close"
        assert transport.outgoing[0]["code"] == 4000


class TestAppLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_true(self):
        app = App(lifespan=True)
        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        await app(lifespan_scope(), transport.receive, transport.send)

        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"

    @pytest.mark.asyncio
    async def test_lifespan_false(self):
        app = App(lifespan=False)
        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        await app(lifespan_scope(), transport.receive, transport.send)

        # Should still acknowledge events
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"

    @pytest.mark.asyncio
    async def test_on_startup_shortcut(self):
        app = App(lifespan=True)
        called = []

        @app.on_startup
        async def startup():
            called.append("startup")

        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        await app(lifespan_scope(), transport.receive, transport.send)

        assert called == ["startup"]

    @pytest.mark.asyncio
    async def test_on_shutdown_shortcut(self):
        app = App(lifespan=True)
        called = []

        @app.on_shutdown
        async def shutdown():
            called.append("shutdown")

        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

        await app(lifespan_scope(), transport.receive, transport.send)

        assert called == ["shutdown"]


class TestAppState:
    def test_state(self):
        app = App()
        app.state.db = "connection"
        assert app.state.db == "connection"


class TestAppMiddleware:
    @pytest.mark.asyncio
    async def test_middleware(self):
        calls = []

        class TestMiddleware:
            def __init__(self, app):
                self.app = app

            async def __call__(self, scope, receive, send):
                calls.append("before")
                await self.app(scope, receive, send)
                calls.append("after")

        async def handler(request: Request) -> Response:
            calls.append("handler")
            return JSONResponse({})

        app = App(handler=handler, middleware=[TestMiddleware])
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert calls == ["before", "handler", "after"]

    @pytest.mark.asyncio
    async def test_middleware_with_kwargs(self):
        class ConfigMiddleware:
            def __init__(self, app, prefix: str = ""):
                self.app = app
                self.prefix = prefix

            async def __call__(self, scope, receive, send):
                scope["prefix"] = self.prefix
                await self.app(scope, receive, send)

        captured_prefix = None

        async def handler(request: Request) -> Response:
            nonlocal captured_prefix
            captured_prefix = request.scope.get("prefix")
            return JSONResponse({})

        app = App(
            handler=handler,
            middleware=[(ConfigMiddleware, {"prefix": "/api"})],
        )
        transport = MockTransport()

        await app(http_scope(), transport.receive, transport.send)

        assert captured_prefix == "/api"
```

## Exports in `__init__.py`

```python
from .applications import App
```

## Checklist

- [ ] Create `src/genro_asgi/applications.py`
- [ ] Create `tests/test_applications.py`
- [ ] Run `pytest tests/test_applications.py`
- [ ] Run `mypy src/genro_asgi/applications.py`
- [ ] Update `__init__.py` exports
- [ ] Commit
