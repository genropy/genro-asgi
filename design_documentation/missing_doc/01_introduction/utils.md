## Source: initial_implementation_plan/to-do/09-utils-01/09-utils-initial.md

**Purpose**: Define shared utilities for URL construction, TYTX hydration/serialization, and the RequestEnvelope pattern.
**Status**: IN DISCUSSION → DECISIONS MADE

- **URL**: Request and WebSocket duplicate URL construction logic from scope. A shared function avoids divergence and bugs.
- **TYTX**: The TYTX protocol requires hydration/serialization hooks. Centralize decode/encode logic and `::TYTX` marker handling.
- **Envelope**: Unified request/response tracking across HTTP and WebSocket transports.

### 1. URL Utility Location
**Decision**: New `utils.py` module

Rationale: More utilities will likely be needed in the future.

### 2. TYTX Auto-Declaration
**Decision**: Marker `::TYTX` at end of text is self-declaring

```
{"price": "100.50::D", "date": "2025-01-15::d"}::TYTX
```

- Receiver auto-detects: `if text.endswith("::TYTX")`
- Works on any text channel (WebSocket, HTTP body, query string)
- Backward compatible: JSON without marker is plain JSON

### 3. TYTX Symmetry Rule
**Decision**: If you receive `::TYTX`, respond with `::TYTX`

- `receive_json()` auto-detects marker, sets `tytx_mode=True` on envelope
- `send_json()` checks `tytx_mode`, appends marker if True
- Zero configuration, client declares protocol with first message

### 4. Behavior Without genro-tytx
**Decision**: Explicit `ImportError`

No silent degradation. If marker present but library missing, raise ImportError.

### 5. Request/Response Model
**Decision**: Everything is request/response with ack

| Type        | Request           | Response              |
|-------------|-------------------|-----------------------|
| RPC call    | method + params   | result                |
| Notify      | event + payload   | ack                   |
| Subscribe   | channel           | ack (subscription_id) |
| Unsubscribe | subscription_id   | ack                   |
| Server push | event + payload   | ack (from client)     |

No "fire and forget". Sender always expects ack. If not received → timeout → sender's problem.

### 6. Envelope Pattern
**Decision**: `RequestEnvelope` / `ResponseEnvelope`

Unified wrapper for HTTP and WebSocket:

```python
@dataclass
class RequestEnvelope:
    internal_id: str           # Server-generated, always present
    external_id: str | None    # Client-provided, optional (echoed back)
    tytx_mode: bool            # Detected from ::TYTX marker
    params: dict               # Already hydrated if TYTX
    metadata: dict             # Additional context
    created_at: float          # Timestamp

# Transport-specific (one of these)
    _http_request: Request | None
    _wsx_message: WSXMessage | None

@dataclass
class ResponseEnvelope:
    request_id: str            # Reference to RequestEnvelope.internal_id
    external_id: str | None    # Echoed from request
    tytx_mode: bool            # Inherited from request
    data: Any                  # Response payload
```

### 7. Envelope Registry
**Decision**: Per-connection for WebSocket, per-request for HTTP

**WebSocket:**
```python
class WSXHandler:
    envelopes: dict[str, RequestEnvelope]  # internal_id → envelope
```
- Request arrives → create envelope, store in `envelopes[internal_id]`
- Process
- Respond
- Cleanup: `del envelopes[internal_id]`
- Connection closes → automatic cleanup of all envelopes

**HTTP:**
- Envelope lives in request scope, no registry needed
- Created at request start, destroyed at response end

### 8. ID Strategy
**Decision**: Always generate internal ID, preserve external ID

- `internal_id`: Server-generated (uuid or sequential), always present
- `external_id`: Client-provided (e.g., WSX message `id`), optional
- Response echoes `external_id` for client correlation
- Internal tracking uses `internal_id`

```python
# src/genro_asgi/utils.py

def url_from_scope(
    scope: Scope,
    default_scheme: str = "http",
) -> URL:
    """
    Construct URL from ASGI scope.

Supports:
    - scheme from scope (http/https, ws/wss), with fallback
    - host/port from server; fallback Host header; fallback localhost
    - default port omission (80/443)
    - path = root_path + path, default "/"
    - query_string decode latin-1
    """
    ...
```

```python
# src/genro_asgi/envelope.py

@dataclass
class RequestEnvelope:
    ...

@classmethod
    def from_http(cls, request: Request) -> RequestEnvelope:
        """Create envelope from HTTP request."""
        ...

@classmethod
    def from_wsx(cls, message: WSXMessage) -> RequestEnvelope:
        """Create envelope from WSX message."""
        ...

@dataclass
class ResponseEnvelope:
    ...

def to_http(self) -> Response:
        """Convert to HTTP Response."""
        ...

def to_wsx(self) -> WSXMessage:
        """Convert to WSX message."""
        ...
```

```python
def detect_tytx(text: str) -> tuple[str, bool]:
    """
    Detect and strip ::TYTX marker.

Returns:
        (content, is_tytx) - content without marker, flag if marker was present
    """
    if text.endswith("::TYTX"):
        return text[:-6], True
    return text, False

def append_tytx(text: str) -> str:
    """Append ::TYTX marker to text."""
    return text + "::TYTX"
```

- Remove duplicate URL construction, use `url_from_scope()`
- Update `receive_json()` to auto-detect TYTX
- Update `send_json()` to respect `tytx_mode`

- [ ] Create `src/genro_asgi/utils.py` with `url_from_scope()`
- [ ] Create `src/genro_asgi/envelope.py` with `RequestEnvelope`, `ResponseEnvelope`
- [ ] Add TYTX helpers: `detect_tytx()`, `append_tytx()`
- [ ] Refactor `Request.url` to use `url_from_scope()`
- [ ] Refactor `WebSocket.url` to use `url_from_scope()`
- [ ] Tests for URL construction (all edge cases)
- [ ] Tests for TYTX detection/append
- [ ] Tests for Envelope creation from HTTP/WSX
- [ ] Update docstrings
- [ ] Commit

1. Write docstring for `utils.py` (Step 2)
2. Get approval
3. Write tests (Step 3)
4. Implement (Step 4)
5. Commit (Step 6)

