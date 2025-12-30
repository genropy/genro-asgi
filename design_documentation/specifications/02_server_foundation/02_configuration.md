# Configuration System

genro-asgi uses a layered configuration system built on **genro-toolbox SmartOptions**. Configuration can come from YAML files, environment variables, CLI arguments, and programmatic parameters.

## Source Location

**File**: `src/genro_asgi/server_config.py`

## Configuration Precedence

Later sources override earlier ones:

```text
1. Built-in DEFAULTS           (lowest priority)
2. Global config: ~/.genro-asgi/config.yaml
3. Project config: <server_dir>/config.yaml
4. Environment variables: GENRO_ASGI_*
5. Command line arguments
6. Explicit constructor parameters  (highest priority)
```

## ServerConfig Class

```python
class ServerConfig:
    """Handles server configuration loading and app instantiation."""

    __slots__ = ("_opts", "_openapi")

    def __init__(
        self,
        server_dir: str | Path | None = None,
        host: str | None = None,
        port: int | None = None,
        reload: bool | None = None,
        argv: list[str] | None = None,
    ) -> None:
        self._opts = self._build_config(...)
```

### Properties

| Property | Type | Description |
| -------- | ---- | ----------- |
| `server` | `SmartOptions` | Server options (host, port, reload, server_dir) |
| `middleware` | `list[Any]` | Middleware configuration |
| `plugins` | `SmartOptions \| None` | Router plugins configuration |
| `apps` | `SmartOptions \| None` | Applications configuration |
| `openapi` | `dict[str, Any]` | OpenAPI info as plain dict |
| `server_dir` | `Path` | Resolved server directory path |

### Methods

| Method | Returns | Description |
| ------ | ------- | ----------- |
| `get_plugin_specs()` | `dict[str, dict]` | `{plugin_name: opts_dict}` |
| `get_app_specs_raw()` | `dict[str, tuple]` | `{name: (module, class, kwargs)}` |

## SmartOptions (genro-toolbox)

SmartOptions is the configuration engine from genro-toolbox:

```python
from genro_toolbox import SmartOptions

# Multiple sources
config = SmartOptions("config.yaml")                    # YAML file
config = SmartOptions({"host": "0.0.0.0"})             # Dict
config = SmartOptions(func, env="MYAPP")               # Env vars with type hints
config = SmartOptions(func, argv=sys.argv[1:])         # CLI args with type hints
```

### Merge with `+` Operator

```python
config = SmartOptions(DEFAULTS) + SmartOptions("config.yaml") + SmartOptions(overrides)
# Right side wins on conflicts
```

### Safe Access

```python
opts.host           # Attribute access
opts["host"]        # Bracket access
opts.missing_key    # → None (no AttributeError)
"host" in opts      # → True/False
opts.as_dict()      # → dict copy
```

### Type Extraction from Functions

SmartOptions can extract types from a function signature for automatic conversion:

```python
def _server_opts_spec(
    server_dir: str,
    host: str,
    port: int,     # ← Will convert "9000" to 9000
    reload: bool,  # ← Will convert "true" to True
) -> None:
    """Reference function for type extraction."""
    pass

# Environment variable GENRO_ASGI_PORT="9000" becomes port=9000 (int)
config = SmartOptions(_server_opts_spec, env="GENRO_ASGI", argv=argv)
```

## Configuration Building

The `_build_config()` method assembles configuration:

```python
def _build_config(self, server_dir, host, port, reload, argv):
    # 1. Parse env + argv using spec function for type conversion
    env_argv_opts = SmartOptions(_server_opts_spec, env="GENRO_ASGI", argv=argv)

    # 2. Explicit parameters from caller (ignores None)
    caller_opts = SmartOptions(
        dict(server_dir=server_dir, host=host, port=port, reload=reload),
        ignore_none=True,
    )

    # 3. Resolve server directory
    resolved_server_dir = Path(
        caller_opts["server_dir"] or env_argv_opts["server_dir"] or "."
    ).resolve()

    # 4. Load global config (~/.genro-asgi/config.yaml)
    global_config_path = Path.home() / ".genro-asgi" / "config.yaml"
    global_config = SmartOptions(str(global_config_path)) if global_config_path.exists() else SmartOptions({})

    # 5. Load project config (<server_dir>/config.yaml)
    project_config = SmartOptions(str(resolved_server_dir / "config.yaml"))

    # 6. Merge all configs
    config = global_config + project_config

    # 7. Build server options with full precedence chain
    server_opts = (
        SmartOptions(DEFAULTS)
        + (global_config["server"] or SmartOptions({}))
        + (project_config["server"] or SmartOptions({}))
        + env_argv_opts
        + caller_opts
    )
    server_opts["server_dir"] = resolved_server_dir

    config["server"] = server_opts
    return config
```

## YAML Configuration Structure

### Complete Example

```yaml
# config.yaml

# Server settings
server:
  host: "0.0.0.0"
  port: 8000
  reload: false
  main_app: shop        # Optional: default app for redirect

# OpenAPI metadata
openapi:
  title: "My API"
  version: "1.0.0"
  description: "API description"

# Middleware configuration
middleware:
  errors: on
  cors: on
  auth: on
  compression: off
  logging: off

# Middleware-specific settings
cors_middleware:
  allow_origins: ["*"]
  allow_methods: ["GET", "POST", "PUT", "DELETE"]
  allow_credentials: false

auth_middleware:
  bearer:
    reader_token:
      token: "tk_abc123"
      tags: "read"
  basic:
    admin:
      password: "secret"
      tags: "admin"

# Router plugins
plugins:
  logging:
    level: info
  pydantic:
    strict: false

# Applications
apps:
  shop:
    module: "main:ShopApp"
    db_uri: "sqlite:///shop.db"
    cache_timeout: 300

  admin:
    module: "admin:AdminApp"
    require_auth: true

  docs:
    module: "genro_asgi:StaticRouter"
    directory: "./public"
```

## Server Section

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `host` | `str` | `"127.0.0.1"` | Bind address |
| `port` | `int` | `8000` | Listen port |
| `reload` | `bool` | `false` | Auto-reload on file changes |
| `main_app` | `str` | `None` | Default app for `/` redirect |

**Built-in defaults**:

```python
DEFAULTS = {"host": "127.0.0.1", "port": 8000, "reload": False}
```

## Middleware Section

Middleware are configured as a dict where keys identify the middleware:

```yaml
middleware:
  cors: on        # Enable
  auth: on        # Enable
  errors: on      # Enable (usually default=True)
  compression: off # Disable
```

### Middleware-Specific Configuration

Each middleware can have additional configuration in a `{name}_middleware` section:

```yaml
# Enable middleware
middleware:
  cors: on

# Configure it
cors_middleware:
  allow_origins: ["https://example.com"]
  allow_methods: ["GET", "POST"]
  max_age: 3600
```

### Available Middleware

| Key | Class | Default | Order | Purpose |
| --- | ----- | ------- | ----- | ------- |
| `errors` | `ErrorMiddleware` | `True` | 100 | Exception handling |
| `logging` | `LoggingMiddleware` | `False` | 200 | Request logging |
| `cors` | `CORSMiddleware` | `False` | 300 | CORS headers |
| `auth` | `AuthMiddleware` | `False` | 400 | Authentication |
| `compression` | `CompressionMiddleware` | `False` | 900 | Gzip responses |
| `cache` | `CacheMiddleware` | `False` | 900 | Response caching |
| `static` | `StaticMiddleware` | `False` | 800 | Static files |

### Middleware Configuration Options

**cors_middleware**:

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `allow_origins` | `list[str]` | `["*"]` | Allowed origins |
| `allow_methods` | `list[str]` | `["GET"]` | Allowed methods |
| `allow_headers` | `list[str]` | `[]` | Allowed headers |
| `allow_credentials` | `bool` | `false` | Allow credentials |
| `max_age` | `int` | `600` | Preflight cache seconds |

**auth_middleware**:

```yaml
auth_middleware:
  bearer:                    # Bearer token auth
    token_name:
      token: "secret_token"
      tags: "read,write"
  basic:                     # Basic auth
    username:
      password: "password"
      tags: "admin"
  jwt:                       # JWT auth
    secret: "jwt_secret"
    algorithms: ["HS256"]
```

**compression_middleware**:

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `minimum_size` | `int` | `500` | Min bytes to compress |
| `compression_level` | `int` | `6` | Gzip level (1-9) |

**logging_middleware**:

| Option | Type | Default | Description |
| ------ | ---- | ------- | ----------- |
| `level` | `str` | `"INFO"` | Log level |
| `include_headers` | `bool` | `false` | Log headers |
| `include_query` | `bool` | `true` | Log query params |

## Plugins Section

Router plugins from genro-routes are configured in `plugins`:

```yaml
plugins:
  logging:
    level: debug
  pydantic:
    strict: true
```

These are applied to all routers via `router.plug(name, **opts)`.

### Middleware vs Plugins

| | Middleware | Plugins |
| - | ---------- | ------- |
| **Level** | ASGI request/response | Individual handler |
| **Scope** | Whole server or per-app | Per-router, per-handler |
| **Config** | `middleware:` | `plugins:` |
| **Examples** | CORS, Compression | Logging, Validation |

## Apps Section

Applications can be configured in two formats:

### Simple Format

For apps with no parameters:

```yaml
apps:
  shop: "main:ShopApp"
  office: "office:OfficeApp"
```

### Extended Format

For apps with configuration:

```yaml
apps:
  shop:
    module: "main:ShopApp"
    db_uri: "sqlite:///shop.db"    # Passed to __init__
    cache_timeout: 300              # Passed to __init__

  static:
    module: "genro_asgi:StaticRouter"
    directory: "./public"
    index: "index.html"
```

**Key**: `module` specifies the class to instantiate (`"module_path:ClassName"`).
**Other keys**: Passed to the app constructor as kwargs.

### App Parsing

```python
def get_app_specs_raw(self) -> dict[str, tuple[str, str, dict[str, Any]]]:
    """Return {name: (module_name, class_name, kwargs)}."""
    result = {}
    for name, app_opts in self.apps.as_dict().items():
        if isinstance(app_opts, str):
            # Simple: "main:ShopApp"
            module_name, class_name = app_opts.split(":")
            kwargs = {}
        else:
            # Extended: dict with module + params
            module_name, class_name = app_opts["module"].split(":")
            kwargs = {k: v for k, v in app_opts.items() if k != "module"}
        result[name] = (module_name, class_name, kwargs)
    return result
```

## Environment Variables

Environment variables use the `GENRO_ASGI_` prefix:

| Variable | Maps to |
| -------- | ------- |
| `GENRO_ASGI_HOST` | `server.host` |
| `GENRO_ASGI_PORT` | `server.port` |
| `GENRO_ASGI_RELOAD` | `server.reload` |
| `GENRO_ASGI_SERVER_DIR` | `server.server_dir` |

**Type conversion** is automatic based on the spec function.

## CLI Arguments

```bash
genro-asgi serve <server_dir> [options]

Options:
  --host HOST     Server host (default: 127.0.0.1)
  --port PORT     Server port (default: 8000)
  --reload        Enable auto-reload
```

## Configuration Access in Code

### In Server

```python
# Direct access
host = self.config.server["host"]
port = self.config.server["port"]

# Apps
for name, (module, cls, kwargs) in self.config.get_app_specs_raw().items():
    ...

# Middleware
middleware_config = self.config.middleware
```

### In Application

```python
class MyApp(AsgiApplication):
    def on_init(self, db_uri: str, cache_timeout: int = 300, **kwargs):
        # Parameters come from config.yaml apps section
        self.db_uri = db_uri
        self.cache_timeout = cache_timeout
```

## OpenAPI Section

```yaml
openapi:
  title: "My API"
  version: "1.0.0"
  description: "API description"
  contact:
    name: "Support"
    email: "support@example.com"
  license:
    name: "MIT"
```

Defaults if not specified:

```python
{"title": "genro-asgi API", "version": "0.1.0"}
```

## Global vs Project Config

**Global config**: `~/.genro-asgi/config.yaml`

- User-wide defaults
- Useful for development settings

**Project config**: `<server_dir>/config.yaml`

- Project-specific settings
- Committed to repository

**Merge behavior**: Project config overrides global config.

## Design Decisions

### 1. SmartOptions as Configuration Engine

genro-toolbox's SmartOptions provides:

- Multi-source loading (YAML, dict, env, argv)
- Type-safe conversion via function signatures
- Merge semantics with `+` operator
- Safe access (missing keys return None)

### 2. Middleware in Dict Format

```yaml
# Dict format (current)
middleware:
  cors: on
  auth: on
```

Not list format, because:

- Easier to override specific middleware
- Clearer on/off semantics
- Consistent with plugins format

### 3. `module` Key for Apps

```yaml
apps:
  shop:
    module: "main:ShopApp"  # Not "type" or "class"
```

Using `module` because:

- `type` is a Python builtin
- `module` is explicit about what's being imported
- Consistent with Python terminology

## Related Documents

- [AsgiServer](01_asgi_server.md) - Server architecture
- [Server Lifecycle](03_lifecycle.md) - Startup/shutdown
- [Middleware Chain](../06_security_and_middleware/01_middleware_chain.md) - Middleware system
