# Lifespan

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## Overview

`ServerLifespan` manages startup and shutdown sequences for `AsgiServer`.

Responsibilities:
- Initialize server resources (config, logger, executors)
- Call sub-app `on_startup` hooks
- Handle shutdown in reverse order
- Report startup failures to ASGI server

---

## ServerLifespan Class

```python
class ServerLifespan:
    """Manages AsgiServer startup/shutdown lifecycle."""

    def __init__(self, server: AsgiServer) -> None:
        self.server = server

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle ASGI lifespan events."""
        while True:
            message = await receive()
            msg_type = message["type"]

            if msg_type == "lifespan.startup":
                try:
                    await self._startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    await send({
                        "type": "lifespan.startup.failed",
                        "message": str(e),
                    })
                    return

            elif msg_type == "lifespan.shutdown":
                await self._shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return
```

---

## Startup Sequence

```python
async def _startup(self) -> None:
    """Execute startup sequence."""
    # 1. Server resources first
    await self._init_config()
    await self._init_logger()
    await self._init_executors()

    # 2. Sub-apps in mount order
    for path, app_handler in self.server.apps.items():
        app = app_handler["app"]
        if hasattr(app, "on_startup"):
            self.server.logger.info(f"Starting app at {path}")
            await app.on_startup()

    self.server._started = True
    self.server.logger.info("Server started")
```

---

## Shutdown Sequence

```python
async def _shutdown(self) -> None:
    """Execute shutdown sequence."""
    self.server.logger.info("Server shutting down")

    # 1. Sub-apps in REVERSE order
    for path in reversed(list(self.server.apps.keys())):
        app_handler = self.server.apps[path]
        app = app_handler["app"]
        if hasattr(app, "on_shutdown"):
            self.server.logger.info(f"Stopping app at {path}")
            await app.on_shutdown()

    # 2. Server resources last
    self.server.shutdown()  # Executors

    self.server._started = False
    self.server.logger.info("Server stopped")
```

---

## Startup/Shutdown Order

| Phase | Startup Order | Shutdown Order |
|-------|---------------|----------------|
| 1 | Config | Sub-apps (reverse) |
| 2 | Logger | Executors |
| 3 | Executors | Logger |
| 4 | Sub-apps (mount order) | Config |

**Principle**: Resources are shut down in reverse order of creation.
Sub-apps may depend on server resources, so server shuts down last.

---

## Sub-App Hooks

Apps can define async hooks:

```python
class MyApp(AsgiServerEnabler):
    async def on_startup(self) -> None:
        """Called when server starts."""
        self.db = await create_db_pool()
        self.binder.logger.info("Database pool created")

    async def on_shutdown(self) -> None:
        """Called when server stops."""
        await self.db.close()
        self.binder.logger.info("Database pool closed")

    async def __call__(self, scope, receive, send):
        # ... handle requests
```

---

## Error Handling

### Startup Failure

If any startup step fails, server reports failure:

```python
try:
    await self._startup()
    await send({"type": "lifespan.startup.complete"})
except Exception as e:
    self.server.logger.error(f"Startup failed: {e}")
    await send({
        "type": "lifespan.startup.failed",
        "message": str(e),
    })
    return  # Don't wait for shutdown
```

### Shutdown Errors

Shutdown continues even if one app fails:

```python
for path in reversed(list(self.server.apps.keys())):
    app = self.server.apps[path]["app"]
    if hasattr(app, "on_shutdown"):
        try:
            await app.on_shutdown()
        except Exception as e:
            self.server.logger.error(f"Shutdown error for {path}: {e}")
            # Continue with other apps
```

---

## ASGI Lifespan Protocol

Lifespan events follow ASGI spec:

```
Server                          Uvicorn
------                          -------
                  <--           lifespan.startup
startup sequence
lifespan.startup.complete -->
                                (server running)
                  <--           lifespan.shutdown
shutdown sequence
lifespan.shutdown.complete -->
```

---

## Usage with AsgiServer

`ServerLifespan` is automatically created by `AsgiServer`:

```python
class AsgiServer(RoutedClass):
    def __init__(self, ...):
        self.lifespan = ServerLifespan(self)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
            return
        # ... handle http/websocket
```

---

## Testing Without Lifespan

For testing, you can skip lifespan:

```python
# Direct call without lifespan
server = AsgiServer()
server.mount("/api", api_app)

# Call directly
await server(scope, receive, send)

# Or manually trigger startup
await server.lifespan._startup()
try:
    await server(scope, receive, send)
finally:
    await server.lifespan._shutdown()
```

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
