# Streaming & Protections

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## Overview

Streaming endpoints have different characteristics than RPC/REST:

- **High throughput**: File uploads/downloads, telemetry
- **Long-lived connections**: WebSocket streams
- **Minimal processing**: Direct I/O, no heavy middleware

---

## Workload Separation

| Type | Characteristics | Paths |
|------|-----------------|-------|
| **Business Logic** | Complex, auth, DB, validation | `/api/*`, `/ws/rpc/*` |
| **Streaming** | High throughput, minimal processing | `/stream/*`, `/ws/raw/*` |

Streaming apps should be mounted separately:

```python
server = AsgiServer()
server.mount("/api", BusinessApp())      # Full middleware
server.mount("/stream", StreamingApp())  # Minimal middleware
```

---

## Streaming Protections

### Protection Matrix

| Protection | HTTP Upload | HTTP Download | WebSocket |
|------------|-------------|---------------|-----------|
| **Max body size** | Configurable | N/A | Per-message limit |
| **Timeout** | Read timeout | Send timeout | Idle timeout |
| **Rate limit** | Requests/sec | Bandwidth | Messages/sec |
| **Connection limit** | Per-IP | Per-IP | Per-user |

### Configuration Example

```python
streaming_app = StreamingApp(
    # Upload limits
    max_upload_size=100 * 1024 * 1024,  # 100MB
    upload_timeout=300,                  # 5 min

    # Download limits
    download_timeout=600,                # 10 min
    chunk_size=64 * 1024,                # 64KB chunks

    # WebSocket limits
    ws_max_message_size=1 * 1024 * 1024, # 1MB per message
    ws_idle_timeout=60,                  # 60s idle disconnect
    ws_max_connections_per_user=10,

    # Rate limiting
    rate_limit_requests=100,             # per minute
    rate_limit_bandwidth=10 * 1024 * 1024,  # 10MB/s
)
```

---

## DoS Protections

### Slowloris Attack

**Attack**: Client sends data very slowly to exhaust connections.

**Protection**: Read timeout kills slow-sending clients.

```python
async def receive_body(receive, timeout=30):
    body = []
    while True:
        try:
            message = await asyncio.wait_for(receive(), timeout=timeout)
        except asyncio.TimeoutError:
            raise HTTPException(408, "Request Timeout")

        body.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(body)
```

### Large Payload Attack

**Attack**: Client sends huge payload to exhaust memory.

**Protection**: Max body size enforced before processing.

```python
async def receive_body_limited(receive, max_size=10 * 1024 * 1024):
    body = []
    total = 0
    while True:
        message = await receive()
        chunk = message.get("body", b"")
        total += len(chunk)
        if total > max_size:
            raise HTTPException(413, "Payload Too Large")
        body.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(body)
```

### Connection Exhaustion

**Attack**: Client opens many connections to exhaust server resources.

**Protection**: Per-IP/per-user connection limits.

```python
class ConnectionLimiter:
    def __init__(self, max_per_ip=100):
        self.max_per_ip = max_per_ip
        self._connections: dict[str, int] = {}

    def acquire(self, client_ip: str) -> bool:
        count = self._connections.get(client_ip, 0)
        if count >= self.max_per_ip:
            return False
        self._connections[client_ip] = count + 1
        return True

    def release(self, client_ip: str) -> None:
        if client_ip in self._connections:
            self._connections[client_ip] -= 1
            if self._connections[client_ip] <= 0:
                del self._connections[client_ip]
```

### Bandwidth Abuse

**Attack**: Client downloads at maximum speed to exhaust bandwidth.

**Protection**: Rate limiting on throughput.

```python
class BandwidthLimiter:
    def __init__(self, bytes_per_second=10 * 1024 * 1024):
        self.bps = bytes_per_second
        self._last_check = time.monotonic()
        self._bytes_sent = 0

    async def throttle(self, chunk_size: int) -> None:
        self._bytes_sent += chunk_size
        elapsed = time.monotonic() - self._last_check

        if elapsed >= 1.0:
            self._bytes_sent = chunk_size
            self._last_check = time.monotonic()
        elif self._bytes_sent > self.bps:
            sleep_time = 1.0 - elapsed
            await asyncio.sleep(sleep_time)
            self._bytes_sent = 0
            self._last_check = time.monotonic()
```

---

## StreamingResponse

For generating streaming responses:

```python
async def generate_report():
    for i in range(1000):
        yield f"Line {i}\n".encode()
        await asyncio.sleep(0.01)

response = StreamingResponse(
    generate_report(),
    media_type="text/plain",
)
```

---

## FileResponse

For file downloads with proper streaming:

```python
response = FileResponse(
    path="/data/large_file.zip",
    filename="download.zip",
    media_type="application/zip",
)
```

Features:
- Async file reading
- Chunked transfer
- Content-Length header
- Content-Disposition header

---

## WebSocket Streaming

### Fire-and-Forget (Telemetry In)

```python
async def telemetry_handler(websocket: WebSocket):
    await websocket.accept()
    async for message in websocket:
        # Process without response
        await process_telemetry(message)
```

### Notifications (Fire-and-Forget Out)

```python
async def notification_handler(websocket: WebSocket):
    await websocket.accept()
    async for event in event_stream:
        await websocket.send_json(event)
```

### Idle Timeout

```python
async def ws_handler(websocket: WebSocket, idle_timeout=60):
    await websocket.accept()
    while True:
        try:
            message = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=idle_timeout,
            )
            await process(message)
        except asyncio.TimeoutError:
            await websocket.close(code=1000, reason="Idle timeout")
            break
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  AsgiServer                                                     │
│                                                                 │
│  ┌───────────────────────────────────────────────┐              │
│  │ /api/* (Business App)                         │              │
│  │ AuthMW → ValidationMW → RequestRegistry       │              │
│  │ (Full middleware, request tracking)           │              │
│  └───────────────────────────────────────────────┘              │
│                                                                 │
│  ┌───────────────────────────────────────────────┐              │
│  │ /stream/* (Streaming App)                     │              │
│  │ ConnectionLimiter → BandwidthLimiter          │              │
│  │ (Minimal middleware, direct I/O)              │              │
│  └───────────────────────────────────────────────┘              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Benefits

1. **Performance**: Heavy logic doesn't slow streaming
2. **Isolation**: Streaming issues don't impact business logic
3. **Flexibility**: Different configs per workload
4. **Security**: Appropriate protections per endpoint type

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
