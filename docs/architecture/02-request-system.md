# Request System

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## Overview

The request system provides transport-agnostic request handling.
All classes live in `request.py`:

- `BaseRequest` - Abstract base class
- `HttpRequest` - ASGI HTTP adapter
- `WsRequest` - ASGI WebSocket adapter (for WSX messages)
- `RequestRegistry` - Factory and tracking
- `REQUEST_FACTORIES` - Default factory mapping

---

## Core Principle

Every request gets an `id` and goes through the registry:

```
ASGI scope arrives
    │
    ▼
scope["type"] == "http"?  ──► HttpRequest
scope["type"] == "websocket"?  ──► WsRequest
    │
    ▼
request.id = uuid4() (or x-request-id header)
    │
    ▼
registry.register(request)
    │
    ▼
handler(request)
    │
    ▼
registry.unregister(request.id)
```

---

## BaseRequest (ABC)

Abstract interface for all request types:

```python
class BaseRequest(ABC):
    """Transport-agnostic request interface."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Correlation ID for request/response matching."""

    @property
    @abstractmethod
    def method(self) -> str:
        """HTTP method: GET, POST, PUT, DELETE, PATCH."""

    @property
    @abstractmethod
    def path(self) -> str:
        """Request path (e.g., '/users/42')."""

    @property
    @abstractmethod
    def headers(self) -> dict[str, str]:
        """Request headers (lowercase keys)."""

    @property
    @abstractmethod
    def cookies(self) -> dict[str, str]:
        """Request cookies."""

    @property
    @abstractmethod
    def query(self) -> dict[str, Any]:
        """Query parameters (TYTX hydrated if available)."""

    @property
    @abstractmethod
    def data(self) -> Any:
        """Request body/payload (TYTX hydrated if available)."""

    @property
    @abstractmethod
    def transport(self) -> str:
        """Transport type: 'http', 'websocket', 'nats'."""

    @classmethod
    @abstractmethod
    async def from_scope(
        cls,
        scope: dict[str, Any],
        receive: Any,
        send: Any | None = None,
        **kwargs: Any,
    ) -> "BaseRequest":
        """Factory method to create request from ASGI scope."""
```

---

## HttpRequest

ASGI HTTP request adapter:

```python
class HttpRequest(BaseRequest):
    """HTTP request wrapping ASGI scope."""

    def __init__(self, scope: Scope, body: bytes) -> None:
        self._scope = scope
        self._body = body
        self._headers = ...   # parsed from scope
        self._cookies = ...   # parsed from Cookie header
        self._query = ...     # parsed from query_string
        self._data = ...      # parsed body (JSON)
        self._id = ...        # from x-request-id or uuid4()

    @classmethod
    async def from_scope(cls, scope, receive, send=None, **kwargs) -> HttpRequest:
        """Read body and create request."""
        body = await cls._read_body(receive)
        return cls(scope, body)

    @property
    def transport(self) -> str:
        return "http"

    # Additional properties
    @property
    def scope(self) -> Scope:
        """Raw ASGI scope."""

    @property
    def body(self) -> bytes:
        """Raw body bytes."""
```

### TYTX Hydration

If `genro-tytx` is available and content-type contains "tytx", full ASGI request
parsing is delegated to `asgi_data()` which handles query, headers, cookies, and body:

```python
@classmethod
async def from_scope(cls, scope, receive, send=None, **kwargs) -> HttpRequest:
    # Check for TYTX mode
    content_type = headers.get("content-type", "")
    is_tytx = "tytx" in content_type.lower()

    if is_tytx:
        try:
            from genro_tytx import asgi_data
            data = await asgi_data(dict(scope), receive)
            # data = {"query": {...}, "headers": {...}, "cookies": {...}, "body": {...}}
            # All values already hydrated
            instance = cls(scope, b"")
            instance._headers = data.get("headers", {})
            instance._cookies = data.get("cookies", {})
            instance._query = data.get("query", {})
            instance._data = data.get("body")
            instance._tytx_mode = True
            return instance
        except ImportError:
            pass
    # ... standard parsing
```

---

## WsRequest

WebSocket request adapter for WSX messages:

```python
class WsRequest(BaseRequest):
    """WebSocket request from WSX message."""

    def __init__(
        self,
        scope: Scope,
        message: dict[str, Any],
        websocket: WebSocket,
    ) -> None:
        self._scope = scope
        self._message = message  # parsed WSX message
        self._websocket = websocket
        self._id = message["id"]
        # ... parse headers, cookies, query, data from message

    @classmethod
    async def from_scope(
        cls,
        scope: Scope,
        receive: Receive,
        send: Send | None = None,
        *,
        message: dict[str, Any],
        websocket: WebSocket,
        **kwargs: Any,
    ) -> WsRequest:
        """Create from WSX message."""
        return cls(scope, message, websocket)

    @property
    def transport(self) -> str:
        return "websocket"

    @property
    def websocket(self) -> WebSocket:
        """Access to underlying WebSocket connection."""
```

---

## RequestRegistry

Factory and tracking for active requests:

```python
class RequestRegistry:
    """Creates and tracks active requests."""

    def __init__(
        self,
        factories: dict[str, type[BaseRequest]] | None = None,
    ) -> None:
        self.factories = factories or REQUEST_FACTORIES.copy()
        self._requests: dict[str, BaseRequest] = {}

    def register_factory(self, scope_type: str, factory: type[BaseRequest]) -> None:
        """Register a factory for a scope type."""
        self.factories[scope_type] = factory

    async def create(
        self,
        scope: Scope,
        receive: Receive,
        send: Send | None = None,
        **kwargs: Any,
    ) -> BaseRequest:
        """
        Create and register a request from ASGI scope.

        Looks up scope["type"] to find factory, creates request,
        registers in _requests dict.

        Raises:
            ValueError: If no factory for scope type.
        """
        scope_type = scope.get("type", "")
        factory = self.factories.get(scope_type)
        if factory is None:
            raise ValueError(f"No factory for scope type: {scope_type!r}")

        request = await factory.from_scope(scope, receive, send, **kwargs)
        self._requests[request.id] = request
        return request

    def unregister(self, request_id: str) -> BaseRequest | None:
        """Remove and return request."""
        return self._requests.pop(request_id, None)

    def get(self, request_id: str) -> BaseRequest | None:
        """Get request by id."""
        return self._requests.get(request_id)

    def __len__(self) -> int:
        """Number of active requests."""
        return len(self._requests)

    def __iter__(self) -> Iterator[BaseRequest]:
        """Iterate active requests."""
        return iter(self._requests.values())

    def __contains__(self, request_id: str) -> bool:
        """Check if request is active."""
        return request_id in self._requests
```

---

## REQUEST_FACTORIES

Default mapping:

```python
REQUEST_FACTORIES: dict[str, type[BaseRequest]] = {
    "http": HttpRequest,
    "websocket": WsRequest,
}
```

Custom factories can be registered:

```python
registry = RequestRegistry()
registry.register_factory("nats", NatsRequest)
```

---

## Usage in Server

```python
# In AsgiServer flat mode
app_handler = self.get_app_handler(scope)
registry = app_handler.get("request_registry")

if registry:
    request = await registry.create(scope, receive, send)
    try:
        await app_handler["app"](scope, receive, send)
    finally:
        registry.unregister(request.id)
```

---

## Transport-Agnostic Handlers

Handlers receive `BaseRequest` and work with any transport:

```python
async def get_user(request: BaseRequest) -> dict:
    """Works with HTTP, WebSocket, or NATS."""
    user_id = request.path.split("/")[-1]
    auth = request.headers.get("authorization")
    session = request.cookies.get("session_id")
    details = request.query.get("details", False)

    user = await db.get_user(user_id)
    return {
        "id": user.id,
        "name": user.name,
        "transport": request.transport,  # "http" or "websocket"
    }
```

---

## Class Hierarchy

```
BaseRequest (ABC)
    │
    ├── HttpRequest
    │       └── ASGI HTTP scope + body
    │
    └── WsRequest
            └── ASGI WebSocket + WSX message
```

Future:
```
BaseRequest (ABC)
    │
    ├── HttpRequest
    ├── WsRequest
    └── NatsRequest (when needed)
```

---

## Migration from Envelope

| Old | New |
|-----|-----|
| `RequestEnvelope` | `BaseRequest` subclasses |
| `ResponseEnvelope` | Not needed |
| `EnvelopeRegistry` | `RequestRegistry` |
| `baseclasses/envelope.py` | Deleted |

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
