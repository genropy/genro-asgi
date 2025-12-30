# Vision and Goals

## What is genro-asgi?

**genro-asgi** is an ASGI-based web framework designed as the async foundation for the Genro ecosystem. It provides a minimal, composable architecture for building high-performance web services with:

- Instance-scoped routing via **genro-routes**
- Type-tagged serialization via **genro-tytx**
- Multi-application mounting with isolated state
- Built-in middleware chain (auth, CORS, errors)
- WebSocket support with WSX RPC protocol

## Project Goals

### 1. ASGI Foundation

Provide a standard ASGI interface that:
- Handles HTTP requests with full async support
- Supports WebSocket connections and the WSX RPC protocol
- Manages server lifecycle (startup/shutdown events)
- Integrates seamlessly with ASGI servers (uvicorn)

### 2. Instance Isolation Architecture

**Core architectural principle**: Server and apps are isolated instances, not global functions.

```python
server = AsgiServer(server_dir=".")  # Instance with own state
del server                            # → Everything garbage collected, zero residue
```

This enables:
- Clean testing (fresh instances per test)
- Hot reload without state bleed
- Multi-tenant scenarios
- Predictable behavior

### 3. Multi-Application Mounting

Support multiple applications mounted on a single server:

```yaml
# config.yaml
apps:
  shop:
    module: "main:ShopApp"
  admin:
    module: "admin:AdminApp"
  docs:
    module: "genro_asgi:StaticRouter"
    directory: "./public"
```

Each app:
- Has its own router subtree
- Receives its own configuration parameters
- Manages its own lifecycle hooks (on_startup, on_shutdown)
- Is isolated from other apps

### 4. Native Integration with Genro Libraries

Leverage core Genro libraries for consistent behavior:

| Library | Purpose | Role in genro-asgi |
|---------|---------|-------------------|
| **genro-routes** | Instance-scoped routing | Router, @route decorator, RoutingClass |
| **genro-toolbox** | Configuration utilities | SmartOptions (YAML), AppLoader |
| **genro-tytx** | Type-tagged serialization | Preserve types (Decimal, date) across HTTP |
| **smartasync** | Async/sync bridging | Call sync handlers from async context |

### 5. Modern SPA Support (Future)

Planned features for Single Page Applications:
- Server-side session management
- Real-time communication via WSX
- State synchronization between client and server

## What genro-asgi is NOT

- **Not a full-stack framework**: No ORM, no templating, no admin panel
- **Not zero-dependency**: Requires genro-routes, genro-toolbox, genro-tytx, uvicorn, pyyaml
- **Not WSGI compatible**: ASGI-only (async-first design)
- **Not a replacement for FastAPI/Starlette**: Different architecture (instance-scoped vs blueprint-based)

## Target Audience

### Primary: Genro Ecosystem Developers

Developers building:
- Genro-based applications
- Services that integrate with genro-storage, genro-bag, genro-orm
- Internal tools using the Genro stack

### Secondary: Developers Seeking Instance Isolation

Developers who need:
- Clean separation between app instances
- Predictable testing without global state
- Hot reload without residual state

## Relationship with Other Genro Modules

```
genro-asgi (this project)
    │
    ├── depends on: genro-routes (routing)
    ├── depends on: genro-toolbox (config utilities)
    ├── depends on: genro-tytx (serialization)
    │
    └── used by: genro-storage, genro-orm, etc.
```

## Version and Status

- **Current Version**: 0.1.0
- **Development Status**: Alpha (API may change)
- **Python Support**: 3.10+
- **License**: Apache 2.0

## Related Documents

- [Core Principles](02_core_principles.md) - Architectural principles
- [Terminology](03_terminology.md) - Glossary of terms
- [Quick Start for Contributors](04_quick_start.md) - Getting started with development
