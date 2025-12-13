# WSGI Support Documentation

This folder contains documentation for running legacy WSGI applications within genro-asgi's ASGI server.

## Purpose

genro-asgi can wrap and serve legacy WSGI applications, enabling gradual migration to ASGI while maintaining backward compatibility.

## Documents

| File | Description |
|------|-------------|
| [01-overview.md](01-overview.md) | High-level overview and goals |
| [02-current-architecture.md](02-current-architecture.md) | Current WSGI production architecture |
| [03-page-id-routing.md](03-page-id-routing.md) | Page ID format with process indicator |
| [04-migration-phases.md](04-migration-phases.md) | Detailed migration phases (0→3→4→5→6→7) |
| [05-deployment-strategy.md](05-deployment-strategy.md) | Green/Blue/Canary deployment |

## Key Capability

**ASGI wrapping WSGI**: Mount legacy WSGI apps alongside native ASGI apps.

```python
from genro_asgi import AsgiServer
from asgiref.wsgi import WsgiToAsgi

# Wrap legacy WSGI app
legacy_wsgi_app = WsgiToAsgi(my_wsgi_app)

# Mount alongside ASGI apps
server = AsgiServer()
server.mount("/legacy", legacy_wsgi_app)
server.mount("/api", my_asgi_app)
```

## Context

The migration involves replacing:

- **gnrdaemon** (Pyro) → In-process PageRegistry + NATS (optional)
- **Tornado** (WebSocket) → Native ASGI WebSocket
- **Gunicorn** (WSGI) → Uvicorn (ASGI)
- **Nginx routing** → AsgiServer dispatcher

## Migration Phases

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

| Phase | Description | gnrdaemon | Pages |
|-------|-------------|-----------|-------|
| **0** | ASGI wraps WSGI | Unchanged | Ephemeral |
| **3** | Mono-process + PageRegistry for WS | Unchanged | Ephemeral + Live (WS) |
| **4** | All registries in-process | Eliminated | Ephemeral (fast) |
| **5** | Resident pages | None | Resident |
| **6** | Stabilization and testing | None | Resident |
| **7** | Multi-process + sticky + scaling | None | Resident |

Phases 1-2 (sticky sessions, NATS) are deferred and integrated into Phase 7.

## Key Principles

1. **Gradual migration** - Each phase is independently deployable
2. **Rollback capability** - Can revert at any stage
3. **Mono-process first** - Delay sticky session complexity
4. **Backward compatibility** - WSGI apps continue to work

## Related

- `interview/answers/` - Will contain WSGI support answer section (O-wsgi-support.md)
