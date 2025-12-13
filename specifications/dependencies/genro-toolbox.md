# genro-toolbox - Summary for genro-asgi

## What it is

`genro-toolbox` is a utilities library for the Genro ecosystem.
Zero external dependencies (stdlib only).

**Package**: `genro-toolbox` on PyPI
**Import**: `from genro_toolbox import SmartOptions`

---

## SmartOptions

### Purpose

Class for managing configurations from multiple sources with automatic merge.
Extends `SimpleNamespace`.

### Supported sources

| Source | Example |
|--------|---------|
| Dict | `SmartOptions({"host": "0.0.0.0"})` |
| YAML/JSON/TOML/INI file | `SmartOptions("config.yaml")` |
| Environment variables | `SmartOptions(func, env="MYAPP")` |
| Callable signature | `SmartOptions(func)` - extracts defaults and types |
| argv | `SmartOptions(func, argv=sys.argv[1:])` |

### Merge priority

```text
defaults < env < argv < caller_opts
```

Rightmost value wins.

### `+` operator

```python
config = SmartOptions('config.yaml') + SmartOptions({"override": True})
```

Right side overrides left side.

### Automatic wrapping

When loading from file:

- **Nested dicts** → become `SmartOptions` recursively
- **String lists** → become feature flags (`["cors", "gzip"]` → `SmartOptions(cors=True, gzip=True)`)
- **Dict lists** → indexed by first key of first element

### Value access

```python
opts.host           # attribute access
opts['host']        # bracket access
opts.missing_key    # → None (no AttributeError)
'host' in opts      # → True/False
for key in opts:    # iterate keys
opts.as_dict()      # → dict copy
```

### Automatic type conversion

When using a callable as source:
- Extracts type hints from signature
- Automatically converts env and argv to correct type

```python
def serve(host: str = '127.0.0.1', port: int = 8000, debug: bool = False):
    pass

config = SmartOptions(serve, env='MYAPP', argv=['--port', '9000'])
config.port  # → 9000 (int, not str!)
```

---

## How genro-asgi uses SmartOptions

### In `server.py`

```python
def _server_opts_spec(
    app_dir: str,
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Reference function for SmartOptions type extraction."""
    pass
```

This "dummy" function serves only to define:
1. **Names** of accepted parameters
2. **Types** for automatic conversion
3. **Defaults** when not specified

### Merge chain in `_configure()`

```python
# 1. Parse env + argv using _server_opts_spec for type conversion
env_argv_opts = SmartOptions(_server_opts_spec, env="GENRO_ASGI", argv=argv)

# 2. Explicit parameters from caller (ignores None)
caller_opts = SmartOptions(
    dict(app_dir=app_dir, host=host, port=port, reload=reload),
    ignore_none=True,
)

# 3. Config from YAML file
config = SmartOptions(str(resolved_app_dir / "config.yaml"))

# 4. Final merge: DEFAULTS < config.server < env_argv < caller
server_opts = (
    SmartOptions(DEFAULTS)
    + (config.server or SmartOptions({}))
    + env_argv_opts
    + caller_opts
)
```

### Effective priority in genro-asgi

```text
DEFAULTS < config.yaml < GENRO_ASGI_* env < argv < explicit params
```

### Usage for middleware

```python
middleware_config = self.opts.middleware or []
```

If in `config.yaml`:

```yaml
middleware:
  - cors
  - gzip
```

Becomes `SmartOptions(cors=True, gzip=True)` thanks to automatic string list wrapping.

---

## Other genro-toolbox utilities

| Utility | Purpose |
|---------|---------|
| `extract_kwargs` | Decorator to group kwargs by prefix |
| `safe_is_instance` | isinstance() without importing the class |
| `render_ascii_table` | ASCII table rendering |
| `render_markdown_table` | Markdown table rendering |
| `dictExtract` | Extract dict subset by key prefix |

---

## Role in Genro ecosystem

**genro-toolbox is the common code base for all Genro libraries.**

### Philosophy

> "Same patterns everywhere, never reinvent the wheel"

Every Genro library (genro-asgi, genro-routes, genro-storage, etc.) uses genro-toolbox for:
- **Configuration**: SmartOptions for parsing env/argv/file
- **Common utilities**: decorators, type checking, etc.

This ensures:
1. **Consistency**: same pattern everywhere
2. **Familiarity**: learn once, use always
3. **Maintainability**: fix in toolbox → benefits all
4. **No drift**: avoids slightly different patterns in each project

### Mandatory dependency

**Yes**, `genro-toolbox` is a mandatory dependency of all Genro libraries.

It's not optional because consistency is an architectural requirement.

---

## Recommended usage pattern

### For new apps

```python
from genro_toolbox import SmartOptions

def _my_app_spec(
    name: str = "default",
    timeout: int = 30,
    debug: bool = False,
) -> None:
    """Spec function for type extraction."""
    pass

class MyApp:
    def __init__(self, config_file: str = "config.yaml", **kwargs):
        file_config = SmartOptions(config_file)
        caller_config = SmartOptions(kwargs, ignore_none=True)
        self.opts = file_config + caller_config
```

### For config access

```python
# Safe access (returns None if missing)
timeout = self.opts.timeout or 30

# Check existence
if 'debug' in self.opts:
    ...

# Nested access
db_host = self.opts.database.host  # if database is dict in YAML
```
