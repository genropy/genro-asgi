# Core Principles

genro-asgi is built on five foundational principles that guide all architectural decisions.

## 1. Instance Isolation (No Global State)

**The most important principle**: All state lives inside instances, never at module level.

### Why This Matters

```python
# ✅ CORRECT: State inside instance
class AsgiServer(RoutingClass):
    def __init__(self, server_dir):
        self.apps = {}                    # Instance state
        self.router = Router(self, name="root")
        self.request_registry = RequestRegistry()

server = AsgiServer(server_dir=".")
del server  # → Everything garbage collected, zero residue
```

```python
# ❌ WRONG: Global state at module level
_apps = {}              # Module-level mutable state
_current_server = None  # Global singleton

def get_server():
    global _current_server
    return _current_server
```

### Benefits

- **Clean testing**: Each test creates fresh instances, no state bleed
- **Hot reload**: No residual state between reloads
- **Multi-tenant**: Multiple server instances can coexist
- **Predictable**: Behavior is deterministic, no hidden globals

### Pattern: Dual Parent-Child Relationship

Every child object maintains a semantic reference to its parent:

```python
# Server creates Dispatcher passing itself
class AsgiServer:
    def __init__(self):
        self.dispatcher = Dispatcher(self)

# Dispatcher stores semantic reference (NOT generic "_parent")
class Dispatcher:
    def __init__(self, server: AsgiServer):
        self.server = server  # Semantic name, not "_parent"
```

## 2. Explicit Configuration (No Magic)

Configuration is explicit and behavior is predictable. No hidden conventions or auto-discovery.

### Configuration via YAML

```yaml
# config.yaml - explicit, readable, no surprises
server:
  host: "127.0.0.1"
  port: 8000
  reload: true

middleware:
  errors: on
  cors: on
  auth: on

apps:
  shop:
    module: "main:ShopApp"
    connection_string: "sqlite:shop.db"  # Explicit param
```

### No Auto-Discovery

```python
# ❌ WRONG: Magic auto-discovery
class Framework:
    def __init__(self):
        self.apps = self._discover_apps()  # Where? What order?

# ✅ CORRECT: Explicit mounting
class AsgiServer:
    def __init__(self, server_dir):
        for name, spec in config.get_app_specs().items():
            self._mount_app(name, spec)  # Explicit, traceable
```

### Explicit Routing

```python
class MyApp(AsgiApplication):
    @route("main")  # Explicit router name
    def endpoint(self):
        return {"data": "value"}

    # NOT: @route()  # Which router? Ambiguous if multiple exist
```

## 3. Composable Architecture

Built as independent components that can be combined, replaced, or extended.

### Middleware Chain

```text
Request
   │
   ▼
ErrorMiddleware ──────┐
   │                  │ Each middleware is
CORSMiddleware ───────┤ independent and
   │                  │ replaceable
AuthMiddleware ───────┘
   │
   ▼
Dispatcher
   │
   ▼
Handler
```

### Application Composition

```python
# Apps are independent units
class ShopApp(AsgiApplication):
    openapi_info = {"title": "Shop API"}

class AdminApp(AsgiApplication):
    openapi_info = {"title": "Admin API"}

# Composed at server level via config
# apps:
#   shop: "main:ShopApp"
#   admin: "admin:AdminApp"
```

### Router Composition

```python
# Routers can be nested
class MyApp(AsgiApplication):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # Creates self.main
        self.backoffice = Router(self, name="backoffice")
        self.main.attach_instance(self.backoffice, name="admin")
```

## 4. Type Safety

Extensive use of type hints for maintainability and IDE support.

### Type Hints Throughout

```python
from typing import Any
from .types import Scope, Receive, Send

class AsgiServer:
    apps: dict[str, AsgiApplication]
    router: Router
    config: ServerConfig

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        ...
```

### Type-Tagged Serialization (genro-tytx)

Preserve Python types across HTTP transport:

| Python Type | Wire Format | Restored As |
| ----------- | ----------- | ----------- |
| `Decimal("99.99")` | `"99.99::N"` | `Decimal("99.99")` |
| `date(2025, 1, 15)` | `"2025-01-15::D"` | `date(2025, 1, 15)` |
| `datetime(...)` | `"2025-01-15T10:30:00::DHZ"` | `datetime(...)` |

### Mypy Strict Mode

```toml
# pyproject.toml
[tool.mypy]
python_version = "3.10"
disallow_untyped_defs = true
warn_return_any = true
```

## 5. Minimal External Dependencies

Only essential dependencies for core functionality.

### Current Dependencies

| Package | Version | Purpose |
| ------- | ------- | ------- |
| `genro-routes` | ≥0.1.0 | Instance-scoped routing |
| `genro-toolbox` | ≥0.2.0 | SmartOptions, AppLoader |
| `genro-tytx` | ≥0.1.0 | Type-tagged serialization |
| `smartasync` | ≥0.5.0 | Async/sync bridging |
| `uvicorn` | ≥0.30.0 | ASGI server |
| `pyyaml` | ≥6.0 | YAML configuration |

### Optional Dependencies

| Package | Purpose | Install with |
| ------- | ------- | ------------ |
| `orjson` | Fast JSON (optional) | `pip install genro-asgi[json]` |
| `pyjwt` | JWT authentication | Auto-detected |

### No Heavy Frameworks

genro-asgi does NOT depend on:

- Django, Flask, or other full-stack frameworks
- SQLAlchemy or any ORM
- Pydantic (optional via genro-routes plugin)
- Jinja2 or templating engines

## Summary: The Five Principles

| # | Principle | Key Rule |
| - | --------- | -------- |
| 1 | Instance Isolation | All state in instances, never module-level |
| 2 | Explicit Configuration | No magic, no auto-discovery |
| 3 | Composable Architecture | Independent, replaceable components |
| 4 | Type Safety | Full type hints, mypy strict |
| 5 | Minimal Dependencies | Essential packages only |

## Related Documents

- [Vision and Goals](01_vision_and_goals.md) - Project overview
- [Terminology](03_terminology.md) - Glossary of terms
- [Server Architecture](../02_server_foundation/01_server_architecture.md) - Detailed server design
