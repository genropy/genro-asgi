# Missing Documentation - 10_spa_management

Paragraphs present in source documents but not in specifications.

## Source: initial_specifications/wsgi_support/README.md

This folder contains documentation for running legacy WSGI applications within genro-asgi's ASGI server.

genro-asgi can wrap and serve legacy WSGI applications, enabling gradual migration to ASGI while maintaining backward compatibility.

| File | Description |
|------|-------------|
| [01-overview.md](01-overview.md) | High-level overview and goals |
| [02-current-architecture.md](02-current-architecture.md) | Current WSGI production architecture |
| [03-page-id-routing.md](03-page-id-routing.md) | Page ID format with process indicator |
| [04-migration-phases.md](04-migration-phases.md) | Detailed migration phases (0→3→4→5→6→7) |
| [05-deployment-strategy.md](05-deployment-strategy.md) | Green/Blue/Canary deployment |

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

The migration involves replacing:

- **gnrdaemon** (Pyro) → In-process PageRegistry + NATS (optional)
- **Tornado** (WebSocket) → Native ASGI WebSocket
- **Gunicorn** (WSGI) → Uvicorn (ASGI)
- **Nginx routing** → AsgiServer dispatcher

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

1. **Gradual migration** - Each phase is independently deployable
2. **Rollback capability** - Can revert at any stage
3. **Mono-process first** - Delay sticky session complexity
4. **Backward compatibility** - WSGI apps continue to work

- `interview/answers/` - Will contain WSGI support answer section (O-wsgi-support.md)

## Source: plan_2025_12_29/17-spa-manager.md

**Stato**: 📋 DA PROGETTARE
**Priorità**: P1 (Necessario per app interattive)
**Data**: 2025-12-30

La documentazione di SpaManager è stata suddivisa in documenti separati per maggiore chiarezza.

**Vedi**: [spa-manager/](spa-manager/)

| # | Documento | Contenuto |
|---|-----------|-----------|
| 00 | [00-index.md](spa-manager/00-index.md) | Overview e indice |
| 01 | [01-core.md](spa-manager/01-core.md) | SpaManager core: gerarchia 4 livelli, registri, TreeDict, WebSocket |
| 02 | [02-worker-pool.md](spa-manager/02-worker-pool.md) | Worker Pool locale con affinità utente |
| 03 | [03-executor-manager.md](spa-manager/03-executor-manager.md) | ExecutorManager: tipi executor, evoluzione 3 fasi |
| 04 | [04-storage-futures.md](spa-manager/04-storage-futures.md) | Storage in-memory, sviluppi futuri (NATS, blue-green/canary) |

```text
User (identity)
  └── Connection (browser/device)
        └── Session (master page + iframe)
              └── Page (singola pagina con WebSocket)
```

Ogni livello ha il proprio **TreeDict** per dati.

**Ultimo aggiornamento**: 2025-12-30

## Source: plan_2025_12_29/spa-manager/00-index.md

**Stato**: 📋 DA PROGETTARE
**Priorità**: P1 (Necessario per app interattive)
**Data**: 2025-12-30

SpaManager è il sistema di gestione connessioni real-time per applicazioni SPA (Single Page Application). Gestisce la gerarchia **User → Connection → Session → Page** con comunicazione WebSocket bidirezionale.

| # | Documento | Contenuto |
|---|-----------|-----------|
| 01 | [01-core.md](01-core.md) | SpaManager core: gerarchia 4 livelli, registri, TreeDict, WebSocket handler |
| 02 | [02-worker-pool.md](02-worker-pool.md) | Worker Pool locale con affinità utente (multiprocessing) |
| 03 | [03-executor-manager.md](03-executor-manager.md) | ExecutorManager: tipi executor, evoluzione 3 fasi, middleware routing |
| 04 | [04-storage-futures.md](04-storage-futures.md) | Storage in-memory, sviluppi futuri (NATS, persistence, blue-green/canary) |

```text
┌─────────────────────────────────────────────────────────────┐
│                      AsgiServer                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   SpaManager                         │    │
│  │                                                      │    │
│  │   ┌─────────────┐    ┌─────────────┐               │    │
│  │   │ UserRegistry │    │ PageRegistry│               │    │
│  │   │ ConnRegistry │    │ SessRegistry│               │    │
│  │   └─────────────┘    └─────────────┘               │    │
│  │                                                      │    │
│  │   ┌─────────────────────────────────────────┐      │    │
│  │   │           ExecutorManager                │      │    │
│  │   │  ├── inline                             │      │    │
│  │   │  ├── local_free / local_assigned        │      │    │
│  │   │  └── remote_free / remote_assigned      │      │    │
│  │   └─────────────────────────────────────────┘      │    │
│  │                                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

```text
User (identity)
  │
  │  data: TreeDict          ←── Persistente, cross-device
  │
  └── Connection (connection_id)
        │
        │  data: TreeDict    ←── Browser/device specifico
        │
        └── Session (session_id)
              │
              │  data: TreeDict    ←── Pagina master + iframe
              │
              ├── Page "abc123" (master)
              ├── Page "def456" (iframe)
              └── Page "ghi789" (iframe)
```

```text
toolbox (uuid, smartasync)
       │
       ▼
treedict (→ Bag in futuro)
       │
       ▼
WebSocket support
       │
       ▼
SpaManager (01-core)
       │
       ├── WorkerPool (02-worker-pool)
       │
       └── ExecutorManager (03-executor-manager)
```

| Documento | Effort |
|-----------|--------|
| 01-core (SpaManager) | ~3 giorni |
| 02-worker-pool | ~1 giorno |
| 03-executor-manager | ~2 giorni |
| 04-storage-futures | Design only |
| **Totale** | ~6 giorni |

**Ultimo aggiornamento**: 2025-12-30

