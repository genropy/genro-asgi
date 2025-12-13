# E. Configuration (via genro-toolbox)

**Date**: 2025-12-13
**Status**: Verified
**Verified in**: `server.py`, `config.py`, genro-toolbox documentation

---

## Dependency

genro-asgi uses **genro-toolbox** for configuration. Full documentation in:
`specifications/dependencies/genro-toolbox.md`

## SmartOptions

Class for managing configurations from multiple sources with automatic merge.

**Supported sources**:

| Source | Example |
|--------|---------|
| Dict | `SmartOptions({"host": "0.0.0.0"})` |
| YAML/JSON/TOML file | `SmartOptions("config.yaml")` |
| Environment variables | `SmartOptions(func, env="MYAPP")` |
| Callable signature | `SmartOptions(func)` - extracts defaults and types |
| argv | `SmartOptions(func, argv=sys.argv[1:])` |

## Merge Priority in genro-asgi

```text
DEFAULTS < config.yaml < GENRO_ASGI_* env < argv < explicit params
```

Rightmost value wins.

## Pattern in server.py

```python
# "spec" function for type extraction
def _server_opts_spec(
    app_dir: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Reference function for SmartOptions type extraction."""
    pass

# Merge chain in _configure()
env_argv_opts = SmartOptions(_server_opts_spec, env="GENRO_ASGI", argv=argv)
caller_opts = SmartOptions(dict(...), ignore_none=True)
config = SmartOptions(str(app_dir / "config.yaml"))

server_opts = (
    SmartOptions(DEFAULTS)
    + (config.server or SmartOptions({}))
    + env_argv_opts
    + caller_opts
)
```

## Key Features

1. **Automatic type conversion**: env and argv converted to signature type
2. **`+` operator**: merge with right-side-wins
3. **Automatic wrapping**: nested dicts → recursive SmartOptions
4. **Safe access**: `opts.missing` → `None`, not AttributeError
5. **String lists → flags**: `["cors", "gzip"]` → `SmartOptions(cors=True, gzip=True)`

## Middleware Configuration

Middleware are configured as a dict where the key identifies the middleware:

```yaml
middleware:
  cors:
    allow_origins: ["*"]
    allow_methods: ["GET", "POST", "PUT", "DELETE"]
    allow_credentials: false

  compression:
    minimum_size: 500
    compression_level: 6

  logging:
    level: INFO
    include_headers: false

  error:
    debug: false
```

**Key** (e.g., `cors`, `compression`): identifies the middleware class.
**Value**: dict of options passed to the middleware constructor.

### Key → Class mapping

| Key | Class | Purpose |
|-----|-------|---------|
| `cors` | `CORSMiddleware` | Cross-Origin Resource Sharing |
| `compression` | `CompressionMiddleware` | Gzip compression |
| `logging` | `LoggingMiddleware` | Request/response logging |
| `error` | `ErrorMiddleware` | Error handling |

### Available middleware options

| Middleware | Key Options |
|------------|-------------|
| `cors` | allow_origins, allow_methods, allow_credentials, max_age |
| `compression` | minimum_size (default: 500), compression_level (1-9) |
| `logging` | logger_name, level, include_headers, include_query |
| `error` | debug (show traceback) |

### Middleware order

Middleware are applied in key order (first key = outermost).

```text
Request → [cors → [compression → [logging → [error → [App]]]]] → Response
```

## Routes Plugins Configuration

Plugins (from genro-routes) are configured as a dict where the key identifies the plugin:

```yaml
routesplugins:
  logging:
    level: debug

  pydantic:
    strict: true
```

**Key** (e.g., `logging`, `pydantic`): identifies the plugin class.
**Value**: dict of options passed to the plugin.

### Middleware vs Plugins

| | Middleware | Plugins |
|---|---|---|
| **Level** | ASGI request/response | Individual handler/method |
| **Scope** | Whole application or per-app | Per-router, per-handler |
| **Config section** | `middleware:` | `routesplugins:` |
| **Examples** | CORS, Compression, Logging | Auth, Validation, Debug |

## Per-App Middleware and Plugins

Middleware and plugins can be configured at **global level** (all apps) or **per-app level**:

```yaml
# Global middleware (applied to all apps)
middleware:
  cors:
    allow_origins: ["*"]
  error:
    debug: false

# Global plugins (applied to all handlers)
routesplugins:
  logging:
    level: info

apps:
  shop:
    module: "shop:ShopApp"
    db: "shop.db"
    # App-specific middleware (only this app)
    middleware:
      compression:
        minimum_size: 1000
    # App-specific plugins (only handlers in this app)
    routesplugins:
      pydantic:
        strict: true
      auth:
        required: true

  admin:
    module: "admin:AdminApp"
    middleware:
      logging:
        level: DEBUG
        include_headers: true

  public: "public:PublicApp"  # Uses only global middleware/plugins
```

### Merge behavior

| Level | Behavior |
|-------|----------|
| **Global** | Applied to all apps |
| **Per-app** | Merged with global (same key = override, different key = add) |

**Example**: If global has `compression.minimum_size: 500` and app has `compression.minimum_size: 1000`, the app uses `1000`.

### Application order

```text
Request → [Global MW → [App MW → [Handler + Global Plugins + App Plugins]]]
```

### Runtime plugin configuration

Plugins can also be configured at runtime via `routedclass.configure()`:

```python
# Global - all handlers
app.routedclass.configure("api:logging/_all_", level="debug")

# Specific handler
app.routedclass.configure("api:logging/create_order", enabled=False)

# Glob pattern
app.routedclass.configure("api:logging/admin_*", level="debug")
```

## Apps Configuration

Apps can be configured in two formats:

### Simple format (string)

For apps that need no parameters:

```yaml
apps:
  shop: "shop:ShopApp"
  office: "office:OfficeApp"
```

The string is `"module_name:ClassName"`.

### Extended format (dict with `module`)

For apps that need parameters:

```yaml
apps:
  shop:
    module: "shop:ShopApp"
    db: "shop.db"
    cache_timeout: 300

  static:
    module: "genro_asgi:StaticSite"
    directory: "./public"
    index: "index.html"
```

**Key**: `module` specifies the class to instantiate.
**Other keys**: passed to the app constructor as kwargs.

### How Server loads apps

```python
for name, app_config in config.apps.items():
    if isinstance(app_config, str):
        # Simple format: "shop:ShopApp"
        module_path, class_name = app_config.split(":")
        app_class = import_class(module_path, class_name)
        app = app_class()
    else:
        # Extended format: dict with module + params
        module_path, class_name = app_config.module.split(":")
        app_class = import_class(module_path, class_name)
        params = {k: v for k, v in app_config.items() if k != "module"}
        app = app_class(**params)

    self.mount(name, app)
```

### Why `module` not `type`

- `type` is a Python builtin → potential conflicts
- `module` is explicit: "which module to import"
- Consistent with Python terminology

## Complete config.yaml Example

```yaml
# Server configuration
server:
  host: "0.0.0.0"
  port: 8000
  reload: false

# Global ASGI Middleware (applied to all apps)
middleware:
  cors:
    allow_origins: ["*"]
    allow_credentials: false
  error:
    debug: false

# Global Routes Plugins (applied to all handlers)
routesplugins:
  logging:
    level: info

# Mounted applications
apps:
  shop:
    module: "shop:ShopApp"
    db: "shop.db"
    # App-specific middleware
    middleware:
      compression:
        minimum_size: 1000
    # App-specific plugins
    routesplugins:
      pydantic:
        strict: true

  office: "office:OfficeApp"

  docs:
    module: "genro_asgi:StaticSite"
    directory: "./public"
```

## Role in the Ecosystem

**genro-toolbox is a mandatory dependency** of all Genro libraries.

Philosophy: "Same patterns everywhere, never reinvent the wheel"

- Consistency: same pattern everywhere
- Familiarity: learn once, use always
- Maintainability: fix in toolbox → benefits all
