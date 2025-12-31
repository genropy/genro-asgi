# Response

HTTP Response class for ASGI applications.

**Source**: `src/genro_asgi/response.py`

## Design Pattern

genro-asgi uses a **single Response class** with dynamic content type detection
via `set_result()`, rather than specialized subclasses (JSONResponse, HTMLResponse, etc.).

This pattern integrates with the dispatcher flow where Response is created by Request
and configured after handler execution.

## Response Class

```python
# src/genro_asgi/response.py
class Response:
    """Base HTTP response class."""

    __slots__ = ("body", "status_code", "_media_type", "_headers", "request")

    media_type: str | None = None
    charset: str = "utf-8"

    def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: HeadersInput = None,
        media_type: str | None = None,
        request: Any = None,
    ) -> None: ...

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - send the response."""

    def set_header(self, name: str, value: str) -> None:
        """Add a response header."""

    def set_result(self, result: Any, metadata: dict[str, Any] | None = None) -> None:
        """Set body with auto content-type detection."""

    def set_error(self, error: Exception) -> None:
        """Set error response from exception."""
```

## Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `body` | `bytes` | Encoded response body |
| `status_code` | `int` | HTTP status code (default 200) |
| `request` | `Any` | Reference to originating Request |
| `_media_type` | `str \| None` | Content-Type media type |
| `_headers` | `list[tuple[str, str]]` | Response headers |

## Class Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `media_type` | `str \| None` | `None` | Default media type for subclasses |
| `charset` | `str` | `"utf-8"` | Character encoding |

## Main Pattern: set_result()

Response is created empty by Request and configured via `set_result()`:

```python
# In dispatcher after calling handler:
result = await handler(**args)
request.response.set_result(result, metadata=node.metadata)
await request.response(scope, receive, send)
```

### Auto Content-Type Detection

`set_result()` automatically detects content type from result:

| Result Type | Content-Type | Encoding |
|-------------|--------------|----------|
| `dict`, `list` | `application/json` | JSON (orjson if available) |
| `Path` | from extension | File bytes |
| `bytes` | `application/octet-stream` | As-is |
| `str` | `text/plain` | UTF-8 |
| `None` | `text/plain` | Empty body |
| other | `text/plain` | str() conversion |

### TYTX Support

If request has TYTX mode enabled, `set_result()` automatically:
- Serializes dict/list using `genro_tytx.to_tytx()`
- Uses the same transport (json/msgpack) as the request
- Sets Content-Type to `application/vnd.tytx+{transport}`

```python
# Request with X-TYTX-Transport: msgpack header
request.response.set_result({"data": [1, 2, 3]})
# → Body: msgpack encoded with TYTX type markers
# → Content-Type: application/vnd.tytx+msgpack
```

## Methods

### set_header()

```python
def set_header(self, name: str, value: str) -> None:
    """Add a response header. Can be called before set_result."""
```

### set_result()

```python
def set_result(self, result: Any, metadata: dict[str, Any] | None = None) -> None:
    """Set response body from result.

    Args:
        result: Handler result (dict, str, bytes, Path, etc.)
        metadata: Route metadata dict. Uses mime_type if present.
    """
```

Priority for MIME type detection:
1. `self._media_type` if already set
2. `metadata["mime_type"]` if present
3. For `Path`: guess from file extension
4. Type-based defaults (see table above)

### set_error()

```python
def set_error(self, error: Exception) -> None:
    """Set error response from exception.

    Maps exception type to HTTP status using ERROR_MAP.
    Unknown exceptions → 500 (logged).
    """
```

**ERROR_MAP**:

| Exception | Status Code |
|-----------|-------------|
| `NotFound` | 404 |
| `NotAuthorized` | 403 |
| `ValueError` | 400 |
| `TypeError` | 400 |
| `PermissionError` | 403 |
| `FileNotFoundError` | 404 |
| (unknown) | 500 |

## Helper Function: make_cookie()

```python
def make_cookie(
    key: str,
    value: str = "",
    *,
    max_age: int | None = None,
    path: str = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    samesite: str | None = "lax",
) -> tuple[str, str]:
    """Create Set-Cookie header tuple."""
```

Module-level function (not method) to preserve Response immutability.
Returns tuple for use in Response headers parameter.

**Example**:
```python
response = Response(
    content="OK",
    headers=[
        make_cookie("session", "abc123", httponly=True, secure=True),
        make_cookie("prefs", "dark", max_age=31536000),
    ]
)
```

## Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Single class | No subclasses | Simpler API, dynamic detection |
| `set_result()` | Post-construction | Integrates with dispatcher flow |
| `__slots__` | Yes | Memory efficiency |
| Headers input | `Mapping \| list` | Flexible input |
| Charset | Auto for `text/*` | Convenience |
| Header encoding | latin-1 | HTTP standard |
| Content-Length | Auto | Always added |
| orjson | Optional | Performance when available |
| make_cookie | Function | Response immutability |

## Usage Examples

### Basic Response

```python
response = Response(content="Hello", media_type="text/plain")
await response(scope, receive, send)
```

### Handler Pattern (Dispatcher)

```python
# Create empty response linked to request
request = HttpRequest(scope, receive)
request.response = Response(request=request)

# After handler returns
result = await handler(**args)
request.response.set_result(result, metadata=route.metadata)
await request.response(scope, receive, send)
```

### With Headers

```python
response = Response(
    content=b"data",
    headers={"X-Custom": "value", "Cache-Control": "no-cache"},
    media_type="application/octet-stream",
)
```

### Error Response

```python
try:
    result = await handler()
except Exception as e:
    request.response.set_error(e)
```
