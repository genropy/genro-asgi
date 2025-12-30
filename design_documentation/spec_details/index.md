# Spec Details - Indice

Micro-decisioni tecniche e dettagli implementativi per genro-asgi.

## Struttura

```
spec_details/
├── core/                    # Componenti core
│   ├── application.md       # AsgiApplication lifecycle, hooks
│   └── server.md            # AsgiServer architecture, request flow
│
├── request-response/        # HTTP handling
│   ├── request.md           # HttpRequest wrapper
│   ├── response.md          # Response classes
│   └── datastructures.md    # Headers, QueryParams, URL, State
│
├── middleware/              # Middleware system
│   ├── chain.md             # BaseMiddleware, chain config
│   ├── authentication.md    # AuthMiddleware, O(1) lookup
│   ├── cors.md              # CORS headers
│   └── errors.md            # Error handling
│
├── websocket/               # WebSocket support
│   ├── websocket.md         # WebSocket class
│   └── wsx-protocol.md      # WSX RPC protocol
│
├── storage/                 # File/resource handling
│   ├── storage.md           # LocalStorage, mounts
│   └── resources.md         # ResourceLoader, hierarchical fallback
│
├── applications/            # Application types
│   ├── api-application.md   # ApiApplication (future)
│   ├── page-application.md  # PageApplication (future)
│   └── system-apps.md       # SwaggerApp, GenroApiApp
│
├── executors/               # Task execution
│   └── executor.md          # ThreadPool, ProcessPool
│
├── dependencies/            # External dependencies
│   ├── genro-routes.md      # Routing system
│   ├── genro-toolbox.md     # SmartOptions, AppLoader
│   └── genro-tytx.md        # Type-tagged text
│
└── future/                  # Planned features
    ├── session.md           # Server-side sessions
    ├── spa-manager.md       # SPA state management
    └── wsgi-migration.md    # Legacy migration
```

## Come Usare

1. **Specifications** (`specifications/`) - Visione d'insieme, architettura
2. **Spec Details** (questa cartella) - Decisioni tecniche, API, parametri

## Convenzioni

Ogni documento include:
- **Stato** - Implementato/Non implementato/Pianificato
- **Classe/API** - Signature e parametri
- **Decisioni** - Scelte fatte e motivazioni
- **Esempi** - Codice d'uso

## Documenti Core

| Documento | Descrizione |
|-----------|-------------|
| [core/server.md](core/server.md) | Entry point ASGI, dispatching |
| [core/application.md](core/application.md) | Lifecycle app, hooks |
| [middleware/chain.md](middleware/chain.md) | Sistema middleware |
| [websocket/wsx-protocol.md](websocket/wsx-protocol.md) | RPC over WebSocket |

## Stato Implementazione

| Area | Stato |
|------|-------|
| Core (Server, Application) | ✅ Implementato |
| Request/Response | ✅ Implementato |
| Middleware base | ✅ Implementato |
| Auth Middleware | ✅ Implementato |
| WebSocket/WSX | ✅ Implementato |
| Storage/Resources | ✅ Implementato |
| Executor | ✅ Implementato |
| Session | ❌ Pianificato |
| SpaManager | 📋 Da progettare |
| ApiApplication | ❌ Pianificato |
| PageApplication | ❌ Pianificato |
