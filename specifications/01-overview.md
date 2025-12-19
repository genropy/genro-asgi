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
│  │  │ CORS   │→ │ Errors │→ │Logging │→ │ Dispatcher │  │  │
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

### Servers

| Component | Module | Description |
|-----------|--------|-------------|
| **AsgiServer** | `servers/base.py` | Main entry point, loads config, mounts apps |
| **Publisher** | `servers/publisher.py` | Event publishing for server lifecycle |

### Core

| Component | Module | Description |
|-----------|--------|-------------|
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

### Applications

| Component | Module | Description |
|-----------|--------|-------------|
| **AsgiApplication** | `applications/base.py` | Base class for apps mounted on server |
| **StaticSite** | `applications/static_site.py` | App for serving static files |

### Routers

| Component | Module | Description |
|-----------|--------|-------------|
| **StaticRouter** | `routers/static_router.py` | Router for serving static files from directory |

### Middleware

| Component | Module | Description |
|-----------|--------|-------------|
| **CORSMiddleware** | `middleware/cors.py` | Cross-Origin Resource Sharing |
| **ErrorMiddleware** | `middleware/errors.py` | Exception handling |
| **LoggingMiddleware** | `middleware/logging.py` | Request/response logging |
| **CompressionMiddleware** | `middleware/compression.py` | Gzip/deflate compression |

### WebSocket

| Component | Module | Description |
|-----------|--------|-------------|
| **WebSocket** | `websocket.py` | WebSocket connection handler |
| **WebSocketState** | `websocket.py` | Connection state enum |

### WSX (WebSocket eXtended)

| Component | Module | Description |
|-----------|--------|-------------|
| **WsxProtocol** | `wsx/protocol.py` | Transport-agnostic RPC protocol |

### Executors

| Component | Module | Description |
|-----------|--------|-------------|
| **BaseExecutor** | `executors/base.py` | Abstract executor interface |
| **LocalExecutor** | `executors/local.py` | Thread/process pool executor |
| **ExecutorRegistry** | `executors/registry.py` | Manages named executors |

### Data Structures

| Component | Module | Description |
|-----------|--------|-------------|
| **Headers** | `datastructures/headers.py` | HTTP headers container |
| **QueryParams** | `datastructures/query_params.py` | URL query parameters |
| **URL** | `datastructures/url.py` | URL parsing and manipulation |
| **Address** | `datastructures/address.py` | Client address (host, port) |
| **State** | `datastructures/state.py` | Request/app state container |

### Utilities

| Component | Module | Description |
|-----------|--------|-------------|
| **ServerBinder** | `utils/binder.py` | Binds apps to server context |

## Dependencies

### Required

| Package | Purpose |
|---------|---------|
| `uvicorn` | ASGI server |
| `pyyaml` | Configuration loading |
| `genro-toolbox` | SmartOptions, utilities |
| `genro-routes` | Router, RoutingClass |
| `genro-tytx` | Typed serialization (WebSocket, WSX, Request) |

### Optional

| Package | Purpose | Install |
|---------|---------|---------|
| `orjson` | Fast JSON serialization | `pip install genro-asgi[json]` |

## Directory Structure

```
src/genro_asgi/
├── __init__.py              # Public exports
├── __main__.py              # CLI entry point
├── dispatcher.py            # Request dispatcher
├── lifespan.py              # Lifecycle management
├── request.py               # Request classes
├── response.py              # Response classes
├── websocket.py             # WebSocket support
├── types.py                 # Type definitions
├── exceptions.py            # Exception classes
├── applications/            # Application classes
│   ├── __init__.py
│   ├── base.py              # AsgiApplication base class
│   ├── static_site.py       # StaticSite (module-based)
│   └── static_site/         # StaticSite (path-based)
│       ├── __init__.py
│       ├── app.py
│       └── config.yaml
├── servers/                 # Server implementations
│   ├── __init__.py
│   ├── base.py              # AsgiServer
│   └── publisher.py         # Event publisher
├── routers/                 # Router implementations
│   ├── __init__.py
│   └── static_router.py     # Static file router
├── middleware/              # Middleware components
│   ├── __init__.py
│   ├── cors.py
│   ├── errors.py
│   ├── logging.py
│   └── compression.py
├── executors/               # Executor system
│   ├── __init__.py
│   ├── base.py
│   ├── local.py
│   └── registry.py
├── datastructures/          # Data structures
│   ├── __init__.py
│   ├── headers.py
│   ├── query_params.py
│   ├── url.py
│   ├── address.py
│   └── state.py
├── utils/                   # Utilities
│   ├── __init__.py
│   └── binder.py
└── wsx/                     # WebSocket extensions
    ├── __init__.py
    ├── protocol.py
    └── registry.py
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

```
specifications/
├── 01-overview.md           # This file
├── architecture/            # Technical details
│   ├── applications.md      # App system architecture
│   └── wsx-protocol.md      # WSX protocol specification
├── guides/                  # Developer guides
│   └── applications.md      # How to create apps
├── interview/               # Q&A format documentation
│   ├── 01-questions.md      # Questions list
│   ├── 02-knowledge-summary.md
│   └── answers/             # Verified answers (A-N)
├── dependencies/            # External dependencies docs
│   ├── genro-routes.md
│   ├── genro-toolbox.md
│   └── genro-tytx.md
├── executors.md             # Executor system analysis
├── wsgi_support/            # WSGI backward compatibility
└── legacy/                  # Historical/TODO items
    └── TODO-to-document.md
```

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
