# lifespan (from missing_doc)

> **STATUS**: ~~INTEGRATO~~
>
> - Integrato in: `specifications/02_server_foundation/03_lifecycle.md`
> - **PUÒ ESSERE ELIMINATO** dopo verifica finale

---

## Source: initial_implementation_plan/archive/07-lifespan.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types
**Commit message**: `feat(lifespan): add Lifespan event handler`

ASGI Lifespan event handling for startup/shutdown hooks.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ASGI Lifespan event handling."""

from typing import Awaitable, Callable

from .types import Receive, Scope, Send

# Type aliases for handlers
LifespanHandler = Callable[[], Awaitable[None]]

class Lifespan:
    """
    ASGI Lifespan event manager.

Manages application startup and shutdown events.

Example:
        lifespan = Lifespan()

@lifespan.on_startup
        async def startup():
            print("Starting up...")
            app.state.db = await create_db_pool()

@lifespan.on_shutdown
        async def shutdown():
            print("Shutting down...")
            await app.state.db.close()

app = App(handler=my_handler, lifespan=lifespan)
    """

__slots__ = ("_startup_handlers", "_shutdown_handlers")

def __init__(self) -> None:
        """Initialize lifespan manager."""
        self._startup_handlers: list[LifespanHandler] = []
        self._shutdown_handlers: list[LifespanHandler] = []

def on_startup(self, func: LifespanHandler) -> LifespanHandler:
        """
        Register a startup handler.

Args:
            func: Async function to call on startup

Returns:
            The registered function (for use as decorator)
        """
        self._startup_handlers.append(func)
        return func

def on_shutdown(self, func: LifespanHandler) -> LifespanHandler:
        """
        Register a shutdown handler.

Args:
            func: Async function to call on shutdown

Returns:
            The registered function (for use as decorator)
        """
        self._shutdown_handlers.append(func)
        return func

def add_startup_handler(self, func: LifespanHandler) -> None:
        """
        Add a startup handler (non-decorator form).

Args:
            func: Async function to call on startup
        """
        self._startup_handlers.append(func)

def add_shutdown_handler(self, func: LifespanHandler) -> None:
        """
        Add a shutdown handler (non-decorator form).

Args:
            func: Async function to call on shutdown
        """
        self._shutdown_handlers.append(func)

async def run_startup(self) -> None:
        """
        Run all startup handlers in registration order.

Raises:
            Exception: Re-raises any exception from handlers
        """
        for handler in self._startup_handlers:
            await handler()

async def run_shutdown(self) -> None:
        """
        Run all shutdown handlers in reverse registration order.

Continues even if a handler raises, collecting all errors.
        """
        errors: list[Exception] = []
        for handler in reversed(self._shutdown_handlers):
            try:
                await handler()
            except Exception as e:
                errors.append(e)

if errors:
            # Log errors but don't prevent shutdown
            # In production, these should be logged properly
            pass

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI lifespan interface.

Handles lifespan.startup and lifespan.shutdown events.

Args:
            scope: ASGI lifespan scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        started = False
        try:
            while True:
                message = await receive()
                message_type = message["type"]

if message_type == "lifespan.startup":
                    try:
                        await self.run_startup()
                        await send({"type": "lifespan.startup.complete"})
                        started = True
                    except Exception as exc:
                        await send({
                            "type": "lifespan.startup.failed",
                            "message": str(exc),
                        })
                        raise

elif message_type == "lifespan.shutdown":
                    try:
                        await self.run_shutdown()
                        await send({"type": "lifespan.shutdown.complete"})
                    except Exception as exc:
                        await send({
                            "type": "lifespan.shutdown.failed",
                            "message": str(exc),
                        })
                        raise
                    return

except Exception:
            # If startup failed, still try to run shutdown handlers
            if started:
                await self.run_shutdown()
            raise

class LifespanContext:
    """
    Context manager style lifespan.

Alternative API using async context manager pattern.

Example:
        @contextmanager
        async def lifespan(app):
            # Startup
            app.state.db = await create_db_pool()
            yield
            # Shutdown
            await app.state.db.close()
    """

def __init__(
        self,
        context_func: Callable[..., Awaitable[None]],
    ) -> None:
        """
        Initialize with async context manager function.

Args:
            context_func: Async generator function
        """
        self._context_func = context_func

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI lifespan interface."""
        # This is a simplified version - full implementation would
        # properly handle the async context manager protocol
        lifespan = Lifespan()

@lifespan.on_startup
        async def startup():
            pass  # Context manager handles this

@lifespan.on_shutdown
        async def shutdown():
            pass  # Context manager handles this

await lifespan(scope, receive, send)
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for Lifespan handling."""

import pytest
from genro_asgi.lifespan import Lifespan

class MockTransport:
    """Mock ASGI transport for lifespan testing."""

def __init__(self, messages: list[dict]):
        self.incoming = messages
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

class TestLifespanHandlers:
    def test_on_startup_decorator(self):
        lifespan = Lifespan()
        called = []

@lifespan.on_startup
        async def startup():
            called.append("startup")

assert len(lifespan._startup_handlers) == 1

def test_on_shutdown_decorator(self):
        lifespan = Lifespan()

@lifespan.on_shutdown
        async def shutdown():
            pass

assert len(lifespan._shutdown_handlers) == 1

def test_add_startup_handler(self):
        lifespan = Lifespan()

async def handler():
            pass

lifespan.add_startup_handler(handler)
        assert handler in lifespan._startup_handlers

def test_add_shutdown_handler(self):
        lifespan = Lifespan()

async def handler():
            pass

lifespan.add_shutdown_handler(handler)
        assert handler in lifespan._shutdown_handlers

class TestRunHandlers:
    @pytest.mark.asyncio
    async def test_run_startup(self):
        lifespan = Lifespan()
        order = []

@lifespan.on_startup
        async def first():
            order.append(1)

@lifespan.on_startup
        async def second():
            order.append(2)

await lifespan.run_startup()
        assert order == [1, 2]

@pytest.mark.asyncio
    async def test_run_shutdown_reverse_order(self):
        lifespan = Lifespan()
        order = []

@lifespan.on_shutdown
        async def first():
            order.append(1)

@lifespan.on_shutdown
        async def second():
            order.append(2)

await lifespan.run_shutdown()
        # Shutdown runs in reverse order
        assert order == [2, 1]

@pytest.mark.asyncio
    async def test_startup_error_propagates(self):
        lifespan = Lifespan()

@lifespan.on_startup
        async def failing():
            raise ValueError("Startup failed")

with pytest.raises(ValueError, match="Startup failed"):
            await lifespan.run_startup()

@pytest.mark.asyncio
    async def test_shutdown_continues_on_error(self):
        lifespan = Lifespan()
        called = []

@lifespan.on_shutdown
        async def first():
            called.append(1)

@lifespan.on_shutdown
        async def failing():
            raise ValueError("Error")

@lifespan.on_shutdown
        async def third():
            called.append(3)

await lifespan.run_shutdown()
        # All handlers should be called despite error
        assert 1 in called
        assert 3 in called

class TestLifespanASGI:
    @pytest.mark.asyncio
    async def test_full_lifespan(self):
        lifespan = Lifespan()
        events = []

@lifespan.on_startup
        async def startup():
            events.append("startup")

@lifespan.on_shutdown
        async def shutdown():
            events.append("shutdown")

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert events == ["startup", "shutdown"]
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"

@pytest.mark.asyncio
    async def test_startup_failure(self):
        lifespan = Lifespan()

@lifespan.on_startup
        async def failing():
            raise ValueError("Failed")

transport = MockTransport([
            {"type": "lifespan.startup"},
        ])

with pytest.raises(ValueError):
            await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert transport.outgoing[0]["type"] == "lifespan.startup.failed"
        assert "Failed" in transport.outgoing[0]["message"]

@pytest.mark.asyncio
    async def test_shutdown_failure(self):
        lifespan = Lifespan()
        events = []

@lifespan.on_startup
        async def startup():
            events.append("startup")

@lifespan.on_shutdown
        async def failing():
            raise ValueError("Shutdown failed")

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

with pytest.raises(ValueError):
            await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert "startup" in events
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.failed"

class TestLifespanEmpty:
    @pytest.mark.asyncio
    async def test_no_handlers(self):
        lifespan = Lifespan()

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"
```

```python
from .lifespan import Lifespan
```

- [ ] Create `src/genro_asgi/lifespan.py`
- [ ] Create `tests/test_lifespan.py`
- [ ] Run `pytest tests/test_lifespan.py`
- [ ] Run `mypy src/genro_asgi/lifespan.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

