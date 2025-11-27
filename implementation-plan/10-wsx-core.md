# Block 10: wsx/ subpackage - Core & Dispatcher

**Status**: DA REVISIONARE
**Dependencies**: 06-websockets
**Commit message**: `feat(wsx): add WSX protocol dispatcher`

---

## Important Note: Potential Standalone Package

> **NOTA**: Il modulo WSX e' progettato per essere **potenzialmente separabile** in un repository
> standalone (`genro-wsx`). Durante l'implementazione, assicurarsi che:
>
> 1. **Nessuna dipendenza circolare** con altri moduli di genro-asgi
> 2. **Import minimi**: WSX dipende solo da `websockets.py` per il transport layer
> 3. **Interface astratta**: Usare ABC/Protocol per il WebSocket transport se possibile
> 4. **Zero side effects**: Nessun stato globale o singleton
>
> Se WSX viene scritto in modo pulito, potra' essere estratto come `genro-wsx` e usato:
>
> - Con genro-asgi (caso primario)
> - Con altri framework ASGI (Starlette, Quart, etc.)
> - Con WebSocket puri (senza ASGI)

---

## Purpose

WSX (WebSocket eXtended) protocol implementation for RPC, notifications, and subscriptions.
This block implements the core dispatcher that handles WSX message routing.

## WSX Protocol Overview

Message types:
- `rpc.request` - Client → Server RPC call
- `rpc.response` - Server → Client RPC result
- `rpc.error` - Server → Client RPC error
- `rpc.notify` - Both directions, no response expected
- `rpc.subscribe` - Client → Server subscription request
- `rpc.unsubscribe` - Client → Server unsubscribe
- `rpc.event` - Server → Client published event
- `rpc.ping` / `rpc.pong` - Keepalive

## Files Structure

```
src/genro_asgi/wsx/
├── __init__.py
├── types.py          # WSX message types
├── dispatcher.py     # Message dispatcher
├── handler.py        # Connection handler
└── errors.py         # WSX-specific errors
```

## File: `src/genro_asgi/wsx/__init__.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX - WebSocket eXtended protocol for genro-asgi."""

from .dispatcher import WSXDispatcher
from .handler import WSXHandler
from .types import (
    WSXMessage,
    WSXRequest,
    WSXResponse,
    WSXError,
    WSXNotify,
    WSXEvent,
)
from .errors import WSXProtocolError

__all__ = [
    "WSXDispatcher",
    "WSXHandler",
    "WSXMessage",
    "WSXRequest",
    "WSXResponse",
    "WSXError",
    "WSXNotify",
    "WSXEvent",
    "WSXProtocolError",
]
```

## File: `src/genro_asgi/wsx/types.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX message types."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WSXMessage:
    """Base WSX message."""
    type: str
    id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: dict[str, Any] = {"type": self.type}
        if self.id:
            result["id"] = self.id
        if self.meta:
            result["meta"] = self.meta
        return result


@dataclass
class WSXRequest(WSXMessage):
    """RPC request message."""
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.type = "rpc.request"

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["method"] = self.method
        if self.params:
            result["params"] = self.params
        return result


@dataclass
class WSXResponse(WSXMessage):
    """RPC response message."""
    result: Any = None

    def __post_init__(self):
        self.type = "rpc.response"

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["result"] = self.result
        return result


@dataclass
class WSXError(WSXMessage):
    """RPC error message."""
    code: str = "ERROR"
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.type = "rpc.error"

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["error"] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["error"]["details"] = self.details
        return result


@dataclass
class WSXNotify(WSXMessage):
    """Notification message (no response expected)."""
    method: str | None = None
    event: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    payload: Any = None

    def __post_init__(self):
        self.type = "rpc.notify"

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.method:
            result["method"] = self.method
        if self.event:
            result["event"] = self.event
        if self.params:
            result["params"] = self.params
        if self.payload is not None:
            result["payload"] = self.payload
        return result


@dataclass
class WSXSubscribe(WSXMessage):
    """Subscription request message."""
    channel: str = ""
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self.type = "rpc.subscribe"

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["channel"] = self.channel
        if self.params:
            result["params"] = self.params
        return result


@dataclass
class WSXUnsubscribe(WSXMessage):
    """Unsubscribe message."""

    def __post_init__(self):
        self.type = "rpc.unsubscribe"


@dataclass
class WSXEvent(WSXMessage):
    """Published event message."""
    channel: str = ""
    payload: Any = None

    def __post_init__(self):
        self.type = "rpc.event"

    def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["channel"] = self.channel
        if self.payload is not None:
            result["payload"] = self.payload
        return result


@dataclass
class WSXPing(WSXMessage):
    """Ping message."""

    def __post_init__(self):
        self.type = "rpc.ping"


@dataclass
class WSXPong(WSXMessage):
    """Pong message."""

    def __post_init__(self):
        self.type = "rpc.pong"


def parse_message(data: dict[str, Any]) -> WSXMessage:
    """
    Parse raw dict into typed WSX message.

    Args:
        data: Raw message dict

    Returns:
        Typed WSX message

    Raises:
        ValueError: If message type is unknown
    """
    msg_type = data.get("type", "")
    msg_id = data.get("id")
    meta = data.get("meta", {})

    if msg_type == "rpc.request":
        return WSXRequest(
            id=msg_id,
            meta=meta,
            method=data.get("method", ""),
            params=data.get("params", {}),
        )
    elif msg_type == "rpc.response":
        return WSXResponse(
            id=msg_id,
            meta=meta,
            result=data.get("result"),
        )
    elif msg_type == "rpc.error":
        error = data.get("error", {})
        return WSXError(
            id=msg_id,
            meta=meta,
            code=error.get("code", "ERROR"),
            message=error.get("message", ""),
            details=error.get("details", {}),
        )
    elif msg_type == "rpc.notify":
        return WSXNotify(
            id=msg_id,
            meta=meta,
            method=data.get("method"),
            event=data.get("event"),
            params=data.get("params", {}),
            payload=data.get("payload"),
        )
    elif msg_type == "rpc.subscribe":
        return WSXSubscribe(
            id=msg_id,
            meta=meta,
            channel=data.get("channel", ""),
            params=data.get("params", {}),
        )
    elif msg_type == "rpc.unsubscribe":
        return WSXUnsubscribe(id=msg_id, meta=meta)
    elif msg_type == "rpc.event":
        return WSXEvent(
            id=msg_id,
            meta=meta,
            channel=data.get("channel", ""),
            payload=data.get("payload"),
        )
    elif msg_type == "rpc.ping":
        return WSXPing(id=msg_id, meta=meta)
    elif msg_type == "rpc.pong":
        return WSXPong(id=msg_id, meta=meta)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
```

## File: `src/genro_asgi/wsx/errors.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX-specific errors."""


class WSXProtocolError(Exception):
    """
    WSX protocol error.

    Raised when a WSX message is malformed or invalid.
    """

    def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class WSXMethodNotFound(WSXProtocolError):
    """Method not found error."""

    def __init__(self, method: str) -> None:
        super().__init__(
            code="METHOD_NOT_FOUND",
            message=f"Method not found: {method}",
            details={"method": method},
        )


class WSXInvalidParams(WSXProtocolError):
    """Invalid parameters error."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(
            code="INVALID_PARAMS",
            message=message,
            details=details,
        )


class WSXInternalError(WSXProtocolError):
    """Internal error."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
        )
```

## File: `src/genro_asgi/wsx/dispatcher.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX message dispatcher."""

from typing import Any, Awaitable, Callable

from .errors import WSXInternalError, WSXMethodNotFound, WSXProtocolError
from .types import (
    WSXError,
    WSXMessage,
    WSXNotify,
    WSXPing,
    WSXPong,
    WSXRequest,
    WSXResponse,
    WSXSubscribe,
    WSXUnsubscribe,
    parse_message,
)

# Type alias for RPC method handlers
RPCHandler = Callable[..., Awaitable[Any]]


class WSXDispatcher:
    """
    WSX message dispatcher.

    Routes incoming WSX messages to appropriate handlers.

    Example:
        dispatcher = WSXDispatcher()

        @dispatcher.method("User.create")
        async def create_user(name: str, email: str):
            return {"id": 1, "name": name, "email": email}

        # Or with external router (SmartRoute)
        dispatcher = WSXDispatcher(router=my_smartrouter)
    """

    def __init__(
        self,
        router: Any | None = None,
        methods: dict[str, RPCHandler] | None = None,
    ) -> None:
        """
        Initialize dispatcher.

        Args:
            router: External router (e.g., SmartRoute) with get() method
            methods: Dict of method_name -> handler function
        """
        self._router = router
        self._methods: dict[str, RPCHandler] = methods or {}
        self._notification_handlers: list[Callable[[WSXNotify], Awaitable[None]]] = []

    def method(self, name: str) -> Callable[[RPCHandler], RPCHandler]:
        """
        Decorator to register an RPC method.

        Args:
            name: Method name (e.g., "User.create")

        Returns:
            Decorator function
        """
        def decorator(func: RPCHandler) -> RPCHandler:
            self._methods[name] = func
            return func
        return decorator

    def on_notify(
        self, func: Callable[[WSXNotify], Awaitable[None]]
    ) -> Callable[[WSXNotify], Awaitable[None]]:
        """
        Register a notification handler.

        Args:
            func: Async function to handle notifications

        Returns:
            The registered function
        """
        self._notification_handlers.append(func)
        return func

    async def dispatch(self, data: dict[str, Any]) -> WSXMessage | None:
        """
        Dispatch a raw message dict.

        Args:
            data: Raw message dict from JSON

        Returns:
            Response message or None (for notifications/pong)
        """
        try:
            message = parse_message(data)
        except ValueError as e:
            return WSXError(
                code="PARSE_ERROR",
                message=str(e),
            )

        return await self.dispatch_message(message)

    async def dispatch_message(self, message: WSXMessage) -> WSXMessage | None:
        """
        Dispatch a typed WSX message.

        Args:
            message: Typed WSX message

        Returns:
            Response message or None
        """
        if isinstance(message, WSXRequest):
            return await self._handle_request(message)
        elif isinstance(message, WSXNotify):
            await self._handle_notify(message)
            return None
        elif isinstance(message, WSXPing):
            return WSXPong(id=message.id)
        elif isinstance(message, WSXSubscribe):
            return await self._handle_subscribe(message)
        elif isinstance(message, WSXUnsubscribe):
            return await self._handle_unsubscribe(message)
        elif isinstance(message, (WSXResponse, WSXError, WSXPong)):
            # These are responses, not requests - ignore
            return None
        else:
            return WSXError(
                id=message.id,
                code="UNSUPPORTED_TYPE",
                message=f"Unsupported message type: {message.type}",
            )

    async def _handle_request(self, request: WSXRequest) -> WSXMessage:
        """Handle RPC request."""
        try:
            handler = await self._get_handler(request.method)
            if handler is None:
                raise WSXMethodNotFound(request.method)

            result = await handler(**request.params)

            return WSXResponse(
                id=request.id,
                result=result,
            )

        except WSXProtocolError as e:
            return WSXError(
                id=request.id,
                code=e.code,
                message=e.message,
                details=e.details,
            )
        except Exception as e:
            return WSXError(
                id=request.id,
                code="INTERNAL_ERROR",
                message=str(e),
            )

    async def _get_handler(self, method: str) -> RPCHandler | None:
        """Get handler for method name."""
        # First check local methods
        if method in self._methods:
            return self._methods[method]

        # Then try external router
        if self._router is not None:
            try:
                # SmartRoute interface: router.get(method, use_smartasync=True)
                return self._router.get(method, use_smartasync=True)
            except Exception:
                pass

        return None

    async def _handle_notify(self, notify: WSXNotify) -> None:
        """Handle notification (no response)."""
        for handler in self._notification_handlers:
            try:
                await handler(notify)
            except Exception:
                pass  # Notifications don't return errors

    async def _handle_subscribe(self, subscribe: WSXSubscribe) -> WSXMessage:
        """Handle subscription request."""
        # Override in subclass or use SubscriptionManager
        return WSXResponse(
            id=subscribe.id,
            result={"status": "subscribed", "channel": subscribe.channel},
        )

    async def _handle_unsubscribe(self, unsubscribe: WSXUnsubscribe) -> WSXMessage:
        """Handle unsubscribe request."""
        # Override in subclass or use SubscriptionManager
        return WSXResponse(
            id=unsubscribe.id,
            result={"status": "unsubscribed"},
        )
```

## Tests: `tests/test_wsx_core.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for WSX core."""

import pytest
from genro_asgi.wsx import (
    WSXDispatcher,
    WSXError,
    WSXNotify,
    WSXRequest,
    WSXResponse,
)
from genro_asgi.wsx.types import (
    WSXPing,
    WSXPong,
    WSXSubscribe,
    parse_message,
)


class TestWSXTypes:
    def test_request_to_dict(self):
        req = WSXRequest(id="1", method="User.create", params={"name": "John"})
        d = req.to_dict()
        assert d["type"] == "rpc.request"
        assert d["id"] == "1"
        assert d["method"] == "User.create"
        assert d["params"] == {"name": "John"}

    def test_response_to_dict(self):
        resp = WSXResponse(id="1", result={"id": 1})
        d = resp.to_dict()
        assert d["type"] == "rpc.response"
        assert d["result"] == {"id": 1}

    def test_error_to_dict(self):
        err = WSXError(id="1", code="NOT_FOUND", message="User not found")
        d = err.to_dict()
        assert d["type"] == "rpc.error"
        assert d["error"]["code"] == "NOT_FOUND"

    def test_notify_to_dict(self):
        notify = WSXNotify(method="log", params={"level": "info"})
        d = notify.to_dict()
        assert d["type"] == "rpc.notify"
        assert d["method"] == "log"


class TestParseMessage:
    def test_parse_request(self):
        data = {
            "type": "rpc.request",
            "id": "123",
            "method": "User.get",
            "params": {"id": 1},
        }
        msg = parse_message(data)
        assert isinstance(msg, WSXRequest)
        assert msg.method == "User.get"
        assert msg.params == {"id": 1}

    def test_parse_response(self):
        data = {
            "type": "rpc.response",
            "id": "123",
            "result": {"name": "John"},
        }
        msg = parse_message(data)
        assert isinstance(msg, WSXResponse)
        assert msg.result == {"name": "John"}

    def test_parse_ping(self):
        data = {"type": "rpc.ping"}
        msg = parse_message(data)
        assert isinstance(msg, WSXPing)

    def test_parse_subscribe(self):
        data = {
            "type": "rpc.subscribe",
            "id": "sub-1",
            "channel": "user.updates",
        }
        msg = parse_message(data)
        assert isinstance(msg, WSXSubscribe)
        assert msg.channel == "user.updates"

    def test_parse_unknown_type(self):
        data = {"type": "unknown.type"}
        with pytest.raises(ValueError, match="Unknown message type"):
            parse_message(data)


class TestWSXDispatcher:
    @pytest.mark.asyncio
    async def test_dispatch_request(self):
        dispatcher = WSXDispatcher()

        @dispatcher.method("echo")
        async def echo(message: str):
            return {"echo": message}

        result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "echo",
            "params": {"message": "hello"},
        })

        assert isinstance(result, WSXResponse)
        assert result.id == "1"
        assert result.result == {"echo": "hello"}

    @pytest.mark.asyncio
    async def test_dispatch_method_not_found(self):
        dispatcher = WSXDispatcher()

        result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "nonexistent",
            "params": {},
        })

        assert isinstance(result, WSXError)
        assert result.code == "METHOD_NOT_FOUND"

    @pytest.mark.asyncio
    async def test_dispatch_ping_pong(self):
        dispatcher = WSXDispatcher()

        result = await dispatcher.dispatch({"type": "rpc.ping"})

        assert isinstance(result, WSXPong)

    @pytest.mark.asyncio
    async def test_dispatch_notify(self):
        dispatcher = WSXDispatcher()
        notifications = []

        @dispatcher.on_notify
        async def handle_notify(notify):
            notifications.append(notify)

        result = await dispatcher.dispatch({
            "type": "rpc.notify",
            "method": "log",
            "params": {"level": "info"},
        })

        assert result is None  # Notifications don't return
        assert len(notifications) == 1

    @pytest.mark.asyncio
    async def test_dispatch_with_router(self):
        # Mock SmartRoute-like router
        class MockRouter:
            def get(self, method, use_smartasync=False):
                if method == "test.method":
                    async def handler(value: int):
                        return value * 2
                    return handler
                raise KeyError(method)

        dispatcher = WSXDispatcher(router=MockRouter())

        result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "test.method",
            "params": {"value": 21},
        })

        assert isinstance(result, WSXResponse)
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_dispatch_handler_error(self):
        dispatcher = WSXDispatcher()

        @dispatcher.method("failing")
        async def failing():
            raise ValueError("Something went wrong")

        result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "failing",
            "params": {},
        })

        assert isinstance(result, WSXError)
        assert result.code == "INTERNAL_ERROR"
        assert "Something went wrong" in result.message

    @pytest.mark.asyncio
    async def test_dispatch_subscribe(self):
        dispatcher = WSXDispatcher()

        result = await dispatcher.dispatch({
            "type": "rpc.subscribe",
            "id": "sub-1",
            "channel": "user.updates",
        })

        assert isinstance(result, WSXResponse)
        assert result.result["status"] == "subscribed"

    @pytest.mark.asyncio
    async def test_dispatch_invalid_json(self):
        dispatcher = WSXDispatcher()

        result = await dispatcher.dispatch({
            "type": "invalid.type.that.does.not.exist"
        })

        assert isinstance(result, WSXError)
```

## Checklist

- [ ] Create `src/genro_asgi/wsx/__init__.py`
- [ ] Create `src/genro_asgi/wsx/types.py`
- [ ] Create `src/genro_asgi/wsx/errors.py`
- [ ] Create `src/genro_asgi/wsx/dispatcher.py`
- [ ] Create `tests/test_wsx_core.py`
- [ ] Run `pytest tests/test_wsx_core.py`
- [ ] Run `mypy src/genro_asgi/wsx/`
- [ ] Update main `__init__.py` if needed
- [ ] Commit
