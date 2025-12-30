## Source: initial_implementation_plan/archive/06-websockets.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types, 02-datastructures, 03-exceptions
**Commit message**: `feat(websockets): add WebSocket transport class`

WebSocket transport class for handling WebSocket connections.
This is the foundation for genro-wsx protocol.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WebSocket transport class."""

import json
from enum import Enum
from typing import Any, AsyncIterator

from .datastructures import Address, Headers, QueryParams, State, URL
from .exceptions import WebSocketDisconnect, WebSocketException
from .types import Message, Receive, Scope, Send

# Optional fast JSON
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

class WebSocketState(Enum):
    """WebSocket connection state."""
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2

class WebSocket:
    """
    WebSocket connection wrapper.

Provides high-level interface for WebSocket communication.

Example:
        async def ws_handler(websocket: WebSocket):
            await websocket.accept()
            async for message in websocket:
                await websocket.send_text(f"Echo: {message}")
    """

__slots__ = (
        "_scope",
        "_receive",
        "_send",
        "_state",
        "_headers",
        "_query_params",
        "_url",
        "_client_state",
    )

def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Initialize WebSocket from ASGI scope, receive, and send.

Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        self._scope = scope
        self._receive = receive
        self._send = send
        self._state = WebSocketState.CONNECTING
        self._headers: Headers | None = None
        self._query_params: QueryParams | None = None
        self._url: URL | None = None
        self._client_state: State | None = None

@property
    def scope(self) -> Scope:
        """Raw ASGI scope."""
        return self._scope

@property
    def state(self) -> State:
        """Connection state for storing custom data."""
        if self._client_state is None:
            self._client_state = State()
        return self._client_state

@property
    def headers(self) -> Headers:
        """Request headers."""
        if self._headers is None:
            self._headers = Headers(scope=self._scope)
        return self._headers

@property
    def query_params(self) -> QueryParams:
        """Query string parameters."""
        if self._query_params is None:
            self._query_params = QueryParams(scope=self._scope)
        return self._query_params

@property
    def url(self) -> URL:
        """WebSocket URL."""
        if self._url is None:
            scheme = self._scope.get("scheme", "ws")
            server = self._scope.get("server")
            path = self._scope.get("root_path", "") + self._scope.get("path", "/")
            query_string = self._scope.get("query_string", b"")

if server:
                host, port = server
                if (scheme == "ws" and port == 80) or (scheme == "wss" and port == 443):
                    netloc = host
                else:
                    netloc = f"{host}:{port}"
            else:
                netloc = self.headers.get("host", "localhost")

url_str = f"{scheme}://{netloc}{path}"
            if query_string:
                url_str += f"?{query_string.decode('latin-1')}"

self._url = URL(url_str)
        return self._url

@property
    def path(self) -> str:
        """Request path."""
        return self._scope.get("path", "/")

@property
    def client(self) -> Address | None:
        """Client address (host, port) if available."""
        client = self._scope.get("client")
        if client:
            return Address(client[0], client[1])
        return None

@property
    def subprotocols(self) -> list[str]:
        """Requested subprotocols."""
        return self._scope.get("subprotocols", [])

@property
    def connection_state(self) -> WebSocketState:
        """Current connection state."""
        return self._state

async def accept(
        self,
        subprotocol: str | None = None,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        """
        Accept the WebSocket connection.

Args:
            subprotocol: Selected subprotocol (from client's list)
            headers: Additional response headers

Raises:
            RuntimeError: If connection is not in CONNECTING state
        """
        if self._state != WebSocketState.CONNECTING:
            raise RuntimeError(
                f"Cannot accept connection in state {self._state.name}"
            )

message: Message = {
            "type": "websocket.accept",
        }
        if subprotocol:
            message["subprotocol"] = subprotocol
        if headers:
            message["headers"] = headers

await self._send(message)
        self._state = WebSocketState.CONNECTED

async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the WebSocket connection.

Args:
            code: WebSocket close code (1000-4999)
            reason: Close reason message
        """
        if self._state == WebSocketState.DISCONNECTED:
            return

await self._send({
            "type": "websocket.close",
            "code": code,
            "reason": reason,
        })
        self._state = WebSocketState.DISCONNECTED

async def receive(self) -> Message:
        """
        Receive raw ASGI message.

Returns:
            ASGI message dict

Raises:
            WebSocketDisconnect: If client disconnected
        """
        if self._state == WebSocketState.DISCONNECTED:
            raise WebSocketDisconnect()

message = await self._receive()

if message["type"] == "websocket.disconnect":
            self._state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(
                code=message.get("code", 1000),
                reason=message.get("reason", ""),
            )

async def receive_text(self) -> str:
        """
        Receive text message.

Returns:
            Text message content

Raises:
            WebSocketDisconnect: If client disconnected
            RuntimeError: If message is not text
        """
        message = await self.receive()
        if message["type"] != "websocket.receive":
            raise RuntimeError(f"Unexpected message type: {message['type']}")
        if "text" in message:
            return message["text"]
        if "bytes" in message:
            return message["bytes"].decode("utf-8")
        raise RuntimeError("Message has no text or bytes content")

async def receive_bytes(self) -> bytes:
        """
        Receive binary message.

Returns:
            Binary message content

Raises:
            WebSocketDisconnect: If client disconnected
            RuntimeError: If message is not binary
        """
        message = await self.receive()
        if message["type"] != "websocket.receive":
            raise RuntimeError(f"Unexpected message type: {message['type']}")
        if "bytes" in message:
            return message["bytes"]
        if "text" in message:
            return message["text"].encode("utf-8")
        raise RuntimeError("Message has no text or bytes content")

async def receive_json(self) -> Any:
        """
        Receive and parse JSON message.

Returns:
            Parsed JSON data

Raises:
            WebSocketDisconnect: If client disconnected
            ValueError: If message is not valid JSON
        """
        text = await self.receive_text()
        if HAS_ORJSON:
            return orjson.loads(text)
        return json.loads(text)

async def send(self, message: Message) -> None:
        """
        Send raw ASGI message.

Args:
            message: ASGI message dict
        """
        if self._state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"Cannot send in state {self._state.name}"
            )
        await self._send(message)

async def send_text(self, data: str) -> None:
        """
        Send text message.

Args:
            data: Text content to send
        """
        await self.send({
            "type": "websocket.send",
            "text": data,
        })

async def send_bytes(self, data: bytes) -> None:
        """
        Send binary message.

Args:
            data: Binary content to send
        """
        await self.send({
            "type": "websocket.send",
            "bytes": data,
        })

async def send_json(self, data: Any) -> None:
        """
        Send JSON message.

Args:
            data: Python object to serialize and send
        """
        if HAS_ORJSON:
            text = orjson.dumps(data).decode("utf-8")
        else:
            text = json.dumps(data, ensure_ascii=False)
        await self.send_text(text)

async def __aiter__(self) -> AsyncIterator[str | bytes]:
        """
        Iterate over incoming messages.

Yields text or bytes depending on message type.
        Stops when connection is closed.

Example:
            async for message in websocket:
                print(f"Received: {message}")
        """
        while True:
            try:
                message = await self.receive()
                if message["type"] == "websocket.receive":
                    if "text" in message:
                        yield message["text"]
                    elif "bytes" in message:
                        yield message["bytes"]
            except WebSocketDisconnect:
                break

def __repr__(self) -> str:
        return f"WebSocket(path={self.path!r}, state={self._state.name})"
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for WebSocket class."""

import pytest
from genro_asgi.exceptions import WebSocketDisconnect
from genro_asgi.websockets import WebSocket, WebSocketState

def make_scope(
    path: str = "/ws",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    subprotocols: list[str] | None = None,
    server: tuple[str, int] | None = ("localhost", 8000),
    client: tuple[str, int] | None = ("127.0.0.1", 50000),
) -> dict:
    """Create a mock WebSocket ASGI scope."""
    return {
        "type": "websocket",
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "subprotocols": subprotocols or [],
        "scheme": "ws",
        "server": server,
        "client": client,
        "root_path": "",
    }

class MockTransport:
    """Mock receive/send for testing."""

def __init__(self, messages: list[dict] | None = None):
        self.incoming = messages or []
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        if not self.incoming:
            return {"type": "websocket.disconnect", "code": 1000}
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

class TestWebSocketProperties:
    def test_path(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(path="/chat"), transport.receive, transport.send)
        assert ws.path == "/chat"

def test_query_params(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(query_string=b"room=general"),
            transport.receive,
            transport.send,
        )
        assert ws.query_params.get("room") == "general"

def test_headers(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(headers=[(b"authorization", b"Bearer token")]),
            transport.receive,
            transport.send,
        )
        assert ws.headers.get("authorization") == "Bearer token"

def test_client(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(client=("192.168.1.1", 12345)),
            transport.receive,
            transport.send,
        )
        assert ws.client is not None
        assert ws.client.host == "192.168.1.1"

def test_subprotocols(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(subprotocols=["graphql-ws", "subscriptions-transport-ws"]),
            transport.receive,
            transport.send,
        )
        assert "graphql-ws" in ws.subprotocols

def test_url(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(path="/ws", query_string=b"token=abc"),
            transport.receive,
            transport.send,
        )
        assert "/ws" in str(ws.url)
        assert "token=abc" in str(ws.url)

def test_state(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        ws.state.user_id = 123
        assert ws.state.user_id == 123

def test_initial_state(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        assert ws.connection_state == WebSocketState.CONNECTING

class TestWebSocketAccept:
    @pytest.mark.asyncio
    async def test_accept(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

assert ws.connection_state == WebSocketState.CONNECTED
        assert transport.outgoing[0]["type"] == "websocket.accept"

@pytest.mark.asyncio
    async def test_accept_with_subprotocol(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept(subprotocol="graphql-ws")

assert transport.outgoing[0]["subprotocol"] == "graphql-ws"

@pytest.mark.asyncio
    async def test_accept_twice_raises(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

with pytest.raises(RuntimeError):
            await ws.accept()

class TestWebSocketClose:
    @pytest.mark.asyncio
    async def test_close(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.close(code=1000, reason="Normal closure")

assert ws.connection_state == WebSocketState.DISCONNECTED
        close_msg = transport.outgoing[-1]
        assert close_msg["type"] == "websocket.close"
        assert close_msg["code"] == 1000

@pytest.mark.asyncio
    async def test_close_idempotent(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.close()
        await ws.close()  # Should not raise

class TestWebSocketReceive:
    @pytest.mark.asyncio
    async def test_receive_text(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": "hello"}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

text = await ws.receive_text()
        assert text == "hello"

@pytest.mark.asyncio
    async def test_receive_bytes(self):
        transport = MockTransport([
            {"type": "websocket.receive", "bytes": b"\x00\x01\x02"}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

data = await ws.receive_bytes()
        assert data == b"\x00\x01\x02"

@pytest.mark.asyncio
    async def test_receive_json(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": '{"key": "value"}'}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

data = await ws.receive_json()
        assert data == {"key": "value"}

@pytest.mark.asyncio
    async def test_receive_disconnect(self):
        transport = MockTransport([
            {"type": "websocket.disconnect", "code": 1001}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_text()
        assert exc_info.value.code == 1001

class TestWebSocketSend:
    @pytest.mark.asyncio
    async def test_send_text(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.send_text("hello")

msg = transport.outgoing[-1]
        assert msg["type"] == "websocket.send"
        assert msg["text"] == "hello"

@pytest.mark.asyncio
    async def test_send_bytes(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.send_bytes(b"\x00\x01\x02")

msg = transport.outgoing[-1]
        assert msg["bytes"] == b"\x00\x01\x02"

@pytest.mark.asyncio
    async def test_send_json(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.send_json({"key": "value"})

msg = transport.outgoing[-1]
        assert "key" in msg["text"]

@pytest.mark.asyncio
    async def test_send_before_accept_raises(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)

with pytest.raises(RuntimeError):
            await ws.send_text("hello")

class TestWebSocketIteration:
    @pytest.mark.asyncio
    async def test_iterate(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": "msg1"},
            {"type": "websocket.receive", "text": "msg2"},
            {"type": "websocket.receive", "text": "msg3"},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

messages = []
        async for msg in ws:
            messages.append(msg)

assert messages == ["msg1", "msg2", "msg3"]

@pytest.mark.asyncio
    async def test_iterate_mixed(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": "text"},
            {"type": "websocket.receive", "bytes": b"bytes"},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

messages = []
        async for msg in ws:
            messages.append(msg)

assert messages == ["text", b"bytes"]

class TestWebSocketRepr:
    def test_repr(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(path="/chat"), transport.receive, transport.send)
        r = repr(ws)
        assert "/chat" in r
        assert "CONNECTING" in r
```

```python
from .websockets import WebSocket, WebSocketState
```

- [ ] Create `src/genro_asgi/websockets.py`
- [ ] Create `tests/test_websockets.py`
- [ ] Run `pytest tests/test_websockets.py`
- [ ] Run `mypy src/genro_asgi/websockets.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

