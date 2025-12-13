# genro-asgi Configuration

**Status**: Draft
**Format**: TOML

## Overview

genro-asgi uses TOML for configuration. TOML is in Python stdlib from 3.11+
(`tomllib`), has clear syntax, and is already familiar from `pyproject.toml`.

Configuration file: `genro-asgi.toml` (default) or specified via CLI/env.

## Complete Example

```toml
# genro-asgi.toml

[server]
host = "0.0.0.0"
port = 8000
debug = false
log_level = "info"

# Static file serving - simple format
[static]
"/static" = "./public"
"/docs" = "./documentation"
"/assets" = "/var/www/shared/assets"

# Static file serving - detailed format
[[static_sites]]
path = "/app"
directory = "./webapp/dist"
index = "index.html"
fallback = "index.html"  # SPA support

[[static_sites]]
path = "/legacy"
directory = "./old_site"
index = "default.htm"

# Application mounts (smartroute-based apps)
[[apps]]
path = "/api"
module = "myapp.api:app"

[[apps]]
path = "/admin"
module = "myapp.admin:admin_app"
```

## Sections

### [server]

Server configuration.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | `"127.0.0.1"` | Bind address |
| `port` | integer | `8000` | Bind port |
| `debug` | boolean | `false` | Debug mode |
| `log_level` | string | `"info"` | Log level: debug, info, warning, error |
| `workers` | integer | `1` | Number of worker processes |

```toml
[server]
host = "0.0.0.0"
port = 8000
debug = true
log_level = "debug"
```

### [static]

Simple static file mapping. Keys are URL paths, values are filesystem paths.

```toml
[static]
"/static" = "./public"
"/docs" = "./documentation"
"/images" = "/var/www/images"
```

- Paths are relative to config file location (or absolute)
- Serves `index.html` by default for directories
- Returns 404 for missing files

### [[static_sites]]

Detailed static site configuration (array of tables).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `path` | string | required | URL mount path |
| `directory` | string | required | Filesystem directory |
| `index` | string | `"index.html"` | Default file for directories |
| `fallback` | string | `null` | Fallback file for SPA routing |
| `cache_max_age` | integer | `3600` | Cache-Control max-age in seconds |
| `cors` | boolean | `false` | Enable CORS headers |

```toml
[[static_sites]]
path = "/app"
directory = "./webapp/dist"
index = "index.html"
fallback = "index.html"  # All 404s serve index.html (SPA)
cache_max_age = 86400
cors = true
```

### [[apps]]

Application mounts (smartroute-based ASGI apps).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `path` | string | required | URL mount path |
| `module` | string | required | Python module:object path |

```toml
[[apps]]
path = "/api"
module = "myapp.api:app"

[[apps]]
path = "/shop"
module = "myapp.shop:published_shop"
```

The `module` string follows the format `package.module:object`, similar to
uvicorn's app specification.

## Environment Variables

Configuration values can reference environment variables:

```toml
[server]
host = "${HOST:-0.0.0.0}"
port = "${PORT:-8000}"

[static]
"/data" = "${DATA_DIR:-./data}"
```

Syntax:
- `${VAR}` - required, error if not set
- `${VAR:-default}` - with default value

## Configuration Loading

Order of precedence (highest to lowest):

1. CLI arguments (`--host`, `--port`)
2. Environment variables (`GENRO_ASGI_HOST`, `GENRO_ASGI_PORT`)
3. Configuration file
4. Defaults

## File Discovery

Default config file locations (checked in order):

1. `./genro-asgi.toml`
2. `./config/genro-asgi.toml`
3. `~/.config/genro-asgi/config.toml`

Override with `--config` CLI argument or `GENRO_ASGI_CONFIG` env var.

## Minimal Examples

### Static site only

```toml
[server]
port = 8080

[static]
"/" = "./public"
```

### API server only

```toml
[server]
host = "0.0.0.0"
port = 8000

[[apps]]
path = "/api"
module = "myapp:api"
```

### Mixed (static + API)

```toml
[server]
port = 8000

[static]
"/static" = "./assets"

[[apps]]
path = "/api"
module = "myapp.api:app"

[[static_sites]]
path = "/"
directory = "./frontend/dist"
index = "index.html"
fallback = "index.html"
```

## CLI Usage

```bash
# Use default config
genro-asgi

# Specify config file
genro-asgi --config myconfig.toml

# Override config values
genro-asgi --host 0.0.0.0 --port 9000

# Show loaded configuration
genro-asgi --show-config
```
