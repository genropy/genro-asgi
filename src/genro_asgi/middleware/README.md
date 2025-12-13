# genro-asgi Middleware System

## Overview

The genro-asgi middleware system uses an **onion-style** pattern with auto-registration.
Middleware wraps the ASGI application and can intercept/modify requests and responses.

## Two Usage Modes

### 1. Config-Driven (recommended)

Middleware declared in YAML configuration, resolved by name from registry:

```yaml
middleware:
  - type: CORSMiddleware
    allow_origins: ["*"]

  - type: CompressionMiddleware
    minimum_size: 1000
```

**Requirement**: middleware must inherit from `BaseMiddleware` for auto-registration.

### 2. Programmatic (override)

Subclasses of `AsgiServer` can override `_build_middleware_chain`:

```python
class MyServer(AsgiServer):
    def _build_middleware_chain(self) -> Any:
        # Use any ASGI-compatible middleware
        from some_library import TheirMiddleware

        app = Dispatcher(self)
        app = TheirMiddleware(app, option="value")
        app = MyCustomMiddleware(app)
        return app
```

Or mix (config + custom):

```python
class MyServer(AsgiServer):
    def _build_middleware_chain(self) -> Any:
        # First apply config middleware
        app = super()._build_middleware_chain()
        # Then add custom middleware
        app = MyCustomMiddleware(app)
        return app
```

**No requirement**: any ASGI callable `(scope, receive, send) -> None` works.

## Architecture

```text
Request → [Middleware1 → [Middleware2 → [App] → Middleware2] → Middleware1] → Response
```

Each middleware:

1. Receives `scope`, `receive`, `send` (standard ASGI interface)
2. Can modify scope or intercept messages
3. Calls `self.app(scope, receive, send)` to pass to next layer
4. Can wrap `send` to modify response

## Creating a Compatible Middleware

### Base Structure

```python
# my_middleware.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class MyMiddleware(BaseMiddleware):
    """Middleware description.

    Config options:
        option1: Description. Default: value
        option2: Description. Default: value
    """

    __slots__ = ("option1", "option2")

    def __init__(
        self,
        app: ASGIApp,
        option1: str = "default",
        option2: int = 100,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.option1 = option1
        self.option2 = option2

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        # Filter HTTP only (or websocket if needed)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Your logic here
        await self.app(scope, receive, send)


if __name__ == "__main__":
    pass
```

### Mandatory Requirements

| Requirement | Description |
|-------------|-------------|
| Inherit `BaseMiddleware` | Auto-registration in registry |
| `__slots__` | Declare all instance attributes |
| `super().__init__(app, **kwargs)` | Pass app and kwargs to parent |
| `**kwargs` in constructor | Allows future configurations |
| `async def __call__` | Implements ASGI interface |
| `if __name__ == "__main__": pass` | Mandatory entry point |

### Auto-Registration

When you create a `BaseMiddleware` subclass:

- `__init_subclass__` automatically registers the class in `MIDDLEWARE_REGISTRY`
- Default name is `cls.__name__` (e.g., `"MyMiddleware"`)
- Customize with `middleware_name` class attribute

```python
class MyMiddleware(BaseMiddleware):
    middleware_name = "my_custom_name"  # optional
```

## Common Patterns

### 1. Pass-Through (HTTP only)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    # HTTP logic
    await self.app(scope, receive, send)
```

### 2. Wrapping `send` (modify response)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    async def wrapped_send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            # Modify headers
            headers = list(message.get("headers", []))
            headers.append((b"x-custom-header", b"value"))
            message = {**message, "headers": headers}
        await send(message)

    await self.app(scope, receive, wrapped_send)
```

### 3. Buffering Response (e.g., compression)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    initial_message: MutableMapping[str, Any] | None = None
    body_parts: list[bytes] = []

    async def buffer_send(message: MutableMapping[str, Any]) -> None:
        nonlocal initial_message, body_parts

        if message["type"] == "http.response.start":
            initial_message = message

        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if body:
                body_parts.append(body)

            if not more_body:
                full_body = b"".join(body_parts)
                # Process full_body
                await send(initial_message)
                await send({"type": "http.response.body", "body": full_body})

    await self.app(scope, receive, buffer_send)
```

### 4. Short-Circuit (respond without calling app)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    # Condition to respond directly
    if self._should_handle_directly(scope):
        await self._send_direct_response(send)
        return  # Don't call self.app

    await self.app(scope, receive, send)
```

### 5. Error Handling

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    try:
        await self.app(scope, receive, send)
    except Exception as e:
        await self._send_error_response(send, e)
```

## Middleware Usage

### Direct

```python
from genro_asgi.middleware.cors import CORSMiddleware

app = CORSMiddleware(my_app, allow_origins=["*"])
```

### Via Registry (configuration)

```python
from genro_asgi.middleware import middleware_chain

middlewares = [
    ("CORSMiddleware", {"allow_origins": ["*"]}),
    ("CompressionMiddleware", {"minimum_size": 1000}),
    ("LoggingMiddleware", {"level": "DEBUG"}),
]

app = middleware_chain(middlewares, my_app)
```

## Included Middleware

| Middleware | Purpose |
|------------|---------|
| `CORSMiddleware` | Cross-Origin Resource Sharing |
| `CompressionMiddleware` | Gzip compression |
| `ErrorMiddleware` | Error handling |
| `LoggingMiddleware` | Request/response logging |

**Note**: For serving static files, use `StaticSite` as an app, not middleware.

## Checklist for New Middleware

- [ ] File in `src/genro_asgi/middleware/`
- [ ] Apache 2.0 copyright header
- [ ] Inherit `BaseMiddleware`
- [ ] Use `__slots__`
- [ ] Constructor with `**kwargs`
- [ ] Call `super().__init__(app, **kwargs)`
- [ ] Implement `async def __call__`
- [ ] Filter by `scope["type"]`
- [ ] Docstring with config options
- [ ] `if __name__ == "__main__": pass`
- [ ] Corresponding test
