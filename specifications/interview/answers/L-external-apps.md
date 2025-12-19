# L. External Apps Integration

## Q: Can I mount external ASGI applications on AsgiServer?

**A:** Yes. External ASGI apps (Starlette, FastAPI, Litestar, etc.) can be mounted on AsgiServer. They can optionally gain access to server resources via the `AsgiServerEnabler` mixin.

---

## Basic Mounting

Any ASGI callable can be mounted:

```yaml
# config.yaml
apps:
  api:
    module: "myapp:app"  # FastAPI/Starlette instance
```

The app works as-is, but has no access to server resources.

---

## With Server Access

To access server resources (config, logger, executors), use `AsgiServerEnabler`:

```python
from fastapi import FastAPI
from genro_asgi import AsgiServerEnabler

class MyFastAPI(FastAPI, AsgiServerEnabler):
    """FastAPI app with access to AsgiServer resources."""
    pass

app = MyFastAPI()

@app.get("/info")
def info():
    if app.binder:
        app.binder.logger.info("Request received")
        return {"debug": app.binder.config.debug}
    return {"debug": False}
```

---

## How It Works

1. **`AsgiServerEnabler`** is a mixin class (no `__call__`)
2. Put it **LAST** in inheritance (so framework's `__call__` is used)
3. When mounted on AsgiServer, server sets `app.binder = ServerBinder(self)`
4. **`ServerBinder`** provides controlled access to:
   - `binder.config` - server configuration
   - `binder.logger` - server logger
   - `binder.executor(name)` - named executor pools

---

## Standalone Compatibility

Apps using `AsgiServerEnabler` still work standalone:

```python
# When mounted on AsgiServer
app.binder  # → ServerBinder instance

# When running standalone (uvicorn myapp:app)
app.binder  # → None
```

Always check `if app.binder:` before using server resources.

---

## Implementation

```python
# genro_asgi/utils/binder.py

class ServerBinder:
    """Controlled interface to server resources."""

    def __init__(self, server):
        self._server = server

    @property
    def config(self):
        return self._server.config

    @property
    def logger(self):
        return self._server.logger

    def executor(self, name="default", **kwargs):
        return self._server.executor(name, **kwargs)


class AsgiServerEnabler:
    """Mixin for external apps that need server access."""
    binder: ServerBinder | None = None
```

---

## When to Use

| Scenario | Solution |
|----------|----------|
| External app, no server features needed | Just mount it |
| External app needs config/logger | Use `AsgiServerEnabler` mixin |
| New app for genro-asgi | Inherit from `AsgiApplication` |

---

## Key Points

- `AsgiServerEnabler` is **optional** - only for apps needing server resources
- Mixin pattern preserves framework's behavior
- `binder` is `None` when running standalone
- `AsgiApplication` (for native apps) inherits from `RoutingClass`, not `AsgiServerEnabler`
