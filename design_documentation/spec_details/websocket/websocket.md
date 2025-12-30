# WebSocket

Wrapper per connessioni WebSocket ASGI.

## WebSocketState

```python
class WebSocketState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2
```

## Classe WebSocket

```python
class WebSocket:
    __slots__ = ("_scope", "_receive", "_send", "_state",
                 "_headers", "_query_params", "_url", "_client_state")

    def __init__(self, scope: Scope, receive: Receive, send: Send): ...
```

## Properties

| Property | Tipo | Descrizione |
|----------|------|-------------|
| `scope` | Scope | ASGI scope |
| `url` | URL | WebSocket URL |
| `headers` | Headers | Connection headers |
| `query_params` | QueryParams | Query string |
| `path` | str | Request path |
| `subprotocols` | list[str] | Requested subprotocols |
| `state` | State | Custom data storage |
| `connection_state` | WebSocketState | Connection state |

## Metodi

```python
async def accept(
    self,
    subprotocol: str | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
    """Accept connection. Must call before send/receive."""

async def receive_text() -> str:
    """Receive text message. Converts bytes to UTF-8 if needed."""

async def receive_bytes() -> bytes:
    """Receive binary message."""

async def receive_json() -> Any:
    """Receive and parse JSON message."""

async def send_text(data: str) -> None:
    """Send text message."""

async def send_bytes(data: bytes) -> None:
    """Send binary message."""

async def send_json(data: Any) -> None:
    """Send JSON message."""

async def close(code: int = 1000, reason: str = "") -> None:
    """Close connection (idempotent)."""
```

## Async Iterator

```python
async for message in websocket:
    # message: str | bytes
    ...
```

Itera fino a disconnect.

## Decisioni

| Aspetto | Decisione |
|---------|-----------|
| Nome file | `websocket.py` (singolare) |
| State naming | `state` (user) vs `connection_state` (ws) |
| receive_text fallback | Sì, converte bytes→text se necessario |
| receive_json errors | Propaga ValueError/JSONDecodeError |
| send() method | Nome OK (wrappa _send interno) |
| __aiter__ type | `str \| bytes` union |
| close() | Idempotente |
| accept() headers | Format ASGI `list[tuple[bytes, bytes]]` |

## Esempio

```python
async def websocket_handler(websocket: WebSocket):
    await websocket.accept()
    try:
        async for message in websocket:
            if isinstance(message, str):
                await websocket.send_text(f"Echo: {message}")
    finally:
        await websocket.close()
```
