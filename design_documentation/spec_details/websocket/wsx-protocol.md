# WSX Protocol

WebSocket eXtended - RPC transport-agnostic con semantica HTTP.

## Overview

WSX porta la semantica HTTP sopra WebSocket, permettendo handler unificati.

```
HTTP Request  ─────┐
                   │
WebSocket RPC ─────┼──► BaseRequest ──► Handler ──► BaseResponse
                   │
NATS Message  ─────┘  (futuro)
```

## Formato Messaggio

Prefisso `WSX://` seguito da JSON:

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

### WSX Response

```json
WSX://{
    "id": "uuid-123",
    "status": 200,
    "headers": {
        "content-type": "application/json"
    },
    "data": {
        "id": "42::L",
        "created": "2025-12-02T10:30:00+01:00::DHZ"
    }
}
```

## Campi Request

| Campo | Tipo | Required | Descrizione |
|-------|------|----------|-------------|
| `id` | string | Sì | Correlation ID |
| `method` | string | Sì | HTTP method |
| `path` | string | Sì | Routing path |
| `headers` | object | No | HTTP headers |
| `cookies` | object | No | Cookies |
| `query` | object | No | Query params (TYTX) |
| `data` | any | No | Payload (TYTX) |

## Campi Response

| Campo | Tipo | Required | Descrizione |
|-------|------|----------|-------------|
| `id` | string | Sì | Stesso della request |
| `status` | int | Sì | HTTP status code |
| `headers` | object | No | Response headers |
| `cookies` | object | No | Set-Cookie equivalents |
| `data` | any | No | Response payload |

## TYTX Integration

Tipi preservati attraverso il trasporto:

```
"price": "99.50::N"     → Decimal("99.50")
"date": "2025-01-15::D" → date(2025, 1, 15)
"count": "42::L"        → int
"active": "true::B"     → bool
```

## Streaming

Per risposte streaming:

- Multiple WSX response con stesso `id`
- `"stream": true` indica altri messaggi in arrivo
- `"stream": false` o assente indica messaggio finale

## Funzioni Implementate

```python
WSX_PREFIX = "WSX://"

def is_wsx_message(data: str) -> bool:
    """Check if message is WSX format."""

def parse_wsx_message(data: str) -> dict:
    """Parse WSX message to dict."""

def build_wsx_message(data: dict) -> str:
    """Build WSX message from dict."""

def build_wsx_response(id: str, status: int, data: Any = None) -> str:
    """Build WSX response message."""
```

## Stato Implementazione

| Componente | Stato |
|------------|-------|
| `WSX_PREFIX`, `is_wsx_message()` | ✅ |
| `parse_wsx_message()` | ✅ |
| `build_wsx_message()` | ✅ |
| `build_wsx_response()` | ✅ |
| `MsgRequest` (WebSocket) | ✅ |
| Classi WsxRequest/WsxResponse | ❌ Planned |
| NATS integration | ❌ Future |
