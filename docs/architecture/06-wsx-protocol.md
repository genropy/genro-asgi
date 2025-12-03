# WSX Protocol

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## Overview

WSX (WebSocket eXtended) is a **message format** for RPC over WebSocket and NATS.
It brings HTTP-like semantics to message-based transports.

**Important**: WSX is a protocol/format specification.
Request handling uses `WsRequest(BaseRequest)` from `request.py`.

---

## Motivation

Different transports have different APIs:

- **HTTP**: method, path, headers, cookies, query, body
- **WebSocket**: just binary/text messages
- **NATS**: subject, payload bytes, reply-to

WSX defines a message format that encapsulates HTTP-like semantics:

```
HTTP Request  ─────┐
                   │
WebSocket RPC ─────┼──► BaseRequest ──► Handler ──► BaseResponse
                   │
NATS Message  ─────┘
```

---

## Message Format

### Prefix

WSX messages start with `WSX://` followed by JSON:

```
WSX://{"id":"...","method":"...","path":"...","headers":{},"data":{}}
```

### WSX Request

```json
WSX://{
    "id": "uuid-123",
    "method": "POST",
    "path": "/users/42",
    "headers": {
        "content-type": "application/json",
        "authorization": "Bearer xxx"
    },
    "cookies": {
        "session_id": "xyz-789"
    },
    "query": {
        "limit": "10::L",
        "active": "true::B"
    },
    "data": {
        "name": "Mario",
        "birth": "1990-05-15::D"
    }
}
```

#### Request Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Correlation ID |
| `method` | string | Yes | GET, POST, PUT, DELETE, PATCH |
| `path` | string | Yes | Routing path (e.g., "/users/42") |
| `headers` | object | No | HTTP headers as dict |
| `cookies` | object | No | Cookies as dict |
| `query` | object | No | Query parameters (TYTX supported) |
| `data` | any | No | Request payload (TYTX supported) |

### WSX Response

```json
WSX://{
    "id": "uuid-123",
    "status": 200,
    "headers": {
        "content-type": "application/json",
        "x-request-id": "trace-456"
    },
    "cookies": {
        "session_id": {
            "value": "new-xyz",
            "max_age": "3600::L",
            "httponly": "true::B"
        }
    },
    "data": {
        "id": "42::L",
        "message": "User created"
    }
}
```

#### Response Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Same correlation ID as request |
| `status` | int | Yes | HTTP status code (200, 404, 500, etc.) |
| `headers` | object | No | Response headers |
| `cookies` | object | No | Set-Cookie equivalents |
| `data` | any | No | Response payload |

---

## TYTX Integration

Values support TYTX type suffixes for type preservation:

```
"price": "99.50::N"     → Decimal("99.50")
"date": "2025-01-15::D" → date(2025, 1, 15)
"count": "42::L"        → 42 (int)
"active": "true::B"     → True (bool)
```

WSX parsing automatically hydrates these values.

---

## Transport Flow

### WebSocket (ASGI)

```
1. WebSocket receive() → text message
2. Detect WSX:// prefix
3. Parse JSON, hydrate TYTX values
4. Create WsRequest(BaseRequest)
5. Handler processes → result
6. WsResponse.send() → serialize WSX:// → WebSocket send()
```

### NATS (Future)

```
1. NATS subscribe callback → msg
2. msg.data contains WSX://...
3. Parse JSON, hydrate TYTX values
4. Create NatsRequest(BaseRequest)
5. Handler processes → result
6. NatsResponse.send() → serialize WSX:// → nc.publish(msg.reply, ...)
```

---

## Module Structure

The `wsx/` directory contains **protocol** code only:

```
src/genro_asgi/wsx/
├── __init__.py
├── protocol.py      # Parse/serialize WSX messages
└── handler.py       # Route WSX messages to handlers
```

**Request classes are in `request.py`**, not in `wsx/`.

---

## Protocol Parsing

```python
# wsx/protocol.py

WSX_PREFIX = "WSX://"

def parse_wsx_message(raw: str) -> dict[str, Any]:
    """
    Parse WSX message string.

    Args:
        raw: Raw message starting with WSX://

    Returns:
        Parsed message dict with hydrated TYTX values

    Raises:
        ValueError: If not a valid WSX message
    """
    if not raw.startswith(WSX_PREFIX):
        raise ValueError(f"Not a WSX message: {raw[:20]}")

    json_str = raw[len(WSX_PREFIX):]
    message = json.loads(json_str)

    # Hydrate TYTX values
    if "query" in message:
        message["query"] = hydrate_dict(message["query"])
    if "data" in message and isinstance(message["data"], dict):
        message["data"] = hydrate_dict(message["data"])

    return message


def serialize_wsx_response(
    request_id: str,
    status: int,
    data: Any,
    headers: dict[str, str] | None = None,
    cookies: dict[str, Any] | None = None,
) -> str:
    """
    Serialize response to WSX format.

    Returns:
        WSX:// prefixed JSON string
    """
    response = {
        "id": request_id,
        "status": status,
        "data": data,
    }
    if headers:
        response["headers"] = headers
    if cookies:
        response["cookies"] = cookies

    return WSX_PREFIX + json.dumps(response)
```

---

## Error Handling

Errors returned as response with status:

```json
WSX://{
    "id": "uuid-123",
    "status": 404,
    "data": {
        "error": "User not found",
        "code": "USER_NOT_FOUND"
    }
}
```

---

## Streaming

For streaming responses:
- Multiple WSX responses with same `id`
- `"stream": true` indicates more messages follow
- `"stream": false` or absent indicates final message

```json
WSX://{"id": "123", "status": 200, "data": {"chunk": 1}, "stream": true}
WSX://{"id": "123", "status": 200, "data": {"chunk": 2}, "stream": true}
WSX://{"id": "123", "status": 200, "data": {"chunk": 3}, "stream": false}
```

---

## Correlation ID

- **HTTP**: Generated by server or from `x-request-id` header
- **WebSocket**: Required in WSX message `id` field
- **NATS**: Uses native reply-to for routing, `id` for application tracing

---

## Transport-Agnostic Handler

```python
async def get_user(request: BaseRequest) -> dict:
    """Works with HTTP, WebSocket, or NATS."""
    user_id = request.path.split("/")[-1]
    auth = request.headers.get("authorization")
    session = request.cookies.get("session_id")

    user = await db.get_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        "transport": request.transport,  # "http", "websocket", or "nats"
    }
```

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
