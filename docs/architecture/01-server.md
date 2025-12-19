# AsgiServer

**Version**: 1.1.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-14

---

## Overview

`AsgiServer` is the root ASGI dispatcher. It inherits from `RoutingClass` (genro-routes)
and can operate in two modes:

1. **Flat mode** (default): Mount apps at paths, dispatch by first segment
2. **Router mode**: Use genro-routes Router for hierarchical routing

---

## Inheritance

```python
from genro_routes import RoutingClass, Router, route

class AsgiServer(RoutingClass):
    """Root ASGI dispatcher."""
```

---

## Routing

`AsgiServer` delegates all routing to **genro-routes**.

See [08-routing.md](08-routing.md) for full documentation on:
- `Router`, `RoutingClass`, `@route` decorator
- Path resolution (uses `/` separator)
- `nodes()` for introspection
- `openapi()` for schema generation
- `FilterPlugin` for tag-based filtering

---

## Class Definition

```python
class AsgiServer(RoutingClass):
    __slots__ = ("apps", "router", "config", "logger", "lifespan", "_started", "__dict__")

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        use_router: bool = False,
    ) -> None:
        self.apps: dict[str, dict[str, Any]] = {}
        self.router: Router | None = None
        self.config = SmartOptions(config or {})
        self.logger = logging.getLogger("genro_asgi")
        self.lifespan = ServerLifespan(self)
        self._started = False

        if use_router:
            self.router = Router(self, name="root")
```

---

## Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `apps` | `dict[str, dict]` | Mounted apps by path (flat mode) |
| `router` | `Router \| None` | genro-routes Router (router mode) |
| `config` | `SmartOptions` | Server configuration |
| `logger` | `Logger` | Server logger |
| `lifespan` | `ServerLifespan` | Manages startup/shutdown |
| `_started` | `bool` | Whether server has started |

---

## Dispatch Modes

### Flat Mode (default)

Apps mounted at paths, dispatched by first path segment:

```python
server = AsgiServer()
server.mount("/api", api_app)      # handles /api/*
server.mount("/stream", stream_app) # handles /stream/*
server.run()
```

Dispatch logic:
1. Extract first path segment: `/api/users/123` → `/api`
2. Lookup in `self.apps` dict (O(1))
3. Call mounted app with modified scope

```
/api/users/123  →  apps["/api"]  →  scope["path"] = "/users/123"
```

### Router Mode

Uses genro-routes for hierarchical routing:

```python
server = AsgiServer(use_router=True)

@route("root")
def index(self):
    return {"status": "ok"}

# Or attach instances
server.docs = DocsApp()
server.router.attach_instance(server.docs, name="docs")
```

Dispatch logic:
1. Convert path to selector: `/docs/info` → `docs/info`
2. Call `router.get(selector)` to find handler
3. Execute handler, convert result to Response

---

## Mount Method

```python
def mount(self, path: str, app: ASGIApp) -> None:
    """
    Mount an ASGI application at a path.

    Args:
        path: Mount path (e.g., "/api"). Must be unique.
        app: ASGI application to mount.

    Raises:
        ValueError: If path is already mounted.
    """
```

Mount behavior:
1. Normalize path (add leading `/`, remove trailing `/`)
2. Check for duplicate path
3. Create app entry dict
4. If app is `AsgiServerEnabler`, attach `ServerBinder`
5. If app is `AsgiServerEnabler`, create `RequestRegistry` for it

```python
app_handler: dict[str, Any] = {
    "app": app,
    "request_registry": RequestRegistry(),  # if AsgiServerEnabler
}
```

---

## ASGI Interface

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    """Handle ASGI request."""
    scope_type = scope["type"]

    # Lifespan events
    if scope_type == "lifespan":
        await self.lifespan(scope, receive, send)
        return

    # Router mode
    if self.router is not None:
        await self._dispatch_router(scope, receive, send)
        return

    # Flat mode
    app_handler = self.get_app_handler(scope)
    registry = app_handler.get("request_registry")

    if registry:
        request = await registry.create(scope, receive, send)
        try:
            await app_handler["app"](scope, receive, send)
        finally:
            registry.unregister(request.id)
    else:
        await app_handler["app"](scope, receive, send)
```

---

## Server-App Integration

### AsgiServerEnabler

Mixin for apps that need server access:

```python
class AsgiServerEnabler:
    """Mixin that enables access to AsgiServer via binder."""
    binder: ServerBinder | None = None
```

### ServerBinder

Controlled interface to server resources:

```python
class ServerBinder:
    def __init__(self, server: AsgiServer):
        self._server = server

    @property
    def config(self) -> SmartOptions:
        return self._server.config

    @property
    def logger(self) -> Logger:
        return self._server.logger

    def executor(self, name: str = "default", ...) -> ExecutorDecorator:
        return self._server.executor(name, ...)
```

### Usage

```python
class MyApp(AsgiServerEnabler):
    async def __call__(self, scope, receive, send):
        self.binder.logger.info("Request received")
        # access self.binder.config, self.binder.executor(), etc.
```

---

## Subclassing AsgiServer

Create custom servers by subclassing:

```python
from genro_asgi import AsgiServer, RedirectResponse
from genro_routes import route

class DocsServer(AsgiServer):
    def __init__(self, modules_dir: Path):
        super().__init__(use_router=True)

        # Attach routed instances
        self.docs = DocsApp(modules_dir)
        self.router.attach_instance(self.docs, name="docs")

        self._sys = SysApi(server=self)
        self.router.attach_instance(self._sys, name="_sys")

    @route("root")
    def index(self) -> RedirectResponse:
        """Override default index."""
        return RedirectResponse("/docs/")
```

---

## Run Method

```python
def run(
    self,
    host: str | None = None,
    port: int | None = None,
    **kwargs: Any,
) -> None:
    """
    Run the server using Uvicorn.

    Args:
        host: Host to bind (default: config or "127.0.0.1")
        port: Port to bind (default: config or 8000)
        **kwargs: Additional uvicorn.run() arguments
    """
    import uvicorn
    uvicorn.run(self, host=host, port=port, **kwargs)
```

---

## Path Resolution

### Flat Mode: get_app_handler

```python
def get_app_handler(self, scope: Scope) -> dict[str, Any]:
    """Get app_handler and modify scope for sub-app."""
    path = scope.get("path", "/")

    # Extract first segment: "/api/users/123" -> "/api"
    if path == "/":
        prefix = "/"
    else:
        parts = path.split("/", 2)
        prefix = "/" + parts[1] if len(parts) > 1 else "/"

    app_handler = self.apps.get(prefix)
    if app_handler is None:
        raise HTTPException(404, detail=f"Application not found: {prefix}")

    # Modify scope for sub-app
    scope["root_path"] = scope.get("root_path", "") + prefix
    scope["path"] = path[len(prefix):] or "/"
    return app_handler
```

### Router Mode: Path as Selector

genro-routes now uses `/` as path separator (same as URL), so no conversion needed:

```python
# URL path is used directly as selector
"/" → "index"
"/sites" → "sites"
"/_sys/sites" → "_sys/sites"
```

---

## Error Handling

### 404 Not Found

Flat mode raises `HTTPException(404)`.
Router mode returns `JSONResponse({"error": "Not found"}, status_code=404)`.

### WebSocket 404

For WebSocket, close with code 4404:
```python
await send({"type": "websocket.close", "code": 4404})
```

---

## Architecture Diagram

```
┌─────────────┐         ┌─────────────────────────────────────────────────────────┐
│   Uvicorn   │         │  AsgiServer (RoutingClass)                               │
│   :8000     │ ──────► │                                                         │
│             │         │  Flat Mode:                                             │
│             │         │    /api/*     → apps["/api"] + RequestRegistry          │
│             │         │    /stream/*  → apps["/stream"]                         │
│             │         │                                                         │
│             │         │  Router Mode:                                           │
│             │         │    /           → router.get("index")                    │
│             │         │    /docs/info  → router.get("docs/info")                │
└─────────────┘         └─────────────────────────────────────────────────────────┘
```

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
