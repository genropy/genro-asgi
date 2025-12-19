# AsgiServer - Design Consolidato

**Status**: 🔴 DA REVISIONARE
**Data**: 2025-12-03

---

## Concetto Fondamentale

`AsgiServer` è un **server multi-protocollo**, non solo un'app ASGI.

A differenza di Starlette (che è un'app ASGI che gira su Uvicorn), il nostro AsgiServer:
1. Riceve richieste da **più trasporti** (HTTP, WebSocket, futuro NATS)
2. Le **normalizza** in una Request unificata
3. Le dispatcha agli **stessi handler**
4. Restituisce la risposta nel formato appropriato per il trasporto

---

## Architettura

```
┌─────────────────────────────────────────────────────────────┐
│                        AsgiServer                           │
│                                                             │
│  Trasporti:                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                     │
│  │  HTTP   │  │   WS    │  │  NATS   │                     │
│  │(Uvicorn)│  │(Uvicorn)│  │(Client) │                     │
│  └────┬────┘  └────┬────┘  └────┬────┘                     │
│       │            │            │                          │
│       ▼            ▼            ▼                          │
│  ┌─────────────────────────────────────────┐               │
│  │         Richiede Risposta?              │               │
│  └──────────────┬─────────────┬────────────┘               │
│                 │             │                            │
│           SÌ (RPC)      NO (Stream)                        │
│                 │             │                            │
│                 ▼             ▼                            │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │  Crea Request    │  │  Fire-and-Forget │               │
│  │  (normalizzata)  │  │  (direct I/O)    │               │
│  └────────┬─────────┘  └──────────────────┘               │
│           │                                                │
│           ▼                                                │
│  ┌─────────────────────────────────────────┐               │
│  │              Handlers                    │               │
│  │  (RoutingClass / mounted apps)           │               │
│  └─────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## Due Tipi di Workload

### 1. Request/Response (RPC-style)

- HTTP REST calls
- WebSocket RPC messages
- NATS request/reply

Caratteristiche:
- Richiede risposta
- Passa attraverso middleware
- Crea oggetto Request
- Tracking in RequestRegistry

### 2. Streaming (Fire-and-Forget)

- File upload/download
- Telemetry in (WebSocket)
- Notifications out (WebSocket)
- NATS publish (no reply)

Caratteristiche:
- Non richiede risposta (o risposta implicita)
- Minimal middleware
- Direct I/O
- No Request object overhead

---

## Request Unificata

Ogni trasporto crea una sottoclasse di `BaseRequest` che **emula** l'interfaccia HTTP:

```python
class BaseRequest:
    """Interfaccia comune per tutti i trasporti."""
    id: str              # Correlation ID
    path: str            # /api/users/123
    method: str          # GET, POST, RPC, etc.
    headers: Headers     # Reali (HTTP) o emulati (WS/NATS)
    cookies: dict        # Reali (HTTP) o emulati
    query_params: QueryParams

    async def body() -> bytes
    async def json() -> Any
    async def form() -> dict
    def make_response(result) -> Response
```

### Sottoclassi per Trasporto

```python
class HttpRequest(BaseRequest):
    """HTTP reale - dati da ASGI scope."""
    # headers, cookies, query_params sono reali

class WsRequest(BaseRequest):
    """WebSocket RPC - emula da messaggio JSON."""
    # Estrae path, method, headers dal payload:
    # {"method": "get_user", "path": "/users/123", "headers": {...}}

class NatsRequest(BaseRequest):
    """NATS - emula da subject e payload."""
    # Subject "rpc.users.get" → path="/users", method="get"
```

L'handler vede sempre `BaseRequest`, non sa quale trasporto sta usando:

```python
async def get_user(request: BaseRequest) -> dict:
    user_id = request.path.split("/")[-1]
    return {"id": user_id, "name": "Mario"}
```

---

## Perché "Server" e non "App"

Starlette è un'**app ASGI**:
```
Uvicorn (server) → Starlette (app) → Routes
```

Il nostro AsgiServer è un **server multi-protocollo**:
```
Uvicorn (HTTP/WS transport) ─┐
                             ├→ AsgiServer → Handlers
NATS (messaging transport) ──┘
```

Il nome "Server" è corretto perché:
1. Gestisce **più protocolli** di trasporto
2. Ha il metodo `run()` che avvia tutto (Uvicorn + NATS client)
3. È il **punto di ingresso** dell'applicazione, non una componente

---

## Mount e Dispatch

### Mount Intelligente

`mount()` accetta diversi tipi:

```python
server = AsgiServer()

# 1. App ASGI esterna (FastAPI, Starlette)
server.mount("/api", fastapi_app)

# 2. RoutingClass interna (genro_routes)
server.mount("/docs", DocsApp())

# 3. Handler semplice
server.mount("/health", lambda: "ok")
```

### Dispatch in `__call__`

```python
async def __call__(self, scope, receive, send):
    if scope["type"] == "lifespan":
        await self.lifespan(scope, receive, send)
        return

    # Cerca app montata per path
    app_handler = self._find_app(scope["path"])
    if app_handler:
        await app_handler(scope, receive, send)
        return

    # Fallback al router interno
    await self._dispatch_router(scope, receive, send)
```

---

## Middleware

I middleware wrappano l'app finale (pattern Starlette):

```python
server = AsgiServer()
server.add_middleware(CORSMiddleware, allow_origins=["*"])
server.add_middleware(GZipMiddleware)

# Catena: GZip → CORS → dispatch interno
```

Ogni middleware è un'app ASGI che wrappa la successiva:

```python
class CORSMiddleware:
    def __init__(self, app, allow_origins):
        self.app = app  # next in chain
        self.allow_origins = allow_origins

    async def __call__(self, scope, receive, send):
        # Pre-processing (add CORS headers)
        await self.app(scope, receive, send)
        # Post-processing (via send wrapper)
```

---

## Separazione Workload

Apps diverse per workload diversi:

```python
server = AsgiServer()

# Business logic - full middleware, request tracking
server.mount("/api", BusinessApp())

# Streaming - minimal middleware, direct I/O
server.mount("/stream", StreamingApp())
```

---

## Riassunto Decisioni

| Decisione | Scelta | Motivazione |
|-----------|--------|-------------|
| Nome classe | `AsgiServer` | È un server multi-protocollo, non solo app |
| Request | Sottoclassi di `BaseRequest` | Interfaccia unificata, trasporto nascosto |
| Emulazione HTTP | Sì per WS/NATS | Handler agnostici al trasporto |
| Streaming | Separato da RPC | Workload diversi, protezioni diverse |
| Middleware | Pattern Starlette | Familiare, testato |
| Router | Sempre presente | Semplifica dispatch |

---

## Solo RoutingClass

**Decisione**: AsgiServer serve SOLO app basate su genro-routes (RoutingClass).

**Non supportiamo**:
- App ASGI esterne (FastAPI, Starlette)
- Decoratori `@app.get()` style
- Mount di app arbitrarie

**Pattern unico**:

```python
from genro_asgi import AsgiServer
from genro_routes import RoutingClass, route

class UsersAPI(RoutingClass):
    @route("list")
    def get_users(self):
        return [{"id": 1, "name": "Mario"}]

    @route("get")
    def get_user(self, user_id: int):
        return {"id": user_id, "name": "Mario"}

server = AsgiServer()
server.mount("/api/users", UsersAPI())
server.run()
```

**Vantaggi**:
1. Un solo pattern per tutto (class-based con `@route`)
2. Coerenza con ecosistema genro
3. Codice server semplificato (tutto passa dal router)
4. Niente ambiguità su cosa supportiamo

**Conseguenze sul codice**:
- `self.apps` potrebbe sparire (tutto via router)
- `mount()` accetta solo RoutingClass
- `__call__` semplificato: lifespan + router dispatch

---

**Prossimi passi**:
1. Rimuovere envelope dependency da `__call__`
2. Semplificare mount (solo RoutingClass)
3. Aggiungere `add_middleware()` a AsgiServer
4. Documentare WsRequest e NatsRequest

---

**Copyright**: Softwell S.r.l. (2025)
