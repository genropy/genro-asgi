# genro-asgi Architecture Overview

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## What is genro-asgi

genro-asgi is a minimal ASGI framework that provides:

- **AsgiServer**: Root dispatcher with multi-app mount and optional routing
- **Request System**: Transport-agnostic request handling (HTTP, WebSocket, future NATS)
- **Response System**: HTTP response classes (JSON, HTML, File, Streaming)
- **Executors**: Process/thread pools for blocking and CPU-bound work
- **WSX Protocol**: RPC message format over WebSocket

---

## Core Principles

### 1. Request-Centric Architecture

Every incoming request:
1. Gets a unique `id` (correlation ID)
2. Is registered in `RequestRegistry`
3. Is processed by handlers
4. Is unregistered on completion

```
Request In --> Registry --> Handler --> Response Out --> Unregister
```

### 2. Transport Agnostic

Handlers receive `BaseRequest`, work identically with HTTP or WebSocket:

```python
async def get_user(request: BaseRequest) -> dict:
    user_id = request.path.split("/")[-1]
    return {"id": user_id, "name": "Mario"}
```

### 3. Zero External Dependencies

Only Python stdlib. Optional `orjson` for faster JSON.

### 4. Starlette-Compatible API

Familiar API for developers coming from Starlette/FastAPI.

---

## Module Structure

```
src/genro_asgi/
├── __init__.py           # Public exports
├── types.py              # ASGI type definitions
├── exceptions.py         # HTTPException, WebSocketException
├── request.py            # BaseRequest, HttpRequest, WsRequest, RequestRegistry
├── response.py           # Response, JSONResponse, HTMLResponse, etc.
├── websocket.py          # WebSocket connection wrapper
├── server.py             # AsgiServer
├── lifespan.py           # ServerLifespan
├── binder.py             # ServerBinder, AsgiServerEnabler
├── datastructures/       # Headers, URL, QueryParams, State
├── executors/            # Process/thread pool execution
└── wsx/                  # WSX protocol (message format only)
```

---

## Architecture Documents

| Document | Description |
|----------|-------------|
| [01-server.md](01-server.md) | AsgiServer, routing, mount, dispatch |
| [02-request-system.md](02-request-system.md) | BaseRequest, HttpRequest, WsRequest, RequestRegistry |
| [03-response-system.md](03-response-system.md) | Response classes |
| [04-executors.md](04-executors.md) | Blocking/CPU task execution |
| [05-lifespan.md](05-lifespan.md) | Startup/shutdown lifecycle |
| [06-wsx-protocol.md](06-wsx-protocol.md) | WSX message format |
| [07-streaming.md](07-streaming.md) | Streaming and protections |

---

## Quick Start

```python
from genro_asgi import AsgiServer, JSONResponse
from genro_routes import route

class MyServer(AsgiServer):
    def __init__(self):
        super().__init__(use_router=True)

    @route("root")
    def index(self):
        return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    server = MyServer()
    server.run(host="127.0.0.1", port=8000)
```

---

## Key Design Decisions

### No Envelope Abstraction

Previous design had `RequestEnvelope`/`ResponseEnvelope` wrappers.
Now requests ARE the trackable unit - no wrapper needed.

| Old | New |
|-----|-----|
| `RequestEnvelope` | `BaseRequest` subclasses |
| `EnvelopeRegistry` | `RequestRegistry` |

### Single request.py Module

All request classes in one file (like `response.py` has all response classes).

### WSX is Protocol Only

The `wsx/` directory contains only WSX **message format** code.
Request handling uses `WsRequest(BaseRequest)` from `request.py`.

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
