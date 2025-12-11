# Block 11: wsx/ - WebSocket Handler

**Status**: DA REVISIONARE
**Dependencies**: 06-websockets, 10-wsx-core
**Commit message**: `feat(wsx): add WSXHandler for WebSocket connection management`

---

## Purpose

High-level handler that manages a WSX WebSocket connection, integrating the dispatcher with the WebSocket transport.

## File: `src/genro_asgi/wsx/handler.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX WebSocket connection handler."""

import asyncio
from typing import Any

from ..exceptions import WebSocketDisconnect
from ..websockets import WebSocket
from .dispatcher import WSXDispatcher
from .types import WSXMessage


class WSXHandler:
    """
    WSX WebSocket connection handler.

    Manages the lifecycle of a WSX WebSocket connection:
    - Accepts the connection
    - Receives messages and dispatches them
    - Sends responses back
    - Handles ping/pong keepalive
    - Manages graceful shutdown

    Example - Standalone:
        async def ws_endpoint(websocket: WebSocket):
            dispatcher = WSXDispatcher()

            @dispatcher.method("echo")
            async def echo(msg: str):
                return msg

            handler = WSXHandler(websocket, dispatcher)
            await handler.run()

    Example - With SmartRoute:
        async def ws_endpoint(websocket: WebSocket):
            dispatcher = WSXDispatcher(router=my_smartrouter)
            handler = WSXHandler(websocket, dispatcher)
            await handler.run()

    Example - With App:
        dispatcher = WSXDispatcher(router=router)

        async def ws_handler(websocket: WebSocket):
            handler = WSXHandler(websocket, dispatcher)
            await handler.run()

        app = App(
            handler=http_handler,
            websocket_handler=ws_handler,
        )
    """

    def __init__(
        self,
        websocket: WebSocket,
        dispatcher: WSXDispatcher,
        *,
        ping_interval: float | None = 30.0,
        ping_timeout: float | None = 10.0,
    ) -> None:
        """
        Initialize WSX handler.

        Args:
            websocket: WebSocket connection
            dispatcher: WSX message dispatcher
            ping_interval: Seconds between pings (None to disable)
            ping_timeout: Seconds to wait for pong (None for no timeout)
        """
        self.websocket = websocket
        self.dispatcher = dispatcher
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self._running = False
        self._last_pong = 0.0

    async def run(self, subprotocol: str | None = None) -> None:
        """
        Run the WSX handler.

        Accepts the WebSocket, then processes messages until disconnect.

        Args:
            subprotocol: Optional subprotocol to accept
        """
        await self.websocket.accept(subprotocol=subprotocol)
        self._running = True

        try:
            if self.ping_interval:
                # Run receiver and ping loop concurrently
                await asyncio.gather(
                    self._receive_loop(),
                    self._ping_loop(),
                )
            else:
                await self._receive_loop()
        except WebSocketDisconnect:
            pass
        finally:
            self._running = False

    async def _receive_loop(self) -> None:
        """Main receive loop."""
        async for message in self.websocket:
            if isinstance(message, str):
                await self._handle_text(message)
            elif isinstance(message, bytes):
                await self._handle_bytes(message)

    async def _handle_text(self, text: str) -> None:
        """Handle incoming text message."""
        import json

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            await self._send_error(None, "PARSE_ERROR", f"Invalid JSON: {e}")
            return

        await self._dispatch_and_respond(data)

    async def _handle_bytes(self, data: bytes) -> None:
        """Handle incoming binary message."""
        import json

        try:
            text = data.decode("utf-8")
            parsed = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            await self._send_error(None, "PARSE_ERROR", f"Invalid message: {e}")
            return

        await self._dispatch_and_respond(parsed)

    async def _dispatch_and_respond(self, data: dict[str, Any]) -> None:
        """Dispatch message and send response if any."""
        # Track pong for keepalive
        if data.get("type") == "rpc.pong":
            self._last_pong = asyncio.get_event_loop().time()
            return

        response = await self.dispatcher.dispatch(data)

        if response is not None:
            await self.websocket.send_json(response.to_dict())

    async def _send_error(
        self, msg_id: str | None, code: str, message: str
    ) -> None:
        """Send error response."""
        from .types import WSXError

        error = WSXError(id=msg_id, code=code, message=message)
        await self.websocket.send_json(error.to_dict())

    async def _ping_loop(self) -> None:
        """Ping loop for keepalive."""
        while self._running:
            await asyncio.sleep(self.ping_interval or 30.0)

            if not self._running:
                break

            # Send ping
            await self.websocket.send_json({"type": "rpc.ping"})

    async def send_event(
        self, channel: str, payload: Any, meta: dict[str, Any] | None = None
    ) -> None:
        """
        Send an event to the client.

        Args:
            channel: Event channel name
            payload: Event data
            meta: Optional metadata
        """
        from .types import WSXEvent

        event = WSXEvent(channel=channel, payload=payload, meta=meta or {})
        await self.websocket.send_json(event.to_dict())

    async def send_notify(
        self, event: str, payload: Any, meta: dict[str, Any] | None = None
    ) -> None:
        """
        Send a notification to the client.

        Args:
            event: Event name
            payload: Event data
            meta: Optional metadata
        """
        from .types import WSXNotify

        notify = WSXNotify(event=event, payload=payload, meta=meta or {})
        await self.websocket.send_json(notify.to_dict())

    async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the WebSocket connection.

        Args:
            code: Close code
            reason: Close reason
        """
        self._running = False
        await self.websocket.close(code=code, reason=reason)


def create_wsx_handler(
    dispatcher: WSXDispatcher,
    **kwargs: Any,
) -> "WSXHandlerFactory":
    """
    Create a WSX handler factory.

    Returns a callable that creates WSXHandler instances for each connection.

    Example:
        dispatcher = WSXDispatcher(router=router)
        ws_handler = create_wsx_handler(dispatcher)

        app = App(
            handler=http_handler,
            websocket_handler=ws_handler,
        )
    """
    async def handler(websocket: WebSocket) -> None:
        wsx = WSXHandler(websocket, dispatcher, **kwargs)
        await wsx.run()

    return handler


# Type alias for clarity
WSXHandlerFactory = Any  # Actually Callable[[WebSocket], Awaitable[None]]
```

## Tests: `tests/test_wsx_handler.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for WSX handler."""

import asyncio
import json

import pytest
from genro_asgi.websockets import WebSocket, WebSocketState
from genro_asgi.wsx import WSXDispatcher
from genro_asgi.wsx.handler import WSXHandler, create_wsx_handler


class MockTransport:
    """Mock WebSocket transport for testing."""

    def __init__(self, messages: list[dict] | None = None):
        self.incoming = [json.dumps(m) for m in (messages or [])]
        self.outgoing: list[dict] = []
        self._accepted = False

    async def receive(self) -> dict:
        if not self.incoming:
            return {"type": "websocket.disconnect", "code": 1000}
        return {"type": "websocket.receive", "text": self.incoming.pop(0)}

    async def send(self, message: dict) -> None:
        if message["type"] == "websocket.accept":
            self._accepted = True
        elif message["type"] == "websocket.send":
            if "text" in message:
                self.outgoing.append(json.loads(message["text"]))


def make_websocket(messages: list[dict] | None = None) -> tuple[WebSocket, MockTransport]:
    """Create WebSocket with mock transport."""
    transport = MockTransport(messages)
    scope = {
        "type": "websocket",
        "path": "/ws",
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "subprotocols": [],
    }
    ws = WebSocket(scope, transport.receive, transport.send)
    return ws, transport


class TestWSXHandler:
    @pytest.mark.asyncio
    async def test_basic_rpc(self):
        dispatcher = WSXDispatcher()

        @dispatcher.method("echo")
        async def echo(message: str):
            return {"echo": message}

        ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "echo", "params": {"message": "hello"}}
        ])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

        assert len(transport.outgoing) == 1
        assert transport.outgoing[0]["type"] == "rpc.response"
        assert transport.outgoing[0]["result"] == {"echo": "hello"}

    @pytest.mark.asyncio
    async def test_multiple_requests(self):
        dispatcher = WSXDispatcher()

        @dispatcher.method("add")
        async def add(a: int, b: int):
            return a + b

        ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "add", "params": {"a": 1, "b": 2}},
            {"type": "rpc.request", "id": "2", "method": "add", "params": {"a": 10, "b": 20}},
        ])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

        assert len(transport.outgoing) == 2
        assert transport.outgoing[0]["result"] == 3
        assert transport.outgoing[1]["result"] == 30

    @pytest.mark.asyncio
    async def test_method_not_found(self):
        dispatcher = WSXDispatcher()

        ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "nonexistent", "params": {}}
        ])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

        assert transport.outgoing[0]["type"] == "rpc.error"
        assert transport.outgoing[0]["error"]["code"] == "METHOD_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        transport = MockTransport()
        transport.incoming = ["not valid json"]

        scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"",
            "headers": [],
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 50000),
            "root_path": "",
            "subprotocols": [],
        }
        ws = WebSocket(scope, transport.receive, transport.send)

        dispatcher = WSXDispatcher()
        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

        assert transport.outgoing[0]["type"] == "rpc.error"
        assert transport.outgoing[0]["error"]["code"] == "PARSE_ERROR"

    @pytest.mark.asyncio
    async def test_notification_no_response(self):
        dispatcher = WSXDispatcher()
        notifications = []

        @dispatcher.on_notify
        async def handle(notify):
            notifications.append(notify)

        ws, transport = make_websocket([
            {"type": "rpc.notify", "method": "log", "params": {"level": "info"}}
        ])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

        # Notifications don't generate responses
        assert len(transport.outgoing) == 0
        assert len(notifications) == 1

    @pytest.mark.asyncio
    async def test_ping_pong(self):
        dispatcher = WSXDispatcher()

        ws, transport = make_websocket([
            {"type": "rpc.ping"}
        ])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

        assert transport.outgoing[0]["type"] == "rpc.pong"

    @pytest.mark.asyncio
    async def test_send_event(self):
        dispatcher = WSXDispatcher()

        ws, transport = make_websocket([])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)

        # Accept manually for this test
        await ws.accept()

        await handler.send_event("user.created", {"id": 1, "name": "John"})

        assert transport.outgoing[0]["type"] == "rpc.event"
        assert transport.outgoing[0]["channel"] == "user.created"
        assert transport.outgoing[0]["payload"] == {"id": 1, "name": "John"}

    @pytest.mark.asyncio
    async def test_send_notify(self):
        dispatcher = WSXDispatcher()

        ws, transport = make_websocket([])

        handler = WSXHandler(ws, dispatcher, ping_interval=None)

        await ws.accept()

        await handler.send_notify("status.changed", {"status": "online"})

        assert transport.outgoing[0]["type"] == "rpc.notify"
        assert transport.outgoing[0]["event"] == "status.changed"


class TestCreateWSXHandler:
    @pytest.mark.asyncio
    async def test_factory(self):
        dispatcher = WSXDispatcher()

        @dispatcher.method("test")
        async def test_method():
            return "ok"

        handler_func = create_wsx_handler(dispatcher, ping_interval=None)

        ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "test", "params": {}}
        ])

        await handler_func(ws)

        assert transport.outgoing[0]["result"] == "ok"
```

## Checklist

- [ ] Create `src/genro_asgi/wsx/handler.py`
- [ ] Create `tests/test_wsx_handler.py`
- [ ] Run `pytest tests/test_wsx_handler.py`
- [ ] Run `mypy src/genro_asgi/wsx/handler.py`
- [ ] Update `wsx/__init__.py` exports
- [ ] Commit
