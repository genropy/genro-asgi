# genro-asgi Overview

**Version**: 0.1.0
**Status**: Alpha
**Last Updated**: 2025-12-13

## What is genro-asgi?

genro-asgi is a minimal ASGI foundation for building web services. It provides:

- ASGI server with multi-app routing
- Request/Response abstractions
- Middleware system
- Static file serving
- WebSocket support
- Lifespan management

## Core Principles

1. **Minimal dependencies** - Only essential packages (uvicorn, pyyaml, genro-toolbox, genro-routes)
2. **No magic** - Explicit configuration, predictable behavior
3. **Composable** - Mix and match components as needed
4. **Type-safe** - Full type hints throughout

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AsgiServer                           │
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │   config    │    │   router    │    │  lifespan   │     │
│  │   (YAML)    │    │(genro_routes│    │  (startup/  │     │
│  │             │    │   Router)   │    │  shutdown)  │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    Middleware Chain                   │  │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────────┐  │  │
│  │  │ CORS   │→ │ Errors │→ │ Static │→ │ Dispatcher │  │  │
│  │  └────────┘  └────────┘  └────────┘  └────────────┘  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                    Mounted Apps                      │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐   │   │
│  │  │ ShopApp  │  │OfficeApp│  │   StaticSite     │   │   │
│  │  │(Routed   │  │(Routed   │  │  (serves files)  │   │   │
│  │  │ Class)   │  │ Class)   │  │                  │   │   │
│  │  └──────────┘  └──────────┘  └──────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Core

| Component | Module | Description |
|-----------|--------|-------------|
| **AsgiServer** | `server.py` | Main entry point, loads config, mounts apps |
| **Dispatcher** | `dispatcher.py` | Routes requests to apps via genro_routes |
| **ServerLifespan** | `lifespan.py` | Manages startup/shutdown lifecycle |

### Request/Response

| Component | Module | Description |
|-----------|--------|-------------|
| **BaseRequest** | `request.py` | Abstract base for all request types |
| **HttpRequest** | `request.py` | HTTP request wrapper |
| **Response** | `response.py` | Base response class |
| **JSONResponse** | `response.py` | JSON response with auto-serialization |
| **HTMLResponse** | `response.py` | HTML response |
| **FileResponse** | `response.py` | File streaming response |

### Static Files

| Component | Module | Description |
|-----------|--------|-------------|
| **StaticSite** | `static_site.py` | RoutedClass for serving static files via router |
| **StaticFiles** | `static.py` | Standalone ASGI app for static files |
| **StaticFilesMiddleware** | `middleware/static.py` | Middleware for path-prefix static serving |

### Middleware

| Component | Module | Description |
|-----------|--------|-------------|
| **BaseMiddleware** | `middleware/base.py` | Base class for middleware |
| **CORSMiddleware** | `middleware/cors.py` | Cross-Origin Resource Sharing |
| **ErrorMiddleware** | `middleware/errors.py` | Exception handling |
| **StaticFilesMiddleware** | `middleware/static.py` | Static file serving |

### WebSocket

| Component | Module | Description |
|-----------|--------|-------------|
| **WebSocket** | `websocket.py` | WebSocket connection handler |
| **WebSocketState** | `websocket.py` | Connection state enum |

### Executors

| Component | Module | Description |
|-----------|--------|-------------|
| **BaseExecutor** | `executors/` | Abstract executor interface |
| **LocalExecutor** | `executors/` | Thread/process pool executor |
| **ExecutorRegistry** | `executors/` | Manages named executors |

## Dependencies

### Required

| Package | Purpose |
|---------|---------|
| `uvicorn` | ASGI server |
| `pyyaml` | Configuration loading |
| `genro-toolbox` | SmartOptions, utilities |
| `genro-routes` | Router, RoutedClass |

### Optional

| Package | Purpose |
|---------|---------|
| `orjson` | Fast JSON serialization |

## Directory Structure

```
src/genro_asgi/
├── __init__.py          # Public exports
├── __main__.py          # CLI entry point
├── server.py            # AsgiServer
├── dispatcher.py        # Request dispatcher
├── config.py            # Configuration loading
├── lifespan.py          # Lifecycle management
├── request.py           # Request classes
├── response.py          # Response classes
├── static.py            # StaticFiles ASGI app
├── static_site.py       # StaticSite RoutedClass
├── websocket.py         # WebSocket support
├── types.py             # Type definitions
├── exceptions.py        # Exception classes
├── binder.py            # Server-app binding
├── default_pages.py     # Default HTML pages
├── middleware/          # Middleware components
│   ├── __init__.py
│   ├── base.py
│   ├── cors.py
│   ├── errors.py
│   └── static.py
├── executors/           # Executor system
│   └── ...
├── datastructures/      # Data structures
│   └── ...
└── wsx/                 # WebSocket extensions
    └── ...
```

## Quick Start

### Minimal Configuration

```yaml
# config.yaml
server:
  host: "127.0.0.1"
  port: 8000

apps:
  myapp: "myapp:MyApp"
```

### Running

```bash
# From app directory
python -m genro_asgi

# Or with explicit directory
python -m genro_asgi --app-dir /path/to/app
```

## Documentation Structure

This specifications folder is organized as:

```
specifications/
├── 01-overview.md           # This file
├── architecture/            # How it's built, internal details
│   ├── 01-server.md
│   ├── 02-dispatcher.md
│   ├── 03-request-response.md
│   ├── 04-middleware.md
│   ├── 05-static-files.md
│   └── 06-lifespan.md
├── guides/                  # How to use it
│   ├── 01-configuration.md
│   ├── 02-creating-apps.md
│   ├── 03-middleware-usage.md
│   └── 04-static-sites.md
└── legacy/                  # Historical documents
    └── ...
```

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
