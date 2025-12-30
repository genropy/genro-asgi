# Missing Documentation - _meta

Paragraphs present in source documents but not in specifications.

## Source: initial_specifications/executors.md

**Stato**: 🔴 DA IMPLEMENTARE
**Ultimo aggiornamento**: 2025-12-13

Il sistema executor in genro-asgi ha codice esistente ma **non è stato realmente implementato/validato**. Questo documento raccoglie tutto ciò che esiste per avere un quadro chiaro quando affronteremo il tema.

Dal file `legacy/genro_asgi_execution.md`, la visione originale prevedeva:

1. **Blocking Task Pool** (ThreadPoolExecutor)
   - Per I/O sincrono e librerie non-async
   - API: `await app.executor.run_blocking(func, *args, **kwargs)`
   - Use case: legacy DB drivers, file system, network blocking

2. **CPU Task Pool** (ProcessPoolExecutor)
   - Per lavoro CPU-intensive parallelo
   - API: `await app.executor.run_process(func, *args, **kwargs)`
   - Use case: data processing, image/audio, compression, calcoli numerici

3. **TaskManager** (Long-Running Jobs)
   - Per job batch e long-running
   - API:
     ```python
     task_id = app.tasks.submit(job_func, *args, **kwargs)
     status = await app.tasks.status(task_id)
     result = await app.tasks.result(task_id)
     ```
   - Features: esecuzione isolata, stato queryable, progress reporting

- Modello di esecuzione unificato built-in
- Supporto nativo per blocking + CPU + long-running
- Architettura predicibile per workload misti

Esiste codice in `src/genro_asgi/executors/` ma con API diversa:

```
src/genro_asgi/executors/
├── __init__.py     # Export pubblici
├── base.py         # BaseExecutor ABC
├── local.py        # LocalExecutor (ProcessPoolExecutor)
└── registry.py     # ExecutorRegistry
```

```python
class BaseExecutor(ABC):
    name: str

@abstractmethod
    async def submit(self, func: Callable, *args, **kwargs) -> Any

@abstractmethod
    def shutdown(self, wait: bool = True) -> None

@property
    @abstractmethod
    def metrics(self) -> dict[str, Any]

def __call__(self, func: F) -> F:  # Decorator pattern
```

**Note**:
- Usa pattern decorator via `__call__` (wrappa `submit`)
- Richiede metrics con: name, pending, submitted, completed, failed
- Eccezioni: `ExecutorError`, `ExecutorOverloadError`

```python
class LocalExecutor(BaseExecutor):
    def __init__(
        self,
        name: str = "default",
        max_workers: int | None = None,
        initializer: Callable | None = None,
        initargs: tuple = (),
        max_pending: int = 100,
        bypass: bool = False,  # Per testing
    )
```

**Features implementate**:
- ProcessPoolExecutor (bypassa GIL)
- Bypass mode per testing (`bypass=True` o `GENRO_EXECUTOR_BYPASS=1`)
- Backpressure via asyncio.Semaphore
- Metrics collection
- Error handling per pickle failures

**Esempio d'uso**:
```python
executor = LocalExecutor(name="pdf", max_workers=2)

@executor
def generate_pdf(data):
    return create_pdf(data)

result = await generate_pdf(report_data)
```

```python
class ExecutorRegistry:
    def register_factory(self, executor_type: str, factory: Callable) -> None
    def get_or_create(self, name: str, executor_type: str = "local", **kwargs) -> BaseExecutor
    def get(self, name: str) -> BaseExecutor | None
    def shutdown_all(self, wait: bool = True) -> None
    def all_metrics(self) -> list[dict]
```

**Features**:
- Lazy creation con caching
- Factory pattern per tipi custom
- Shutdown centralizzato
- Aggregazione metriche

| Feature | Legacy Vision | Codice Esistente |
|---------|---------------|------------------|
| ThreadPool (blocking I/O) | `run_blocking()` | ❌ Non presente |
| ProcessPool (CPU) | `run_process()` | ✅ `LocalExecutor.submit()` |
| TaskManager (long-running) | `tasks.submit/status/result` | ❌ Non presente |
| Decorator pattern | Non menzionato | ✅ `__call__` |
| Backpressure | Non menzionato | ✅ Semaphore |
| Bypass mode (testing) | Non menzionato | ✅ Presente |
| Registry | Non menzionato | ✅ `ExecutorRegistry` |
| Accesso via `app.executor` | ✅ Previsto | ❌ Non integrato |

1. **Serve ThreadPool separato?**
   - Per blocking I/O potrebbe bastare `asyncio.to_thread()`
   - O serve pool dedicato per isolare carico?

2. **TaskManager è necessario?**
   - Per job batch serve davvero un sistema interno?
   - O meglio delegare a Celery/RQ/etc?

3. **Integrazione con Server/Application**
   - Come si accede? `server.executors`? `app.executor`?
   - Chi gestisce il lifecycle (startup/shutdown)?

1. **Il codice esistente è corretto?**
   - Non ci sono test (o non validati)
   - Pattern decorator funziona come atteso?
   - Pickle serialization gestita bene?

2. **Semaphore è sufficiente per backpressure?**
   - O serve qualcosa di più sofisticato?

3. **Metriche: Prometheus integration?**
   - Il codice menziona "optional" ma non c'è

1. **Mantenere solo LocalExecutor** (ProcessPool)
   - Copre il caso principale: CPU-bound work
   - Per blocking I/O: usare `asyncio.to_thread()`

2. **Rimuovere visione TaskManager**
   - Troppo complesso per un framework minimale
   - Chi serve job complessi usa strumenti dedicati

3. **Validare e testare codice esistente**
   - Scrivere test per LocalExecutor
   - Verificare integrazione con server lifecycle

Se si vuole la visione completa:

1. **Aggiungere ThreadExecutor** per blocking I/O
2. **Implementare TaskManager** con status/result
3. **Integrare con Lifespan** per startup/shutdown
4. **Aggiungere Prometheus metrics**

Dal documento `legacy/architecture.md` emergono idee aggiuntive sugli executor:

**Idea**: Worker che caricano dati immutabili all'avvio e li riusano per tutte le esecuzioni.

```python
# Worker-side globals
_model = None

def init_ml_worker(model_path):
    """Chiamata una volta per worker all'avvio."""
    global _model
    _model = load_heavy_model(model_path)  # Caricato una volta

def predict(data):
    """Usa dati precaricati - nessun overhead di caricamento."""
    return _model.predict(data)

# Creazione pool con initializer
executor_ml = server.executor(
    name='ml',
    max_workers=4,
    initializer=init_ml_worker,
    initargs=('/models/v1.pkl',)
)
```

**Use case**:
- ML models (sklearn, pytorch, tensorflow)
- Large lookup tables / dictionaries
- Compiled regex patterns
- Database connection pools (per-worker)
- Configuration immutabile

**Nota**: Il codice esistente in `LocalExecutor` **già supporta** `initializer` e `initargs`.

**Idea**: Worker con thread pool interno per task I/O-bound.

```
Main Process (asyncio event loop)
│
├── DB Worker Process 1
│     ├── _orm_metadata (preloaded schema)
│     ├── _db_url (connection string)
│     └── _thread_pool (8 threads)
│           ├── Thread → connect → transaction → close
│           └── ...
│
└── DB Worker Process 2
      └── (same structure)
```

**Benefici**:
- ORM schema caricato una volta per worker
- Multiple thread gestiscono transazioni concorrenti durante I/O wait
- External pooler (Neon, PgBouncer) gestisce connessioni reali
- Processi isolano DB work dal main async loop

**Valutazione**: Potrebbe essere troppo complesso per un framework minimale. Alternativa: lasciare che l'utente gestisca i thread nel proprio `initializer`.

**Idea**: Pool separati per workload diversi, così un task lento non blocca gli altri.

```python
# Pool isolati - un PDF lento non blocca prediction ML
executor_pdf = server.executor(name='pdf', max_workers=2)
executor_ml = server.executor(name='ml', max_workers=4)
executor_image = server.executor(name='image', max_workers=2)
```

**Nota**: `ExecutorRegistry` esistente **già supporta** questo pattern.

**Idea**: Offload handler a pool con configurazione runtime.

```python
class ExecutorPlugin(BasePlugin):
    """Offloads handler execution to a server-managed executor."""

def wrap_handler(self, route, entry, call_next):
        def wrapper(*args, **kwargs):
            cfg = self.configuration(entry.name)
            pool_name = cfg.get("pool")

if not pool_name or cfg.get("disabled"):
                return call_next(*args, **kwargs)  # Run inline

executor = self.binder.get_executor(pool_name)
            return executor.run(call_next, *args, **kwargs)

**Uso**:
```python
@route("generate_report", executor="pdf")
def generate_report(self, data):
    return make_pdf(data)

# Runtime debugging - forza esecuzione locale
app.router.configure("generate_report", executor_disabled=True)
```

**Valutazione**: Interessante per debugging runtime, ma aggiunge complessità.

**Idea**: Estendere il pattern a worker remoti via NATS o WebSocket.

```python
executor_remote = server.executor(
    'nats',
    name='heavy',
    subject='tasks.heavy',
    url='nats://worker:4222'
)

@executor_remote
def heavy_task(data):
    return process(data)  # Eseguito su worker remoto

result = await heavy_task(data)  # Stessa API
```

**Benefici dichiarati**:
- Horizontal scaling across machines
- Automatic load balancing (NATS)
- Fault tolerance
- Stessa API dei local executor

**Valutazione**: Fuori scope per framework minimale. Chi serve questo usa Celery/RQ/etc.

**Option 1: Semaphore-based Throttling** (implementato)
```python
async with self._semaphore:
    result = await self._execute(func, *args, **kwargs)
```
Blocca se troppi task pending.

**Option 2: Fail-Fast on Overload**
```python
if self._semaphore.locked():
    raise ExecutorOverloadError(
        f"Executor '{self.name}' has {self.max_pending} pending tasks."
    )
```
Fallisce immediatamente invece di bloccare.

**Valutazione**: Option 1 già implementata. Option 2 potrebbe essere un parametro.

**Idea**: Metriche esportabili per Prometheus.

```python
from prometheus_client import Counter, Histogram, Gauge

executor_tasks_total = Counter(
    'executor_tasks_total',
    'Total executor tasks',
    ['executor', 'status']
)
executor_duration = Histogram(
    'executor_task_duration_seconds',
    'Task execution duration',
    ['executor']
)
executor_pending = Gauge(
    'executor_pending_tasks',
    'Currently pending tasks',
    ['executor']
)
```

**Valutazione**: Utile ma opzionale. Il codice esistente ha già metriche base, Prometheus può essere aggiunto sopra.

**Idea**: Endpoint per esporre metriche di tutti gli executor.

```python
class AsgiServer:
    def get_executor_metrics(self) -> list[dict]:
        return [ex.metrics for ex in self._executors.values()]

@metrics_app.route("/metrics/executors")
async def executor_metrics(request):
    return JSONResponse(server.get_executor_metrics())
```

**Nota**: `ExecutorRegistry.all_metrics()` **già implementa** questo.

| Idea | Già Implementato | Da Implementare | Scartare |
|------|------------------|-----------------|----------|
| Worker Initialization | ✅ `initializer/initargs` | - | - |
| Multithreaded Workers | - | - | ⚠️ Troppo complesso |
| Multiple Isolated Pools | ✅ `ExecutorRegistry` | - | - |
| Executor Plugin | - | ❓ Valutare | - |
| Remote Executors | - | - | ❌ Fuori scope |
| Backpressure Semaphore | ✅ Implementato | - | - |
| Backpressure Fail-Fast | - | ❓ Come opzione | - |
| Prometheus Integration | - | ❓ Opzionale | - |
| Server Metrics Endpoint | ✅ `all_metrics()` | - | - |

- `legacy/genro_asgi_execution.md` - **ELIMINATO** (contenuto integrato qui)
- `legacy/architecture.md` - Sezione Executors integrata qui

Quando si deciderà di implementare gli executors:

1. [ ] Decidere approccio (minimalista vs completo)
2. [ ] Scrivere test per codice esistente
3. [ ] Definire API di integrazione con Server (`server.executor()` vs `ServerBinder.executor()`)
4. [ ] Implementare integrazione Lifespan (shutdown automatico)
5. [ ] Valutare: aggiungere fail-fast backpressure come opzione
6. [ ] Valutare: Executor Plugin per genro-routes
7. [ ] Documentare in answers/J-executors.md

## Source: initial_specifications/01-overview.md

**Version**: 0.1.0
**Status**: Alpha
**Last Updated**: 2025-12-13

genro-asgi is a minimal ASGI foundation for building web services. It provides:

- ASGI server with multi-app routing
- Request/Response abstractions
- Middleware system
- Static file serving
- WebSocket support
- Lifespan management

1. **Minimal dependencies** - Only essential packages (uvicorn, pyyaml, genro-toolbox, genro-routes)
2. **No magic** - Explicit configuration, predictable behavior
3. **Composable** - Mix and match components as needed
4. **Type-safe** - Full type hints throughout

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

| Component | Module | Description |
|-----------|--------|-------------|
| **AsgiServer** | `servers/base.py` | Main entry point, loads config, mounts apps |
| **Publisher** | `servers/publisher.py` | Event publishing for server lifecycle |

| Component | Module | Description |
|-----------|--------|-------------|
| **Dispatcher** | `dispatcher.py` | Routes requests to apps via genro_routes |
| **ServerLifespan** | `lifespan.py` | Manages startup/shutdown lifecycle |

| Component | Module | Description |
|-----------|--------|-------------|
| **BaseRequest** | `request.py` | Abstract base for all request types |
| **HttpRequest** | `request.py` | HTTP request wrapper |
| **Response** | `response.py` | Base response class |
| **JSONResponse** | `response.py` | JSON response with auto-serialization |
| **HTMLResponse** | `response.py` | HTML response |
| **FileResponse** | `response.py` | File streaming response |

| Component | Module | Description |
|-----------|--------|-------------|
| **AsgiApplication** | `applications/base.py` | Base class for apps mounted on server |
| **StaticSite** | `applications/static_site.py` | App for serving static files |

| Component | Module | Description |
|-----------|--------|-------------|
| **StaticRouter** | `routers/static_router.py` | Router for serving static files from directory |

| Component | Module | Description |
|-----------|--------|-------------|
| **CORSMiddleware** | `middleware/cors.py` | Cross-Origin Resource Sharing |
| **ErrorMiddleware** | `middleware/errors.py` | Exception handling |
| **LoggingMiddleware** | `middleware/logging.py` | Request/response logging |
| **CompressionMiddleware** | `middleware/compression.py` | Gzip/deflate compression |

| Component | Module | Description |
|-----------|--------|-------------|
| **WebSocket** | `websocket.py` | WebSocket connection handler |
| **WebSocketState** | `websocket.py` | Connection state enum |

| Component | Module | Description |
|-----------|--------|-------------|
| **WsxProtocol** | `wsx/protocol.py` | Transport-agnostic RPC protocol |

| Component | Module | Description |
|-----------|--------|-------------|
| **BaseExecutor** | `executors/base.py` | Abstract executor interface |
| **LocalExecutor** | `executors/local.py` | Thread/process pool executor |
| **ExecutorRegistry** | `executors/registry.py` | Manages named executors |

| Component | Module | Description |
|-----------|--------|-------------|
| **Headers** | `datastructures/headers.py` | HTTP headers container |
| **QueryParams** | `datastructures/query_params.py` | URL query parameters |
| **URL** | `datastructures/url.py` | URL parsing and manipulation |
| **Address** | `datastructures/address.py` | Client address (host, port) |
| **State** | `datastructures/state.py` | Request/app state container |

| Component | Module | Description |
|-----------|--------|-------------|
| **ServerBinder** | `utils/binder.py` | Binds apps to server context |

| Package | Purpose |
|---------|---------|
| `uvicorn` | ASGI server |
| `pyyaml` | Configuration loading |
| `genro-toolbox` | SmartOptions, utilities |
| `genro-routes` | Router, RoutingClass |
| `genro-tytx` | Typed serialization (WebSocket, WSX, Request) |

| Package | Purpose | Install |
|---------|---------|---------|
| `orjson` | Fast JSON serialization | `pip install genro-asgi[json]` |

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

```yaml
# config.yaml
server:
  host: "127.0.0.1"
  port: 8000

apps:
  myapp: "myapp:MyApp"
```

```bash
# From app directory
python -m genro_asgi

# Or with explicit directory
python -m genro_asgi --app-dir /path/to/app
```

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

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0

## Source: initial_specifications/legacy/TODO-to-document.md

This file collects items found in legacy files that still need to be documented in `interview/answers/`.

As items get documented, they are removed from here.
As legacy files are analyzed, they are deleted.

- [ ] Middleware pattern (wrap handler)
- [ ] apply_middlewares with reversed()
- [ ] Centralized error middleware

- [ ] lifespan.startup / lifespan.shutdown events
- [ ] lifespan.startup.complete / lifespan.shutdown.complete

- [ ] Delegation to genro_wsx
- [ ] ws_app(scope, receive, send)

- [ ] Pattern with ApplicationCommunicator
- [ ] asgiref.testing

Content moved to `specifications/executors.md`.

OBSOLETE - used TOML format, project uses YAML.
Current documentation already in `interview/answers/E-configuration.md`.

- Envelope pattern - replaced by BaseRequest/HttpRequest/MsgRequest inheritance

- Multi-App Dispatcher (`servers/base.py`, `dispatcher.py`)
- Server-App Integration (`utils/binder.py`: ServerBinder, AsgiServerEnabler)
- Lifespan Management (`lifespan.py`)
- Error Handling 404 (`dispatcher.py`, `exceptions.py`)

Content moved to `specifications/executors.md` (comprehensive analysis).

DoS protections for streaming endpoints:
- Max body size (upload)
- Timeouts (read/send/idle)
- Rate limiting (requests/sec, bandwidth)
- Connection limits (per-IP, per-user)

```python
# Example config
streaming_app = StreamingApp(
    max_upload_size=100 * 1024 * 1024,  # 100MB
    upload_timeout=300,
    ws_max_message_size=1 * 1024 * 1024,
    ws_idle_timeout=60,
    rate_limit_requests=100,  # per minute
)
```

Multiple servers on different ports in same process:

```python
public_server = AsgiServer()   # Port 80
admin_server = AsgiServer()    # Port 9090 (VPN)
ops_server = AsgiServer()      # Port 9100 (metrics)
```

Mount different app types for different workloads:

```
AsgiServer
├── /api/* → BusinessApp (full middleware, auth, DB)
├── /ws/rpc/* → BusinessApp (WSX protocol)
├── /stream/* → StreamingApp (minimal, high throughput)
└── /ws/raw/* → StreamingApp (raw WebSocket)
```

This is **fundamental** documentation for WSGI support - the server must be able to run legacy WSGI apps.

Moved to `specifications/wsgi_support/` with updated README.

- [ ] How to mount WSGI apps in AsgiServer
- [ ] WsgiToAsgi wrapper usage
- [ ] Migration phases overview
- [ ] Backward compatibility guarantees

- [x] `genro_asgi_execution.md` - DELETED
- [x] `configuration.md` - DELETED
- [x] `architecture.md` - DELETED
- [x] `legacy-migration/` - MOVED to specifications/wsgi_support/
- [x] `migration-opinions/` - MOVED to specifications/wsgi_support/

**All legacy files processed!**

## Source: initial_specifications/wsgi_support/04-migration-phases.md

**Status**: Design Proposal
**Source**: migrate_docs/EN/asgi/arc/architecture.md

Migration from WSGI to ASGI occurs in eight phases, each independently deployable with rollback capability.

| Phase | Description | gnrdaemon | Pages | Notes |
|-------|-------------|-----------|-------|-------|
| **0** | ASGI wrapper for WSGI | Unchanged | Ephemeral | Single entry point |
| **1** | Sticky sessions + PageRegistry | Reduced | Ephemeral | Multi-process (FUTURE) |
| **2** | NATS as alternative channel | Fallback | Ephemeral | Flag-based IPC (FUTURE) |
| **3** | Mono-process + PageRegistry for WS | Unchanged | Ephemeral + Live (WS) | Delay sticky adoption |
| **4** | All registries in-process | Eliminated | Ephemeral (fast load) | No daemon IPC |
| **5** | Resident pages | None | Resident | No reconstruction |
| **6** | Stabilization and testing | None | Resident | Bug fixing |
| **7** | Multi-process + sticky + scaling | None | Resident | Production ready |

**Note**: Phases 1-2 are deferred. The migration path is: 0 → 3 → 4 → 5 → 6 → 7

**Goal**: AsgiServer as single entry point, wrapping the existing WSGI app. Infrastructure ready for WebSocket and Executors when needed.

```
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (NEW entry)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │ WSGI App  │  │ WebSocket │  │ Executors │
        │ (wrapped) │  │ (ready)   │  │ (ready)   │
        └─────┬─────┘  └───────────┘  └───────────┘
              │
              ▼
        ┌─────────────────┐
        │   gnrdaemon     │
        │  (unchanged)    │
        └─────────────────┘
```

- **AsgiServer** becomes the single entry point (replaces Nginx routing to Gunicorn)
- **WSGI app** is wrapped and served by AsgiServer
- **WebSocket** infrastructure available if/when needed
- **Executors** infrastructure available if/when needed
- **gnrdaemon** unchanged - still handles all state

- WebSocket connections via AsgiServer
- ProcessPoolExecutor for CPU-bound tasks
- Modern async infrastructure

- **Unchanged** - maintains global registry of pages and connections
- Handles broadcasts and shared events
- All state management as before

Revert to Nginx + Gunicorn direct setup (gnrdaemon unchanged).

> **Note**: This phase is deferred. We proceed directly from Phase 0 to Phase 3 to delay sticky session complexity.

**Goal**: Introduce sticky sessions and process-local page registry.

```
                     ┌─────────────────┐
                     │   Nginx :8080   │
                     │ (sticky routing)│
                     └────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Process P1   │     │  Process P2   │     │  Process P3   │
│  users: 1-20  │     │  users: 21-40 │     │  users: 41-60 │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │PageRegistry│ │     │ │PageRegistry│ │     │ │PageRegistry│ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│  HTTP + WS    │     │  HTTP + WS    │     │  HTTP + WS    │
└───────┬───────┘     └───────┬───────┘     └───────┬───────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   gnrdaemon     │
                    │ (coordinator)   │
                    │ (reduced role)  │
                    └─────────────────┘
```

- **Sticky routing** by user_id (nginx or internal router)
- **Page ID with process indicator** (`page_xxx|p01`)
- **Local PageRegistry** per process
- **Unified HTTP + WS** per process (AsgiServer)
- **gnrdaemon** becomes lightweight coordinator

- Cross-process broadcasts only
- Fallback for legacy page IDs without process indicator
- User → process mapping (or move to DB)

```python
# Process-local registry
class PageRegistry:
    def __init__(self):
        self._pages: dict[str, Page] = {}

def get(self, page_id: str) -> Page | None:
        return self._pages.get(page_id)

def register(self, page: Page) -> None:
        self._pages[page.page_id] = page
```

Disable sticky routing, re-enable gnrdaemon as primary registry.

> **Note**: This phase is deferred. NATS integration will be considered later if needed.

**Goal**: Introduce NATS as an alternative IPC channel to Pyro. Both coexist, selected via flag.

```
                     ┌─────────────────┐
                     │   Nginx :8080   │
                     │ (sticky routing)│
                     └────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Process P1   │     │  Process P2   │     │  Process P3   │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │PageRegistry│ │     │ │PageRegistry│ │     │ │PageRegistry│ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│  HTTP + WS    │     │  HTTP + WS    │     │  HTTP + WS    │
└───────┬───────┘     └───────┬───────┘     └───────┬───────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   gnrdaemon     │             │      NATS       │
    │    (Pyro)       │             │   (pub/sub)     │
    │   [fallback]    │             │   [new option]  │
    └─────────────────┘             └─────────────────┘
              │                               │
              └───────────┬───────────────────┘
                          │
                   USE_NATS flag
                   selects channel
```

- **NATS** introduced as alternative IPC channel
- **gnrdaemon** stays available as fallback
- **Flag-based selection**: `USE_NATS=1` or `USE_PYRO=1` (default: Pyro)
- **Gradual migration**: Test NATS with subset of users/processes

```python
# Environment variable selects IPC channel
import os

IPC_BACKEND = os.environ.get('IPC_BACKEND', 'pyro')  # 'pyro' or 'nats'

if IPC_BACKEND == 'nats':
    from .ipc_nats import publish_dbevent, subscribe_dbevent
else:
    from .ipc_pyro import publish_dbevent, subscribe_dbevent
```

nc = await nats.connect("nats://localhost:4222")

# dbevent broadcast
await nc.publish("dbevent", json_payload)

# Each process subscribes and filters locally
async def on_dbevent(msg):
    data = json.loads(msg.data)
    for page in local_registry.get_subscribed(data["table"]):
        page.store.add_changes(data)

await nc.subscribe("dbevent", cb=on_dbevent)
```

Topics:
- `dbevent` - Database change notifications (broadcast)
- `user.{id}.notify` - User-specific notifications
- `system.broadcast` - System-wide messages

Set `IPC_BACKEND=pyro` to revert to gnrdaemon.

> **Note**: This is the first step after Phase 0. Using mono-process delays sticky session complexity.

**Goal**: Single process, multi-threaded. PageRegistry keeps pages alive for WebSocket push only. Ephemeral page lifecycle unchanged - pages still reconstructed from gnrdaemon.

```
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (mono-proc)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
        ┌───────────┐                  ┌───────────┐
        │ HTTP req  │                  │ WebSocket │
        │           │                  │           │
        │ Page      │                  │ Page      │
        │ REBUILD   │                  │ from      │
        │ (as now)  │                  │ REGISTRY  │
        └─────┬─────┘                  └─────┬─────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │  PageRegistry   │
                     │  (keeps pages   │
                     │   alive for WS) │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   gnrdaemon     │
                     │  (unchanged)    │
                     └─────────────────┘
```

**Pages are still reconstructed for HTTP requests** (same as current behavior), but **also kept alive in PageRegistry** for WebSocket push.

```python
class PageRegistry:
    """Registry of live pages for WebSocket push only."""

def __init__(self):
        self._pages: dict[str, Page] = {}

def register(self, page: Page) -> None:
        """Keep page alive for WS push."""
        self._pages[page.page_id] = page

def get_for_ws(self, page_id: str) -> Page | None:
        """Get live page for WebSocket operations."""
        return self._pages.get(page_id)

def unregister(self, page_id: str) -> None:
        """Remove page when client disconnects."""
        self._pages.pop(page_id, None)
```

```
Client → AsgiServer → Page RECONSTRUCTED from gnrdaemon → Execute → Response → Page discarded
```

```
dbevent → gnrdaemon → Process → PageRegistry.get_for_ws(page_id) → Live Page → WS Push
```

- **Single process** - No sticky routing needed
- **Multi-threaded** - Handles concurrent requests
- **PageRegistry** - Keeps pages alive for WS only
- **gnrdaemon** - Unchanged, still handles state and dbevent
- **Page ID** - No format change (no `|pXX` suffix)

- **Simpler deployment** - Single process, no routing complexity
- **Test PageRegistry** - Validate concept before multi-process
- **WebSocket enabled** - Push notifications to live pages
- **Backward compatible** - HTTP flow unchanged

Remove PageRegistry, disable WebSocket features.

**Goal**: Move ALL registries from gnrdaemon into the process. Ephemeral pages still reconstructed, but data is already in-process (no Pyro IPC).

```text
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (mono-proc)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
        ┌───────────┐                  ┌───────────┐
        │ HTTP req  │                  │ WebSocket │
        │           │                  │           │
        │ Page      │                  │ Page      │
        │ REBUILD   │                  │ from      │
        │ (fast!)   │                  │ REGISTRY  │
        └─────┬─────┘                  └─────┬─────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │  IN-PROCESS     │
                     │  ┌───────────┐  │
                     │  │PageRegistry│  │
                     │  │UserRegistry│  │
                     │  │ConnRegistry│  │
                     │  │GlobalReg   │  │
                     │  └───────────┘  │
                     └─────────────────┘
                              │
                              ✗ (no gnrdaemon)
```

**gnrdaemon eliminated**. All registries (global, users, connections, pages) are now in-process.

Pages are still ephemeral (reconstructed per request), but reconstruction is **fast** because data is already in memory (no Pyro IPC overhead).

```python
class ProcessRegistries:
    """All registries previously in gnrdaemon, now in-process."""

def __init__(self):
        self.global_registry: dict[str, Any] = {}
        self.users: dict[str, dict] = {}        # user_id → user data
        self.connections: dict[str, dict] = {}  # conn_id → connection data
        self.pages: dict[str, Page] = {}        # page_id → live page (for WS)

def get_page_data(self, page_id: str) -> dict | None:
        """Get page state for reconstruction (fast, in-memory)."""
        return self._page_states.get(page_id)

def save_page_data(self, page_id: str, state: dict) -> None:
        """Save page state after request."""
        self._page_states[page_id] = state
```

**HTTP Request** (ephemeral page, fast reconstruction):

```text
Client → AsgiServer → ProcessRegistries.get_page_data() → Page REBUILT (in-memory, fast) → Execute → Save state → Response
```

**WebSocket Push** (unchanged from Phase 3):

```text
dbevent → ProcessRegistries → PageRegistry.get_for_ws(page_id) → Live Page → WS Push
```

- **gnrdaemon eliminated** - No more Pyro IPC
- **All registries in-process** - global, users, connections, pages
- **Fast reconstruction** - No network overhead
- **Pages still ephemeral** - Same lifecycle, just faster

- **No IPC latency** - All data in-process
- **Simpler architecture** - No external daemon
- **Same page lifecycle** - Minimal code changes

Re-enable gnrdaemon, configure registries to use Pyro.

**Goal**: Eliminate page reconstruction. Pages stay alive between requests.

```text
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (mono-proc)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
        ┌───────────┐                  ┌───────────┐
        │ HTTP req  │                  │ WebSocket │
        │           │                  │           │
        │ Page      │                  │ Page      │
        │ from      │    ◄── SAME ──►  │ from      │
        │ REGISTRY  │                  │ REGISTRY  │
        └─────┬─────┘                  └─────┬─────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │  PageRegistry   │
                     │  (RESIDENT)     │
                     │                 │
                     │  Pages live     │
                     │  between reqs   │
                     └─────────────────┘
```

**No more page reconstruction**. HTTP requests and WebSocket use the **same live page** from the registry.

```python
class PageRegistry:
    """Registry of RESIDENT pages."""

def get_or_create(self, page_id: str, user_id: str) -> Page:
        """Get existing page or create new one."""
        if page_id not in self._pages:
            self._pages[page_id] = Page(page_id, user_id)
        return self._pages[page_id]
```

**HTTP Request** (resident page):

```text
Client → AsgiServer → PageRegistry.get_or_create(page_id) → SAME Page → Execute → Response
```

**WebSocket Push** (same page):

```text
dbevent → PageRegistry.get(page_id) → SAME Page → WS Push
```

- **Pages are resident** - Live between requests
- **No reconstruction** - Same page object reused
- **Unified access** - HTTP and WS use same page

- **Zero reconstruction overhead** - Pages always ready
- **Consistent state** - Same page for HTTP and WS
- **Simpler code** - No save/restore logic

Re-enable ephemeral page lifecycle (Phase 4).

**Goal**: Comprehensive testing and bug fixing of the new architecture.

1. **Memory management** - Page lifecycle, garbage collection
2. **Concurrency** - Thread safety, race conditions
3. **State consistency** - Page state across HTTP/WS
4. **Error handling** - Graceful degradation
5. **Performance** - Benchmarks, profiling

```python
# Memory tests
def test_page_cleanup_on_disconnect():
    """Pages should be cleaned up when client disconnects."""
    pass

def test_no_memory_leaks():
    """Memory should not grow unbounded."""
    pass

# Concurrency tests
def test_concurrent_requests_same_page():
    """Multiple concurrent requests to same page."""
    pass

def test_ws_push_during_http_request():
    """WS push while HTTP request in progress."""
    pass

# State tests
def test_state_consistency_http_ws():
    """HTTP changes visible in WS and vice versa."""
    pass
```

- **No new features** - Focus on stability
- **Bug fixes** - Address issues found in testing
- **Documentation** - Update for new architecture

- [ ] All existing tests pass
- [ ] New architecture tests pass
- [ ] Memory stable under load
- [ ] No race conditions detected
- [ ] Performance meets or exceeds baseline

Revert to Phase 5 if critical issues found.

**Goal**: Scale to multiple processes with sticky routing for production.

```text
                     ┌─────────────────┐
                     │   Load Balancer │
                     │ (sticky by user)│
                     └────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Process P1   │     │  Process P2   │     │  Process P3   │
│  users: 1-N   │     │  users: N-M   │     │  users: M-Z   │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │PageRegistry│ │     │ │PageRegistry│ │     │ │PageRegistry│ │
│ │(resident)  │ │     │ │(resident)  │ │     │ │(resident)  │ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│  HTTP + WS    │     │  HTTP + WS    │     │  HTTP + WS    │
└───────────────┘     └───────────────┘     └───────────────┘
```

**Sticky routing by user_id**. Each user always routes to the same process. Pages are resident within each process.

```python
def route_to_process(user_id: str, num_processes: int) -> int:
    """Deterministic routing: same user always goes to same process."""
    return hash(user_id) % num_processes
```

```text
page_abc123def456|p02
                 └─┬─┘
           process indicator
```

- **Multi-process** - Scale horizontally
- **Sticky routing** - User → Process affinity
- **Page ID format** - Includes process indicator
- **Cross-process IPC** - For notifications (NATS or similar)

- **Horizontal scaling** - Add processes as needed
- **Process isolation** - Fault containment
- **Load distribution** - Users spread across processes

Revert to mono-process (Phase 6).

For local development, simulate multi-process behavior:

```bash
# Single process (default)
gnr asgi serve --reload

# Simulated multi-process
gnr asgi serve --reload --local-balancer --max-processes 3
```

- Starts multiple local processes
- Each with own event loop and PageRegistry
- Tests routing, balancing, cross-process communication
- Same code runs in production multi-machine setup

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

```text
Now ─────────────────────────────────────────────────────────────────────────────────► Future

Phase 0          Phase 3              Phase 4              Phase 5         Phase 6         Phase 7
[ASGI Wrap]      [Mono+WS]            [No daemon]          [Resident]      [Testing]       [Scale]
    │                 │                    │                    │               │               │
    │   - AsgiServer  │   - PageRegistry   │   - All registries │   - Pages     │   - Bug fix   │   - Multi-proc
    │     entry point │     for WS only    │     in-process     │     resident  │   - Testing   │   - Sticky
    │   - WSGI wrap   │   - Ephemeral      │   - No Pyro IPC    │   - No rebuild│   - Stability │   - Scaling
    │   - gnrdaemon   │     pages +        │   - Fast rebuild   │   - HTTP=WS   │               │   - page_id|p
    │     unchanged   │     gnrdaemon      │                    │     same page │               │
```

- [ ] AsgiServer serves as single entry point
- [ ] WSGI app wrapped and functional
- [ ] WebSocket infrastructure available
- [ ] Executors infrastructure available
- [ ] gnrdaemon unchanged, all tests pass

- [ ] Sticky routing works correctly
- [ ] PageRegistry maintains state across requests
- [ ] Page ID with process indicator (`page_xxx|p01`) works
- [ ] gnrdaemon only handles cross-process broadcasts

- [ ] NATS connection and pub/sub working
- [ ] IPC_BACKEND flag switches between Pyro and NATS
- [ ] dbevent broadcast via NATS working
- [ ] gnrdaemon available as fallback
- [ ] Gradual migration path validated

- [ ] Mono-process multi-threaded app working
- [ ] PageRegistry keeps pages alive for WS
- [ ] HTTP requests still reconstruct pages (unchanged)
- [ ] WebSocket push to live pages working
- [ ] gnrdaemon unchanged, no page_id format change

- [ ] All registries moved in-process
- [ ] gnrdaemon eliminated
- [ ] Pages still ephemeral but fast reconstruction
- [ ] No Pyro IPC overhead

- [ ] Pages are resident (no reconstruction)
- [ ] HTTP and WS use same page object
- [ ] Page lifecycle managed by registry

- [ ] All existing tests pass
- [ ] New architecture tests pass
- [ ] Memory stable under load
- [ ] No race conditions detected
- [ ] Performance meets or exceeds baseline

- [ ] Multi-process deployment working
- [ ] Sticky routing by user_id
- [ ] Page ID with process indicator
- [ ] Cross-process IPC (NATS) for notifications
- [ ] Horizontal scaling validated

## Source: initial_specifications/wsgi_support/03-page-id-routing.md

**Status**: Design Proposal
**Source**: migrate_docs/EN/asgi/arc/architecture.md

Currently, page IDs are 22-character unique identifiers:

To find which process owns a page, the system must query the global gnrdaemon registry.

Embed the process identifier directly in the page ID:

```
abc123def456ghi789|p02
                  └─┬─┘
                process indicator
```

1. **Direct routing** - No global registry lookup needed
2. **Stateless routing** - Any router can decode the destination
3. **Backward compatible** - Old IDs without `|` default to legacy behavior

base_id:     22 characters (existing format)
separator:   | (pipe)
process_id:  p{NN} where NN is zero-padded process number
```

```
abc123def456ghi789jkl|p01  → Process 1
xyz789abc123def456ghi|p02  → Process 2
old_style_page_id_here     → Legacy (no indicator)
```

```python
def route_request(page_id: str) -> int:
    """Extract process number from page_id."""
    if '|' in page_id:
        _, process_part = page_id.rsplit('|', 1)
        if process_part.startswith('p'):
            return int(process_part[1:])
    # Legacy page_id - use fallback routing
    return route_by_user(request.user_id)

def create_page_id(process_id: int) -> str:
    """Generate new page_id with process indicator."""
    base_id = generate_unique_id(22)  # Existing logic
    return f"{base_id}|p{process_id:02d}"
```

Same pattern can apply to connection IDs:

```
conn_abc123def456ghi|p01
```

This allows routing WebSocket messages directly to the correct process.

With process indicators embedded in IDs:

| Level | ID Format | Routing |
|-------|-----------|---------|
| **Process** | `p01`, `p02`, ... | From page_id/conn_id |
| **User** | `user_123` | Hash or lookup table |
| **Connection** | `conn_xxx|p01` | Direct from ID |
| **Page** | `page_xxx|p01` | Direct from ID |

```python
def parse_page_id(page_id: str) -> tuple[str, int | None]:
    """Parse page_id, return (base_id, process_id or None)."""
    if '|' in page_id:
        base, process_part = page_id.rsplit('|', 1)
        process_id = int(process_part[1:]) if process_part.startswith('p') else None
        return base, process_id
    return page_id, None  # Legacy format
```

All newly created pages get process indicator. Old pages continue to work via gnrdaemon fallback.

After sufficient time, all active pages have new format. gnrdaemon registry becomes optional.

If process P02 dies and restarts, pages with `|p02` still route correctly. The process must be able to reconstruct page state (from DB or accept reconstruction).

Adding P03 doesn't affect existing pages. New pages can be assigned to P03.

Removing P02 requires:
1. Drain existing connections
2. Let pages expire naturally
3. Or migrate pages to another process (state serialization)

With sticky routing by page_id, load balancing happens at:
1. **User assignment time** - Which process gets new user
2. **Page creation time** - Which process creates new page

Not at request time (requests are deterministically routed).

## Source: initial_specifications/wsgi_support/02-current-architecture.md

**Status**: Reference Document
**Source**: migrate_docs/EN/wsgi/arc/production.md

The current Genropy production environment uses a multi-process architecture managed by supervisord, with nginx as reverse proxy.

```
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   Nginx :8080   │
                     │  (reverse proxy)│
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │ Gunicorn :8888  │             │ gnrasync :9999  │
    │   (HTTP/WSGI)   │             │   (WebSocket)   │
    │   5 workers     │             │   (Tornado)     │
    └────────┬────────┘             └────────┬────────┘
             │                               │
             └───────────────┬───────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   gnrdaemon     │
                    │  (Pyro server)  │
                    │  (in-memory)    │
                    └─────────────────┘
```

Entry point for all traffic. Routes by path:

- `/websocket` → gnrasync (9999)
- `/*` → Gunicorn (8888)

```nginx
server {
    listen 8080 default_server;

# WebSocket
    location /websocket {
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_pass http://127.0.0.1:9999;
    }

# HTTP
    location / {
        proxy_pass http://127.0.0.1:8888;
    }
}
```

WSGI server handling HTTP requests:

- 5 worker processes
- 120s timeout
- Graceful restart support

```bash
gunicorn --workers 5 --timeout 120 --bind 0.0.0.0:8888 root
```

Tornado-based WebSocket server:

- Handles real-time bidirectional communication
- Connected to gnrdaemon for state

Central Pyro server holding in-memory state:

```python
# Registries maintained by gnrdaemon
registries = {
    'global': {...},                    # Global state
    'users': {user_id: {...}},          # Per-user state
    'connections': {conn_id: {...}},    # Per-connection state (22 char ID)
    'pages': {page_id: {...}},          # Per-page state (22 char ID)
}
```

Communication via Pyro (async, one request at a time).

- **gnrtaskscheduler** - Scheduled tasks
- **gnrtaskworker** - Task execution

All processes managed by supervisord:

```ini
[supervisord]
nodaemon=true

[program:gnrdaemon]
command=gnrdaemon main

[program:gunicorn]
command=gunicorn --workers 5 --timeout 120 --bind 0.0.0.0:8888 root

[program:gnrasync]
command=gnrasync -p 9999 main

[program:gnrtaskscheduler]
command=gnrtaskscheduler main

[program:gnrtaskworker]
command=gnrtaskworker main
```

```
Client
  │
  ▼
Nginx :8080
  │ proxy_pass
  ▼
Gunicorn :8888
  │
  ▼
Worker Process (ephemeral page)
  │
  ├── Parse request (page_id, user_id)
  │
  ├── Pyro call to gnrdaemon
  │   └── Fetch page/user/connection state
  │
  ├── Execute business logic
  │
  ├── Pyro call to gnrdaemon
  │   └── Save updated state
  │
  └── Return response (page dies)
```

```
Client
  │
  ▼
Nginx :8080 /websocket
  │ proxy_pass (upgrade)
  ▼
gnrasync :9999 (Tornado)
  │
  ├── Maintain persistent WS connection
  │
  ├── On message: Pyro call to gnrdaemon
  │
  └── Push messages to client
```

1. **gnrdaemon bottleneck** - Single Pyro server, one request at a time
2. **Page reconstruction** - Every HTTP request rebuilds page from gnrdaemon
3. **IPC overhead** - Pyro calls for every state access
4. **Separate WS process** - Tornado isolated from Gunicorn workers
5. **No sticky sessions** - Any worker can handle any user

1. **Supervisord** - Process management works well
2. **Nginx** - Reverse proxy pattern (or replace with Uvicorn multi-worker)
3. **Async workers** - Task scheduler/worker pattern
4. **Page/Connection IDs** - 22 char unique identifiers

1. **gnrdaemon** → In-process PageRegistry (eliminate IPC)
2. **Tornado** → Native ASGI WebSocket (unified stack)
3. **Gunicorn** → Uvicorn (ASGI native)
4. **Ephemeral pages** → Resident pages (eliminate reconstruction)
5. **Random routing** → Sticky sessions by user

## Source: initial_specifications/wsgi_support/01-overview.md

**Status**: Draft - Design Discussion
**Last Updated**: 2025-11-28

Migrating from a legacy architecture based on:

- **Gunicorn**: WSGI workers serving SPA pages
- **Tornado**: WebSocket handling
- **gnrdaemon**: Pyro-based in-memory state server (registries)
- **Nginx**: Routing between Tornado and Gunicorn

Current flow:
```
Client SPA
    │
    ├── page_id (22 char unique)
    ├── connection_id (22 char unique)
    └── local JS state

Gunicorn Worker (ephemeral)
    │
    ├── receives page_id, connection_id, user_id
    ├── reconstructs Page context from gnrdaemon (Pyro)
    │       │
    │       ▼
    │   gnrdaemon (persistent Pyro server)
    │   ├── global registry
    │   ├── users registry {user_id: data}
    │   ├── connections registry {conn_id: data}
    │   └── pages registry {page_id: data}
    │
    ├── executes business logic
    ├── writes state back to gnrdaemon
    └── responds and dies
```

**Problem with current architecture:**

- gnrdaemon is a bottleneck (single Pyro server, one request at a time)
- Page reconstruction on every request adds latency
- IPC overhead (Pyro) for every state access

Keep Page objects alive in-process, eliminating:

- Pyro IPC latency
- Page reconstruction overhead
- Single-point-of-failure daemon

Route users to specific processes. Each process maintains its own page registry.

```
                    Load Balancer / Router
                    (sticky by user_id)
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   Process P1         Process P2         Process P3
   users: 1-20        users: 21-40       users: 41-60
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ PageRegistry│    │ PageRegistry│    │ PageRegistry│
   │ {id1: Page} │    │ {id5: Page} │    │ {id9: Page} │
   │ {id2: Page} │    │ {id6: Page} │    │ {id10: Page}│
   │ {id3: Page} │    │ {id7: Page} │    │   ...       │
   └─────────────┘    └─────────────┘    └─────────────┘
```

```python
def get_process_for_user(user_id: str, num_processes: int) -> int:
    """Deterministic routing: same user always goes to same process."""
    return hash(user_id) % num_processes
```

Or with explicit mapping for more control:

```python
# Lookup table (could be in shared config or external store)
user_process_map: dict[str, int] = {
    'user_001': 0,
    'user_002': 0,
    'user_003': 1,
    # ...
}
```

**Ideal**: HTTP and WS for same user → same process

```
User 1 ──HTTP──→ P1 ──→ Page object
User 1 ──WS────→ P1 ──→ same Page object (direct access!)
```

**Question**: Can we guarantee WS sticky routing same as HTTP?

Options:
- Single process handles both HTTP and WS (AsgiServer with mounted apps)
- Separate WS process with forwarding to correct HTTP process

When User 2 (on P2) needs to notify User 1 (on P1):

```
User 2 ──HTTP──→ P2 ──→ notify(user_1, message)
                           │
                           ▼ NATS publish
                          P1 ──→ User 1's Page ──→ WS ──→ Client
```

**Decision**: NATS for all cross-process communication.

Each process subscribes to relevant topics and filters locally. See "NATS for IPC" section below.

If P1 dies, pages for users 1-20 are lost.

- **Accept it**: Pages get reconstructed on next request (lazy recovery)
- **Replicate state**: Periodic snapshot to disk or peer process
- **Stateless fallback**: If page not found, reconstruct from DB

**Likely choice**: Accept lazy recovery (same as current behavior if gnrdaemon restarts)

Adding/removing processes requires re-routing users.

- **Consistent hashing**: Minimize re-routing when processes change
- **Fixed pool**: Don't scale dynamically, size for peak load
- **Graceful migration**: Drain connections before removing process

```python
server = AsgiServer()
server.mount("/api", LegacyWsgiApp())  # Wrapped WSGI
server.mount("/ws", WebSocketApp())    # Native ASGI WS

# Both share same PageRegistry in-process
```

**Pros**: No IPC needed for same-user operations
**Cons**: Single process limits concurrency

```python
# Main process (router)
router = AsgiServer()
router.mount("/", StickyRouter(
    workers=[P1, P2, P3],
    route_by='user_id'
))

# Each worker process
worker = AsgiServer()
worker.mount("/api", BusinessApp())
worker.mount("/ws", WebSocketApp())
worker.page_registry = PageRegistry()  # Local to this process
```

**Pros**: Better concurrency, process isolation
**Cons**: Needs IPC for cross-user operations

NATS replaces gnrdaemon for all cross-process communication:

# Connect to NATS
nc = await nats.connect("nats://localhost:4222")

# Publish dbevent (broadcast to all processes)
await nc.publish("dbevent", json.dumps(payload).encode())

# Subscribe to dbevent
async def on_dbevent(msg):
    data = json.loads(msg.data)
    for page in local_registry.get_subscribed(data["table"]):
        page.store.add_changes(data)

await nc.subscribe("dbevent", cb=on_dbevent)
```

Topics:
- `dbevent` - Database change notifications (broadcast)
- `user.{id}.notify` - User-specific notifications
- `system.broadcast` - System-wide messages

**Why NATS**:
- Single binary (~10MB), easy to deploy
- Sub-millisecond latency
- Pub/Sub + Request/Reply patterns
- Multi-host ready (cluster native)
- CNCF project, actively maintained

Local registry for each process:

```python
class PageRegistry:
    """In-process registry of live Page objects."""

def __init__(self):
        self._pages: dict[str, Page] = {}
        self._user_pages: dict[str, set[str]] = {}  # user_id → set of page_ids

def register(self, page: Page) -> None:
        """Register a new page."""
        self._pages[page.page_id] = page
        self._user_pages.setdefault(page.user_id, set()).add(page.page_id)

def unregister(self, page_id: str) -> None:
        """Remove a page from registry."""
        page = self._pages.pop(page_id, None)
        if page:
            self._user_pages.get(page.user_id, set()).discard(page_id)

def get(self, page_id: str) -> Page | None:
        """Get page by ID."""
        return self._pages.get(page_id)

def get_user_pages(self, user_id: str) -> list[Page]:
        """Get all pages for a user."""
        page_ids = self._user_pages.get(user_id, set())
        return [self._pages[pid] for pid in page_ids if pid in self._pages]

def __len__(self) -> int:
        return len(self._pages)
```

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

- AsgiServer as single entry point
- WSGI app wrapped and served by AsgiServer
- WebSocket and Executors available if needed
- gnrdaemon unchanged

- Sticky routing by user_id
- Page ID with process indicator (`page_xxx|p01`)
- Local PageRegistry per process
- gnrdaemon reduced to coordinator for cross-process

- NATS introduced as alternative IPC channel
- gnrdaemon stays available as fallback
- Flag-based selection: `IPC_BACKEND=pyro` or `IPC_BACKEND=nats`
- Gradual migration: test NATS with subset of processes

- Single process, multi-threaded (delays sticky session complexity)
- PageRegistry keeps pages alive for WebSocket push only
- HTTP requests still reconstruct pages (unchanged behavior)
- gnrdaemon unchanged, no page_id format change

- All registries (global, users, connections, pages) moved in-process
- gnrdaemon eliminated
- Pages still ephemeral but fast reconstruction (no Pyro IPC)

- Pages stay alive between requests (no reconstruction)
- HTTP and WS use same page object
- Page lifecycle managed by registry

- Comprehensive testing and bug fixing
- Memory management, concurrency, state consistency
- No new features, focus on stability

- Scale to multiple processes
- Sticky routing by user_id
- Page ID with process indicator (`page_xxx|p01`)
- Cross-process IPC (NATS) for notifications

- This document captures design discussion, not final decisions
- Each stage should be independently deployable
- Rollback path must exist at each stage

## Source: initial_specifications/wsgi_support/claude_opinion.md

**Status**: Independent Analysis
**Date**: 2025-11-28
**Author**: Claude (AI Assistant)

The 8-phase migration strategy (with actual path 0 → 3 → 4 → 5 → 6 → 7) is **solid and pragmatic**. The decision to defer phases 1-2 (sticky sessions and NATS) and proceed with mono-process first is smart: it reduces initial complexity and allows architecture validation in a controlled environment.

| Aspect | Benefit |
|--------|---------|
| **Each phase is deployable** | Progressive release capability |
| **Rollback always possible** | Minimized risk |
| **Step-by-step validation** | Bugs identified early |

**Excellent choice** for several reasons:

- **Eliminates routing complexity**: No sticky sessions, no `page_id|pXX`
- **Simplified debugging**: Everything in one process, clear stack trace
- **Easier testing**: No IPC to mock
- **Fast development**: Focus on logic, not infrastructure

```
Phase 3: PageRegistry for WS only (ephemeral pages unchanged)
Phase 4: In-process registries (eliminates Pyro IPC)
Phase 5: Resident pages (eliminates reconstruction)
Phase 6: Stabilization (no features)
Phase 7: Scaling (only then multi-process)
```

This separation allows problem isolation: if something fails in Phase 5, you know it's related to resident pages, not registries (already validated in Phase 4).

```
Phases 0-3: gnrdaemon unchanged (safety net)
Phase 4: gnrdaemon eliminated (all registries in-process)
Phase 5+: No Pyro dependency
```

The daemon remains available as fallback until Phase 4, reducing risk.

**Problem**: The transition from "gnrdaemon for everything" to "everything in-process" is significant.

**Risks**:
- Different behaviors between Pyro and in-process
- Memory management (gnrdaemon was external)
- Concurrency (gnrdaemon serialized, in-process doesn't)

**Suggested mitigation**:
- Extended A/B testing before deploy
- Implicit Phase 4.5: in-process registries but gnrdaemon still active for comparison
- Detailed logging for post-deploy debugging

**Problem**: Pages are no longer destroyed after each request.

**Risks**:
- **Memory leaks**: Pages that are never removed
- **Stale state**: Old pages with obsolete state
- **OOM**: With many users, memory exhausted

**Suggested mitigation**:
- TTL for pages (e.g., 30 minutes without activity → cleanup)
- LRU cache with maximum page limit
- Memory monitoring with alerts
- Graceful degradation: if memory > threshold, revert to ephemeral

**Problem**: Sticky sessions and NATS are only deferred to Phase 7.

**Risks**:
- Complexity arrives anyway
- May require significant refactoring
- NATS introduces external dependency

**Suggested mitigation**:
- Design interfaces in Phases 3-6 already thinking about multi-process
- Abstract IPC from the start (even if mono-process)
- Test with local NATS during development

**Clarification**: Both ephemeral and resident pages are **READ-ONLY**. Data is written **only to PageRegistry**.

```
HTTP: Page rebuilt (READ-ONLY) → Execute → Writes to REGISTRY → Discarded
WS:   Live page (READ-ONLY) → Reads from REGISTRY → WS Push
```

```text
PageRegistry = Source of Truth (read/write)
Page (ephemeral or live) = View (read-only)
```

**Architectural advantage**: The "read-only pages + registry as store" pattern is clean, well-defined, and thread-safe by design.

**Clarification**: This risk already existed with gnrdaemon. Multiple requests from the same page in different threads require synchronization.

- **Lock per page**: Already implemented in current system, to be maintained
- **Lock on registry insert/delete**: Structural modification operations require lock

```python
class PageRegistry:
    def __init__(self):
        self._pages: dict[str, Page] = {}
        self._lock = threading.Lock()  # For insert/delete

def register(self, page: Page) -> None:
        with self._lock:
            self._pages[page.page_id] = page

def unregister(self, page_id: str) -> None:
        with self._lock:
            self._pages.pop(page_id, None)
```

**Recommendation**: Maintain the same locking pattern already in use.

The dbevent flow changes significantly:

**Phase 3** (with gnrdaemon):
```
DB commit → gnrdaemon → Process → PageRegistry → WS Push
```

**Phase 4** (without gnrdaemon):
```
DB commit → ??? → PageRegistry → WS Push
```

**Question**: Who generates the dbevent in Phase 4? The process itself? How?

**Recommendation**: Document the new dbevent flow without gnrdaemon.

In Phase 5+ pages are resident, but what happens in case of:
- Process restart?
- Crash?
- New version deploy?

**Recommendation**: Define persistence/recovery strategy (accept loss? periodic snapshots? event sourcing?).

Before moving to multi-process, validate that mono-process handles expected load.

**Recommendation**: Benchmark with realistic load in Phase 6, document limits (max users, max pages, max RPS).

| Aspect | Rating | Comment |
|--------|--------|---------|
| **Graduality** | ⭐⭐⭐⭐⭐ | Excellent, each phase is incremental |
| **Rollback** | ⭐⭐⭐⭐⭐ | Always possible, well documented |
| **Risk reduction** | ⭐⭐⭐⭐ | Mono-process first reduces complexity |
| **Clarity** | ⭐⭐⭐⭐⭐ | Excellent: read-only pages, registry as store |
| **Realism** | ⭐⭐⭐⭐ | Feasible, reasonable timeline |
| **Completeness** | ⭐⭐⭐ | Missing details on dbevent and persistence |

**Overall rating**: 4/5 - Solid strategy with some points to elaborate.

1. **Define dbevent flow without gnrdaemon** before Phase 4
2. **Plan memory management strategy** before Phase 5
3. **Benchmark in Phase 6** to validate mono-process limits
4. **Design IPC-agnostic interfaces** from Phase 3

The strategy is **approved with reservations**. The identified attention points are manageable and not blocking, but require explicit documentation before implementation. The decision to proceed mono-process first is particularly wise and significantly reduces overall project risk.

The path 0 → 3 → 4 → 5 → 6 → 7 is logical and well-structured. The most critical phase is 4 (gnrdaemon elimination) which will require particular attention during implementation.

## Source: initial_specifications/wsgi_support/chatgpt_opinion.md

**Date**: 2025-02-11  
**Scope**: Revisione dei documenti in `spec/legacy-migration/` e valutazione del percorso sticky ASGI con PageRegistry in-process.

## Per documento: sintesi + opinione
- `01-overview.md`: propone sticky routing per eliminare gnrdaemon, PageRegistry in-process, tolleranza al rilogin su crash. Opinione: direzione giusta; serve policy esplicita per process down (`pXX` non disponibile).
- `02-current-architecture.md`: foto dell’attuale WSGI/Tornado/Pyro con supervisord. Opinione: chiaro baseline; nessuna azione.
- `03-page-id-routing.md`: introduce `page_id|pXX` per routing deterministico, fallback per legacy. Opinione: bene; da fissare validazione/formato e comportamento se il processo indicato è down.
- `04-migration-phases.md`: fasi 0→1→2 con rollback. Opinione: struttura ok; mancano Definition of Done per fase (test/metriche/rollback concreti).
- `05-deployment-strategy.md`: green/blue/canary per rollout ASGI/legacy. Opinione: utile, ma vanno aggiunti limiti stickiness per WS/HTTP durante switch di colore e metriche per colore.
- `09-gemini-opinion.md`: propone container + NATS come evoluzione. Opinione: interessante come step successivo, ma non vincolante; con volumi attuali basta IPC leggero.
- `10-migration-proposal.md`: “Modern Monolith” con smart router + worker stateful. Opinione: coerente con sticky; richiede scelte pratiche su IPC e backpressure.
- `11-chatgpt-opinion.md`: bozza precedente (questa è la versione aggiornata).

## Valutazione sintetica complessiva
- Direzione corretta: sticky routing (`page_id|pXX`), PageRegistry in memoria per eliminare Pyro/gnrdaemon e unificare HTTP/WS in ASGI. Con volumi (10–20 utenti, 20–300 pagine, payload 0.2–20 KB) è fattibile e a basso rischio.
- Stato in-process: purge on close già previsto; TTL idle + sweep probabilistico e persistenza JSON opzionale sono economici. Servono write atomico + checksum/versione, cleanup periodico.
- Routing ID: `page_id|pXX` per nuovi; legacy senza `|` devono restare sul percorso legacy con fail fast in ASGI. Da definire riassegnazione su process down.
- IPC cross-process: oggi solo opzioni; scegliere canale minimo (socket/queue) e misurare latenza; NATS è evoluzione, non prerequisito.
- Backpressure/ops: da completare limiti connessioni/payload, timeout, health/readiness e metriche base (pagine attive, evict, restore, drop per flag errato, riassegnazioni).

## Raccomandazioni operative
1) Aggiungere DoD per fasi 0/1/2 in `04-migration-phases.md` (test, metriche, rollback).  
2) Formalizzare policy process down: rigenerare `page_id|pYY` al primo roundtrip o errore chiaro; loggare riassegnazioni.  
3) Scegliere un IPC minimo e misurare latenza (socket/queue locale; NATS se già a portata).  
4) Documentare backpressure/limiti e health/readiness; aggiungere metriche base.  
5) Persist/restore: usare write atomico + checksum/versione, naming per processo, cleanup periodico; ricreare pagina se file mancante/corrotto.

## PoC sì/no
- Se mancano misure in ASGI su p50/p95 WS/HTTP, stickiness `|pXX`, e latenza IPC, fare un micro-PoC (router + 2 worker + PageRegistry + echo RPC) in 1–2 giorni.  
- Se questi punti sono già accettati, si può procedere direttamente con implementazione incrementale sotto feature flag.

## Source: initial_specifications/architecture/wsx-protocol.md

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2025-12-02

WSX (WebSocket eXtended) è un protocollo per RPC transport-agnostic che porta la semantica HTTP sopra WebSocket e NATS. Permette di scrivere handler che funzionano identicamente indipendentemente dal trasporto sottostante.

I diversi trasporti hanno API diverse:

- **HTTP**: method, path, headers, cookies, query params, body
- **WebSocket**: solo messaggi binari/testo, nessuna struttura predefinita
- **NATS**: subject, payload bytes, reply-to automatico

Questo costringe a scrivere handler diversi per ogni trasporto, duplicando la business logic.

WSX definisce un formato messaggio che incapsula la semantica HTTP-like, permettendo:

```
HTTP Request  ─────┐
                   │
WebSocket RPC ─────┼──► BaseRequest ──► Handler ──► BaseResponse
                   │
NATS Message  ─────┘
```

L'handler riceve sempre `BaseRequest` e produce `BaseResponse`, ignorando il trasporto.

I messaggi WSX iniziano con il prefisso `WSX://` seguito da JSON:

```
WSX://{"id":"...","method":"...","path":"...","headers":{},"data":{}}
```

```json
WSX://{
    "id": "uuid-123",
    "method": "POST",
    "path": "/users/42",
    "headers": {
        "content-type": "application/json",
        "authorization": "Bearer xxx",
        "accept-language": "it-IT",
        "x-request-id": "trace-456"
    },
    "cookies": {
        "session_id": "xyz-789",
        "preferences": "dark_mode=true"
    },
    "query": {
        "limit": "10::L",
        "active": "true::B"
    },
    "data": {
        "name": "Mario",
        "birth": "1990-05-15::D",
        "balance": "1234.56::N"
    }
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `id` | string | Sì | Correlation ID per correlare request/response |
| `method` | string | Sì | HTTP method: GET, POST, PUT, DELETE, PATCH |
| `path` | string | Sì | Routing path (es. "/users/42") |
| `headers` | object | No | HTTP headers come dict |
| `cookies` | object | No | Cookies come dict |
| `query` | object | No | Query parameters (supporta TYTX types) |
| `data` | any | No | Payload della request (supporta TYTX types) |

```json
WSX://{
    "id": "uuid-123",
    "status": 200,
    "headers": {
        "content-type": "application/json",
        "x-request-id": "trace-456",
        "cache-control": "no-cache"
    },
    "cookies": {
        "session_id": {
            "value": "new-xyz",
            "max_age": "3600::L",
            "path": "/",
            "httponly": "true::B",
            "secure": "true::B"
        }
    },
    "data": {
        "id": "42::L",
        "created": "2025-12-02T10:30:00+01:00::DHZ",
        "message": "User created"
    }
}
```

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `id` | string | Sì | Stesso correlation ID della request |
| `status` | int | Sì | HTTP status code (200, 404, 500, etc.) |
| `headers` | object | No | Response headers |
| `cookies` | object | No | Set-Cookie equivalents |
| `data` | any | No | Payload della response |

I cookies nella response possono essere:
- Stringa semplice: `"session_id": "value"`
- Oggetto con opzioni: `"session_id": {"value": "...", "max_age": "3600::L", ...}`

Opzioni supportate:
- `value`: valore del cookie
- `max_age`: durata in secondi
- `path`: path del cookie
- `domain`: dominio
- `secure`: solo HTTPS
- `httponly`: non accessibile da JS
- `samesite`: "strict", "lax", "none"

I valori in `query`, `data`, e `cookies` supportano la sintassi TYTX per i tipi:

```
"price": "99.50::N"     → Decimal("99.50")
"date": "2025-01-15::D" → date(2025, 1, 15)
"count": "42::L"        → 42 (int)
"active": "true::B"     → True (bool)
```

Il parsing WSX idrata automaticamente questi valori.

```
BaseRequest (ABC)
    │
    ├── HttpRequest
    │       └── Wrappa ASGI scope per HTTP
    │
    └── WsxRequest
            │   └── Parsa messaggi WSX://
            │
            ├── WsRequest
            │       └── Trasporto: ASGI WebSocket
            │
            └── NatsRequest
                    └── Trasporto: NATS
```

```
BaseResponse (ABC)
    │
    ├── HttpResponse
    │       └── Produce ASGI HTTP response
    │
    └── WsxResponse
            │   └── Serializza in formato WSX://
            │
            ├── WsResponse
            │       └── Invia su WebSocket
            │
            └── NatsResponse
                    └── Pubblica su NATS reply-to
```

```python
class BaseRequest(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Correlation ID per request/response matching."""

@property
    @abstractmethod
    def method(self) -> str:
        """HTTP method (GET, POST, PUT, DELETE, PATCH)."""

@property
    @abstractmethod
    def path(self) -> str:
        """Request path (es. '/users/42')."""

@property
    @abstractmethod
    def headers(self) -> dict[str, str]:
        """Request headers."""

@property
    @abstractmethod
    def cookies(self) -> dict[str, str]:
        """Request cookies."""

@property
    @abstractmethod
    def query(self) -> dict[str, Any]:
        """Query parameters (già idratati)."""

@property
    @abstractmethod
    def data(self) -> Any:
        """Request body/payload (già idratato)."""

@property
    @abstractmethod
    def transport(self) -> str:
        """Trasporto: 'http', 'websocket', 'nats'."""
```

```python
class BaseResponse(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Correlation ID (stesso della request)."""

@property
    @abstractmethod
    def status(self) -> int:
        """HTTP status code."""

@abstractmethod
    def set_header(self, name: str, value: str) -> None:
        """Aggiunge un header alla response."""

@abstractmethod
    def set_cookie(
        self,
        name: str,
        value: str,
        *,
        max_age: int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "lax"
    ) -> None:
        """Imposta un cookie."""

@abstractmethod
    async def send(self, data: Any) -> None:
        """Invia la response con il payload."""
```

```
1. ASGI receive() → body bytes
2. Parse body (JSON/TYTX/XTYTX)
3. Crea HttpRequest da ASGI scope
4. Handler processa → HttpResponse
5. HttpResponse → ASGI send()
```

```
1. WebSocket receive() → text message
2. Detect WSX:// prefix
3. Parse JSON, hydrate TYTX values
4. Crea WsRequest
5. Handler processa → WsResponse
6. WsResponse.send() → serialize WSX:// → WebSocket send()
```

```
1. NATS subscribe callback → msg
2. msg.data contiene WSX://...
3. Parse JSON, hydrate TYTX values
4. Crea NatsRequest (conserva msg.reply)
5. Handler processa → NatsResponse
6. NatsResponse.send() → serialize WSX:// → nc.publish(msg.reply, ...)
```

```python
async def get_user(request: BaseRequest) -> dict:
    """Handler che funziona con qualsiasi trasporto."""

user_id = request.path.split("/")[-1]  # /users/42 → "42"

# Accesso uniforme a headers, cookies, query, data
    auth = request.headers.get("authorization")
    session = request.cookies.get("session_id")
    include_details = request.query.get("details", False)

# Business logic
    user = await db.get_user(user_id)

return {
        "id": user.id,
        "name": user.name,
        "email": user.email if include_details else None
    }
```

1. **Uniformità**: Stesso handler per HTTP, WebSocket, NATS
2. **Type Safety**: TYTX preserva i tipi attraverso il trasporto
3. **Familiar API**: Semantica HTTP-like anche su messaging
4. **Estensibilità**: Facile aggiungere nuovi trasporti
5. **Testabilità**: Mock semplificato con BaseRequest/BaseResponse

- Per HTTP: generato dal server o da header `x-request-id`
- Per WebSocket: obbligatorio nel messaggio WSX
- Per NATS: usa il meccanismo reply-to nativo, `id` è per tracing applicativo

Gli errori vengono ritornati come response con status appropriato:

```json
WSX://{
    "id": "uuid-123",
    "status": 404,
    "data": {
        "error": "User not found",
        "code": "USER_NOT_FOUND"
    }
}
```

Per risposte streaming (es. Server-Sent Events equivalent):
- Multiple WSX response con stesso `id`
- Campo aggiuntivo `"stream": true` per indicare che seguono altri messaggi
- `"stream": false` o assente indica messaggio finale

| Componente | Stato | Note |
|------------|-------|------|
| `WSX_PREFIX`, `is_wsx_message()` | ✅ Implementato | `wsx/protocol.py` |
| `parse_wsx_message()` | ✅ Implementato | `wsx/protocol.py` |
| `build_wsx_message()` | ✅ Implementato | `wsx/protocol.py` |
| `build_wsx_response()` | ✅ Implementato | `wsx/protocol.py` |
| `BaseRequest` | ✅ Implementato | `request.py` |
| `HttpRequest` | ✅ Implementato | `request.py` |
| `MsgRequest` | ✅ Implementato | `request.py` - usa WSX parsing |
| `WsxRequest`, `WsRequest` | ❌ Non implementato | Planned |
| `NatsRequest` | ❌ Non implementato | Planned |
| `BaseResponse` | ❌ Non implementato | Planned |
| `WsxResponse`, `WsResponse` | ❌ Non implementato | Planned |
| `NatsResponse` | ❌ Non implementato | Planned |
| Integrazione NATS | ❌ Non implementato | Planned |

1. **Fase 1**: BaseRequest/BaseResponse ABC ✅ (parziale - solo BaseRequest)
2. **Fase 2**: HttpRequest/HttpResponse (ASGI HTTP) ✅ (parziale - solo HttpRequest)
3. **Fase 3**: WsxRequest/WsxResponse (parsing WSX) ❌
4. **Fase 4**: WsRequest/WsResponse (ASGI WebSocket) ❌
5. **Fase 5**: NatsRequest/NatsResponse (quando necessario) ❌

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0

## Source: initial_specifications/architecture/applications.md

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2025-12-13

Le **applications** (apps) sono componenti modulari che possono essere montati su `AsgiServer`. Ogni app è una unità autocontenuta che può avere:

- Propri routes
- Propria configurazione (`config.yaml`)
- Propri middleware
- Propri plugin

```
src/genro_asgi/
└── applications/
    ├── __init__.py          # Exports: AsgiApplication, StaticSite
    ├── base.py              # AsgiApplication base class
    ├── static_site.py       # StaticSite (module-based app)
    └── static_site/         # StaticSite (path-based app)
        ├── __init__.py
        ├── app.py           # StaticSite class
        └── config.yaml      # Default configuration
```

```python
from genro_routes import RoutingClass

class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer."""
    pass
```

Tutte le app ereditano da `AsgiApplication`, che a sua volta eredita da `RoutingClass` (genro_routes). Questo fornisce:

- Sistema di routing via decoratore `@route`
- Metodi `get()` e `members()` per interrogare routes
- Integrazione automatica con il router del server

```yaml
# server config.yaml
apps:
  docs:
    module: "genro_asgi:StaticSite"
    directory: "./public"
    name: "docs"
```

I parametri (`directory`, `name`) vengono passati al costruttore.

```yaml
# server config.yaml
apps:
  docs:
    path: "./my_docs_app"
```

Dove `./my_docs_app/` contiene:

```
my_docs_app/
├── __init__.py      # Exports app class
├── app.py           # App implementation
└── config.yaml      # App configuration
```

```yaml
# App-level configuration

# Basic settings
directory: "./public"
name: "docs"

# App-specific middleware (optional)
middleware:
  - type: "compression"
    level: 6
  - type: "cache"
    max_age: 3600

# App-specific plugins (optional)
plugins:
  - "my_plugin:MyPlugin"
```

Quando un'app ha middleware propri:

1. **Server middleware** si applicano a tutte le richieste
2. **App middleware** si applicano solo alle richieste per quell'app
3. Ordine: `Server middleware → App middleware → Handler`

```
Request → [Server CORS] → [Server Errors] → [App Compression] → Handler
```

I plugin sono estensioni che aggiungono funzionalità all'app:

```yaml
plugins:
  - "auth:AuthPlugin"
  - module: "cache:CachePlugin"
    ttl: 300
```

I plugin vengono inizializzati all'avvio dell'app e hanno accesso al contesto dell'app.

App per servire file statici da una directory.

```python
class StaticSite(AsgiApplication):
    def __init__(self, directory: str | Path, name: str = "static"):
        self.directory = Path(directory)
        self.name = name
        self.router = StaticRouter(self.directory, name=name)
```

**Caratteristiche**:
- Usa `StaticRouter` internamente
- Supporta file di qualsiasi tipo
- MIME type detection automatica

1. Server legge `apps:` dal config
2. Per ogni app:
   - Se `module:` → importa e istanzia con parametri inline
   - Se `path:` → legge `config.yaml` dalla directory, importa e istanzia
3. App viene attaccata al router del server

1. Request arriva al server
2. Dispatcher identifica l'app dal path prefix
3. App middleware chain viene eseguita
4. Handler dell'app processa la richiesta
5. Response risale la chain

1. Server riceve shutdown signal
2. Ogni app riceve evento `lifespan.shutdown`
3. App può fare cleanup (chiudere connessioni, flush cache, ecc.)

```
┌─────────────────┐
│   RoutingClass   │  (from genro_routes)
│   (abstract)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ AsgiApplication │
│   (base.py)     │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐  ┌─────────────┐
│  App1  │  │  StaticSite │
└────────┘  └─────────────┘
```

- [Routing](../interview/answers/D-routing.md) - Come funziona il routing
- [Configuration](../interview/answers/E-configuration.md) - Sistema di configurazione
- [StaticRouter](../interview/answers/H-static-files.md) - Router per file statici

## Source: initial_specifications/interview/02-knowledge-summary.md

**Data**: 2025-12-13
**Fonte**: Documenti in `specifications/legacy/`

| File | Contenuto | Stato |
|------|-----------|-------|
| `architecture.md` | Multi-App Dispatcher, ServerBinder, Executors dettagliati | Molto dettagliato ma non allineato al codice |
| `configuration.md` | Formato TOML con sezioni server/static/apps | OBSOLETO - ora si usa YAML |
| `genro-asgi-complete-en.md` | Guida implementazione base (Request, Response, Router, Middleware) | Generico, non specifico per genro |
| `genro_asgi_execution.md` | ThreadPool, ProcessPool, TaskManager | NON IMPLEMENTATO |
| `wsx-protocol.md` | Protocollo WSX per RPC transport-agnostic | FUTURO - non implementato |
| `legacy-migration/` | Migrazione da WSGI/Tornado/gnrdaemon | Contesto storico |

```
Uvicorn → AsgiServer (Root Dispatcher)
              │
              ├── /api/*, /ws/rpc/* → Business App (Envelope pattern)
              │                        AuthMW → EnvelopeMW → Handler
              │
              └── /stream/*, /ws/raw/* → Streaming App
                                         MinimalMW → RawHandler
```

**Concetti chiave**:
- Separazione workload (RPC vs Streaming)
- Envelope pattern per unificare HTTP e WebSocket RPC
- Path prefix routing
- mount() per aggiungere apps

```python
class ServerBinder:
    """Accesso controllato a risorse server."""
    @property
    def config(self): ...
    @property
    def logger(self): ...
    def executor(self, name, ...): ...

class AsgiServerEnabler:
    """Mixin per ricevere ServerBinder."""
    binder: ServerBinder | None = None
```

```python
# Named process pools con decorator pattern
executor_pdf = server.executor(name='pdf', max_workers=2)

@executor_pdf
def generate_pdf(data):
    return create_pdf(data)

# Uso
result = await generate_pdf(data)
```

Features descritte:
- Worker initialization con preloaded data
- Multiple isolated pools
- Multithreaded workers per I/O
- Backpressure con semafori
- Metrics e observability
- Bypass mode per testing

Ordine startup: Config → Logger → Executors → Sub-apps (mount order)
Ordine shutdown: Sub-apps (reverse) → Executors → Logger → Config

Formato TOML:
```toml
[server]
host = "0.0.0.0"
port = 8000

[static]
"/static" = "./public"

[[apps]]
path = "/api"
module = "myapp.api:app"
```

**NOTA**: Il codice attuale usa YAML, non TOML.

Protocollo per RPC transport-agnostic:

```
HTTP Request  ─────┐
                   │
WebSocket RPC ─────┼──► BaseRequest ──► Handler ──► BaseResponse
                   │
NATS Message  ─────┘
```

Formato messaggio:
```
WSX://{"id":"...","method":"POST","path":"/users/42","data":{...}}
```

Gerarchia classi:
```
BaseRequest (ABC)
├── HttpRequest (ASGI HTTP)
└── WsxRequest (parsing WSX://)
    ├── WsRequest (ASGI WebSocket)
    └── NatsRequest (NATS)
```

```python
# Blocking I/O
result = await app.executor.run_blocking(func, *args)

# CPU-bound
result = await app.executor.run_process(func, *args)

# Long-running jobs
task_id = app.tasks.submit(job_func, *args)
status = await app.tasks.status(task_id)
result = await app.tasks.result(task_id)
```

Migrazione da:
- gnrdaemon (Pyro) → In-process PageRegistry + NATS
- Tornado (WebSocket) → Native ASGI WebSocket
- Gunicorn (WSGI) → Uvicorn (ASGI)
- Nginx routing → AsgiServer dispatcher

Fasi: 0 → 3 → 4 → 5 → 6 → 7 (1-2 deferred)

**Core**:
- `Application`, `AsgiServer`, `AsgiPublisher`

**Request**:
- `BaseRequest`, `HttpRequest`, `MsgRequest`, `RequestRegistry`

**Response**:
- `Response`, `JSONResponse`, `HTMLResponse`, `PlainTextResponse`
- `RedirectResponse`, `StreamingResponse`, `FileResponse`

**Middleware**:
- `BaseMiddleware`, `middleware_chain` (in middleware/__init__.py)

**Static**:
- `StaticFiles`, `StaticSite`

**WebSocket**:
- `WebSocket`, `WebSocketState`

**Executors**:
- `BaseExecutor`, `LocalExecutor`, `ExecutorRegistry`
- `ExecutorError`, `ExecutorOverloadError`

**Integration**:
- `ServerBinder`, `AsgiServerEnabler`

**Config**:
- `load_config`, `find_config_file`, `ConfigError`

**Lifespan**:
- `Lifespan`, `ServerLifespan`

1. **Routing**: Doc descrive path-prefix mount, codice usa genro_routes.Router
2. **Config**: Doc dice TOML, codice usa YAML
3. **Executors**: Doc molto dettagliato, codice ha struttura base
4. **WSX Protocol**: Doc dettagliato, probabilmente non implementato
5. **AsgiServer**: Doc descrive mount(), codice usa attach_instance()

```python
from genro_toolbox import SmartOptions
from genro_routes import RoutingClass, Router, route
```

- **genro-toolbox**: SmartOptions per configurazione
- **genro-routes**: Router, RoutingClass per routing
- **uvicorn**: ASGI server
- **pyyaml**: Config loading

1. Rispondere alle domande in `01-questions.md`
2. Consolidare le risposte verificate
3. Riscrivere `specifications/01-overview.md` basato su fatti verificati
4. Popolare `architecture/` con specifiche accurate
5. Popolare `guides/` con guide d'uso

## Source: initial_specifications/interview/01-questions.md

**Data**: 2025-12-13
**Scopo**: Chiarire architettura e funzionamento prima di scrivere le specifiche ufficiali

1. **Cos'è genro-asgi oggi?**
   - Le vecchie spec parlano di "minimal ASGI layer", "Multi-App Dispatcher", "foundation of Genro ecosystem". Qual è la definizione corretta attuale?

2. **Qual è il rapporto con genro_routes?**
   - Il codice attuale usa `genro_routes.Router` e `RoutingClass`. AsgiServer eredita da `RoutingClass`. È corretto? Questo significa che genro-asgi dipende fortemente da genro_routes?

3. **Qual è il rapporto con genro-toolbox?**
   - Il codice usa `SmartOptions` per la configurazione. È una dipendenza obbligatoria?

4. **AsgiServer è un singleton o può essere istanziato più volte?**
   - Le vecchie spec parlano di "singleton", ma il codice sembra permettere istanze multiple.

5. **Qual è il flusso di una request HTTP oggi?**
   - Le spec mostrano: `Uvicorn → AsgiServer → Dispatcher → Router → Handler`
   - Ma il codice mostra: `AsgiServer.__call__ → middleware_chain(Dispatcher) → Dispatcher → router.get()`
   - Qual è il flusso corretto?

6. **Come funziona il routing?**
   - Le vecchie spec parlano di "path prefix routing" (`/api/*`, `/stream/*`)
   - Il codice attuale usa `genro_routes.Router` con selettori e `attach_instance`
   - Quale dei due modelli è corretto?

7. **Cosa sono le "apps" oggi?**
   - Config: `apps: {shop: "shop:ShopApp"}`
   - Sono `RoutingClass` attaccate al router? O ASGI apps montate per path?

8. **Formato config: TOML o YAML?**
   - Le vecchie spec dicono TOML, il codice usa YAML (`config.yaml`). Quale è il formato ufficiale?

9. **Come si passano parametri alle apps?**
   - Formato deciso nella discussione:
     ```yaml
     apps:
       office: "office:OfficeApp"  # senza parametri
       shop:
         module: "shop:ShopApp"    # con parametri
         db: "shop.db"
     ```
   - Confermi questo formato?

10. **Priorità configurazione?**
    - Le vecchie spec dicono: CLI > ENV > file > defaults
    - Il codice (`_configure`) fa: `DEFAULTS < config.yaml < env_argv < caller_opts`
    - Confermi questa priorità?

11. **Come funziona il sistema middleware oggi?**
    - Auto-registrazione via `__init_subclass__`?
    - Configurazione via `middleware` nel config.yaml?
    - Formato: lista di tuple, lista di dict, o dict flattened?

12. **Quali middleware esistono e sono funzionanti?**
    - CORS, Errors, Static sono tutti implementati e funzionanti?

13. **Tre modi per servire static files: quali sono attivi?**
    - `StaticSite` (RoutingClass con genro_routes)
    - `StaticFiles` (ASGI app standalone)
    - `StaticFilesMiddleware` (middleware per prefisso)
    - Tutti e tre sono supportati? Quando usare quale?

14. **Gerarchia Request: cosa esiste oggi?**
    - Le spec WSX parlano di: `BaseRequest → HttpRequest, WsxRequest → WsRequest, NatsRequest`
    - Il codice esporta: `BaseRequest`, `HttpRequest`, `MsgRequest`
    - Qual è la struttura corretta?

15. **Response classes: quali esistono?**
    - Il codice esporta: `Response`, `JSONResponse`, `HTMLResponse`, `PlainTextResponse`, `RedirectResponse`, `StreamingResponse`, `FileResponse`
    - Sono tutte funzionanti?

16. **Come funziona il lifespan oggi?**
    - `ServerLifespan` gestisce startup/shutdown?
    - Le apps montate ricevono eventi lifespan?
    - Ordine: server prima, poi apps in ordine di mount?

17. **Il sistema executor esiste ed è funzionante?**
    - Le vecchie spec descrivono `ProcessPoolExecutor`, `ExecutorDecorator`, metriche, backpressure...
    - Il codice esporta: `BaseExecutor`, `LocalExecutor`, `ExecutorRegistry`
    - Quanto di questo è implementato vs pianificato?

18. **Come funziona WebSocket oggi?**
    - `WebSocket` class in websocket.py
    - Delegazione a genro_wsx o gestione diretta?

19. **ServerBinder e AsgiServerEnabler esistono?**
    - Le spec li descrivono per permettere alle apps di accedere a config/logger/executors
    - Il codice esporta entrambi. Sono funzionanti?

**Cosa è implementato vs cosa è pianificato?**

- WSX protocol (BaseRequest/BaseResponse transport-agnostic)
- NATS integration
- Remote executors
- Envelope pattern
- TaskManager per long-running jobs

**Come posso montare app esterne (Starlette, FastAPI) su AsgiServer?**

- Possono accedere alle risorse del server (config, logger, executors)?
- Come funziona `AsgiServerEnabler`?

**Dove vanno le risorse statiche del framework (HTML, CSS, JS, loghi)?**

- Pagine di default del server
- Assets interni del framework
- Differenza rispetto alle static files delle app utente

**Come si avvia genro-asgi da riga di comando?**

- C'è un comando CLI?
- Come funziona `python -m genro_asgi`?
- Quali opzioni sono disponibili?

1. Rispondere a queste domande una alla volta
2. Consolidare le risposte in `02-answers.md`
3. Usare le risposte come base per riscrivere `01-overview.md`
4. Procedere con architecture/ e guides/

## Source: initial_specifications/interview/answers/README.md

**Start date**: 2025-12-13
**Method**: Discussion → Code verification → Documentation

| Section | File | Status |
|---------|------|--------|
| A. Identity and Purpose | [A-identity.md](A-identity.md) | ✅ Verified |
| B. Communication Modes | [B-communication.md](B-communication.md) | ✅ Verified |
| C. Request Lifecycle | [C-request-lifecycle.md](C-request-lifecycle.md) | ✅ Verified |
| D. Routing | [D-routing.md](D-routing.md) | ✅ Verified |
| E. Configuration | [E-configuration.md](E-configuration.md) | ✅ Verified |
| F. Transport and Serialization | [F-transport.md](F-transport.md) | ✅ Verified |
| L. External Apps Integration | [L-external-apps.md](L-external-apps.md) | ✅ Verified |
| M. Resources and Assets | [M-resources.md](M-resources.md) | ✅ Verified |
| N. CLI | [N-cli.md](N-cli.md) | ✅ Verified |

- G. Middleware
- H. Static Files
- I. Lifespan
- J. Executors
- K. WebSocket/WSX

See `specifications/dependencies/`:
- [genro-routes.md](../dependencies/genro-routes.md)
- [genro-toolbox.md](../dependencies/genro-toolbox.md)
- [genro-tytx.md](../dependencies/genro-tytx.md)

## Source: initial_implementation_plan/README.md

Questa cartella contiene la documentazione di design e implementazione per tutti i moduli di genro-asgi.

```
implementation-plan/
├── README.md              # Questo file
├── to-do/                 # Blocchi in lavorazione
│   └── XX-name-NN/        # Blocco logico (es. 04-server-01)
│       ├── XX-name-initial.md    # Idea iniziale, motivazioni
│       ├── XX-name-questions.md  # Domande aperte (se ci sono)
│       ├── XX-name-decisions.md  # Decisioni prese (se ci sono)
│       ├── 01-submodule/         # Sotto-modulo (se il blocco è complesso)
│       │   ├── initial.md
│       │   ├── questions.md
│       │   ├── decisions.md
│       │   └── final.md
│       └── 02-submodule-done/    # Sotto-modulo completato (marcato -done)
│           └── ...
├── done/                  # Blocchi completati
│   └── XX-name-NN-done/   # Blocco completato
│       ├── ...            # Tutti i file del blocco
│       └── XX-name-release_note.md  # Note di rilascio
└── archive/               # Documentazione storica (piani originali)
```

| # | Blocco | Descrizione | Stato |
|---|--------|-------------|-------|
| 01 | types | Tipi base ASGI (Scope, Receive, Send) | DONE |
| 02 | datastructures | Headers, URL, QueryParams, Envelope | DONE |
| 03 | exceptions | Eccezioni HTTP/WS | DONE |
| 04 | server | AsgiServer, config, logger, registry | TO-DO |
| 05 | middleware | Sistema middleware, EnvelopeMiddleware | TO-DO |
| 06 | application | AsgiApplication, dispatch | TO-DO |
| 07 | http | Request, Response | DONE |
| 08 | websocket | WebSocket connection | TO-DO |
| 09 | utils | Utilities condivise (url_from_scope, TYTX) | TO-DO |

1. Creare `XX-name-initial.md` con:
   - Motivazione e contesto
   - Architettura proposta
   - Dipendenze
   - Scope (cosa è incluso, cosa è escluso)

2. Se ci sono domande aperte, creare `XX-name-questions.md`

3. Discutere con l'utente fino a chiarire tutti i dubbi

1. Documentare le decisioni in `XX-name-decisions.md`
2. Ogni decisione deve avere:
   - Contesto
   - Opzioni considerate
   - Decisione presa
   - Motivazione

1. Creare `XX-name-final.md` con il design definitivo
2. Questo documento è la **source of truth** per l'implementazione
3. Deve contenere:
   - API pubblica completa
   - Docstring dettagliate
   - Esempi d'uso
   - Edge cases

**IMPORTANTE**: Il documento `final.md` richiede **approvazione esplicita** dell'utente prima di procedere all'implementazione.

1. Scrivere i test basandosi su `final.md`
2. I test devono coprire:
   - Happy path
   - Edge cases
   - Error handling
3. I test devono passare prima di procedere

1. Implementare seguendo esattamente `final.md`
2. Tutti i test devono passare
3. mypy e ruff devono passare

1. Commit con messaggio descrittivo
2. Aggiungere `release_note.md` al blocco
3. Rinominare sotto-modulo con suffisso `-done` (es. `01-config` → `01-config-done`)
4. Quando tutti i sotto-moduli sono `-done`, spostare il blocco in `done/`

Se un blocco tocca più moduli, viene diviso in sotto-moduli:

```
to-do/04-server-01/
├── 04-server-initial.md      # Overview del blocco
├── 04-server-questions.md    # Domande generali
├── 04-server-decisions.md    # Decisioni generali
├── 01-config/                # Sotto-modulo 1
│   ├── initial.md
│   ├── final.md
│   └── release_note.md
├── 02-logger-done/           # Sotto-modulo 2 (completato)
│   └── ...
└── 03-registry/              # Sotto-modulo 3
    └── ...
```

Ogni sotto-modulo segue lo stesso workflow (initial → questions → decisions → final → test → impl → commit).

1. **`initial.md` deve esistere** - descrive cosa vogliamo fare
2. **Domande devono essere risolte** - nessuna ambiguità
3. **`final.md` deve essere approvato** - l'utente deve dire esplicitamente "ok" o "procedi"

- Combinare scrittura docstring + implementazione senza approvazione
- Saltare la fase di test
- Implementare senza `final.md` approvato
- Modificare codice già approvato senza nuova discussione

- Sotto-modulo in lavorazione: `01-config/`
- Sotto-modulo completato: `01-config-done/`
- Blocco in lavorazione: `to-do/04-server-01/`
- Blocco completato: `done/04-server-01-done/`

- `initial.md` - Idea e motivazione iniziale
- `questions.md` - Domande aperte (opzionale)
- `decisions.md` - Decisioni prese (opzionale)
- `final.md` - Design approvato, source of truth
- `release_note.md` - Note di rilascio post-implementazione
- `divergenze.md` - Differenze tra piano e implementazione (se ci sono)
- `improvements.md` - Miglioramenti successivi

La cartella `archive/` contiene i piani originali scritti prima di adottare questa struttura. Sono mantenuti come riferimento storico ma non sono più la source of truth.

**Ultimo aggiornamento**: 2025-11-27

## Source: initial_implementation_plan/archive/00-overview.md

**Status**: DA REVISIONARE
**Version**: 0.2.0
**Last Updated**: 2025-01-27

genro-asgi is a minimal, stable ASGI foundation with first-class WebSocket support, including the WSX protocol for RPC and subscriptions, and a **unified execution subsystem** for blocking, CPU-bound, and long-running tasks.

```
SmartPublisher
      │
      ├── CLI (direct)
      ├── genro-api (HTTP, future)
      └── genro-asgi
            ├── HTTP (Request/Response)
            ├── WebSocket (transport)
            ├── Execution (blocking/CPU/tasks)  ← NEW
            └── wsx/ (RPC protocol)
                  │
                  └── NATS (future)
```

genro-asgi provides features that Starlette does NOT include:
- **Integrated process executor** for CPU-bound work
- **Unified execution module** for blocking + CPU + long-running jobs
- **TaskManager** for background batch processing
- Stable horizontal scalability with stateless workers

| Block | File | Description | Dependencies |
|-------|------|-------------|--------------|
| 01 | types.py | ASGI type definitions | None |
| 02 | datastructures.py | Headers, QueryParams, URL, State, Address | 01 |
| 03 | exceptions.py | HTTPException, WebSocketException | None |
| 04 | requests.py | Request class | 01, 02 |
| 05 | responses.py | Response classes | 01, 02 |
| 06 | websockets.py | WebSocket transport | 01, 02, 03 |
| 07 | lifespan.py | Lifespan handling | 01 |
| 08 | applications.py | App class | 01-07 |
| **08b** | **executor.py** | **Executor (run_blocking, run_process)** | **01, 07** |
| **08c** | **tasks.py** | **TaskManager for long-running jobs** | **08b** |
| 09 | middleware/base.py | BaseHTTPMiddleware | 01, 04, 05 |
| 10 | wsx/dispatcher.py | WSX message dispatcher | 06 |
| 11 | wsx/rpc.py | RPC handling | 10 |
| 12 | wsx/subscriptions.py | Channel subscriptions | 10 |

1. **Zero dependencies** - stdlib only (orjson optional)
2. **Standalone components** - each usable independently
3. **Full type hints** - mypy strict compatible
4. **Docstring-driven** - module docstring is the source of truth
5. **Test-first** - tests before implementation
6. **Incremental commits** - one block = one commit

**MANDATORY** workflow for each block:

- Discuss the block's purpose and scope
- Ask questions, explore options
- Make design decisions
- **Create analysis document** in `implementation-plan/analysis/XX-name-analysis.md`:
  - Document all questions and decisions
  - Include alternatives considered with pros/cons
  - Record final decisions with rationale
  - This becomes the reference for implementation

- Write an **extremely detailed and exhaustive** module docstring
- This docstring IS the specification
- Include: purpose, API, usage examples, edge cases, design rationale
- All implementation must conform to this docstring

- Create test file based on the docstring specification
- Tests define the expected behavior
- Cover: happy path, edge cases, error conditions
- Tests must pass before moving to step 4

- Implement the module to pass all tests
- Follow the docstring specification exactly
- **Write complete docstrings for all classes and methods** (for ReadTheDocs/Sphinx autodoc):
  - Class docstrings: purpose, attributes, usage example
  - Method docstrings: description, args, returns, raises, example if useful
  - All docstrings in English
- Run `pytest`, `mypy`, `ruff` after implementation

- Write user-facing documentation for the block
- Add to `docs/` if applicable
- Update README if needed

- Single commit per block
- Use conventional commit message from block `.md` file
- Ensure all checks pass before commit

```
src/genro_asgi/
├── __init__.py
├── types.py
├── datastructures.py
├── exceptions.py
├── requests.py
├── responses.py
├── websockets.py
├── lifespan.py
├── applications.py
├── executor.py          ← NEW: Blocking/CPU task pools
├── tasks.py             ← NEW: TaskManager for long-running jobs
├── middleware/
│   ├── __init__.py
│   ├── base.py
│   ├── cors.py
│   └── errors.py
└── wsx/
    ├── __init__.py
    ├── dispatcher.py
    ├── rpc.py
    ├── subscriptions.py
    └── jsonrpc.py
```

## Source: initial_implementation_plan/archive/08-applications.md

**Status**: DA REVISIONARE
**Dependencies**: 01-07 (all previous blocks)
**Commit message**: `feat(applications): add App class with HTTP/WebSocket/Lifespan support`

Main ASGI Application class that composes all components.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

from typing import Awaitable, Callable

from .datastructures import State
from .exceptions import HTTPException
from .lifespan import Lifespan
from .requests import Request
from .responses import JSONResponse, PlainTextResponse, Response
from .types import ASGIApp, Receive, Scope, Send
from .websockets import WebSocket

# Handler type aliases
HTTPHandler = Callable[[Request], Awaitable[Response]]
WebSocketHandler = Callable[[WebSocket], Awaitable[None]]
RawASGIHandler = Callable[[Scope, Receive, Send], Awaitable[None]]

class App:
    """
    ASGI Application.

Main entry point for genro-asgi applications.
    Composes HTTP handling, WebSocket support, lifespan events,
    and middleware chain.

Example - Simple HTTP:
        async def handler(request: Request) -> Response:
            return JSONResponse({"hello": "world"})

Example - With WebSocket:
        async def http_handler(request: Request) -> Response:
            return JSONResponse({"status": "ok"})

async def ws_handler(websocket: WebSocket) -> None:
            await websocket.accept()
            async for msg in websocket:
                await websocket.send_text(f"Echo: {msg}")

app = App(
            handler=http_handler,
            websocket_handler=ws_handler,
        )

Example - With Lifespan:
        lifespan = Lifespan()

@lifespan.on_startup
        async def startup():
            app.state.db = await connect_db()

app = App(handler=handler, lifespan=lifespan)

Example - With Middleware:
        from genro_asgi.middleware import CORSMiddleware

app = App(
            handler=handler,
            middleware=[
                (CORSMiddleware, {"allow_origins": ["*"]}),
            ],
        )
    """

__slots__ = (
        "_handler",
        "_websocket_handler",
        "_lifespan",
        "_middleware",
        "_debug",
        "_state",
        "_app",
    )

def __init__(
        self,
        handler: HTTPHandler | RawASGIHandler | None = None,
        *,
        websocket_handler: WebSocketHandler | None = None,
        lifespan: Lifespan | bool = False,
        middleware: list[tuple[type, dict] | type] | None = None,
        debug: bool = False,
    ) -> None:
        """
        Initialize ASGI application.

Args:
            handler: HTTP request handler (Request -> Response or raw ASGI)
            websocket_handler: WebSocket connection handler
            lifespan: Lifespan instance or True for empty Lifespan
            middleware: List of middleware classes (or tuples with kwargs)
            debug: Enable debug mode (detailed error messages)
        """
        self._handler = handler
        self._websocket_handler = websocket_handler
        self._debug = debug
        self._state = State()

# Setup lifespan
        if lifespan is True:
            self._lifespan = Lifespan()
        elif lifespan is False:
            self._lifespan = None
        else:
            self._lifespan = lifespan

# Setup middleware
        self._middleware = middleware or []

# Build the middleware-wrapped app
        self._app = self._build_app()

@property
    def state(self) -> State:
        """Application state for storing shared data."""
        return self._state

@property
    def debug(self) -> bool:
        """Debug mode flag."""
        return self._debug

def _build_app(self) -> ASGIApp:
        """Build the ASGI app with middleware chain."""
        app: ASGIApp = self._dispatch

# Apply middleware in reverse order (last added = outermost)
        for mw in reversed(self._middleware):
            if isinstance(mw, tuple):
                mw_class, mw_kwargs = mw
                app = mw_class(app, **mw_kwargs)
            else:
                app = mw(app)

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI interface.

Routes to appropriate handler based on scope type.

Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        scope["app"] = self

if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
        else:
            await self._app(scope, receive, send)

async def _dispatch(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Dispatch to HTTP or WebSocket handler.

Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
        elif scope["type"] == "websocket":
            await self._handle_websocket(scope, receive, send)

async def _handle_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Handle lifespan events."""
        if self._lifespan:
            await self._lifespan(scope, receive, send)
        else:
            # No lifespan handler - just acknowledge events
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return

async def _handle_http(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Handle HTTP requests."""
        if self._handler is None:
            response = PlainTextResponse("Not Found", status_code=404)
            await response(scope, receive, send)
            return

request = Request(scope, receive)

try:
            # Check if handler is raw ASGI or high-level
            response = await self._handler(request)  # type: ignore

# If handler returned a Response, send it
            if isinstance(response, Response):
                await response(scope, receive, send)
            # If handler is raw ASGI (returned None), it handled send itself

except HTTPException as exc:
            response = self._http_exception_response(exc)
            await response(scope, receive, send)

except Exception as exc:
            response = self._error_response(exc)
            await response(scope, receive, send)

async def _handle_websocket(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Handle WebSocket connections."""
        if self._websocket_handler is None:
            # No WebSocket handler - close connection
            await send({"type": "websocket.close", "code": 4000})
            return

websocket = WebSocket(scope, receive, send)

try:
            await self._websocket_handler(websocket)
        except Exception:
            # WebSocket errors - try to close gracefully
            try:
                await websocket.close(code=1011, reason="Internal error")
            except Exception:
                pass

def _http_exception_response(self, exc: HTTPException) -> Response:
        """Create response from HTTPException."""
        if exc.headers:
            headers = exc.headers
        else:
            headers = {}

return JSONResponse(
            {"detail": exc.detail},
            status_code=exc.status_code,
            headers=headers,
        )

def _error_response(self, exc: Exception) -> Response:
        """Create response from unexpected exception."""
        if self._debug:
            import traceback
            detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        else:
            detail = "Internal Server Error"

return JSONResponse(
            {"detail": detail},
            status_code=500,
        )

def on_startup(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """
        Register startup handler (shortcut for lifespan.on_startup).

Creates lifespan if not exists.
        """
        if self._lifespan is None:
            self._lifespan = Lifespan()
        return self._lifespan.on_startup(func)

def on_shutdown(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """
        Register shutdown handler (shortcut for lifespan.on_shutdown).

Creates lifespan if not exists.
        """
        if self._lifespan is None:
            self._lifespan = Lifespan()
        return self._lifespan.on_shutdown(func)
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import pytest
from genro_asgi.applications import App
from genro_asgi.exceptions import HTTPException
from genro_asgi.requests import Request
from genro_asgi.responses import JSONResponse, Response
from genro_asgi.websockets import WebSocket

class MockTransport:
    """Mock ASGI transport for testing."""

def __init__(self, messages: list[dict] | None = None):
        self.incoming = messages or []
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        if not self.incoming:
            return {"type": "http.request", "body": b"", "more_body": False}
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

def http_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
    }

def ws_scope(path: str = "/ws") -> dict:
    return {
        "type": "websocket",
        "path": path,
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "subprotocols": [],
    }

def lifespan_scope() -> dict:
    return {"type": "lifespan"}

class TestAppHTTP:
    @pytest.mark.asyncio
    async def test_simple_handler(self):
        async def handler(request: Request) -> Response:
            return JSONResponse({"message": "hello"})

app = App(handler=handler)
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 200
        assert b"hello" in transport.outgoing[1]["body"]

@pytest.mark.asyncio
    async def test_no_handler_404(self):
        app = App()
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 404

@pytest.mark.asyncio
    async def test_http_exception(self):
        async def handler(request: Request) -> Response:
            raise HTTPException(403, detail="Forbidden")

app = App(handler=handler)
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 403
        assert b"Forbidden" in transport.outgoing[1]["body"]

@pytest.mark.asyncio
    async def test_unhandled_exception(self):
        async def handler(request: Request) -> Response:
            raise ValueError("Unexpected error")

app = App(handler=handler)
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 500

@pytest.mark.asyncio
    async def test_debug_mode_shows_traceback(self):
        async def handler(request: Request) -> Response:
            raise ValueError("Debug error")

app = App(handler=handler, debug=True)
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

body = transport.outgoing[1]["body"]
        assert b"Debug error" in body
        assert b"Traceback" in body or b"ValueError" in body

@pytest.mark.asyncio
    async def test_app_in_scope(self):
        captured_app = None

async def handler(request: Request) -> Response:
            nonlocal captured_app
            captured_app = request.scope.get("app")
            return JSONResponse({})

app = App(handler=handler)
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

class TestAppWebSocket:
    @pytest.mark.asyncio
    async def test_websocket_handler(self):
        messages_received = []

async def ws_handler(websocket: WebSocket) -> None:
            await websocket.accept()
            msg = await websocket.receive_text()
            messages_received.append(msg)
            await websocket.send_text(f"Echo: {msg}")

app = App(websocket_handler=ws_handler)
        transport = MockTransport([
            {"type": "websocket.receive", "text": "hello"},
            {"type": "websocket.disconnect", "code": 1000},
        ])

await app(ws_scope(), transport.receive, transport.send)

assert messages_received == ["hello"]
        assert transport.outgoing[0]["type"] == "websocket.accept"
        assert transport.outgoing[1]["text"] == "Echo: hello"

@pytest.mark.asyncio
    async def test_no_websocket_handler(self):
        app = App()
        transport = MockTransport()

await app(ws_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["type"] == "websocket.close"
        assert transport.outgoing[0]["code"] == 4000

class TestAppLifespan:
    @pytest.mark.asyncio
    async def test_lifespan_true(self):
        app = App(lifespan=True)
        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await app(lifespan_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"

@pytest.mark.asyncio
    async def test_lifespan_false(self):
        app = App(lifespan=False)
        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await app(lifespan_scope(), transport.receive, transport.send)

# Should still acknowledge events
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"

@pytest.mark.asyncio
    async def test_on_startup_shortcut(self):
        app = App(lifespan=True)
        called = []

@app.on_startup
        async def startup():
            called.append("startup")

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await app(lifespan_scope(), transport.receive, transport.send)

@pytest.mark.asyncio
    async def test_on_shutdown_shortcut(self):
        app = App(lifespan=True)
        called = []

@app.on_shutdown
        async def shutdown():
            called.append("shutdown")

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await app(lifespan_scope(), transport.receive, transport.send)

class TestAppState:
    def test_state(self):
        app = App()
        app.state.db = "connection"
        assert app.state.db == "connection"

class TestAppMiddleware:
    @pytest.mark.asyncio
    async def test_middleware(self):
        calls = []

class TestMiddleware:
            def __init__(self, app):
                self.app = app

async def __call__(self, scope, receive, send):
                calls.append("before")
                await self.app(scope, receive, send)
                calls.append("after")

async def handler(request: Request) -> Response:
            calls.append("handler")
            return JSONResponse({})

app = App(handler=handler, middleware=[TestMiddleware])
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert calls == ["before", "handler", "after"]

@pytest.mark.asyncio
    async def test_middleware_with_kwargs(self):
        class ConfigMiddleware:
            def __init__(self, app, prefix: str = ""):
                self.app = app
                self.prefix = prefix

async def __call__(self, scope, receive, send):
                scope["prefix"] = self.prefix
                await self.app(scope, receive, send)

async def handler(request: Request) -> Response:
            nonlocal captured_prefix
            captured_prefix = request.scope.get("prefix")
            return JSONResponse({})

app = App(
            handler=handler,
            middleware=[(ConfigMiddleware, {"prefix": "/api"})],
        )
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert captured_prefix == "/api"
```

```python
from .applications import App
```

- [ ] Create `src/genro_asgi/applications.py`
- [ ] Create `tests/test_applications.py`
- [ ] Run `pytest tests/test_applications.py`
- [ ] Run `mypy src/genro_asgi/applications.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/13-final-integration.md

**Status**: DA REVISIONARE
**Dependencies**: All previous blocks (01-12)
**Commit message**: `feat: complete genro-asgi with full public API`

Final integration of all components and complete public API exports.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
genro-asgi - Minimal ASGI foundation with WebSocket support.

A lightweight, framework-agnostic ASGI toolkit featuring:
- HTTP Request/Response handling
- WebSocket support with WSX protocol
- Lifespan management
- Composable middleware

Example - Simple HTTP:
    from genro_asgi import App, Request, JSONResponse

async def handler(request: Request) -> JSONResponse:
        return JSONResponse({"hello": "world"})

Example - WebSocket with WSX:
    from genro_asgi import App, WebSocket
    from genro_asgi.wsx import WSXDispatcher, WSXHandler

@dispatcher.method("echo")
    async def echo(message: str):
        return {"echo": message}

async def ws_handler(websocket: WebSocket):
        handler = WSXHandler(websocket, dispatcher)
        await handler.run()

app = App(websocket_handler=ws_handler)
"""

# Core application
from .applications import App

# Request/Response
from .requests import Request
from .responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

# WebSocket
from .websockets import WebSocket, WebSocketState

# Lifespan
from .lifespan import Lifespan

# Data structures
from .datastructures import Address, Headers, QueryParams, State, URL

# Exceptions
from .exceptions import HTTPException, WebSocketDisconnect, WebSocketException

# Types
from .types import ASGIApp, Message, Receive, Scope, Send

# Middleware
from .middleware import BaseHTTPMiddleware, CORSMiddleware, ErrorMiddleware

__all__ = [
    # Version
    "__version__",
    # Core
    "App",
    # Request/Response
    "Request",
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "StreamingResponse",
    "RedirectResponse",
    "FileResponse",
    # WebSocket
    "WebSocket",
    "WebSocketState",
    # Lifespan
    "Lifespan",
    # Data structures
    "Headers",
    "QueryParams",
    "State",
    "URL",
    "Address",
    # Exceptions
    "HTTPException",
    "WebSocketException",
    "WebSocketDisconnect",
    # Types
    "ASGIApp",
    "Scope",
    "Receive",
    "Send",
    "Message",
    # Middleware
    "BaseHTTPMiddleware",
    "CORSMiddleware",
    "ErrorMiddleware",
]
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Integration tests for genro-asgi."""

import pytest
from genro_asgi import (
    App,
    HTTPException,
    JSONResponse,
    Lifespan,
    Request,
    WebSocket,
)
from genro_asgi.middleware import CORSMiddleware, ErrorMiddleware
from genro_asgi.wsx import WSXDispatcher, WSXHandler

class MockTransport:
    """Mock ASGI transport for testing."""

def __init__(self, messages: list[dict] | None = None):
        self.incoming = messages or []
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        if not self.incoming:
            if self.outgoing and self.outgoing[-1].get("type") == "websocket.accept":
                return {"type": "websocket.disconnect", "code": 1000}
            return {"type": "http.request", "body": b"", "more_body": False}
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

def http_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> dict:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
    }

def ws_scope(path: str = "/ws") -> dict:
    return {
        "type": "websocket",
        "path": path,
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "subprotocols": [],
    }

class TestFullHTTPFlow:
    """Test complete HTTP request/response flow."""

@pytest.mark.asyncio
    async def test_json_api(self):
        """Test JSON API endpoint."""
        async def handler(request: Request):
            data = await request.json()
            return JSONResponse({
                "received": data,
                "method": request.method,
            })

app = App(handler=handler)
        transport = MockTransport([
            {"type": "http.request", "body": b'{"key": "value"}', "more_body": False}
        ])

await app(http_scope(method="POST"), transport.receive, transport.send)

body = json.loads(transport.outgoing[1]["body"])
        assert body["received"] == {"key": "value"}
        assert body["method"] == "POST"

@pytest.mark.asyncio
    async def test_query_params(self):
        """Test query parameter parsing."""
        async def handler(request: Request):
            name = request.query_params.get("name", "World")
            return JSONResponse({"hello": name})

app = App(handler=handler)
        transport = MockTransport()

await app(
            http_scope(query_string=b"name=John"),
            transport.receive,
            transport.send,
        )

body = json.loads(transport.outgoing[1]["body"])
        assert body["hello"] == "John"

@pytest.mark.asyncio
    async def test_http_exception(self):
        """Test HTTP exception handling."""
        async def handler(request: Request):
            raise HTTPException(404, detail="Not found")

app = App(handler=handler)
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 404

class TestFullWSXFlow:
    """Test complete WSX WebSocket flow."""

@pytest.mark.asyncio
    async def test_wsx_rpc(self):
        """Test WSX RPC call."""
        dispatcher = WSXDispatcher()

@dispatcher.method("greet")
        async def greet(name: str):
            return f"Hello, {name}!"

async def ws_handler(websocket: WebSocket):
            handler = WSXHandler(websocket, dispatcher, ping_interval=None)
            await handler.run()

app = App(websocket_handler=ws_handler)
        transport = MockTransport([
            {"type": "websocket.receive", "text": json.dumps({
                "type": "rpc.request",
                "id": "1",
                "method": "greet",
                "params": {"name": "World"},
            })},
        ])

await app(ws_scope(), transport.receive, transport.send)

# Find the response
        responses = [
            msg for msg in transport.outgoing
            if msg.get("type") == "websocket.send"
        ]
        assert len(responses) >= 1

response = json.loads(responses[0]["text"])
        assert response["type"] == "rpc.response"
        assert response["result"] == "Hello, World!"

class TestMiddlewareIntegration:
    """Test middleware integration."""

@pytest.mark.asyncio
    async def test_cors_middleware(self):
        """Test CORS middleware."""
        async def handler(request: Request):
            return JSONResponse({"status": "ok"})

app = App(
            handler=handler,
            middleware=[(CORSMiddleware, {"allow_origins": ["*"]})],
        )
        transport = MockTransport()

await app(
            http_scope(headers=[(b"origin", b"http://example.com")]),
            transport.receive,
            transport.send,
        )

headers = dict(transport.outgoing[0]["headers"])
        assert b"access-control-allow-origin" in headers

@pytest.mark.asyncio
    async def test_error_middleware(self):
        """Test error middleware."""
        async def handler(request: Request):
            raise ValueError("Test error")

app = App(
            handler=handler,
            middleware=[(ErrorMiddleware, {"debug": True})],
        )
        transport = MockTransport()

await app(http_scope(), transport.receive, transport.send)

assert transport.outgoing[0]["status"] == 500
        body = transport.outgoing[1]["body"]
        assert b"Test error" in body

class TestLifespanIntegration:
    """Test lifespan integration."""

@pytest.mark.asyncio
    async def test_lifespan_events(self):
        """Test startup and shutdown events."""
        events = []

@lifespan.on_startup
        async def startup():
            events.append("startup")

@lifespan.on_shutdown
        async def shutdown():
            events.append("shutdown")

app = App(lifespan=lifespan)
        transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await app({"type": "lifespan"}, transport.receive, transport.send)

assert events == ["startup", "shutdown"]
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"

class TestSmartPublisherPattern:
    """Test the pattern used by SmartPublisher."""

@pytest.mark.asyncio
    async def test_smartpublisher_style_handler(self):
        """
        Test handler pattern similar to SmartPublisher http_channel.

This simulates how SmartPublisher would use genro-asgi
        instead of FastAPI.
        """
        # Mock SmartRoute-like router
        class MockRouter:
            def __init__(self):
                self.handlers = {
                    "service.list": self._list,
                    "service.create": self._create,
                }

async def _list(self):
                return ["item1", "item2"]

async def _create(self, name: str):
                return {"id": 1, "name": name}

def get(self, method, use_smartasync=False):
                if method in self.handlers:
                    return self.handlers[method]
                raise KeyError(method)

async def handler(request: Request):
            # Parse path to method name
            path = request.path.strip("/")
            segments = path.split("/")
            method_name = ".".join(segments)

try:
                method_callable = router.get(method_name, use_smartasync=True)
            except KeyError:
                raise HTTPException(404, detail=f"Method not found: {method_name}")

# Get params from query (GET) or body (POST)
            if request.method == "GET":
                params = {k: v for k, v in request.query_params.items()}
            else:
                try:
                    params = await request.json()
                except Exception:
                    params = {}

# Call the method
            result = await method_callable(**params)

return JSONResponse({"result": result})

# Test list
        transport = MockTransport()
        await app(http_scope(path="/service/list"), transport.receive, transport.send)

body = json.loads(transport.outgoing[1]["body"])
        assert body["result"] == ["item1", "item2"]

# Test create
        transport = MockTransport([
            {"type": "http.request", "body": b'{"name": "test"}', "more_body": False}
        ])
        await app(
            http_scope(method="POST", path="/service/create"),
            transport.receive,
            transport.send,
        )

body = json.loads(transport.outgoing[1]["body"])
        assert body["result"] == {"id": 1, "name": "test"}
```

- [ ] Update `src/genro_asgi/__init__.py` with full exports
- [ ] Create `tests/test_integration.py`
- [ ] Run full test suite: `pytest tests/`
- [ ] Run mypy: `mypy src/genro_asgi/`
- [ ] Run ruff: `ruff check src/`
- [ ] Verify all imports work: `python -c "from genro_asgi import *"`
- [ ] Update README.md with examples
- [ ] Final commit

## Source: initial_implementation_plan/archive/10-wsx-core.md

**Status**: DA REVISIONARE
**Dependencies**: 06-websockets
**Commit message**: `feat(wsx): add WSX protocol dispatcher`

> **NOTA**: Il modulo WSX e' progettato per essere **potenzialmente separabile** in un repository
> standalone (`genro-wsx`). Durante l'implementazione, assicurarsi che:
>
> 1. **Nessuna dipendenza circolare** con altri moduli di genro-asgi
> 2. **Import minimi**: WSX dipende solo da `websockets.py` per il transport layer
> 3. **Interface astratta**: Usare ABC/Protocol per il WebSocket transport se possibile
> 4. **Zero side effects**: Nessun stato globale o singleton
>
> Se WSX viene scritto in modo pulito, potra' essere estratto come `genro-wsx` e usato:
>
> - Con genro-asgi (caso primario)
> - Con altri framework ASGI (Starlette, Quart, etc.)
> - Con WebSocket puri (senza ASGI)

WSX (WebSocket eXtended) protocol implementation for RPC, notifications, and subscriptions.
This block implements the core dispatcher that handles WSX message routing.

Message types:
- `rpc.request` - Client → Server RPC call
- `rpc.response` - Server → Client RPC result
- `rpc.error` - Server → Client RPC error
- `rpc.notify` - Both directions, no response expected
- `rpc.subscribe` - Client → Server subscription request
- `rpc.unsubscribe` - Client → Server unsubscribe
- `rpc.event` - Server → Client published event
- `rpc.ping` / `rpc.pong` - Keepalive

```
src/genro_asgi/wsx/
├── __init__.py
├── types.py          # WSX message types
├── dispatcher.py     # Message dispatcher
├── handler.py        # Connection handler
└── errors.py         # WSX-specific errors
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX - WebSocket eXtended protocol for genro-asgi."""

from .dispatcher import WSXDispatcher
from .handler import WSXHandler
from .types import (
    WSXMessage,
    WSXRequest,
    WSXResponse,
    WSXError,
    WSXNotify,
    WSXEvent,
)
from .errors import WSXProtocolError

__all__ = [
    "WSXDispatcher",
    "WSXHandler",
    "WSXMessage",
    "WSXRequest",
    "WSXResponse",
    "WSXError",
    "WSXNotify",
    "WSXEvent",
    "WSXProtocolError",
]
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

from dataclasses import dataclass, field
from typing import Any

@dataclass
class WSXMessage:
    """Base WSX message."""
    type: str
    id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result: dict[str, Any] = {"type": self.type}
        if self.id:
            result["id"] = self.id
        if self.meta:
            result["meta"] = self.meta
        return result

@dataclass
class WSXRequest(WSXMessage):
    """RPC request message."""
    method: str = ""
    params: dict[str, Any] = field(default_factory=dict)

def __post_init__(self):
        self.type = "rpc.request"

def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["method"] = self.method
        if self.params:
            result["params"] = self.params
        return result

@dataclass
class WSXResponse(WSXMessage):
    """RPC response message."""
    result: Any = None

def __post_init__(self):
        self.type = "rpc.response"

def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["result"] = self.result
        return result

@dataclass
class WSXError(WSXMessage):
    """RPC error message."""
    code: str = "ERROR"
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

def __post_init__(self):
        self.type = "rpc.error"

def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["error"] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            result["error"]["details"] = self.details
        return result

@dataclass
class WSXNotify(WSXMessage):
    """Notification message (no response expected)."""
    method: str | None = None
    event: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    payload: Any = None

def __post_init__(self):
        self.type = "rpc.notify"

def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        if self.method:
            result["method"] = self.method
        if self.event:
            result["event"] = self.event
        if self.params:
            result["params"] = self.params
        if self.payload is not None:
            result["payload"] = self.payload
        return result

@dataclass
class WSXSubscribe(WSXMessage):
    """Subscription request message."""
    channel: str = ""
    params: dict[str, Any] = field(default_factory=dict)

def __post_init__(self):
        self.type = "rpc.subscribe"

def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["channel"] = self.channel
        if self.params:
            result["params"] = self.params
        return result

@dataclass
class WSXUnsubscribe(WSXMessage):
    """Unsubscribe message."""

def __post_init__(self):
        self.type = "rpc.unsubscribe"

@dataclass
class WSXEvent(WSXMessage):
    """Published event message."""
    channel: str = ""
    payload: Any = None

def __post_init__(self):
        self.type = "rpc.event"

def to_dict(self) -> dict[str, Any]:
        result = super().to_dict()
        result["channel"] = self.channel
        if self.payload is not None:
            result["payload"] = self.payload
        return result

@dataclass
class WSXPing(WSXMessage):
    """Ping message."""

def __post_init__(self):
        self.type = "rpc.ping"

@dataclass
class WSXPong(WSXMessage):
    """Pong message."""

def __post_init__(self):
        self.type = "rpc.pong"

def parse_message(data: dict[str, Any]) -> WSXMessage:
    """
    Parse raw dict into typed WSX message.

Args:
        data: Raw message dict

Returns:
        Typed WSX message

Raises:
        ValueError: If message type is unknown
    """
    msg_type = data.get("type", "")
    msg_id = data.get("id")
    meta = data.get("meta", {})

if msg_type == "rpc.request":
        return WSXRequest(
            id=msg_id,
            meta=meta,
            method=data.get("method", ""),
            params=data.get("params", {}),
        )
    elif msg_type == "rpc.response":
        return WSXResponse(
            id=msg_id,
            meta=meta,
            result=data.get("result"),
        )
    elif msg_type == "rpc.error":
        error = data.get("error", {})
        return WSXError(
            id=msg_id,
            meta=meta,
            code=error.get("code", "ERROR"),
            message=error.get("message", ""),
            details=error.get("details", {}),
        )
    elif msg_type == "rpc.notify":
        return WSXNotify(
            id=msg_id,
            meta=meta,
            method=data.get("method"),
            event=data.get("event"),
            params=data.get("params", {}),
            payload=data.get("payload"),
        )
    elif msg_type == "rpc.subscribe":
        return WSXSubscribe(
            id=msg_id,
            meta=meta,
            channel=data.get("channel", ""),
            params=data.get("params", {}),
        )
    elif msg_type == "rpc.unsubscribe":
        return WSXUnsubscribe(id=msg_id, meta=meta)
    elif msg_type == "rpc.event":
        return WSXEvent(
            id=msg_id,
            meta=meta,
            channel=data.get("channel", ""),
            payload=data.get("payload"),
        )
    elif msg_type == "rpc.ping":
        return WSXPing(id=msg_id, meta=meta)
    elif msg_type == "rpc.pong":
        return WSXPong(id=msg_id, meta=meta)
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

class WSXProtocolError(Exception):
    """
    WSX protocol error.

Raised when a WSX message is malformed or invalid.
    """

def __init__(self, code: str, message: str, details: dict | None = None) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

class WSXMethodNotFound(WSXProtocolError):
    """Method not found error."""

def __init__(self, method: str) -> None:
        super().__init__(
            code="METHOD_NOT_FOUND",
            message=f"Method not found: {method}",
            details={"method": method},
        )

class WSXInvalidParams(WSXProtocolError):
    """Invalid parameters error."""

def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(
            code="INVALID_PARAMS",
            message=message,
            details=details,
        )

class WSXInternalError(WSXProtocolError):
    """Internal error."""

def __init__(self, message: str) -> None:
        super().__init__(
            code="INTERNAL_ERROR",
            message=message,
        )
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

from typing import Any, Awaitable, Callable

from .errors import WSXInternalError, WSXMethodNotFound, WSXProtocolError
from .types import (
    WSXError,
    WSXMessage,
    WSXNotify,
    WSXPing,
    WSXPong,
    WSXRequest,
    WSXResponse,
    WSXSubscribe,
    WSXUnsubscribe,
    parse_message,
)

# Type alias for RPC method handlers
RPCHandler = Callable[..., Awaitable[Any]]

class WSXDispatcher:
    """
    WSX message dispatcher.

Routes incoming WSX messages to appropriate handlers.

Example:
        dispatcher = WSXDispatcher()

@dispatcher.method("User.create")
        async def create_user(name: str, email: str):
            return {"id": 1, "name": name, "email": email}

# Or with external router (SmartRoute)
        dispatcher = WSXDispatcher(router=my_smartrouter)
    """

def __init__(
        self,
        router: Any | None = None,
        methods: dict[str, RPCHandler] | None = None,
    ) -> None:
        """
        Initialize dispatcher.

Args:
            router: External router (e.g., SmartRoute) with get() method
            methods: Dict of method_name -> handler function
        """
        self._router = router
        self._methods: dict[str, RPCHandler] = methods or {}
        self._notification_handlers: list[Callable[[WSXNotify], Awaitable[None]]] = []

def method(self, name: str) -> Callable[[RPCHandler], RPCHandler]:
        """
        Decorator to register an RPC method.

Args:
            name: Method name (e.g., "User.create")

Returns:
            Decorator function
        """
        def decorator(func: RPCHandler) -> RPCHandler:
            self._methods[name] = func
            return func
        return decorator

def on_notify(
        self, func: Callable[[WSXNotify], Awaitable[None]]
    ) -> Callable[[WSXNotify], Awaitable[None]]:
        """
        Register a notification handler.

Args:
            func: Async function to handle notifications

Returns:
            The registered function
        """
        self._notification_handlers.append(func)
        return func

async def dispatch(self, data: dict[str, Any]) -> WSXMessage | None:
        """
        Dispatch a raw message dict.

Args:
            data: Raw message dict from JSON

Returns:
            Response message or None (for notifications/pong)
        """
        try:
            message = parse_message(data)
        except ValueError as e:
            return WSXError(
                code="PARSE_ERROR",
                message=str(e),
            )

return await self.dispatch_message(message)

async def dispatch_message(self, message: WSXMessage) -> WSXMessage | None:
        """
        Dispatch a typed WSX message.

Args:
            message: Typed WSX message

Returns:
            Response message or None
        """
        if isinstance(message, WSXRequest):
            return await self._handle_request(message)
        elif isinstance(message, WSXNotify):
            await self._handle_notify(message)
            return None
        elif isinstance(message, WSXPing):
            return WSXPong(id=message.id)
        elif isinstance(message, WSXSubscribe):
            return await self._handle_subscribe(message)
        elif isinstance(message, WSXUnsubscribe):
            return await self._handle_unsubscribe(message)
        elif isinstance(message, (WSXResponse, WSXError, WSXPong)):
            # These are responses, not requests - ignore
            return None
        else:
            return WSXError(
                id=message.id,
                code="UNSUPPORTED_TYPE",
                message=f"Unsupported message type: {message.type}",
            )

async def _handle_request(self, request: WSXRequest) -> WSXMessage:
        """Handle RPC request."""
        try:
            handler = await self._get_handler(request.method)
            if handler is None:
                raise WSXMethodNotFound(request.method)

result = await handler(**request.params)

return WSXResponse(
                id=request.id,
                result=result,
            )

except WSXProtocolError as e:
            return WSXError(
                id=request.id,
                code=e.code,
                message=e.message,
                details=e.details,
            )
        except Exception as e:
            return WSXError(
                id=request.id,
                code="INTERNAL_ERROR",
                message=str(e),
            )

async def _get_handler(self, method: str) -> RPCHandler | None:
        """Get handler for method name."""
        # First check local methods
        if method in self._methods:
            return self._methods[method]

# Then try external router
        if self._router is not None:
            try:
                # SmartRoute interface: router.get(method, use_smartasync=True)
                return self._router.get(method, use_smartasync=True)
            except Exception:
                pass

async def _handle_notify(self, notify: WSXNotify) -> None:
        """Handle notification (no response)."""
        for handler in self._notification_handlers:
            try:
                await handler(notify)
            except Exception:
                pass  # Notifications don't return errors

async def _handle_subscribe(self, subscribe: WSXSubscribe) -> WSXMessage:
        """Handle subscription request."""
        # Override in subclass or use SubscriptionManager
        return WSXResponse(
            id=subscribe.id,
            result={"status": "subscribed", "channel": subscribe.channel},
        )

async def _handle_unsubscribe(self, unsubscribe: WSXUnsubscribe) -> WSXMessage:
        """Handle unsubscribe request."""
        # Override in subclass or use SubscriptionManager
        return WSXResponse(
            id=unsubscribe.id,
            result={"status": "unsubscribed"},
        )
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import pytest
from genro_asgi.wsx import (
    WSXDispatcher,
    WSXError,
    WSXNotify,
    WSXRequest,
    WSXResponse,
)
from genro_asgi.wsx.types import (
    WSXPing,
    WSXPong,
    WSXSubscribe,
    parse_message,
)

class TestWSXTypes:
    def test_request_to_dict(self):
        req = WSXRequest(id="1", method="User.create", params={"name": "John"})
        d = req.to_dict()
        assert d["type"] == "rpc.request"
        assert d["id"] == "1"
        assert d["method"] == "User.create"
        assert d["params"] == {"name": "John"}

def test_response_to_dict(self):
        resp = WSXResponse(id="1", result={"id": 1})
        d = resp.to_dict()
        assert d["type"] == "rpc.response"
        assert d["result"] == {"id": 1}

def test_error_to_dict(self):
        err = WSXError(id="1", code="NOT_FOUND", message="User not found")
        d = err.to_dict()
        assert d["type"] == "rpc.error"
        assert d["error"]["code"] == "NOT_FOUND"

def test_notify_to_dict(self):
        notify = WSXNotify(method="log", params={"level": "info"})
        d = notify.to_dict()
        assert d["type"] == "rpc.notify"
        assert d["method"] == "log"

class TestParseMessage:
    def test_parse_request(self):
        data = {
            "type": "rpc.request",
            "id": "123",
            "method": "User.get",
            "params": {"id": 1},
        }
        msg = parse_message(data)
        assert isinstance(msg, WSXRequest)
        assert msg.method == "User.get"
        assert msg.params == {"id": 1}

def test_parse_response(self):
        data = {
            "type": "rpc.response",
            "id": "123",
            "result": {"name": "John"},
        }
        msg = parse_message(data)
        assert isinstance(msg, WSXResponse)
        assert msg.result == {"name": "John"}

def test_parse_ping(self):
        data = {"type": "rpc.ping"}
        msg = parse_message(data)
        assert isinstance(msg, WSXPing)

def test_parse_subscribe(self):
        data = {
            "type": "rpc.subscribe",
            "id": "sub-1",
            "channel": "user.updates",
        }
        msg = parse_message(data)
        assert isinstance(msg, WSXSubscribe)
        assert msg.channel == "user.updates"

def test_parse_unknown_type(self):
        data = {"type": "unknown.type"}
        with pytest.raises(ValueError, match="Unknown message type"):
            parse_message(data)

class TestWSXDispatcher:
    @pytest.mark.asyncio
    async def test_dispatch_request(self):
        dispatcher = WSXDispatcher()

@dispatcher.method("echo")
        async def echo(message: str):
            return {"echo": message}

result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "echo",
            "params": {"message": "hello"},
        })

assert isinstance(result, WSXResponse)
        assert result.id == "1"
        assert result.result == {"echo": "hello"}

@pytest.mark.asyncio
    async def test_dispatch_method_not_found(self):
        dispatcher = WSXDispatcher()

result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "nonexistent",
            "params": {},
        })

assert isinstance(result, WSXError)
        assert result.code == "METHOD_NOT_FOUND"

@pytest.mark.asyncio
    async def test_dispatch_ping_pong(self):
        dispatcher = WSXDispatcher()

result = await dispatcher.dispatch({"type": "rpc.ping"})

assert isinstance(result, WSXPong)

@pytest.mark.asyncio
    async def test_dispatch_notify(self):
        dispatcher = WSXDispatcher()
        notifications = []

@dispatcher.on_notify
        async def handle_notify(notify):
            notifications.append(notify)

result = await dispatcher.dispatch({
            "type": "rpc.notify",
            "method": "log",
            "params": {"level": "info"},
        })

assert result is None  # Notifications don't return
        assert len(notifications) == 1

@pytest.mark.asyncio
    async def test_dispatch_with_router(self):
        # Mock SmartRoute-like router
        class MockRouter:
            def get(self, method, use_smartasync=False):
                if method == "test.method":
                    async def handler(value: int):
                        return value * 2
                    return handler
                raise KeyError(method)

dispatcher = WSXDispatcher(router=MockRouter())

result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "test.method",
            "params": {"value": 21},
        })

assert isinstance(result, WSXResponse)
        assert result.result == 42

@pytest.mark.asyncio
    async def test_dispatch_handler_error(self):
        dispatcher = WSXDispatcher()

@dispatcher.method("failing")
        async def failing():
            raise ValueError("Something went wrong")

result = await dispatcher.dispatch({
            "type": "rpc.request",
            "id": "1",
            "method": "failing",
            "params": {},
        })

assert isinstance(result, WSXError)
        assert result.code == "INTERNAL_ERROR"
        assert "Something went wrong" in result.message

@pytest.mark.asyncio
    async def test_dispatch_subscribe(self):
        dispatcher = WSXDispatcher()

result = await dispatcher.dispatch({
            "type": "rpc.subscribe",
            "id": "sub-1",
            "channel": "user.updates",
        })

assert isinstance(result, WSXResponse)
        assert result.result["status"] == "subscribed"

@pytest.mark.asyncio
    async def test_dispatch_invalid_json(self):
        dispatcher = WSXDispatcher()

result = await dispatcher.dispatch({
            "type": "invalid.type.that.does.not.exist"
        })

assert isinstance(result, WSXError)
```

- [ ] Create `src/genro_asgi/wsx/__init__.py`
- [ ] Create `src/genro_asgi/wsx/types.py`
- [ ] Create `src/genro_asgi/wsx/errors.py`
- [ ] Create `src/genro_asgi/wsx/dispatcher.py`
- [ ] Create `tests/test_wsx_core.py`
- [ ] Run `pytest tests/test_wsx_core.py`
- [ ] Run `mypy src/genro_asgi/wsx/`
- [ ] Update main `__init__.py` if needed
- [ ] Commit

## Source: initial_implementation_plan/done/03-exceptions-01-done/initial.md

**Scopo**: Classi di eccezione per gestione errori HTTP e WebSocket.

Il modulo `exceptions.py` fornisce eccezioni tipizzate per segnalare errori
nel ciclo request/response HTTP e nelle connessioni WebSocket.

```
Tipo Errore                      Eccezione genro-asgi
───────────                      ────────────────────
HTTP 4xx/5xx                     HTTPException(status_code, detail, headers)
WebSocket close con errore       WebSocketException(code, reason)
WebSocket disconnessione client  WebSocketDisconnect(code, reason)
```

Eccezione da sollevare negli handler per ritornare una risposta HTTP di errore.

```python
# In un handler
async def get_user(request):
    user = await db.get_user(request.path_params["id"])
    if not user:
        raise HTTPException(404, detail="User not found")
    return JSONResponse(user)

# Con headers custom
raise HTTPException(
    401,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer realm='api'"}
)
```

```python
class HTTPException(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str = "",
        headers: dict[str, str] | None = None
    ) -> None

**Domanda**: Validare che status_code sia nel range 400-599?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Nessuna validazione** | KISS, flessibile | Permette valori insensati |
| **Validazione 400-599** | Correttezza garantita | Overhead, meno flessibile |
| **Validazione 100-599** | Include tutti i codici HTTP | 1xx/2xx/3xx non sono "errori" |

**Riferimenti**:
- Starlette: nessuna validazione
- FastAPI: nessuna validazione
- Django Rest Framework: nessuna validazione

**Raccomandazione**: Nessuna validazione. Documentare che ci si aspetta 4xx/5xx.

**Domanda**: `dict[str, str]` è sufficiente o serve supporto multi-value?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **dict[str, str]** | Semplice, API chiara | No multi-value (es. Set-Cookie multipli) |
| **dict[str, str \| list[str]]** | Multi-value supportato | API più complessa |
| **list[tuple[str, str]]** | Massima flessibilità | Scomodo da usare |

**Considerazioni**:
- HTTPException è per errori, raramente serve Set-Cookie multiplo
- Se servono header complessi, l'handler può gestirli direttamente
- Casi d'uso comuni (WWW-Authenticate, Retry-After) sono single-value

**Raccomandazione**: `dict[str, str]` per semplicità. Casi edge gestiti a livello handler.

**Domanda**: Aggiungere `__slots__` per consistenza con altre classi?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Con `__slots__`** | Consistenza, memoria | Inusuale per Exception |
| **Senza `__slots__`** | Pattern standard | Inconsistenza con datastructures |

**Considerazioni**:
- Le eccezioni con `__slots__` funzionano ma sono inusuali
- Le eccezioni sono tipicamente short-lived, il risparmio memoria è trascurabile
- Exception base non usa `__slots__`

**Raccomandazione**: NON usare `__slots__` per eccezioni. Fanno eccezione alla regola generale.

Eccezione da sollevare per chiudere una connessione WebSocket con un codice di errore.

```python
async def websocket_handler(websocket):
    message = await websocket.receive_json()
    if not validate(message):
        raise WebSocketException(code=4000, reason="Invalid message format")
```

```
Codice    Significato
──────    ───────────
1000      Normal closure
1001      Going away (server shutdown, browser navigating)
1002      Protocol error
1003      Unsupported data type
1006      Abnormal closure (reserved, no close frame)
1007      Invalid payload data
1008      Policy violation
1009      Message too big
1010      Missing extension
1011      Internal server error
1015      TLS handshake failure (reserved)

4000-4999 Application-specific codes (usabili liberamente)
```

```python
class WebSocketException(Exception):
    def __init__(
        self,
        code: int = 1000,
        reason: str = ""
    ) -> None

**Domanda**: Validare che code sia nel range valido?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Nessuna validazione** | KISS, flessibile | Permette codici riservati |
| **Validazione 1000-4999** | Correttezza | Overhead |

**Raccomandazione**: Nessuna validazione. Come HTTPException, documentare l'uso atteso.

**Domanda**: Il default 1000 (normal closure) ha senso per un'eccezione?

**Considerazioni**:
- 1000 = chiusura normale, non è tecnicamente un errore
- Potrebbe essere più appropriato un default come 1011 (internal error)
- Ma 1000 con reason custom è pattern comune

**Raccomandazione**: Mantenere default 1000 per flessibilità. L'utente può specificare codici di errore espliciti.

Eccezione sollevata quando il client chiude la connessione WebSocket.
Non è un errore, è un segnale per il codice chiamante.

| Aspetto | WebSocketException | WebSocketDisconnect |
|---------|-------------------|---------------------|
| Chi la solleva | Server (raise esplicito) | Framework (receive fallita) |
| Semantica | Errore, chiudi connessione | Informazione, client andato |
| Handling | Log errore, cleanup | Cleanup normale |

```python
async def websocket_handler(websocket):
    try:
        while True:
            data = await websocket.receive_text()
            await process(data)
    except WebSocketDisconnect:
        # Client se n'è andato, cleanup normale
        logger.info("Client disconnected")
```

```python
class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000, reason: str = "") -> None

# __repr__ non definito, usa default di Exception
```

**Domanda**: Il piano non include `__repr__` per WebSocketDisconnect. Aggiungerlo per consistenza?

**Raccomandazione**: Sì, aggiungere `__repr__` per consistenza con le altre due eccezioni.

**Domanda**: Serve entry point per modulo con solo eccezioni?

**Raccomandazione**: No. Come deciso per datastructures.py, i moduli utility puri non hanno entry point.

**Domanda**: Le eccezioni devono ereditare da una base comune?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Tutte da Exception** | Semplice, indipendenti | No catch comune |
| **Base GenroException** | Catch `except GenroException` | Over-engineering |
| **WebSocket da base comune** | Catch tutti WS errors | Complessità |

**Raccomandazione**: Tutte da Exception direttamente. KISS. Se serve catch comune, si può usare tuple:
```python
except (HTTPException, WebSocketException):
```

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Validare HTTPException.status_code? | **No** - KISS, documentare uso atteso |
| 2 | HTTPException.headers tipo? | **dict[str, str]** - semplicità |
| 3 | `__slots__` per eccezioni? | **No** - eccezioni fanno eccezione alla regola |
| 4 | Validare WebSocketException.code? | **No** - KISS |
| 5 | WebSocketException default code=1000? | **Sì** - flessibile |
| 6 | `__repr__` per WebSocketDisconnect? | **Sì** - consistenza |
| 7 | Entry point per exceptions.py? | **No** - modulo utility |
| 8 | Base exception comune? | **No** - KISS, tutte da Exception |

Basandosi sulle decisioni, il piano originale va modificato:

1. **Aggiungere `__repr__` a WebSocketDisconnect** (decisione #6)
2. **NON aggiungere `__slots__`** (decisione #3 - eccezione alla regola)
3. **Nessuna validazione** per status_code e code (decisioni #1, #4)

Dopo conferma delle decisioni:
1. Scrivere docstring completa del modulo (Step 2)
2. Scrivere test (Step 3)
3. Implementare (Step 4)
4. Commit (Step 6)

## Source: initial_implementation_plan/done/07-http-01-done/02-response-done/initial.md

**Scopo**: Classi Response per invio risposte HTTP tramite ASGI.
**Status**: 🟢 APPROVATO

Il modulo `response.py` fornisce le classi Response per costruire e inviare
risposte HTTP attraverso l'interfaccia ASGI `send()`.

```
User Code                          ASGI Send
─────────                          ─────────
Response(content, status)          http.response.start (status, headers)
await response(scope, receive, send)  http.response.body (body, more_body)
```

| Classe | Uso | Note |
|--------|-----|------|
| Response | Base, content bytes/str | Media type generico |
| JSONResponse | Serializza Python → JSON | orjson fallback |
| HTMLResponse | HTML content | text/html |
| PlainTextResponse | Plain text | text/plain |
| RedirectResponse | HTTP redirect | Location header |
| StreamingResponse | Body da async iterator | Chunked |
| FileResponse | Download file da disco | Content-Disposition |

**Problema**: Il piano usa `responses.py` (plurale), ma lo stub esistente è `response.py` (singolare).

| Opzione | Pro | Contro |
|---------|-----|--------|
| `response.py` (singolare) | Coerente con stub, con Starlette | - |
| `responses.py` (plurale) | Coerente col piano | Richiede rename |

**Domanda**: Usare il singolare come per `request.py`?

**Problema**: Il piano usa `__call__(scope, receive, send)` come interfaccia ASGI.
Lo stub esistente usa `send(send)` che richiede solo il callable send.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `__call__(scope, receive, send)` | Standard ASGI, componibile | receive non usato |
| `send(send)` | Più semplice | Non standard ASGI |

```python
# Piano: __call__
response = Response(content=b"Hello")
await response(scope, receive, send)

# Stub esistente: send()
response = Response(content=b"Hello")
await response.send(send)
```

**Domanda**: Usare `__call__` per coerenza ASGI?

**Problema**: Il piano usa `status_code`, lo stub usa `status`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `status_code` | Esplicito, come Starlette | Più lungo |
| `status` | Più breve | Ambiguo |

**Problema**: Il piano accetta `Mapping[str, str] | None`, lo stub `dict[str, str] | None`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `Mapping[str, str]` | Più flessibile (accetta Headers, dict, etc) | - |
| `dict[str, str]` | Specifico | Meno flessibile |

**Nota**: Headers del Block 02 è un Mapping, quindi accettarlo sarebbe utile.

**Domanda**: Usare `Mapping` per flessibilità?

**Problema**: Il piano ha `media_type: str | None = None` a livello di classe.
Lo stub ha `media_type: str = "text/plain"`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Default `None` | Nessun Content-Type automatico | Utente deve specificare |
| Default `"text/plain"` | Sempre un content-type | Potrebbe non essere desiderato |

**Comportamento Starlette**: `media_type = None` (nessun default)

**Domanda**: Seguire Starlette con `None` default?

**Problema**: Il piano ha logica per aggiungere charset a text/* media types:
```python
if self.media_type.startswith("text/") and "charset" not in self.media_type:
    return f"{self.media_type}; charset={self.charset}"
```

**Domanda**: Questa logica è corretta? Charset default dovrebbe essere "utf-8"?

**Problema**: Il piano specifica `AsyncIterator[bytes]`, ma `AsyncIterable[bytes]`
sarebbe più flessibile (accetta anche async generators).

```python
# AsyncIterator - solo oggetti con __anext__
async def generate():
    yield b"chunk"

# AsyncIterable - oggetti con __aiter__ (include async generators)
async def generate():
    yield b"chunk"
```

**Nota**: async generators sono `AsyncGenerator` che è sottotipo di `AsyncIterator`,
ma tecnicamente il type hint `AsyncIterator` è corretto per async generators.

**Domanda**: Mantenere `AsyncIterator[bytes]`?

**Problema**: Il piano supporta solo async iterator. Starlette supporta anche sync.

```python
# Solo async (piano)
async def generate():
    yield b"chunk"

# Starlette supporta anche sync
def generate():
    yield b"chunk"
```

**Domanda**: Supportare solo async per semplicità? O anche sync?

**Problema**: Il piano usa `open()` sincrono:
```python
with open(self.path, "rb") as f:
    while True:
        chunk = f.read(self.chunk_size)
```

Questo blocca l'event loop per file grandi.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Sync `open()` | Semplice, stdlib | Blocca event loop |
| Async con `aiofiles` | Non blocca | Aggiunge dipendenza |
| Async con thread pool | Non blocca | Complessità |

**Domanda**: Per ora sync è accettabile? O serve async?

**Problema**: Il piano controlla `path.exists()` solo per content-length:
```python
if self.path.exists():
    self._headers["content-length"] = str(self.path.stat().st_size)
```

Ma se il file non esiste, `open()` in `__call__` solleverà `FileNotFoundError`.

**Domanda**: Comportamento OK (eccezione naturale)? O validare nel costruttore?

**Problema**: Il piano non valida che status_code sia un redirect code (301, 302, 303, 307, 308).

**Domanda**: Validare o lasciare libertà all'utente?

**Problema**: Le decisioni di design del progetto richiedono `__slots__` ovunque.
Il piano non mostra `__slots__`.

**Domanda**: Aggiungere `__slots__` a tutte le Response classes?

**Problema**: Il piano usa latin-1 per header encoding:
```python
(k.lower().encode("latin-1"), v.encode("latin-1"))
```

Questo è corretto per HTTP/1.1 (RFC 7230), ma alcuni server potrebbero voler UTF-8.

**Domanda**: Mantenere latin-1 (standard HTTP)?

**Problema**: Il piano NON aggiunge automaticamente Content-Length per Response base.
Solo FileResponse lo aggiunge.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Aggiungere Content-Length | Più completo | Overhead calcolo |
| Non aggiungere | Semplice | Client non sa dimensione |

**Comportamento Starlette**: Aggiunge Content-Length automaticamente.

**Domanda**: Aggiungere Content-Length per Response base?

**Problema**: Il piano usa `ensure_ascii=False` per stdlib json:
```python
json.dumps(content, ensure_ascii=False).encode("utf-8")
```

Questo è corretto per output UTF-8.

**Domanda**: OK così? Servono opzioni per separatori/indent?

**Problema**: Le regole del progetto richiedono entry point per moduli con classe primaria.

**Domanda**: Quale demo per Response? Server mock non è triviale.

**Problema**: Quali classi esportare dal package?

**Piano**: Tutte (Response, JSONResponse, HTMLResponse, PlainTextResponse,
RedirectResponse, StreamingResponse, FileResponse)

**Domanda**: OK esportare tutte?

1. **Nome file**: `response.py` (singolare) o `responses.py` (plurale)?
2. **API**: `__call__(scope, receive, send)` o `send(send)`?
3. **Parametro**: `status_code` o `status`?
4. **Headers input**: `Mapping[str, str]` o `dict[str, str]`?
5. **Media type default**: `None` o `"text/plain"`?
6. **Charset auto-append**: Per text/* media types?
7. **StreamingResponse type hint**: `AsyncIterator` OK?
8. **Sync iterator support**: Solo async o anche sync?
9. **FileResponse I/O**: Sync blocking OK per ora?
10. **File non esistente**: Eccezione naturale OK?
11. **Redirect status validation**: Validare o no?
12. **`__slots__`**: Aggiungere a tutte le classi?
13. **Header encoding**: latin-1 (standard)?
14. **Content-Length**: Aggiungere automaticamente a Response?
15. **JSONResponse options**: Solo ensure_ascii o più opzioni?
16. **Entry point**: Quale demo?
17. **Exports**: Tutte le classi?

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Nome file | `response.py` (singolare, come request.py) |
| 2 | API | `__call__(scope, receive, send)` - standard ASGI |
| 3 | Parametro | `status_code` - esplicito |
| 4 | Headers | `Mapping[str, str]` - flessibile |
| 5 | Media type | `None` default - come Starlette |
| 6 | Charset | Sì, auto-append per text/* |
| 7 | Streaming type | `AsyncIterator[bytes]` - corretto |
| 8 | Sync iterator | Solo async per semplicità |
| 9 | FileResponse I/O | Sync OK per ora (v1) |
| 10 | File missing | Eccezione naturale OK |
| 11 | Redirect validation | No - libertà utente |
| 12 | `__slots__` | Sì - per efficienza |
| 13 | Header encoding | latin-1 - standard HTTP |
| 14 | Content-Length | **Sì per non-streaming, No per StreamingResponse** |
| 15 | JSON options | Solo base per ora |
| 16 | Entry point | Demo con mock send |
| 17 | Exports | Tutte le classi |

Content-Length viene aggiunto automaticamente **solo** per:

- `Response` (base) - body noto al costruttore
- `JSONResponse` - body noto al costruttore
- `HTMLResponse` - body noto al costruttore
- `PlainTextResponse` - body noto al costruttore
- `RedirectResponse` - body vuoto (Content-Length: 0)
- `FileResponse` - solo se file esiste e size è nota

- `StreamingResponse` - size non nota a priori (chunked transfer)

1. ~~Confermare le decisioni~~ ✅ FATTO
2. **Scrivere docstring** modulo (Step 2)
3. **Scrivere test** (Step 3)
4. **Implementare** (Step 4)
5. **Commit** (Step 6)

## Source: initial_implementation_plan/to-do/04-server-01/04-server-initial.md

**Purpose**: Definire il fondamento architetturale - il singleton di processo su cui tutto si appoggia.
**Status**: 🔴 DA REVISIONARE

Tutti i moduli già implementati (types, datastructures, exceptions, request, response) funzionano ma manca il **collante centrale**.

Il pattern collaudato (usato in WSGI per anni):
- Un **Server** che gestisce il processo, config, infrastruttura
- Un'**Application** ASGI che gestisce request/response

```
┌──────────────────────────────────────────────────────────────┐
│  AsgiServer (singleton di processo)                          │
│                                                              │
│  Configurazione:                                             │
│  ├── config: ConfigParser (da .ini)                          │
│  ├── config_path: str                                        │
│                                                              │
│  Infrastruttura:                                             │
│  ├── logger: Logger                                          │
│  ├── metrics: MetricsCollector                               │
│  ├── registry: EnvelopeRegistry                              │
│                                                              │
│  Rete:                                                       │
│  ├── host, port, workers                                     │
│  ├── ssl_context (opzionale)                                 │
│                                                              │
│  Background Tasks:                                           │
│  ├── watchdog_task: controlla request piantate               │
│  ├── metrics_task: esporta metriche                          │
│                                                              │
│  Error Handling:                                             │
│  ├── error_handlers: dict[type[Exception], Handler]          │
│  ├── on_error(envelope, exception)                           │
│                                                              │
│  Debug (opzionale):                                          │
│  ├── debug_server: RemoteDebugServer                         │
│                                                              │
│  Lifecycle:                                                  │
│  ├── on_startup, on_shutdown                                 │
│  ├── run() → avvia uvicorn                                   │
│                                                              │
│  └── AsgiApplication                                         │
│       ├── server: AsgiServer (parent, accesso a tutto)       │
│       ├── routes                                             │
│       ├── middleware                                         │
│       └── __call__(scope, receive, send)                     │
└──────────────────────────────────────────────────────────────┘
```

```python
# main.py
from genro_asgi import AsgiServer

server = AsgiServer(config_path='server.ini')

if __name__ == '__main__':
    server.run()
```

```ini
[server]
host = 0.0.0.0
port = 8000
workers = 4
debug = false

[ssl]
enabled = false
certfile = /path/to/cert.pem
keyfile = /path/to/key.pem

[logging]
level = INFO
format = %(asctime)s - %(name)s - %(levelname)s - %(message)s
file = /var/log/app.log

[metrics]
enabled = true
endpoint = /metrics
export_port = 9090

[watchdog]
enabled = true
interval = 30           # check ogni 30s
timeout = 60            # warning dopo 60s
critical = 300          # alert dopo 5min

[errors]
show_traceback = false  # true solo in debug
notify_critical = true
notify_webhook = https://...

[debug]
enabled = false         # MAI in produzione!
remote_pdb = false
debug_port = 8001
allowed_ips = 127.0.0.1
secret = xxxxx

[application]
name = myapp
secret_key = xxxxx
```

Registro centrale delle request in-flight:

```python
class EnvelopeRegistry:
    """Registro thread-safe delle RequestEnvelope attive."""

def __init__(self):
        self._envelopes: dict[str, RequestEnvelope] = {}
        self._lock: asyncio.Lock

async def add(self, envelope: RequestEnvelope) -> None:
        """Registra un nuovo envelope."""

async def get(self, internal_id: str) -> RequestEnvelope | None:
        """Recupera envelope per ID."""

async def remove(self, internal_id: str) -> None:
        """Rimuove envelope dal registry."""

async def get_stuck(self, threshold: float) -> list[RequestEnvelope]:
        """Ritorna envelope più vecchi di threshold secondi."""

def __len__(self) -> int:
        """Numero di envelope attivi."""
```

```python
class EnvelopeMiddleware:
    """Middleware infrastrutturale - sempre primo della catena."""

async def __call__(self, scope, receive, send):
        if scope['type'] in ('http', 'websocket'):
            # Crea envelope
            envelope = RequestEnvelope(
                internal_id=str(uuid.uuid4()),
                external_id=None,
                tytx_mode=False,
                params={},
                metadata={
                    'path': scope.get('path'),
                    'method': scope.get('method'),
                    'client': scope.get('client'),
                },
                created_at=time.time(),
            )

# Registra
            await self.server.registry.add(envelope)
            scope['envelope'] = envelope

try:
                await self.app(scope, receive, send)
            finally:
                # Cleanup garantito
                await self.server.registry.remove(envelope.internal_id)
        else:
            await self.app(scope, receive, send)
```

```python
async def watchdog_loop(self):
    """Background task che monitora request piantate."""

while self.running:
        await asyncio.sleep(self.config['watchdog']['interval'])

timeout = self.config['watchdog']['timeout']
        critical = self.config['watchdog']['critical']

stuck = await self.registry.get_stuck(timeout)

for envelope in stuck:
            age = time.time() - envelope.created_at

if age > critical:
                self.logger.critical(
                    f"CRITICAL: Request bloccata da {age:.0f}s",
                    extra={'envelope_id': envelope.internal_id}
                )
                await self.notify_stuck_request(envelope, critical=True)
            else:
                self.logger.warning(
                    f"WARNING: Request lenta {age:.0f}s",
                    extra={'envelope_id': envelope.internal_id}
                )

self.metrics.increment('requests_stuck')
```

```python
async def on_error(self, envelope: RequestEnvelope, exc: Exception):
    """Gestione centralizzata errori con contesto completo."""

error_id = envelope.internal_id[:8]  # short ID per utente

# 1. Log strutturato
    self.logger.exception(
        f"Error {error_id}",
        extra={
            'error_id': error_id,
            'envelope_id': envelope.internal_id,
            'path': envelope.metadata.get('path'),
            'method': envelope.metadata.get('method'),
            'exc_type': type(exc).__name__,
        }
    )

# 2. Metrics
    self.metrics.increment('errors_total')
    self.metrics.increment(f'errors.{type(exc).__name__}')

# 3. Debug remoto (se abilitato)
    if self.config['debug']['remote_pdb']:
        await self.remote_debug_session(envelope, exc)

# 4. Notifica (se critico)
    if self.is_critical_error(exc):
        await self.notify_error(envelope, exc)

# 5. Response al client
    return self.error_response(error_id, exc)
```

```python
class RemoteDebugServer:
    """Debug remoto via WebSocket - solo development!"""

def __init__(self, server: AsgiServer):
        self.server = server
        self.port = server.config['debug']['debug_port']
        self.secret = server.config['debug']['secret']
        self.allowed_ips = server.config['debug']['allowed_ips']

async def wait_for_session(
        self,
        envelope: RequestEnvelope,
        exception: Exception,
        frame: FrameType,
    ):
        """
        Blocca la request e attende connessione debugger.

Il debugger remoto può:
        - Ispezionare envelope (tutta la request)
        - Ispezionare exception
        - Navigare stack trace
        - Ispezionare locals del frame
        - Eseguire comandi pdb (continue, step, quit)
        """

self.server.logger.warning(
            f"Debug session waiting on ws://localhost:{self.port}"
        )

# Attende connessione e interazione
        await self._debug_loop(envelope, exception, frame)
```

```
┌─────────────────────────┐         ┌─────────────────────────┐
│  Server                 │   WS    │  Debug Console          │
│                         │◄───────►│  (altra finestra)       │
│  1. Errore in request   │         │                         │
│  2. on_error() chiamato │         │  $ genro-debug localhost:8001
│  3. wait_for_session()  │         │  Password: xxxxx        │
│     ↓                   │         │                         │
│  4. BLOCCATO            │         │  > Connected to error   │
│     aspetta debugger    │         │  > envelope.internal_id │
│                         │         │  > exc: ValueError(...) │
│                         │         │  > (Pdb) p locals()     │
│                         │         │  > (Pdb) continue       │
│     ↓                   │         │                         │
│  5. Riprende            │         │  > Session closed       │
└─────────────────────────┘         └─────────────────────────┘
```

```python
class AsgiApplication:
    """Applicazione ASGI - gestisce routing e middleware."""

def __init__(self, server: AsgiServer):
        self.server = server
        self.routes: list[Route] = []
        self.middleware: list[Middleware] = []

async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """Entry point ASGI."""

if scope_type == 'lifespan':
            await self.handle_lifespan(scope, receive, send)
        elif scope_type == 'http':
            await self.handle_http(scope, receive, send)
        elif scope_type == 'websocket':
            await self.handle_websocket(scope, receive, send)

# Accesso a tutto via server
    @property
    def config(self):
        return self.server.config

@property
    def logger(self):
        return self.server.logger

@property
    def registry(self):
        return self.server.registry
```

```python
class AsgiServer:
    """Server ASGI - singleton di processo."""

def __init__(self, config_path: str = 'server.ini'):
        # Config
        self.config = self._load_config(config_path)

# Infrastruttura
        self.logger = self._setup_logger()
        self.metrics = MetricsCollector(self)
        self.registry = EnvelopeRegistry()

# Debug (opzionale)
        if self.config['debug']['remote_pdb']:
            self.debug_server = RemoteDebugServer(self)

# Application
        self.app = AsgiApplication(server=self)

# Background tasks
        self._tasks: list[asyncio.Task] = []
        self.running = False

def run(self):
        """Avvia il server."""
        import uvicorn

uvicorn.run(
            self._asgi_app,  # wrapped con EnvelopeMiddleware
            host=self.config['server']['host'],
            port=self.config['server'].getint('port'),
            workers=self.config['server'].getint('workers'),
            log_config=None,  # usiamo il nostro logger
        )

@property
    def _asgi_app(self):
        """ASGI app wrapped con middleware infrastrutturali."""
        app = self.app
        app = EnvelopeMiddleware(app, server=self)  # sempre primo
        return app

async def startup(self):
        """Chiamato all'avvio."""
        self.running = True

# Avvia background tasks
        if self.config['watchdog'].getboolean('enabled'):
            self._tasks.append(
                asyncio.create_task(self.watchdog_loop())
            )

if self.config['debug'].getboolean('remote_pdb'):
            self._tasks.append(
                asyncio.create_task(self.debug_server.run())
            )

self.logger.info(f"Server started on {self.config['server']['host']}:{self.config['server']['port']}")

async def shutdown(self):
        """Chiamato allo shutdown."""
        self.running = False

# Ferma background tasks
        for task in self._tasks:
            task.cancel()

self.logger.info("Server stopped")
```

```
src/genro_asgi/
├── __init__.py           # esporta AsgiServer, AsgiApplication
├── server.py             # AsgiServer + background tasks
├── application.py        # AsgiApplication
├── registry.py           # EnvelopeRegistry
├── middleware/
│   ├── __init__.py
│   ├── envelope.py       # EnvelopeMiddleware (built-in)
│   └── ...
├── debug/
│   ├── __init__.py
│   └── remote.py         # RemoteDebugServer
├── types.py              # ✅ già fatto
├── datastructures.py     # ✅ già fatto (include Envelope)
├── exceptions.py         # ✅ già fatto
├── request.py            # ✅ già fatto
└── response.py           # ✅ già fatto
```

```
1. Avvio Processo
   └── server = AsgiServer('server.ini')
   └── server.run()
       └── uvicorn.run(server._asgi_app, ...)

2. Startup (lifespan)
   └── server.startup()
       └── avvia watchdog_loop
       └── avvia debug_server (se abilitato)

3. Request HTTP
   └── EnvelopeMiddleware.__call__()
       └── crea RequestEnvelope
       └── registry.add(envelope)
       └── scope['envelope'] = envelope
       └── app(scope, receive, send)
           └── routing → handler
           └── handler accede a request.envelope
           └── handler accede a request.app.server.*
       └── finally: registry.remove(envelope)

4. Errore
   └── server.on_error(envelope, exc)
       └── log con contesto
       └── metrics
       └── debug remoto (se abilitato)
       └── notifica (se critico)
       └── response errore

5. Shutdown
   └── server.shutdown()
       └── ferma background tasks
       └── cleanup
```

1. **Metrics format**: **Prometheus**
   - Export su endpoint `/metrics` (configurabile)
   - Formato standard Prometheus per integrazione con Grafana, AlertManager, ecc.

2. **Routing**: **SmartRoute** (libreria nostra)
   - Sistema di routing proprietario
   - Integrato in AsgiApplication
   - Dipendenza: `smartroute` (da genro-libs)

3. **Config override**: **Sì, env vars override su .ini**
   - Pattern: `GENRO_ASGI_<SECTION>_<KEY>=value`
   - Esempio: `GENRO_ASGI_SERVER_PORT=9000` override `[server] port`
   - Priorità: env var > .ini > default

4. **Graceful shutdown**: **Sì, ma dipende da Executors**
   - Attendere request in-flight prima di shutdown
   - **NOTA**: Implementiamo anche Executors (thread/process pool)
   - Il graceful shutdown deve coordinare:
     - Request HTTP in-flight
     - WebSocket connections
     - Executor tasks pendenti
   - Da definire meglio quando implementiamo Executors

```
AsgiServer
├── executor_thread: ThreadPoolExecutor
├── executor_process: ProcessPoolExecutor
└── run_in_executor(func, *args, pool='thread')
```

Il graceful shutdown deve:
1. Smettere di accettare nuove request
2. Attendere request in-flight (con timeout)
3. Attendere executor tasks (con timeout)
4. Chiudere WebSocket connections
5. Shutdown

Minimo indispensabile per far funzionare tutto il resto.

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| `AsgiServer` (base) | Config .ini, logger, run() con uvicorn | P0 |
| `AsgiApplication` | `__call__`, dispatch http/ws/lifespan | P0 |
| `EnvelopeRegistry` | add/get/remove, dict thread-safe | P0 |
| `EnvelopeMiddleware` | Crea envelope, registra, cleanup | P0 |
| Config env override | `GENRO_ASGI_*` override su .ini | P1 |

**Deliverable Fase 1**:
- Server avviabile con `server.run()`
- Ogni request ha il suo envelope nel registry
- Config da file .ini con env override
- Logger funzionante

**NO in Fase 1**:
- Metrics
- Watchdog
- Error handler avanzato
- Debug remoto
- Executors
- SmartRoute (routing base inline)

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| Prometheus metrics | Counter, Histogram, export `/metrics` | P1 |
| Watchdog task | Rileva request piantate, log warning | P1 |
| Error handler | Log strutturato, metrics per errore | P1 |

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| SmartRoute integration | Routing avanzato da genro-libs | P1 |
| Middleware chain | Stack configurabile | P1 |
| CORS middleware | Headers CORS | P2 |
| Compression middleware | Gzip response | P2 |

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| ThreadPoolExecutor | Task sync in thread pool | P2 |
| ProcessPoolExecutor | Task CPU-bound in process pool | P2 |
| `run_in_executor()` | API unificata | P2 |
| Graceful shutdown | Coordinamento shutdown completo | P2 |

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| Remote debug server | pdb via WebSocket | P3 |
| Hot reload | Ricarica codice in sviluppo | P3 |
| Request inspector | Visualizza request in-flight | P3 |

1. ✅ Decisioni prese
2. Docstring dettagliata per `server.py` (solo componenti Fase 1)
3. Test
4. Implementazione
5. Commit

**Fase 1** (zero dipendenze esterne):
- Solo stdlib Python
- uvicorn (già in uso)

**Fase 2+**:
- `prometheus_client` (metriche)
- `smartroute` (routing)

```
src/genro_asgi/
├── server.py             # AsgiServer (base)
├── application.py        # AsgiApplication
├── registry.py           # EnvelopeRegistry
├── middleware/
│   └── envelope.py       # EnvelopeMiddleware
└── ... (esistenti)
```

## Source: initial_implementation_plan/to-do/08-websocket-01/08-websocket-initial.md

**Scopo**: Classe WebSocket per connessioni WebSocket ASGI.
**Status**: 🔴 DA REVISIONARE

Il modulo `websockets.py` fornisce la classe `WebSocket` per gestire connessioni WebSocket
attraverso l'interfaccia ASGI. Questa classe è la base per il protocollo genro-wsx.

```
Client                            WebSocket Class                    ASGI Server
──────                            ───────────────                    ───────────
Connect  ─────────────────────>   WebSocket(scope, receive, send)
                                  await ws.accept()  ───────────>    websocket.accept
                                  await ws.receive_text()  <────────  websocket.receive
                                  await ws.send_text()  ──────────>  websocket.send
                                  await ws.close()  ──────────────>  websocket.close
```

| Componente | Descrizione |
|------------|-------------|
| WebSocketState | Enum: CONNECTING, CONNECTED, DISCONNECTED |
| WebSocket | Wrapper per connessione WebSocket |

**Problema**: Il piano usa `websockets.py` (plurale), coerente con la convenzione
che il modulo contiene più di una classe (WebSocket + WebSocketState).

| Opzione | Pro | Contro |
|---------|-----|--------|
| `websockets.py` (plurale) | Coerente col piano, indica modulo multi-classe | Potenziale conflitto nome con libreria `websockets` |
| `websocket.py` (singolare) | Come `request.py`, `response.py` | Non segue il piano |

**Domanda**: Usare il plurale come nel piano?

**Problema**: Il piano passa `scope` a `Headers`:
```python
self._headers = Headers(scope=self._scope)
```

Ma l'implementazione attuale di Headers accetta `raw_headers`:
```python
def __init__(self, raw_headers: list[tuple[bytes, bytes]] | None = None, scope: Scope | None = None)
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Passare `scope` | Semplice, Headers estrae headers dallo scope | - |
| Passare `raw_headers` | Esplicito | Più verboso |

**Verifica**: Headers accetta `scope` e può estrarre headers automaticamente?

**Domanda**: Usare `Headers(scope=self._scope)` come nel piano?

**Problema**: Il piano costruisce l'URL lazily con logica complessa:
```python
@property
def url(self) -> URL:
    if self._url is None:
        scheme = self._scope.get("scheme", "ws")
        server = self._scope.get("server")
        # ... 15+ righe di logica
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Lazy (come piano) | Calcolo solo se usato | Logica duplicata con Request |
| Fattorizzare in utility | DRY, riuso tra Request/WebSocket | Nuova dipendenza |

**Nota**: Request ha logica simile per URL construction.

**Domanda**: Accettabile duplicare la logica? O creare una utility condivisa?

**Problema**: Il piano usa `state` come property che inizializza lazily:
```python
@property
def state(self) -> State:
    if self._client_state is None:
        self._client_state = State()
    return self._client_state
```

Ma il nome `_client_state` è confusionario (in `__slots__` c'è `_client_state`).

| Opzione | Pro | Contro |
|---------|-----|--------|
| `_client_state` | Come nel piano | Nome confuso |
| `_state` | Più chiaro, coerente con pattern | Diverso dal piano |

**Domanda**: Rinominare a `_state` per chiarezza?

**Problema**: Il piano usa un Enum:
```python
class WebSocketState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Enum | Type-safe, auto-completamento | Overhead minimo |
| Constants | Più semplice | Meno type-safe |

**Problema**: Il piano accetta headers per accept come bytes:
```python
async def accept(
    self,
    subprotocol: str | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
```

Questo è coerente con ASGI ma poco ergonomico.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `list[tuple[bytes, bytes]]` | Diretto ASGI | Poco user-friendly |
| `dict[str, str]` | User-friendly | Richiede conversione |
| `Mapping[str, str] | list[tuple[str, str]]` | Flessibile, come Response | Più complesso |

**Domanda**: Mantenere formato ASGI per semplicità? O essere più user-friendly?

**Problema**: Il piano converte bytes a text se necessario:
```python
if "text" in message:
    return message["text"]
if "bytes" in message:
    return message["bytes"].decode("utf-8")
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Fallback (come piano) | Flessibile | Potrebbe nascondere problemi |
| Strict (solo text) | Chiaro, fallisce se tipo sbagliato | Meno flessibile |

**Nota**: Alcuni server WebSocket inviano sempre bytes anche per text.

**Domanda**: Mantenere il fallback?

**Problema**: Il piano lascia che json.loads/orjson.loads sollevi ValueError:
```python
async def receive_json(self) -> Any:
    text = await self.receive_text()
    if HAS_ORJSON:
        return orjson.loads(text)
    return json.loads(text)
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Propagare ValueError | Semplice, standard | Utente deve gestire |
| Wrappare in custom exception | Più contesto | Over-engineering |

**Domanda**: OK propagare ValueError/JSONDecodeError?

**Problema**: Il piano ha un metodo `send()` pubblico che wrappa `_send`:
```python
async def send(self, message: Message) -> None:
    if self._state != WebSocketState.CONNECTED:
        raise RuntimeError(...)
    await self._send(message)
```

Ma `send` è anche il nome del callable ASGI interno.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `send()` | Intuitivo | Collisione nomi |
| `send_raw()` | Più esplicito | Meno intuitivo |
| `send_message()` | Chiaro | Più lungo |

**Domanda**: Mantenere `send()` come nel piano?

**Problema**: L'iteratore può yielddare sia str che bytes:
```python
async def __aiter__(self) -> AsyncIterator[str | bytes]:
    if "text" in message:
        yield message["text"]
    elif "bytes" in message:
        yield message["bytes"]
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| `str | bytes` | Flessibile | Type checking meno utile |
| Solo `str` | Type-safe | Perde dati binari |
| Metodi separati | Chiaro | Più verboso |

**Domanda**: Union type OK per iterazione?

**Problema**: Il piano rende close idempotente:
```python
async def close(self, code: int = 1000, reason: str = "") -> None:
    if self._state == WebSocketState.DISCONNECTED:
        return  # No-op se già disconnesso
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Idempotente | Safe, user-friendly | Nasconde chiamate multiple |
| Raise se già chiuso | Esplicito | Meno friendly |

**Problema**: Le regole richiedono entry point. Ma WebSocket richiede
un server ASGI mock completo per demo.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Demo con mock | Segue regole | Mock complesso |
| Solo print info | Minimale | Non testa funzionalità |
| Skip entry point | Semplice | Non segue regole |

**Domanda**: Quale approccio per entry point?

**Problema**: Il piano importa tutto da datastructures:
```python
from .datastructures import Address, Headers, QueryParams, State, URL
```

Queste classi esistono e sono testate nel Block 02.

**Domanda**: Import OK? O verificare API compatibility?

**Problema**: Il piano ritorna `list[str]`:
```python
@property
def subprotocols(self) -> list[str]:
    return self._scope.get("subprotocols", [])
```

Ma potrebbe ritornare la lista mutabile dallo scope.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Return diretto | Semplice | Mutabile, può causare bug |
| Copy `list(...)` | Immutabile | Overhead |
| Tuple | Immutabile | Diverso tipo |

**Domanda**: Return diretto OK?

**Problema**: Il piano ha due "state":
- `state` - custom data storage (State object)
- `connection_state` - WebSocketState enum

| Opzione | Pro | Contro |
|---------|-----|--------|
| Come piano | Distingue chiaramente | Verboso |
| `ws_state` | Più corto | Meno chiaro |

**Problema**: Il piano NON gestisce esplicitamente il messaggio `websocket.connect`.
ASGI spec dice che il primo messaggio ricevuto dopo `scope` potrebbe essere
`websocket.connect` (dipende dal server).

| Opzione | Pro | Contro |
|---------|-----|--------|
| Ignorare (come piano) | Semplice | Potrebbe fallire con alcuni server |
| Gestire in accept() | Completo | Più complesso |

**Domanda**: Serve gestire `websocket.connect`?

**Problema**: I test usano `@pytest.mark.asyncio`. Serve verificare che
pytest-asyncio sia nelle dev dependencies.

**Domanda**: pytest-asyncio è già configurato?

1. **Nome file**: `websockets.py` (plurale) o `websocket.py` (singolare)?
2. **Headers constructor**: Passare `scope` direttamente?
3. **URL construction**: Duplicare logica o fattorizzare utility?
4. **State naming**: `_client_state` o `_state`?
5. **WebSocketState**: Enum OK?
6. **accept() headers**: Format ASGI bytes o più friendly?
7. **receive_text() fallback**: Da bytes a text OK?
8. **receive_json() errors**: Propagare ValueError?
9. **send() method**: Nome OK nonostante collisione?
10. **__aiter__ type**: `str | bytes` union OK?
11. **close() idempotenza**: OK?
12. **Entry point**: Quale approccio?
13. **Imports**: Da datastructures OK?
14. **subprotocols return**: Diretto o copy?
15. **Naming**: `state` vs `connection_state` OK?
16. **websocket.connect**: Gestire?
17. **pytest-asyncio**: Configurato?

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Nome file | **DA DECIDERE** |
| 2 | Headers | **DA DECIDERE** |
| 3 | URL construction | **DA DECIDERE** |
| 4 | State naming | **DA DECIDERE** |
| 5 | WebSocketState | **DA DECIDERE** |
| 6 | accept() headers | **DA DECIDERE** |
| 7 | receive_text() fallback | **DA DECIDERE** |
| 8 | receive_json() errors | **DA DECIDERE** |
| 9 | send() method | **DA DECIDERE** |
| 10 | __aiter__ type | **DA DECIDERE** |
| 11 | close() idempotenza | **DA DECIDERE** |
| 12 | Entry point | **DA DECIDERE** |
| 13 | Imports | **DA DECIDERE** |
| 14 | subprotocols return | **DA DECIDERE** |
| 15 | Naming | **DA DECIDERE** |
| 16 | websocket.connect | **DA DECIDERE** |
| 17 | pytest-asyncio | **DA VERIFICARE** |

1. **Confermare le decisioni** ← SIAMO QUI
2. Scrivere docstring modulo (Step 2)
3. Scrivere test (Step 3)
4. Implementare (Step 4)
5. Commit (Step 6)

## Source: plan_2025_12_29/11-authentication.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `src/genro_asgi/middleware/authentication.py` (223 linee)
**Test**: `tests/test_authentication.py` (25+ test)
**Data**: 2025-12-29

Il documento originale proponeva:
- Preprocessing in `__init__` per O(1) lookup
- Supporto bearer, basic, JWT
- `scope["auth"]` con tags, identity, backend
- 401 su credenziali invalide
- Configurazione YAML gerarchica

```python
"""Authentication middleware with O(1) lookup.

YAML Configuration:
    middleware: cors, auth

auth_middleware:
      bearer:
        reader_token:
          token: "tk_abc123"
          tags: "read"
        writer_token:
          token: "tk_xyz789"
          tags: "read,write"

basic:
        mrossi:
          password: "secret123"
          tags: "read,write"
        admin:
          password: "supersecret"
          tags: "admin"

jwt:
        internal:
          secret: "my-secret"
          algorithm: "HS256"
          tags: "read,write"
          exp: 3600

scope["auth"] format (if authenticated):
    Bearer: {"tags": ["read"], "identity": "reader_token", "backend": "bearer"}
    Basic:  {"tags": ["read"], "identity": "mrossi", "backend": "basic"}
    JWT:    {"tags": ["read"], "identity": "sub_from_token", "backend": "jwt:internal"}

scope["auth"] = None if no auth header present.
Raises HTTPException(401) if credentials are present but invalid.
"""
```

```python
class AuthMiddleware(BaseMiddleware):
    """Authentication middleware with O(1) lookup at request time."""

middleware_name = "auth"
    middleware_order = 400
    middleware_default = False

def __init__(self, app: ASGIApp, **entries: Any) -> None:
        super().__init__(app)
        self._auth_config: defaultdict[str, dict[str, Any]] = defaultdict(dict)

for auth_type, credentials in entries.items():
            method = getattr(self, f"_configure_{auth_type}", self._configure_default)
            method(credentials=credentials)
```

```python
def _configure_bearer(self, *, credentials: dict[str, Any]) -> None:
    """Configure bearer tokens. Each entry: {token: "...", tags: "..."}"""
    for cred_name, config in credentials.items():
        token_value = config.get("token")
        if not token_value:
            raise ValueError(f"Bearer token '{cred_name}' missing 'token' value")
        self._auth_config["bearer"][token_value] = {
            "tags": split_and_strip(config.get("tags", [])),
            "identity": cred_name,
        }
```

**Risultato**: `_auth_config["bearer"]["tk_abc123"] = {"tags": ["read"], "identity": "reader_token"}`

```python
def _configure_basic(self, *, credentials: dict[str, Any]) -> None:
    """Configure basic auth. Each entry: {password: "...", tags: "..."}"""
    for username, config in credentials.items():
        password = config.get("password")
        if not password:
            raise ValueError(f"Basic auth user '{username}' missing 'password'")
        b64_key = base64.b64encode(f"{username}:{password}".encode()).decode()
        self._auth_config["basic"][b64_key] = {
            "tags": split_and_strip(config.get("tags", [])),
            "identity": username,
        }
```

**Risultato**: `_auth_config["basic"]["bXJvc3NpOnNlY3JldDEyMw=="] = {"tags": ["read", "write"], "identity": "mrossi"}`

```python
def _configure_jwt(self, *, credentials: dict[str, Any]) -> None:
    """Configure JWT verifiers."""
    if not HAS_JWT:
        raise ImportError("JWT config requires pyjwt")
    for config_name, config in credentials.items():
        self._auth_config["jwt"][config_name] = {
            "secret": config.get("secret"),
            "public_key": config.get("public_key"),
            "algorithm": config.get("algorithm", "HS256"),
            "default_tags": split_and_strip(config.get("tags", [])),
            "default_exp": config.get("exp", 3600),
        }
```

```python
def _get_auth(self, scope: Scope) -> tuple[str | None, str | None]:
    """Extract auth type and credentials from Authorization header."""
    auth_header = scope["_headers"].get("authorization")
    if auth_header and " " in auth_header:
        auth_type, credentials = auth_header.split(" ", 1)
        return auth_type.lower(), credentials
    return None, None
```

```python
def _authenticate(self, scope: Scope) -> dict[str, Any] | None:
    """Authenticate request via dynamic dispatch."""
    auth_type, credentials = self._get_auth(scope)
    if not auth_type or not credentials:
        return None

method = getattr(self, f"_auth_{auth_type}", self._auth_default)
    result = method(auth_type=auth_type, credentials=credentials)

if result is None:
        raise HTTPException(
            401,
            detail="Invalid or expired credentials",
            headers={"WWW-Authenticate": f"{auth_type.title()} realm=\"api\""},
        )
    return result
```

```python
def _auth_bearer(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
    """Authenticate bearer token. Falls back to JWT if not found."""
    entry = self._auth_config.get("bearer", {}).get(credentials)
    if entry:
        return {"tags": entry["tags"], "identity": entry["identity"], "backend": "bearer"}
    return self._auth_jwt(credentials=credentials)

def _auth_basic(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
    """Authenticate basic auth credentials."""
    entry = self._auth_config.get("basic", {}).get(credentials)
    if entry:
        return {"tags": entry["tags"], "identity": entry["identity"], "backend": "basic"}
    return None

def _auth_jwt(self, *, credentials: str, **kw: Any) -> dict[str, Any] | None:
    """Authenticate JWT token by trying all configured verifiers."""
    for name, jwt_config in self._auth_config.get("jwt", {}).items():
        result = self._verify_jwt(credentials, jwt_config)
        if result:
            result["backend"] = f"jwt:{name}"
            return result
    return None
```

```python
def _verify_jwt(self, credentials: str, jwt_config: dict[str, Any]) -> dict[str, Any] | None:
    """Verify JWT token and extract payload."""
    if not HAS_JWT or jwt is None:
        return None
    secret = jwt_config.get("secret") or jwt_config.get("public_key")
    if not secret:
        return None
    algorithm = jwt_config.get("algorithm", "HS256")
    try:
        payload = jwt.decode(credentials, secret, algorithms=[algorithm])
        return {
            "identity": payload.get("sub"),
            "tags": payload.get("tags", []),
        }
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

```python
{
    "tags": ["read"],
    "identity": "reader_token",  # Nome config
    "backend": "bearer"
}
```

```python
{
    "tags": ["read", "write"],
    "identity": "mrossi",  # Username
    "backend": "basic"
}
```

```python
{
    "tags": ["read", "write"],
    "identity": "user123",  # Da payload["sub"]
    "backend": "jwt:internal"  # jwt:config_name
}
```

```python
def verify_credentials(self, username: str, password: str) -> dict[str, Any] | None:
    """Verify username/password against basic auth config.

Useful for login endpoints that need to verify credentials
    before issuing a JWT token.
    """
    b64_key = base64.b64encode(f"{username}:{password}".encode()).decode()
    entry = self._auth_config.get("basic", {}).get(b64_key)
    if entry:
        return {"tags": entry["tags"], "identity": username}
    return None
```

| Scenario | Comportamento |
|----------|---------------|
| No header Authorization | `scope["auth"] = None`, procede |
| Header presente, valido | `scope["auth"] = {...}` |
| Header presente, invalido | `HTTPException(401)` |
| Endpoint richiede tag mancante | `HTTPForbidden(403)` da router |

auth_middleware:
  # Bearer tokens - lookup diretto per valore token
  bearer:
    reader_token:
      token: "tk_reader123"
      tags: "read"
    writer_token:
      token: "tk_writer456"
      tags: "read,write"
    admin_token:
      token: "tk_admin789"
      tags: "read,write,admin"

# Basic auth - lookup per base64(user:pass)
  basic:
    reader:
      password: "read123"
      tags: "read"
    writer:
      password: "write456"
      tags: "read,write"
    admin:
      password: "admin789"
      tags: "read,write,admin"

# JWT - verifica firma, dati nel payload
  jwt:
    internal:
      secret: "my-super-secret-key"
      algorithm: "HS256"
      tags: "read,write"
      exp: 3600
```

1. **AuthMiddleware** setta `scope["auth"]`
2. **HttpRequest.init()** legge `scope["auth_tags"]`
3. **Dispatcher** passa `auth_tags` a `router.node()`
4. **Router** verifica autorizzazione

```python
# dispatcher.py
node = self.router.node(
    request.path,
    auth_tags=request.auth_tags,
    env_capabilities=request.env_capabilities,
    errors=ROUTER_ERRORS,
)
```

`tests/test_authentication.py` (25+ test):

### TestBearerBackend
- `test_valid_token` - Token valido ritorna auth dict
- `test_readonly_token` - Tags corretti
- `test_invalid_token` - Token invalido ritorna None
- `test_token_without_tags` - Tags vuoti se non specificati
- `test_tags_as_list` - Tags come lista

### TestBasicBackend
- `test_valid_credentials` - Credenziali valide
- `test_invalid_password` - Password errata
- `test_unknown_user` - Utente sconosciuto
- `test_invalid_base64` - Base64 invalido
- `test_missing_colon` - Formato errato

### TestAuthMiddleware
- `test_bearer_auth` - Autenticazione bearer
- `test_basic_auth` - Autenticazione basic
- `test_no_auth_header` - Nessun header → None
- `test_invalid_token` - Token invalido → 401
- `test_multiple_entries` - Config multipla
- `test_non_http_passthrough` - Non-HTTP passa

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Config structure | `type:` field per entry | Tipo come chiave primo livello |
| JWT tags | Da config only | Da payload["tags"] se presente |
| Bearer fallback JWT | Non specificato | ✅ Implementato |
| verify_credentials | Non menzionato | ✅ Implementato |

1. **RS256 support** - public_key per JWT asimmetrici
2. **Audience/Issuer** - Validazione extra JWT
3. **_create_jwt endpoint** - Attualmente stub
4. **Auto capabilities** - Middleware per has_jwt

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/5-avatar.md

**Stato**: ❌ NON IMPLEMENTATO
**Priorità**: P2 (Nice to have)
**Dipendenze**: Session Management
**Data**: 2025-12-29

Il documento originale proponeva un sistema Avatar per rappresentare l'utente autenticato con capabilities e permessi:

Avatar è un oggetto che rappresenta l'utente corrente con:
- **Identity** - Chi è l'utente
- **Tags** - Tag di autorizzazione (da auth)
- **Roles** - Ruoli applicativi
- **Permissions** - Permessi granulari

```python
# Accesso
avatar = request.avatar
# o
avatar = self.avatar  # da app

# Metodi
avatar.identity          # "user123"
avatar.tags              # ["read", "write"]
avatar.roles             # ["editor", "reviewer"]
avatar.has_tag("admin")  # True/False
avatar.has_role("admin") # True/False
avatar.has_permission("article.delete")  # True/False
```

**Non implementato**. L'autenticazione attuale fornisce solo:
- `scope["auth"]` con `tags`, `identity`, `backend`
- `request.auth_tags` lista tag

1. **Avatar class** - Oggetto wrapper
2. **Roles** - Sistema ruoli separato da tags
3. **Permissions** - Sistema permessi granulari
4. **Persistenza** - Integrazione con Session per stato

```python
class Avatar:
    """Represents the authenticated user with capabilities."""

__slots__ = (
        "_identity",
        "_tags",
        "_roles",
        "_permissions",
        "_data",
    )

def __init__(
        self,
        identity: str | None = None,
        tags: list[str] | None = None,
        roles: list[str] | None = None,
        permissions: dict[str, bool] | None = None,
        **data: Any,
    ) -> None:
        self._identity = identity
        self._tags = tags or []
        self._roles = roles or []
        self._permissions = permissions or {}
        self._data = data

@property
    def identity(self) -> str | None:
        """User identity (username, user_id, etc.)."""
        return self._identity

@property
    def tags(self) -> list[str]:
        """Authorization tags from auth middleware."""
        return self._tags

@property
    def roles(self) -> list[str]:
        """Application roles."""
        return self._roles

@property
    def is_authenticated(self) -> bool:
        """True if user is authenticated."""
        return self._identity is not None

@property
    def is_anonymous(self) -> bool:
        """True if user is not authenticated."""
        return self._identity is None

def has_tag(self, tag: str) -> bool:
        """Check if user has specific tag."""
        return tag in self._tags

def has_any_tag(self, *tags: str) -> bool:
        """Check if user has any of the specified tags."""
        return any(tag in self._tags for tag in tags)

def has_all_tags(self, *tags: str) -> bool:
        """Check if user has all specified tags."""
        return all(tag in self._tags for tag in tags)

def has_role(self, role: str) -> bool:
        """Check if user has specific role."""
        return role in self._roles

def has_any_role(self, *roles: str) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self._roles for role in roles)

def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission.

Supports dot-notation wildcards:
        - "article.delete" - exact match
        - "article.*" - any article permission
        - "*" - superuser
        """
        if "*" in self._permissions:
            return True
        if permission in self._permissions:
            return self._permissions[permission]

# Check wildcards
        parts = permission.split(".")
        for i in range(len(parts)):
            wildcard = ".".join(parts[:i]) + ".*"
            if wildcard in self._permissions:
                return self._permissions[wildcard]

def get(self, key: str, default: Any = None) -> Any:
        """Get custom data attribute."""
        return self._data.get(key, default)

def __repr__(self) -> str:
        return f"Avatar(identity={self._identity!r}, tags={self._tags})"
```

```python
class AnonymousAvatar(Avatar):
    """Avatar for unauthenticated users."""

def __init__(self) -> None:
        super().__init__(identity=None, tags=[], roles=[], permissions={})

def has_tag(self, tag: str) -> bool:
        return False

def has_role(self, role: str) -> bool:
        return False

def has_permission(self, permission: str) -> bool:
        return False
```

```python
class AvatarFactory:
    """Creates Avatar from auth info and optionally loads roles/permissions."""

def __init__(
        self,
        role_loader: Callable[[str], list[str]] | None = None,
        permission_loader: Callable[[str], dict[str, bool]] | None = None,
    ) -> None:
        self._role_loader = role_loader
        self._permission_loader = permission_loader

async def create(self, auth: dict[str, Any] | None) -> Avatar:
        """Create Avatar from auth dict."""
        if auth is None:
            return AnonymousAvatar()

identity = auth.get("identity")
        tags = auth.get("tags", [])

# Optionally load roles
        roles = []
        if self._role_loader and identity:
            roles = await smartasync(self._role_loader)(identity)

# Optionally load permissions
        permissions = {}
        if self._permission_loader and identity:
            permissions = await smartasync(self._permission_loader)(identity)

return Avatar(
            identity=identity,
            tags=tags,
            roles=roles,
            permissions=permissions,
        )
```

```python
class HttpRequest(BaseRequest):
    __slots__ = ("_avatar",)

async def init(self, scope, receive, send, **kwargs):
        # ...
        self._avatar = None  # Lazy loaded

@property
    def avatar(self) -> Avatar:
        """Get Avatar for current user. Lazy loaded."""
        if self._avatar is None:
            auth = self._scope.get("auth")
            self._avatar = Avatar(
                identity=auth.get("identity") if auth else None,
                tags=auth.get("tags", []) if auth else [],
            )
        return self._avatar
```

Avatar può persistere dati in Session:

```python
class Avatar:
    def __init__(self, session: Session | None = None, **kwargs):
        self._session = session
        # ...

def remember(self, key: str, value: Any) -> None:
        """Store value in session."""
        if self._session:
            self._session[f"avatar:{key}"] = value

def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve value from session."""
        if self._session:
            return self._session.get(f"avatar:{key}", default)
        return default
```

```python
@route(auth_tags="read")
def get_article(self, id: int):
    avatar = self.server.request.avatar

if avatar.is_anonymous:
        raise HTTPUnauthorized()

article = self.db.get_article(id)

# Check permission
    if article.draft and not avatar.has_permission("article.view_draft"):
        raise HTTPForbidden("Cannot view draft articles")

# Log access
    logger.info(f"Article {id} viewed by {avatar.identity}")

| Aspetto | Auth Tags | Avatar |
|---------|-----------|--------|
| Fonte | Token/Header | Token + DB + Session |
| Contenuto | Lista stringhe | Oggetto strutturato |
| Persistenza | Stateless | Può usare Session |
| Roles | ❌ | ✅ |
| Permissions | ❌ | ✅ |
| Custom data | ❌ | ✅ |

1. **Avatar class** - Core implementation
2. **AnonymousAvatar** - Per utenti non autenticati
3. **AvatarFactory** - Creazione con role/permission loading
4. **Session** (opzionale) - Per persistenza stato

Avatar è utile per:
- **Applicazioni con ruoli** - Editor, Admin, Reviewer
- **Permessi granulari** - article.create, article.delete
- **PageApplication** - App web complesse
- **Multi-tenant** - Utenti con contesti diversi

NON necessario per:
- **API semplici** - auth_tags sufficienti
- **M2M stateless** - Nessun concetto di "utente"
- **Tag-based auth** - Già coperto da auth_tags

- **Avatar class**: 2h
- **AvatarFactory**: 2h
- **Request integration**: 1h
- **Session integration**: 2h (se Session esiste)
- **Tests**: 4h
- **Totale**: ~1 giorno (+ Session se non esiste)

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/7-resources.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `src/genro_asgi/resources.py` (206 linee)
**Data**: 2025-12-29

Il documento originale proponeva:
- Sistema di fallback gerarchico per risorse
- Invariante "dove + cosa = costante"
- Strategie di composizione: override e merge
- Integrazione con LocalStorage
- Endpoint `/_resource/*`

```python
"""ResourceLoader - Hierarchical resource loading with fallback.

Loads resources from the routing tree with fallback from specific to general.
Uses LocalStorage for filesystem access.

Invariant "dove + cosa = costante":
For /_resource/shop/tables/article?name=assets/logo.png:

| Level   | Where (resources/)              | What (name)                          |
|---------|---------------------------------|--------------------------------------|
| article | article/resources/              | assets/logo.png                      |
| tables  | tables/resources/               | article/assets/logo.png              |
| shop    | shop/resources/                 | tables/article/assets/logo.png       |
| server  | server/resources/               | shop/tables/article/assets/logo.png  |

Composition strategies:
- Override (images, HTML, JSON): first found wins (most specific)
- Merge (CSS, JS): concatenate all (general to specific)
"""

MERGE_EXTENSIONS = {".css", ".js"}

class ResourceLoader:
    """Loads resources with hierarchical fallback along the routing tree."""

def __init__(self, server: Any) -> None:
        self.server = server

def collect_levels(self, args: tuple[str, ...]) -> list[Any]:
        """Collect routing levels from path segments.

Walks the routing tree and collects instances that may have resources.

Args:
            args: Path segments (e.g., ("shop", "tables", "article"))

Returns:
            List of instances (server, apps, routing classes) from root to leaf
        """
        levels = [self.server]
        current = self.server.router

for segment in args:
            child = current.get(segment) if hasattr(current, "get") else None
            if child is None:
                break

if hasattr(child, "instance") and child.instance is not None:
                levels.append(child.instance)

def get_resources_node(self, level: Any) -> LocalStorageNode | None:
        """Get the resources storage node for a level."""
        resources_path = getattr(level, "resources_path", None)
        if resources_path is None:
            return None

if not isinstance(resources_path, (str, Path)):
            return None

path = Path(resources_path)
        if not path.is_dir():
            return None

storage = self.server.storage
        mount_name = f"_resources_{id(level)}"

if not storage.has_mount(mount_name):
            storage.add_mount({
                "name": mount_name,
                "type": "local",
                "path": str(path),
            })

return storage.node(mount_name)

def find_candidates(
        self,
        levels: list[Any],
        args: tuple[str, ...],
        name: str,
    ) -> list[LocalStorageNode]:
        """Find resource candidates using the invariant.

Returns:
            List of StorageNodes that exist, from most specific to most general
        """
        candidates = []
        segments = list(args)
        accumulated = name

for i, level in enumerate(reversed(levels)):
            resources_node = self.get_resources_node(level)

if resources_node is not None:
                resource = resources_node.child(accumulated)
                if resource.exists and resource.isfile:
                    candidates.append(resource)

level_index = len(levels) - 1 - i
            if level_index > 0 and level_index <= len(segments):
                segment = segments[level_index - 1]
                accumulated = f"{segment}/{accumulated}"

def compose(
        self,
        candidates: list[LocalStorageNode],
        name: str,
    ) -> tuple[bytes, str]:
        """Compose resource response from candidates."""
        ext = Path(name).suffix.lower()

if ext in MERGE_EXTENSIONS:
            # Merge: concatenate all from general to specific
            content = b""
            for node in reversed(candidates):
                content += node.read_bytes() + b"\n"
            mime_type = "text/css" if ext == ".css" else "application/javascript"
        else:
            # Override: use most specific (first candidate)
            node = candidates[0]
            content = node.read_bytes()
            mime_type = node.mimetype

def load(
        self,
        *args: str,
        name: str,
    ) -> tuple[bytes, str] | None:
        """Load resource with hierarchical fallback."""
        levels = self.collect_levels(args)
        candidates = self.find_candidates(levels, args, name)

if not candidates:
            return None

return self.compose(candidates, name)
```

La chiave del sistema è che la combinazione `where + what` è sempre costante:

```
Richiesta: /_resource/shop/tables/article?name=assets/logo.png

Livello    | Dove cerca (resources/)         | Cosa cerca (name)
-----------|--------------------------------|----------------------------------
article    | article/resources/             | assets/logo.png
tables     | tables/resources/              | article/assets/logo.png
shop       | shop/resources/                | tables/article/assets/logo.png
server     | server/resources/              | shop/tables/article/assets/logo.png
```

Ad ogni livello superiore, il path della risorsa si "allarga" per includere i segmenti inferiori.

Per la maggior parte dei file (immagini, HTML, JSON), vince il più specifico:

```
article/resources/logo.png     ← USATO (più specifico)
shop/resources/logo.png        ← ignorato
server/resources/logo.png      ← ignorato
```

Per `.css` e `.js`, i file vengono concatenati dal generale allo specifico:

```
server/resources/style.css     ← primo nel risultato
shop/resources/style.css       ← secondo
article/resources/style.css    ← ultimo (più specifico)
```

Questo permette:
- CSS base a livello server
- Override/aggiunte per app
- Override/aggiunte per componente

```python
@route("root")
def load_resource(self, *args: str, name: str = "") -> Any:
    """Load resource from hierarchical resource system."""
    result = self.resource_loader.load(*args, name=name)
    if result is None:
        raise HTTPNotFound(f"Resource not found: {name}")

content, mime_type = result
    self.response._media_type = mime_type
    return content
```

| URL | Ricerca |
|-----|---------|
| `/_resource?name=logo.png` | Solo server resources/ |
| `/_resource/shop?name=logo.png` | shop/, poi server/ |
| `/_resource/shop/tables?name=logo.png` | tables/, shop/, server/ |
| `/_resource/shop/tables/article?name=style.css` | Merge di tutti i livelli |

Ogni livello (server, app, routing class) può avere una property `resources_path`:

```python
@property
def resources_path(self) -> Path | None:
    """Path alla directory resources/ del server."""
    resources = self.base_dir / "resources"
    return resources if resources.is_dir() else None
```

Le app usano `base_dir / "resources"`:

```python
# applications/swagger/main.py
class SwaggerApp(AsgiApplication):
    @route()
    def index(self):
        return self.load_resource(name="index.html")
```

ResourceLoader usa LocalStorage per accedere al filesystem:

```python
def get_resources_node(self, level: Any) -> LocalStorageNode | None:
    storage = self.server.storage
    mount_name = f"_resources_{id(level)}"

if not storage.has_mount(mount_name):
        storage.add_mount({
            "name": mount_name,
            "type": "local",
            "path": str(path),
        })

return storage.node(mount_name)
```

I mount vengono creati dinamicamente per ogni livello che ha risorse.

```python
# application.py
def load_resource(self, *args: str, name: str) -> Any:
    """Load resource via server's ResourceLoader, prepending this app's mount name."""
    if not self.server:
        return None
    mount_name = getattr(self, "_mount_name", "")
    return self.server.load_resource(mount_name, *args, name=name)
```

L'app prepende automaticamente il suo `_mount_name` al path.

```
my_project/
├── resources/                    # Server resources
│   ├── logo.png
│   └── style.css
├── apps/
│   └── shop/
│       ├── resources/            # App resources
│       │   ├── shop-logo.png
│       │   └── style.css         # Override/merge con server
│       └── tables/
│           └── article/
│               └── resources/    # Component resources
│                   └── style.css # Override/merge con app e server
└── config.yaml
```

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| StorageNode type | `StorageNode` Protocol | `LocalStorageNode` concreto |
| Mount creation | Pre-configurato | Dinamico per livello |
| Merge separator | Non specificato | `\n` (newline) |

Nessuna differenza significativa nel design generale.

Testato via:
- `test_basic.py` - Integration test endpoint
- Test manuali con struttura risorse

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/12-middleware-config.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `src/genro_asgi/middleware/__init__.py` (214 linee)
**Data**: 2025-12-29

Il documento originale proponeva:
- Ordine definito nelle classi middleware (non configurabile)
- Default on/off definito nelle classi
- Config YAML come dict per abilitare merge con `+`
- ErrorMiddleware sempre on di default
- Range di ordine: 100 (core), 200 (logging), 300 (security), 400 (auth), 500-800 (business), 900 (transformation)
- `__init_subclass__` per auto-registrazione

```python
"""Middleware package - ASGI middleware for genro-asgi."""

MIDDLEWARE_REGISTRY: dict[str, type["BaseMiddleware"]] = {}
```

```python
class BaseMiddleware(ABC):
    """Base class for all middleware. Subclasses auto-register via __init_subclass__.

Class attributes:
        middleware_name: Registry key (default: class name).
        middleware_order: Order in chain (lower = earlier). Ranges:
            100: Core (errors)
            200: Logging/Tracing
            300: Security (cors, csrf)
            400: Authentication (auth)
            500-800: Business logic (custom)
            900: Transformation (compression, caching)
        middleware_default: Default on/off state. Default: False.

Use @headers_dict decorator on __call__ to access scope["_headers"].
    """

middleware_name: str = ""
    middleware_order: int = 500
    middleware_default: bool = False

def __init__(self, app: ASGIApp, **kwargs: Any) -> None:
        self.app = app

def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Use middleware_name if set, otherwise derive from class name
        name = cls.middleware_name or cls.__name__
        if name in MIDDLEWARE_REGISTRY:
            raise ValueError(f"Middleware name '{name}' already registered")
        cls.middleware_name = name
        MIDDLEWARE_REGISTRY[name] = cls

@abstractmethod
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None: ...
```

Ogni middleware definisce tre attributi:

| Attributo | Tipo | Descrizione |
|-----------|------|-------------|
| `middleware_name` | str | Chiave nel registry e config YAML |
| `middleware_order` | int | Posizione nella catena (minore = prima) |
| `middleware_default` | bool | Default on/off se non in config |

```python
class ErrorMiddleware(BaseMiddleware):
    middleware_name = "errors"
    middleware_order = 100
    middleware_default = True  # ← sempre on di default

class CorsMiddleware(BaseMiddleware):
    middleware_name = "cors"
    middleware_order = 300
    middleware_default = False

class AuthMiddleware(BaseMiddleware):
    middleware_name = "auth"
    middleware_order = 400
    middleware_default = False
```

| Range | Categoria | Middleware |
|-------|-----------|------------|
| 100 | Core | errors |
| 200 | Logging/Tracing | logging (futuro) |
| 300 | Security | cors, csrf (futuro) |
| 400 | Authentication | auth |
| 500-800 | Business Logic | custom utente |
| 900 | Transformation | compression, caching (futuro) |

L'utente ha 100 slot tra ogni categoria per middleware custom.

```python
def _autodiscover() -> None:
    """Import all middleware modules in this package to trigger registration."""
    package_dir = Path(__file__).parent
    for py_file in package_dir.glob("*.py"):
        if py_file.name.startswith("_"):
            continue
        module_name = py_file.stem
        importlib.import_module(f".{module_name}", __package__)

_autodiscover()
globals().update(MIDDLEWARE_REGISTRY)
```

Importa automaticamente tutti i moduli `.py` nel package `middleware/` per triggerare `__init_subclass__` e popolare il registry.

```python
def middleware_chain(
    middleware_config: str | list[str] | dict[str, Any],
    app: ASGIApp,
    full_config: Any = None,
) -> ASGIApp:
    """Build middleware chain from config with automatic ordering.

YAML format:
        middleware:
          cors: on
          auth: on
          errors: on  # default=True, so usually omitted

cors_middleware:
          allow_origins: "*"

auth_middleware:
          bearer:
            reader_token:
              token: "tk_abc123"
              tags: "read"

Args:
        middleware_config: Dict {name: on/off}, comma-separated string, or list.
        app: The innermost ASGI app (usually Dispatcher).
        full_config: Full config object to lookup {name}_middleware sections.

Returns:
        Wrapped ASGI app with middleware chain.
    """
```

```python
# 1. Parse config into {name: enabled} dict
config_dict: dict[str, bool] = {}

if isinstance(middleware_config, str):
    # "cors, auth" -> all enabled
    for name in middleware_config.split(","):
        name = name.strip()
        if name:
            config_dict[name] = True
elif hasattr(middleware_config, "as_dict"):
    # SmartOptions
    for name, value in middleware_config.as_dict().items():
        config_dict[name] = _parse_enabled(value)
elif isinstance(middleware_config, dict):
    for name, value in middleware_config.items():
        config_dict[name] = _parse_enabled(value)

# 2. Collect enabled middleware with their order
enabled: list[tuple[int, str, type[BaseMiddleware]]] = []

for name, cls in MIDDLEWARE_REGISTRY.items():
    # Check if enabled: config override or class default
    if name in config_dict:
        is_enabled = config_dict[name]
    else:
        is_enabled = cls.middleware_default

if is_enabled:
        enabled.append((cls.middleware_order, name, cls))

# 3. Sort by order (lower first)
enabled.sort(key=lambda x: x[0])

# 4. Build chain (reversed: first in order = outermost wrapper)
for order, name, cls in reversed(enabled):
    config: Any = {}
    if full_config is not None:
        config_key = f"{name}_middleware"
        mw_config = full_config[config_key]
        if mw_config is not None:
            if hasattr(mw_config, "as_dict"):
                config = mw_config.as_dict()
            else:
                config = mw_config
    app = cls(app, **config)

```python
def headers_dict(
    func: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Decorator that parses headers into scope["_headers"] dict if not present."""

@functools.wraps(func)
    async def wrapper(
        self: "BaseMiddleware", scope: "Scope", receive: "Receive", send: "Send"
    ) -> None:
        if "_headers" not in scope:
            scope["_headers"] = {
                name.decode("latin-1").lower(): value.decode("latin-1")
                for name, value in scope.get("headers", [])
            }
        await func(self, scope, receive, send)

Usato dai middleware che devono accedere agli headers:

```python
class AuthMiddleware(BaseMiddleware):
    @headers_dict
    async def __call__(self, scope, receive, send):
        auth_header = scope["_headers"].get("authorization")
        # ...
```

```yaml
middleware:
  errors: on      # già default=True
  cors: on
  auth: on

cors_middleware:
  allow_origins: ["https://mysite.com"]
  allow_methods: ["GET", "POST", "PUT", "DELETE"]

auth_middleware:
  bearer:
    reader_token:
      token: "tk_xxx"
      tags: "read,write"
```

```yaml
middleware: cors, auth
```

```yaml
middleware:
  - cors
  - auth
```

```python
def _parse_enabled(value: Any) -> bool:
    """Parse on/off/true/false value to bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ("on", "true", "yes", "1")
    return bool(value)
```

Supporta: `on`, `off`, `true`, `false`, `yes`, `no`, `1`, `0`

```
Request in →
    │
    ▼
┌─────────────────┐
│ ErrorMiddleware │  order=100, default=True
│   (outermost)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ CorsMiddleware  │  order=300, se enabled
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ AuthMiddleware  │  order=400, se enabled
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Dispatcher    │  (innermost app)
└─────────────────┘
         │
         ▼
    Response out
```

**Nota**: La costruzione avviene in ordine inverso (reversed) per ottenere il wrapping corretto.

```python
# server.py
self.dispatcher = middleware_chain(
    self.config.middleware,     # dict da config.yaml
    Dispatcher(self),           # innermost app
    full_config=self.config._opts  # per {name}_middleware config
)
```

```python
class RateLimitMiddleware(BaseMiddleware):
    middleware_name = "ratelimit"
    middleware_order = 450  # dopo auth (400), prima di business (500+)
    middleware_default = False

def __init__(self, app, requests_per_minute: int = 60, **kwargs):
        super().__init__(app, **kwargs)
        self.rpm = requests_per_minute

async def __call__(self, scope, receive, send):
        # rate limiting logic
        await self.app(scope, receive, send)
```

```yaml
middleware:
  ratelimit: on

ratelimit_middleware:
  requests_per_minute: 100
```

```yaml
middleware:
  errors: off
```

In questo caso le eccezioni non gestite causeranno 500 da uvicorn direttamente.

```python
__all__ = [
    "BaseMiddleware",
    "MIDDLEWARE_REGISTRY",
    "headers_dict",
    "middleware_chain",
    *MIDDLEWARE_REGISTRY.keys(),  # ErrorMiddleware, CorsMiddleware, etc.
]
```

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Config merge | Menzionato SmartOptions `+` | ✅ Supportato via `as_dict()` |
| String format | Menzionato | ✅ Supportato `"cors, auth"` |
| Flattened keys | `middleware_static_directory` | ✅ `_extract_flattened_middleware` presente |
| headers_dict | Non menzionato | ✅ Implementato come decoratore |
| Auto-discovery | Non menzionato | ✅ Implementato `_autodiscover()` |
| Compression/Caching | Menzionato order=900 | ❌ Non ancora implementato |
| Logging middleware | Menzionato order=200 | ❌ Non ancora implementato |

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/2-genro-api.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `applications/genro_api/main.py` (172 linee)
**Risorse**: `applications/genro_api/resources/` (index.html, tree.js, tester.js, doc.js)
**Data**: 2025-12-29

Il documento originale proponeva:
- Refactoring di GenroApiApp come app esterna
- Struttura `applications/genro_api/` con risorse proprie
- Endpoints: `index()`, `apps()`, `nodes()`, `getdoc()`, `static()`
- Supporto lazy loading per tree view
- Path consumption per URL preselection

**Stato nel documento**: Marcato come priorità P0, "fatto".

```
applications/genro_api/
├── __init__.py
├── main.py             # GenroApiApp class (172 linee)
├── config.yaml         # Config standalone per sviluppo
└── resources/
    ├── index.html      # Explorer UI
    ├── tree.js         # Tree view component
    ├── tester.js       # API tester component
    └── doc.js          # Documentation viewer
```

```python
class GenroApiApp(AsgiApplication):
    """Genro API Explorer - custom API documentation UI.

Mount in config.yaml:
        apps:
          _genro_api:
            module: "main:GenroApiApp"
    """

openapi_info = {
        "title": "Genro API Explorer",
        "version": "1.0.0",
        "description": "Interactive API documentation and testing interface",
    }

@route(meta_mime_type="text/html")
    def index(self, *args: str) -> str:
        """Serve the main explorer page.

With path consumption at N levels:
        - /_genro_api/shop → app="shop", basepath=""
        - /_genro_api/shop/article → app="shop", basepath="article"
        - /_genro_api/shop/article/sub → app="shop", basepath="article/sub"
        """
        app_name = args[0] if args else ""
        basepath = "/".join(args[1:]) if len(args) > 1 else ""
        return self._serve_explorer(app=app_name, basepath=basepath)

def _serve_explorer(self, app: str = "", basepath: str = "") -> str:
        """Serve the explorer HTML with optional app and basepath preselected."""
        html_path = self.base_dir / "resources" / "index.html"
        html = html_path.read_text()

if app or basepath:
            # Inject script to preselect app and basepath on load
            init_script = f"""
    <script type="module">
      window.GENRO_API_INITIAL_APP = "{app}";
      window.GENRO_API_INITIAL_BASEPATH = "{basepath}";
    </script>
  </head>"""
            html = html.replace("</head>", init_script)

@route(openapi_method="get")
    def apps(self) -> dict:
        """Return list of available apps with API routers."""
        if not self.server:
            return {"apps": []}

app_list = []
        for name, instance in self.server.apps.items():
            if hasattr(instance, "api"):
                app_list.append({"name": name, "has_api": True})
        return {"apps": app_list}

@route()
    def nodes(self, app: str = "", basepath: str = "", lazy: bool = False) -> dict:
        """Return hierarchical OpenAPI schema for tree view.

Args:
            app: App name to get schema for (empty = server router)
            basepath: Base path for lazy loading subtrees
            lazy: If True, don't expand child routers
        """
        if not self.server:
            return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}

# Get auth_tags and capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.capabilities if request else ""

if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                result = instance.api.nodes(
                    mode="h_openapi",
                    basepath=basepath,
                    lazy=lazy,
                    auth_tags=auth_tags,
                    env_capabilities=capabilities,
                )
                return result
            return {"description": None, "owner_doc": None, "paths": {}, "routers": {}}

result = self.server.router.nodes(
            mode="h_openapi",
            basepath=basepath,
            lazy=lazy,
            auth_tags=auth_tags,
            env_capabilities=capabilities,
        )
        return dict(result)

@route(openapi_method="get")
    def getdoc(self, path: str, app: str = "") -> dict:
        """Get documentation for a single node (router or endpoint).

Args:
            path: The path to the node (e.g., "/table/article/get")
            app: App name (empty = server router)
        """
        if not self.server:
            return {"error": "No server available"}

router = None
        if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                router = instance.api
        else:
            router = self.server.router

if not router:
            return {"error": f"Router not found for app '{app}'"}

# Get auth_tags and capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.capabilities if request else ""

# Remove leading slash - router.node() expects path without it
        clean_path = path.lstrip("/")
        node = router.node(
            clean_path,
            mode="openapi",
            auth_tags=auth_tags,
            env_capabilities=capabilities,
        )
        return node.openapi or {"error": f"No OpenAPI schema for '{path}'"}

@route()
    def static(self, file: str = "") -> Path:
        """Serve static resources (JS, CSS) from resources folder.

Returns Path - set_result() handles mime type detection.
        Raises ValueError/FileNotFoundError for errors (mapped by set_error()).
        """
        if not file:
            raise ValueError("File parameter required")

resources_dir = self.base_dir / "resources"
        file_path = resources_dir / file

if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError(f"Resource not found: {file}")

| Path | Metodo | Descrizione |
|------|--------|-------------|
| `/_genro_api/` | GET | Explorer UI HTML |
| `/_genro_api/{app}` | GET | Explorer con app preselezionata |
| `/_genro_api/{app}/{path...}` | GET | Explorer con app e basepath preselezionati |
| `/_genro_api/apps` | GET | Lista apps con API router |
| `/_genro_api/nodes` | GET | Tree gerarchico OpenAPI |
| `/_genro_api/getdoc` | GET | Doc singolo nodo |
| `/_genro_api/static` | GET | Risorse statiche (JS, CSS) |

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `app` | str | "" | Nome app (vuoto = server router) |
| `basepath` | str | "" | Base path per lazy loading |
| `lazy` | bool | False | Se True, non espande child routers |

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `path` | str | required | Path al nodo (es. `/table/article/get`) |
| `app` | str | "" | Nome app (vuoto = server router) |

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `file` | str | required | Nome file (es. `tree.js`) |

L'explorer filtra gli endpoint visibili in base alle credenziali dell'utente:

```python
# Get auth_tags and capabilities from current request
request = self.server.request
auth_tags = request.auth_tags if request else ""
capabilities = request.capabilities if request else ""

result = router.nodes(
    mode="h_openapi",
    auth_tags=auth_tags,           # ← filtro per permessi
    env_capabilities=capabilities,  # ← filtro per capabilities
)
```

Un utente senza tag `admin` non vedrà endpoint protetti con `auth_tags="admin"`.

L'app usa `self.base_dir` per accedere alle sue risorse:

```python
def _serve_explorer(self, app: str = "", basepath: str = "") -> str:
    html_path = self.base_dir / "resources" / "index.html"
    html = html_path.read_text()
    # ...
```

Il server setta `base_dir` quando monta l'app:

```python
# server.py
instance = cls(**kwargs)  # kwargs include base_dir
```

```yaml
apps:
  shop:
    module: "shop:ShopApp"

_genro_api:
    module: "applications.genro_api:GenroApiApp"
```

```yaml
# applications/genro_api/config.yaml
server:
  host: "127.0.0.1"
  port: 8002
  reload: true

apps:
  _genro_api:
    module: "main:GenroApiApp"
```

```bash
cd applications/genro_api
python -m genro_asgi serve . --port 8002
```

HTML principale con:
- Dropdown per selezione app
- Tree view per navigare endpoints
- Panel per documentazione
- Form per testare chiamate

Componente per visualizzazione ad albero:
- Nodi collassabili
- Lazy loading di sottorami
- Click per visualizzare doc

Form per testare API:
- Input parametri
- Selezione metodo HTTP
- Visualizzazione response

Visualizzatore documentazione:
- Schema OpenAPI renderizzato
- Parametri con tipi
- Esempi se disponibili

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Location | `src/genro_asgi/applications/` | `applications/genro_api/` |
| Accesso risorse | `self.load_resource()` | `self.base_dir / "resources"` |
| auth_tags type | string | list[str] |
| Static files | Non definito | Endpoint `static()` |

L'app è in `applications/` (top-level) invece di `src/genro_asgi/applications/` perché:
1. È un'app **esterna** montabile, non parte del core
2. Ha le sue risorse HTML/JS
3. Può essere sviluppata/testata standalone

L'app è testata manualmente. Test automatici per:
- Endpoint `apps()` ritorna lista corretta
- Endpoint `nodes()` con/senza app
- Filtraggio auth_tags

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/0-readme.md

**Data audit**: 2025-12-29
**Progetto**: genro-asgi
**Versione corrente**: 0.1.0 (Alpha)

Il documento originale conteneva:
- Tabella con 16 documenti e relative priorità (P0-P3)
- Checkmark ✓ per documenti considerati "fatti"
- Lista di discrepanze tra piano e implementazione
- Checklist implementativa incompleta

| Componente | Stato | File | Note |
|------------|-------|------|------|
| **AsgiServer** | ✅ Funzionante | `server.py` | 256 linee, routing via genro-routes |
| **AsgiApplication** | ✅ Funzionante | `application.py` | 115 linee, hooks on_init/startup/shutdown |
| **Dispatcher** | ✅ Funzionante | `dispatcher.py` | 83 linee, passa auth_tags e env_capabilities |
| **Request System** | ✅ Funzionante | `request.py` | 682 linee, HttpRequest + MsgRequest |
| **Response** | ✅ Funzionante | `response.py` | 465 linee, set_result con auto-detection |
| **LocalStorage** | ✅ Funzionante | `storage.py` | 396 linee, mount predefiniti + dinamici |
| **ResourceLoader** | ✅ Funzionante | `resources.py` | 206 linee, fallback gerarchico |
| **AuthMiddleware** | ✅ Funzionante | `middleware/authentication.py` | 223 linee, O(1) lookup |
| **CORS Middleware** | ✅ Funzionante | `middleware/cors.py` | Configurabile via YAML |
| **Error Middleware** | ✅ Funzionante | `middleware/errors.py` | Gestione eccezioni HTTP |
| **Lifespan** | ✅ Funzionante | `lifespan.py` | 234 linee, ServerLifespan |
| **SwaggerApp** | ✅ Funzionante | `applications/swagger/main.py` | 80 linee, app esterna |
| **GenroApiApp** | ✅ Funzionante | `applications/genro_api/main.py` | 172 linee, app esterna |
| **Session** | ❌ Non implementato | - | Solo progettazione |
| **Avatar** | ❌ Non implementato | - | Solo progettazione |
| **PageApplication** | ❌ Non implementato | - | Solo concetto |
| **ApiApplication** | ❌ Non implementato | - | Solo concetto |

| Stato | Significato |
|-------|-------------|
| ✅ Funzionante | Implementato, verificato nel codice, testato |
| ⚠️ Parziale | Core implementato, alcune feature mancanti |
| 🔸 Stub | Placeholder presente, implementazione da completare |
| ❌ Non implementato | Solo nella documentazione, zero codice |
| 📋 Da progettare | Nessuna implementazione, solo concetto |

| # | Documento | Argomento | Stato Implementazione |
|---|-----------|-----------|----------------------|
| 0 | [0-readme.md](0-readme.md) | Overview (questo file) | ✓ |
| 1 | [1-applications.md](1-applications.md) | AsgiApplication base class | ✅ Implementato |
| 2 | [2-genro-api.md](2-genro-api.md) | GenroApiApp explorer | ✅ Implementato |
| 3 | [3-context.md](3-context.md) | Context injection | ⚠️ Semplificato |
| 4 | [4-session.md](4-session.md) | Session management | ❌ Non implementato |
| 5 | [5-avatar.md](5-avatar.md) | Avatar/auth system | ❌ Non implementato |
| 6 | [6-naming.md](6-naming.md) | Terminologia | ✅ Applicata |
| 7 | [7-resources.md](7-resources.md) | ResourceLoader | ✅ Implementato |
| 8 | [8-storage.md](8-storage.md) | LocalStorage | ✅ Implementato |
| 9 | [9-page-application.md](9-page-application.md) | PageApplication | ❌ Non implementato |
| 10 | [10-api-application.md](10-api-application.md) | ApiApplication | ❌ Non implementato |
| 11 | [11-authentication.md](11-authentication.md) | AuthMiddleware | ✅ Implementato |
| 12 | [12-middleware-config.md](12-middleware-config.md) | Middleware chain | ✅ Implementato |
| 13 | [13-swagger-app.md](13-swagger-app.md) | SwaggerApp | ✅ Implementato |
| 14 | [14-openapi-info.md](14-openapi-info.md) | OpenAPI info | ⚠️ Parziale |
| 15 | [15-asgiapplication-refactor.md](15-asgiapplication-refactor.md) | Refactor AsgiApplication | ✅ Implementato |
| 16 | [16-server-separation.md](16-server-separation.md) | Server/ServerApp separation | 📋 Proposta |

Le seguenti discrepanze dal piano 2025-12-21 sono state **risolte**:

| # | Discrepanza | Soluzione |
|---|-------------|-----------|
| 1 | `__init__` signature (server passato) | Server NON passa self, usa `attach_instance` |
| 2 | Context injection (AsgiContext) | Rimosso, usa `request.auth_tags` e `request.env_capabilities` |
| 3 | `set_response` method | Usa `response.set_result()` con auto-detection |
| 4 | Lifecycle hooks | Implementati `on_init`, `on_startup`, `on_shutdown` |
| 5 | Main router | Creato automaticamente come `self.main` |
| 6 | Auto tags (has_jwt) | Ora è `env_capabilities` settato da middleware |
| 7 | request.auth_tags | Implementato, legge da `scope["auth_tags"]` |
| 8 | auth_tags nel router | Dispatcher passa `auth_tags` e `env_capabilities` a `router.node()` |
| 9 | _resource endpoint | Implementato con ResourceLoader |
| 10 | README status | Aggiornato |

```
Browser/Client
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ AsgiServer.__call__(scope, receive, send)                   │
│   │                                                         │
│   ├── scope["type"] == "lifespan" → self.lifespan          │
│   └── else → self.dispatcher(scope, receive, send)          │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Middleware Chain (ordine crescente)                         │
│   │                                                         │
│   ├── ErrorMiddleware (100) - gestisce eccezioni           │
│   ├── CorsMiddleware (300) - se attivo                     │
│   └── AuthMiddleware (400) - setta scope["auth"]           │
│                                  scope["auth_tags"]         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Dispatcher.__call__                                         │
│   │                                                         │
│   ├── request = registry.create(scope, receive, send)      │
│   │      └── request._auth_tags = scope["auth_tags"]       │
│   │      └── request._env_capabilities = scope["env_cap"]  │
│   ├── set_current_request(request)                         │
│   ├── node = router.node(path,                             │
│   │           auth_tags=request.auth_tags,                 │
│   │           env_capabilities=request.env_capabilities)   │
│   ├── result = await smartasync(node)(**query)             │
│   ├── request.response.set_result(result, metadata)        │
│   └── await request.response(scope, receive, send)         │
└─────────────────────────────────────────────────────────────┘
```

```
genro_routes.RoutingClass
    │
    ├── AsgiServer
    │     ├── router = Router(self, name="root")
    │     ├── apps: dict[str, AsgiApplication]
    │     ├── storage: LocalStorage
    │     ├── resource_loader: ResourceLoader
    │     ├── lifespan: ServerLifespan
    │     ├── request_registry: RequestRegistry
    │     └── Endpoints: index(), _openapi(), load_resource(), _create_jwt()
    │
    └── AsgiApplication
          ├── main = Router(self, name="main")
          ├── base_dir: Path | None
          ├── openapi_info: ClassVar[dict]
          ├── Hooks: on_init(), on_startup(), on_shutdown()
          ├── Methods: load_resource()
          └── Endpoint: index()
```

```python
# Server NON passa self nel costruttore
for name, (cls, kwargs) in self.config.get_app_specs().items():
    instance = cls(**kwargs)           # NO self
    instance._mount_name = name
    self.apps[name] = instance
    self.router.attach_instance(instance, name=name)  # setta _routing_parent

# AsgiApplication.server legge da _routing_parent
@property
def server(self) -> AsgiServer | None:
    return getattr(self, "_routing_parent", None)
```

- **339 test** passano
- **Coverage**: 59%
- File test principali:
  - `test_authentication.py` - 25+ test auth
  - `test_storage.py` - 50+ test storage
  - `test_response.py` - Response tests
  - `test_basic.py` - Integration tests

| Aspetto | Piano 2025-12-21 | Implementazione 2025-12-29 |
|---------|------------------|---------------------------|
| Server passa self | `cls(self, **kwargs)` | `cls(**kwargs)` + `attach_instance` |
| Context injection | `AsgiContext` separato | `request.auth_tags`, `request.env_capabilities` |
| Auto tags | `server.auto_tags` | `scope["env_capabilities"]` da middleware |
| Response | `set_response()` method | `response.set_result()` con auto-detection |
| Hooks | Non definiti | `on_init`, `on_startup`, `on_shutdown` |

| Componente | Motivo |
|------------|--------|
| Session | Non prioritario per API stateless |
| Avatar | Dipende da Session |
| PageApplication | Dipende da Session + Avatar |
| ApiApplication | Richiede design aggiuntivo |
| Server/ServerApp separation | Proposta da validare |

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/9-page-application.md

**Stato**: ❌ NON IMPLEMENTATO
**Priorità**: P2 (Nice to have)
**Dipendenze**: Session, Avatar
**Data**: 2025-12-29

Il documento originale proponeva:
- `PageApplication` come micro-app on-demand per risorse
- Caricamento da `resources/*/index.py`
- Scoped alla risorsa che la contiene
- Supporto per session e avatar
- Pattern diverso da `AsgiApplication` montata

```
GET /_resource/swagger/
→ Carica resources/swagger/index.py
→ Istanzia PageApplication
→ Chiama index() → HTML
```

**Non implementato**. Zero codice presente.

- `AsgiApplication` - App montate staticamente in config.yaml
- `SwaggerApp`, `GenroApiApp` - Implementate come AsgiApplication
- `ResourceLoader` - Caricamento risorse statiche

- Caricamento dinamico da `index.py`
- `PageApplication` base class
- Integrazione con Session/Avatar

```python
class PageApplication:
    """Micro-app for dynamic resource pages.

Unlike AsgiApplication (mounted statically), PageApplication is
    instantiated on-demand when accessing a resource directory with index.py.

Lifecycle:
    1. Request arrives for /_resource/swagger/
    2. ResourceLoader finds resources/swagger/index.py
    3. PageApplication is instantiated
    4. index() method is called
    5. Response is returned
    6. Instance is discarded (no persistence)
    """

def __init__(
        self,
        server: AsgiServer,
        request: BaseRequest,
        resource_path: Path,
    ) -> None:
        self.server = server
        self.request = request
        self.resource_path = resource_path
        self._session: Session | None = None
        self._avatar: Avatar | None = None

@property
    def session(self) -> Session | None:
        """Session for this request (if SessionMiddleware enabled)."""
        if self._session is None:
            self._session = self.request.scope.get("session")
        return self._session

@property
    def avatar(self) -> Avatar | None:
        """Avatar for current user."""
        if self._avatar is None:
            auth = self.request.scope.get("auth")
            if auth:
                self._avatar = Avatar(
                    identity=auth.get("identity"),
                    tags=auth.get("tags", []),
                )
            else:
                self._avatar = AnonymousAvatar()
        return self._avatar

def load_resource(self, name: str) -> bytes:
        """Load resource from this page's resource directory."""
        path = self.resource_path / name
        if not path.exists():
            raise FileNotFoundError(f"Resource not found: {name}")
        return path.read_bytes()

def render_template(self, name: str, **context: Any) -> str:
        """Render a template with context."""
        # Simple string substitution, or integrate with Jinja2
        template = self.load_resource(name).decode()
        for key, value in context.items():
            template = template.replace(f"{{{{{key}}}}}", str(value))
        return template

def redirect(self, url: str, status_code: int = 302) -> Response:
        """Return a redirect response."""
        return Response(
            status_code=status_code,
            headers={"Location": url},
        )

def index(self) -> str | bytes | dict | Response:
        """Default index page. Override in subclass."""
        return f"<h1>{self.__class__.__name__}</h1>"
```

```python
class PageLoader:
    """Loads and instantiates PageApplication from index.py files."""

def __init__(self, server: AsgiServer) -> None:
        self.server = server
        self._cache: dict[Path, type[PageApplication]] = {}

def find_page(self, resource_path: Path) -> type[PageApplication] | None:
        """Find PageApplication class for a resource directory."""
        index_py = resource_path / "index.py"
        if not index_py.exists():
            return None

if resource_path in self._cache:
            return self._cache[resource_path]

# Dynamic import
        spec = importlib.util.spec_from_file_location(
            f"page_{resource_path.name}",
            index_py,
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

# Find PageApplication subclass
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, PageApplication)
                and obj is not PageApplication
            ):
                self._cache[resource_path] = obj
                return obj

async def handle(
        self,
        request: BaseRequest,
        resource_path: Path,
    ) -> Any:
        """Handle request for a page resource."""
        page_cls = self.find_page(resource_path)
        if page_cls is None:
            return None

page = page_cls(
            server=self.server,
            request=request,
            resource_path=resource_path,
        )

# Call index method
        result = page.index()
        if hasattr(result, "__await__"):
            result = await result

```python
# resources.py
class ResourceLoader:
    def load(self, *args: str, name: str) -> tuple[bytes, str] | None:
        # ... existing logic ...

# Check for index.py (PageApplication)
        if name == "" or name == "index.html":
            for level in levels:
                resources_path = getattr(level, "resources_path", None)
                if resources_path:
                    page_dir = Path(resources_path) / "/".join(args)
                    if (page_dir / "index.py").exists():
                        # Delegate to PageLoader
                        return self._handle_page(page_dir)

# ... existing static file logic ...
```

```python
from genro_asgi.page import PageApplication

class AdminPage(PageApplication):
    """Admin dashboard page."""

def index(self) -> str:
        if not self.avatar.has_tag("admin"):
            return self.redirect("/login")

return self.render_template(
            "dashboard.html",
            user=self.avatar.identity,
            session_id=self.session.session_id if self.session else None,
        )

def stats(self) -> dict:
        """API endpoint for stats."""
        return {
            "users": 100,
            "orders": 50,
        }
```

```html
<!DOCTYPE html>
<html>
<head><title>Admin Dashboard</title></head>
<body>
    <h1>Welcome, {{user}}</h1>
    <p>Session: {{session_id}}</p>
</body>
</html>
```

| Aspetto | AsgiApplication | PageApplication |
|---------|-----------------|-----------------|
| Montaggio | Statico in config.yaml | Dinamico da index.py |
| Lifecycle | Persistente | Per-request |
| Router | Ha router genro-routes | No router |
| Endpoints | Via @route() | Metodi diretti |
| Session | Via middleware | Accesso diretto |
| Scope | Tutta l'app | Singola risorsa |

Per implementare PageApplication:

1. **Session** - Per stato utente tra pagine
2. **Avatar** - Per identificare l'utente
3. **PageLoader** - Per caricamento dinamico
4. **Template system** - Per rendering HTML

PageApplication è utile per:
- **Dashboard admin** - UI con session
- **Wizard multi-step** - Stato tra pagine
- **Form complessi** - Con validazione server-side
- **Pagine protette** - Con check avatar

NON necessario per:
- **API REST** - Usa AsgiApplication
- **SPA** - Frontend gestisce tutto
- **Risorse statiche** - ResourceLoader sufficiente

- **PageApplication class**: 4h
- **PageLoader**: 4h
- **ResourceLoader integration**: 2h
- **Template system**: 4h (o usare Jinja2)
- **Tests**: 4h
- **Totale**: ~2-3 giorni (dopo Session/Avatar)

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/16-server-separation.md

**Stato**: 📋 PROPOSTA NON IMPLEMENTATA
**Data**: 2025-12-29

Il documento originale proponeva:
- Separare `AsgiServer` in due classi distinte
- `AsgiServer`: Orchestratore puro (config, lifespan, dispatcher, request_registry)
- `ServerApp`: Root application con endpoint di sistema (index, _openapi, _resource, _create_jwt)
- `ServerApp` eredita da `AsgiApplication`
- Vantaggi: separazione netta, coerenza, testabilità

`AsgiServer` attualmente ha due responsabilità mescolate:

### 1. Orchestratore ASGI
- `config`: ServerConfig
- `lifespan`: ServerLifespan
- `dispatcher`: Middleware chain + Dispatcher
- `request_registry`: RequestRegistry
- `storage`: LocalStorage
- `resource_loader`: ResourceLoader

### 2. Root Application
- `router = Router(self, name="root")`
- `index()`: Default page, redirect to main_app
- `_openapi()`: OpenAPI schema
- `load_resource()`: Resource endpoint
- `_create_jwt()`: JWT creation (stub)

```python
# Server eredita da RoutingClass ma non da AsgiApplication
class AsgiServer(RoutingClass):
    ...
    self.router = Router(self, name="root")  # ← "root", non "main"
```

```python
# Le app ereditano da AsgiApplication
class ShopApp(AsgiApplication):
    ...
    self.main = Router(self, name="main")  # ← "main"
```

Le app montate vedono il server come parent (`_routing_parent`), ma server non è una app.

```python
class AsgiServer:
    """ASGI orchestrator - NO routing, solo infrastruttura."""

__slots__ = ("config", "lifespan", "dispatcher", "request_registry", "root", "apps")

def __init__(self, server_dir=None, host=None, port=None, reload=None, argv=None):
        self.config = ServerConfig(server_dir, host, port, reload, argv)
        self.request_registry = RequestRegistry()

# Root app con router primario
        self.root = ServerApp(self)
        self.apps = {"_root": self.root}

# Monta le app sotto root
        for name, (cls, kwargs) in self.config.get_app_specs().items():
            instance = cls(**kwargs)
            self.apps[name] = instance
            self.root.main.attach_instance(instance, name=name)

self.lifespan = ServerLifespan(self)
        self.dispatcher = middleware_chain(
            self.config.middleware,
            Dispatcher(self),
            full_config=self.config._opts
        )

async def __call__(self, scope, receive, send):
        """ASGI interface."""
        if scope["type"] == "lifespan":
            await self.lifespan(scope, receive, send)
        else:
            await self.dispatcher(scope, receive, send)

def run(self):
        """Run with Uvicorn."""
        import uvicorn
        uvicorn.run(self, host=..., port=..., reload=...)

@property
    def router(self):
        """Proxy to root.main for backward compatibility."""
        return self.root.main
```

```python
class ServerApp(AsgiApplication):
    """Root application - endpoint di sistema."""

openapi_info = {
        "title": "GenroASGI Server",
        "version": "1.0.0",
        "description": "System endpoints"
    }

def __init__(self, asgi_server: AsgiServer):
        super().__init__()  # ← crea self.main
        self._asgi_server = asgi_server

# ─────────────────────────────────────────────────────────────────
    # Proxy alle risorse del server
    # ─────────────────────────────────────────────────────────────────

@property
    def config(self):
        return self._asgi_server.config

@property
    def request(self):
        return self._asgi_server.request_registry.current

@property
    def response(self):
        req = self.request
        return req.response if req else None

@property
    def apps(self):
        return self._asgi_server.apps

# ─────────────────────────────────────────────────────────────────
    # Endpoint di sistema (spostati da AsgiServer)
    # ─────────────────────────────────────────────────────────────────

@route(meta_mime_type="text/html")
    def index(self):
        """Default index page. Redirects to main_app if configured."""
        if self.config.main_app:
            raise Redirect(f"/{self.config.main_app}/")
        return self._default_index_html()

@route(meta_mime_type="application/json")
    def _openapi(self, *args):
        """OpenAPI schema endpoint."""
        basepath = "/".join(args) if args else None
        return self.main.nodes(basepath=basepath, mode="openapi")

@route()
    def _resource(self, *args):
        """Resource endpoint with hierarchical fallback."""
        basepath = "/".join(args) if args else None
        return {"resource": basepath, "status": "not_implemented"}

@route(auth_tags="superadmin&has_jwt")
    def _create_jwt(self, jwt_config=None, sub=None, tags=None, exp=None, **extra):
        """Create JWT token via HTTP endpoint."""
        ...
```

```
AsgiServer (non RoutingClass, puro orchestratore)
    │
    └── self.root = ServerApp (AsgiApplication)
            │
            ├── self._asgi_server = AsgiServer (riferimento esplicito)
            │
            ├── self.main (Router "main")
            │       │
            │       ├── attach_instance(shop, "shop")
            │       │       └── shop._routing_parent = ServerApp
            │       │
            │       └── attach_instance(swagger, "_swagger")
            │               └── swagger._routing_parent = ServerApp
            │
            └── Endpoint: index, _openapi, _resource, _create_jwt
```

```python
class ShopApp(AsgiApplication):
    @route()
    def products(self):
        # self.server → ServerApp (via _routing_parent)
        # self.server.config → config del server
        # self.server.request → request corrente
        # self.server.apps → dict delle app
        return {"products": [...]}
```

```python
class ServerApp(AsgiApplication):
    @route()
    def index(self):
        # self._asgi_server → AsgiServer diretto
        # self.config → proxy a self._asgi_server.config
        ...
```

1. **Separazione netta**: Orchestratore vs Application
2. **Coerenza**: Tutte le app (inclusa ServerApp) ereditano da AsgiApplication
3. **`self.server`** funziona uniformemente: ritorna sempre un'AsgiApplication (o None)
4. **Testabilità**: ServerApp testabile indipendentemente
5. **Estensibilità**: Facile sostituire/estendere ServerApp
6. **Router naming**: Tutti usano "main" invece di mescolare "root" e "main"

1. **Un livello in più**: ServerApp intermedia tra Server e App
2. **Proxy methods**: ServerApp deve fare proxy per config, request, etc.
3. **Breaking change**: Richiede refactoring del dispatcher
4. **Backward compatibility**: `server.router` deve diventare proxy

| File | Modifica |
|------|----------|
| `src/genro_asgi/server.py` | Rimuovere RoutingClass, creare istanza ServerApp |
| `src/genro_asgi/server_app.py` | Nuovo file per ServerApp |
| `src/genro_asgi/dispatcher.py` | Usare `server.root.main` invece di `server.router` |
| `src/genro_asgi/__init__.py` | Esportare ServerApp |

1. [ ] Creare feature branch `feat/server-separation`
2. [ ] Creare `server_app.py` con ServerApp
3. [ ] Refactoring `server.py` per rimuovere routing
4. [ ] Aggiornare `dispatcher.py`
5. [ ] Aggiornare test
6. [ ] Verificare che tutti i test passino
7. [ ] Merge se validato

1. **Nome del router in ServerApp**: `main` (standard) o `root` (semantico)?
   - Proposta: usare `main` per coerenza con AsgiApplication

2. **Backward compatibility**: Mantenere `server.router` come alias?
   - Proposta: sì, `server.router → server.root.main`

3. **Dispatcher**: Deve conoscere ServerApp o solo il router?
   - Proposta: usa `server.router` (alias), così è trasparente

```python
class AsgiServer(AsgiApplication):
    def __init__(self, ...):
        super().__init__()  # crea self.main
        self.router = self.main
        ...
```

**Scartata**: Server ha troppe responsabilità extra (config, lifespan, etc.) che non appartengono a un'application.

Server resta RoutingClass con router "root".

**Scartata**: Incoerenza con le app che usano AsgiApplication e "main".

L'implementazione attuale mantiene AsgiServer come RoutingClass:

```python
# server.py attuale
class AsgiServer(RoutingClass):
    def __init__(self, ...):
        self.router = Router(self, name="root")  # ← mix di responsabilità
        # ... orchestratore + endpoint ...
```

La proposta di separazione è **DA VALIDARE** prima dell'implementazione.

**Stato**: 📋 PROPOSTA DA REVISIONARE

Prima di implementare:
1. Validare i vantaggi vs complessità aggiunta
2. Verificare impatto su backward compatibility
3. Discutere naming convention (root vs main)

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/6-naming.md

**Stato**: ✅ APPLICATA
**Data**: 2025-12-29

Il documento originale definiva la terminologia ufficiale per genro-asgi:

| Termine | Significato |
|---------|-------------|
| Server | `AsgiServer`, entry point ASGI |
| Application/App | `AsgiApplication`, montata sul server |
| Router | Oggetto genro-routes per routing |
| Middleware | Wrapper ASGI nella chain |
| Handler | Metodo che gestisce una route |
| Endpoint | Combinazione route + handler |

| Termine | Classe | File | Descrizione |
|---------|--------|------|-------------|
| **Server** | `AsgiServer` | `server.py` | Entry point ASGI, gestisce apps e routing |
| **Application/App** | `AsgiApplication` | `application.py` | Base class per app montate |
| **Dispatcher** | `Dispatcher` | `dispatcher.py` | Smista request agli handler |
| **Router** | `Router` (genro-routes) | - | Gestisce registrazione e lookup routes |
| **Request** | `HttpRequest`, `MsgRequest` | `request.py` | Wrapper richiesta ASGI |
| **Response** | `Response` | `response.py` | Wrapper risposta ASGI |

| Termine | Classe | File | Descrizione |
|---------|--------|------|-------------|
| **Middleware** | `BaseMiddleware` | `middleware/__init__.py` | Base class per middleware |
| **AuthMiddleware** | `AuthMiddleware` | `middleware/authentication.py` | Autenticazione |
| **CorsMiddleware** | `CorsMiddleware` | `middleware/cors.py` | CORS headers |
| **ErrorMiddleware** | `ErrorMiddleware` | `middleware/errors.py` | Error handling |

| Termine | Classe | File | Descrizione |
|---------|--------|------|-------------|
| **Storage** | `LocalStorage` | `storage.py` | Accesso filesystem |
| **StorageNode** | `LocalStorageNode` | `storage.py` | Singolo file/directory |
| **ResourceLoader** | `ResourceLoader` | `resources.py` | Caricamento risorse con fallback |

| Termine | Classe | File | Descrizione |
|---------|--------|------|-------------|
| **Lifespan** | `ServerLifespan` | `lifespan.py` | Gestione startup/shutdown |
| **Registry** | `RequestRegistry` | `request.py` | Tracking richieste attive |

| Pattern | Esempio | Uso |
|---------|---------|-----|
| `Asgi*` | `AsgiServer`, `AsgiApplication` | Componenti core ASGI |
| `*Middleware` | `AuthMiddleware` | Middleware ASGI |
| `*Request` | `HttpRequest` | Tipi di request |
| `*Response` | `Response` | Tipi di response |
| `*App` | `SwaggerApp`, `GenroApiApp` | App concrete |
| `*Store` | `MemorySessionStore` | Storage backends |
| `*Loader` | `ResourceLoader` | Caricatori risorse |
| `*Node` | `LocalStorageNode` | Nodi in strutture |

| Pattern | Esempio | Uso |
|---------|---------|-----|
| `on_*` | `on_init`, `on_startup` | Lifecycle hooks |
| `_configure_*` | `_configure_bearer` | Setup interno |
| `_auth_*` | `_auth_bearer` | Metodi auth per tipo |
| `load_*` | `load_resource` | Caricamento dati |
| `set_*` | `set_result`, `set_header` | Setters |
| `get_*` | `get_mount_names` | Getters |
| `has_*` | `has_mount`, `has_tag` | Predicati |

| Pattern | Esempio | Uso |
|---------|---------|-----|
| `_*` | `_scope`, `_headers` | Private/internal |
| `*_config` | `_auth_config` | Configurazione preprocessata |
| `*_dir` | `base_dir` | Directory paths |
| `*_path` | `resources_path` | File paths |
| `*_name` | `_mount_name` | Identificatori |

| Key | Tipo | Settato da | Descrizione |
|-----|------|------------|-------------|
| `type` | str | ASGI server | "http", "websocket", "lifespan" |
| `auth` | dict\|None | AuthMiddleware | Info autenticazione |
| `auth_tags` | list[str] | Da auth | Tags autorizzazione |
| `env_capabilities` | list[str] | Middleware | Capabilities ambiente |
| `_headers` | dict | headers_dict decorator | Headers preprocessati |
| `session` | Session | SessionMiddleware | Sessione (futuro) |

| Key | Tipo | Descrizione |
|-----|------|-------------|
| `server` | dict | Configurazione server (host, port, reload) |
| `middleware` | dict | Enable/disable middleware |
| `apps` | dict | App da montare |
| `openapi` | dict | Info OpenAPI globali |
| `main_app` | str | Nome app principale |

| Key | Tipo | Descrizione |
|-----|------|-------------|
| `*_middleware` | dict | Config specifica middleware |
| `auth_middleware` | dict | Config AuthMiddleware |
| `cors_middleware` | dict | Config CorsMiddleware |
| `session_middleware` | dict | Config SessionMiddleware (futuro) |

```yaml
apps:
  shop:                           # nome mount
    module: "main:ShopApp"        # modulo:classe
    connection_string: "..."      # kwargs per on_init
```

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `router_name` | str | Nome router (default: unico disponibile) |
| `auth_tags` | str | Tag richiesti (sintassi: `a\|b`, `a&b`) |
| `env_capabilities` | str | Capabilities richieste |
| `meta_mime_type` | str | MIME type override |
| `openapi_method` | str | Metodo HTTP per OpenAPI |

| Sintassi | Significato |
|----------|-------------|
| `"admin"` | Richiede tag admin |
| `"read\|write"` | Richiede read O write |
| `"admin&write"` | Richiede admin E write |
| `"(admin\|super)&write"` | (admin O super) E write |

App con prefisso `_` sono di sistema:

```yaml
apps:
  shop:          # App utente
  _swagger:      # App di sistema
  _genro_api:    # App di sistema
```

Endpoint con prefisso `_` sono di sistema:

| Endpoint | Descrizione |
|----------|-------------|
| `/_openapi/*` | Schema OpenAPI |
| `/_resource/*` | Caricamento risorse |
| `/_create_jwt` | Creazione JWT (stub) |
| `/_swagger/` | Swagger UI |
| `/_genro_api/` | API Explorer |

Nessuna differenza significativa. La terminologia è stata applicata consistentemente.

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/spa-manager/03-executor-manager.md

**Stato**: 📋 IDEE E SPUNTI
**Priorità**: P2 (Estensione worker pool)
**Dipendenze**: Worker Pool
**Data**: 2025-12-30

Il sistema worker è progettato per evolversi in 3 fasi, ognuna compatibile con la precedente:

```text
┌─────────────────────────────────────┐
│           AsgiServer                │
│                                     │
│  SpaManager                         │
│  └── Tutto eseguito inline          │
│      (stesso processo, stesso thread)│
│                                     │
└─────────────────────────────────────┘
```

- **Config**: `workers.enabled: false` (o assente)
- **Comportamento**: `delegate_to_worker()` esegue direttamente nel processo principale
- **Pro**: Zero overhead, semplice
- **Contro**: Computazioni pesanti bloccano l'event loop

```python
async def delegate_to_worker(self, identity: str, task: dict) -> Any:
    # Fase 1: esecuzione diretta
    if not self._worker_pool:
        return await execute_task(task)
    # ...
```

```text
┌─────────────────────────────────────┐
│           AsgiServer                │
│                                     │
│  SpaManager                         │
│  └── WorkerPool                     │
│      ├── Worker 0 (Process)         │
│      ├── Worker 1 (Process)         │
│      ├── Worker 2 (Process)         │
│      └── Worker 3 (Process)         │
│                                     │
│      Comunicazione: Queue (IPC)     │
│                                     │
└─────────────────────────────────────┘
```

- **Config**: `workers.enabled: true`, `workers.backend: local`
- **Comportamento**: Task eseguiti in processi separati via `multiprocessing.Queue`
- **Pro**: Non blocca event loop, usa più CPU
- **Contro**: Solo stessa macchina

```text
┌─────────────────────────────────────┐
│           AsgiServer                │
│                                     │
│  SpaManager                         │
│  └── WorkerPool (coordinator)       │
│      ├── worker-0 (local)           │
│      ├── worker-1 (local)           │
│      ├── worker-2 → remote          │
│      └── worker-3 → remote          │
│                                     │
└──────────────┬──────────────────────┘
               │
               ▼ NATS request/reply
     ┌─────────────────┐
     │   NATS Server   │
     └────────┬────────┘
              │
    ┌─────────┼─────────┐
    ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│Worker  │ │Worker  │ │Worker  │
│Container│ │Container│ │Container│
└────────┘ └────────┘ └────────┘
```

- **Config**: `workers.enabled: true`, `workers.backend: nats`
- **Comportamento**: Task inviati via NATS request/reply
- **Pro**: Scalabilità orizzontale, worker su macchine diverse
- **Contro**: Richiede NATS, latenza rete

```yaml
# Fase 1: Nessun worker
spa_manager:
  workers:
    enabled: false

# Fase 2: Worker locali
spa_manager:
  workers:
    enabled: true
    backend: local
    num_workers: 4
    affinity: user

# Fase 3: Worker distribuiti
spa_manager:
  workers:
    enabled: true
    backend: nats
    nats_url: nats://localhost:4222
    worker_subject: "spa.worker"
    num_workers: 4          # Worker locali
    remote_workers:         # Worker remoti registrati
      - worker-5
      - worker-6
    affinity: user
```

L'API `delegate_to_worker()` rimane identica in tutte le fasi:

```python
result = await spa_manager.delegate_to_worker(
    identity="mario.rossi",
    task={"type": "compute", "data": {...}}
)
```

Il backend cambia, il codice applicativo no.

Il server avrà un **ExecutorManager** che gestisce tutti i processi di esecuzione.

| Tipo | Descrizione | Affinità |
|------|-------------|----------|
| `inline` | Thread principale (event loop) | - |
| `local_free` | Processo locale, pool condiviso | Nessuna |
| `local_assigned` | Processo locale, assegnato a utente | Per utente |
| `remote_free` | Container/macchina remota, pool condiviso | Nessuna |
| `remote_assigned` | Container/macchina remota, assegnato a utente | Per utente |

```text
┌─────────────────────────────────────────────────────────────────┐
│                      ExecutorManager                             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Registry                                                 │    │
│  │                                                          │    │
│  │ Local Executors:                                        │    │
│  │ ├── inline (thread principale)                          │    │
│  │ ├── local_free_pool: [proc_0, proc_1, proc_2]          │    │
│  │ └── local_assigned: {user_hash → proc_id}              │    │
│  │                                                          │    │
│  │ Remote Executors:                                       │    │
│  │ ├── remote_free_pool: [worker_a, worker_b, worker_c]   │    │
│  │ └── remote_assigned: {user_hash → worker_id}           │    │
│  │                                                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
│  Routing:                                                        │
│  ├── exec_mode="inline"   → inline                              │
│  ├── exec_mode="any"      → local_free_pool (round robin)       │
│  └── exec_mode="assigned" → local_assigned o remote_assigned    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

Un middleware può assegnare l'executor di default per la request:

```python
class ExecutorMiddleware(BaseMiddleware):
    """Assegna executor default basato su user/config."""

async def __call__(self, scope, receive, send):
        identity = scope.get("auth", {}).get("identity")

if identity:
            # Utente autenticato → executor assegnato
            scope["default_executor"] = "assigned"
            scope["assigned_worker"] = self._get_worker_for_user(identity)
        else:
            # Anonimo → executor libero
            scope["default_executor"] = "any"

await self.app(scope, receive, send)
```

Ogni endpoint può sovrascrivere la modalità:

```python
@route("fast_query", exec_mode="inline")
async def fast_query(self) -> dict:
    """Sempre inline, ignora default."""
    return {"data": self.db.query()}

@route("heavy_compute", exec_mode="any")
async def heavy_compute(self, data: dict) -> dict:
    """Sempre su worker libero."""
    return {"result": compute(data)}

@route("user_report")  # exec_mode non specificato
async def user_report(self) -> dict:
    """Usa default da middleware (assigned per utenti auth)."""
    return {"report": generate_report()}

@route("user_cache", exec_mode="assigned")
async def user_cache(self) -> dict:
    """Forza worker assegnato (cache utente)."""
    return {"cached": get_user_cache()}
```

```python
class ExecutorManager:
    """Gestisce tutti gli executor (locali e remoti)."""

def __init__(self, server: AsgiServer):
        self._server = server
        self._local_free: list[LocalExecutor] = []
        self._local_assigned: dict[int, LocalExecutor] = {}  # hash → executor
        self._remote_free: list[RemoteExecutor] = []
        self._remote_assigned: dict[int, RemoteExecutor] = {}
        self._round_robin_idx = 0

async def execute(
        self,
        task: Callable,
        exec_mode: str = "inline",
        identity: str | None = None,
    ) -> Any:
        """Esegue task secondo la modalità specificata."""

if exec_mode == "inline":
            return await task()

elif exec_mode == "any":
            executor = self._get_free_executor()
            return await executor.run(task)

elif exec_mode == "assigned":
            if not identity:
                raise ValueError("exec_mode='assigned' requires identity")
            executor = self._get_assigned_executor(identity)
            return await executor.run(task)

def _get_free_executor(self) -> Executor:
        """Round-robin su executor liberi."""
        all_free = self._local_free + self._remote_free
        if not all_free:
            raise NoExecutorAvailable()
        executor = all_free[self._round_robin_idx % len(all_free)]
        self._round_robin_idx += 1
        return executor

def _get_assigned_executor(self, identity: str) -> Executor:
        """Executor assegnato per utente (hash-based)."""
        h = hash(identity)

# Prima cerca locale
        if self._local_assigned:
            idx = h % len(self._local_assigned)
            return list(self._local_assigned.values())[idx]

# Fallback remoto
        if self._remote_assigned:
            idx = h % len(self._remote_assigned)
            return list(self._remote_assigned.values())[idx]

# Gestione lifecycle
    async def register_local(self, executor: LocalExecutor, assigned: bool = False): ...
    async def register_remote(self, executor: RemoteExecutor, assigned: bool = False): ...
    async def unregister(self, executor_id: str): ...

# Stats
    def get_stats(self) -> dict:
        return {
            "local_free": len(self._local_free),
            "local_assigned": len(self._local_assigned),
            "remote_free": len(self._remote_free),
            "remote_assigned": len(self._remote_assigned),
        }
```

```yaml
executor_manager:
  local:
    free_pool_size: 2          # Processi locali liberi
    assigned_pool_size: 4      # Processi locali per utenti

remote:
    enabled: false             # Abilita remote workers
    backend: nats              # nats | http
    nats_url: nats://localhost:4222
    discovery: manual          # manual | auto
    workers:                   # Se manual
      - id: worker_a
        type: free
      - id: worker_b
        type: assigned

default_mode: inline         # Default se non specificato
```

```text
Request
   │
   ▼
┌──────────────────────────────┐
│ ExecutorMiddleware           │
│ - legge identity             │
│ - setta scope["default_exec"]│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Dispatcher                   │
│ - trova route                │
│ - legge exec_mode da route   │
│   (o usa default da scope)   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ ExecutorManager.execute()    │
│ - inline → esegui qui        │
│ - any → worker libero        │
│ - assigned → worker utente   │
└──────────────────────────────┘
```

1. **Serializzazione task**: Come passare callable a processo remoto? Pickle? JSON + registry?
2. **Timeout**: Cosa fare se worker non risponde?
3. **Retry**: Se worker fallisce, riprovare su altro?
4. **Health check**: Come sapere se un remote worker è vivo?
5. **Auto-scaling**: Aggiungere/rimuovere worker dinamicamente?

| Componente | Effort |
|------------|--------|
| ExecutorManager base | 4h |
| Evoluzione 3 fasi | 8h |
| Middleware integrazione | 2h |
| Tests | 6h |
| **Totale** | ~2.5 giorni |

**Ultimo aggiornamento**: 2025-12-30

## Source: plan_2025_12_29/spa-manager/04-storage-futures.md

**Stato**: 📋 IDEE E SPUNTI
**Priorità**: P3 (Sviluppi futuri)
**Data**: 2025-12-30

**Tutto in-memory** nel processo AsgiServer (non nei worker).

```text
10.000 utenti × 1 KB     = 10 MB (user data)
30.000 pagine × 1 KB     = 30 MB (page data)
10.000 sessions × 0.5 KB = 5 MB (session data)
10.000 connections × 0.5 KB = 5 MB (connection data)

50 MB in memoria è trascurabile per un processo server.

Se servono più istanze AsgiServer con load balancer:

```text
┌─────────────┐     ┌─────────────┐
│ Server A    │     │ Server B    │
│ SpaManager  │◄───►│ SpaManager  │
└──────┬──────┘     └──────┬──────┘
       │    NATS Pub/Sub   │
       └─────────┬─────────┘
                 │
           ┌─────┴─────┐
           │   NATS    │
           │  Pub/Sub  │
           └───────────┘
```

- Broadcast cross-instance (`send_to_user` raggiunge utente su altro server)
- Store rimane in-memory locale per ogni istanza

Se serve persistenza per recovery dopo crash o migrazione:

```python
class PersistenceBackend(Protocol):
    async def save(self, key: str, data: TreeDict) -> None: ...
    async def load(self, key: str) -> TreeDict | None: ...

# Implementazioni possibili:
# - FilePersistence (filesystem locale)
# - S3Persistence (object storage)
# - NatsKVPersistence (JetStream KV)
# - RedisPersistence
```

Se utente si riconnette a server diverso e deve recuperare session:

- Persistence backend per session data
- Oppure: JetStream KV per condividere stato

**Per ora**: Nessuna di queste è necessaria. In-memory puro è sufficiente.

I worker remoti possono supportare strategie di deployment avanzate:

```text
┌─────────────────────────────────────────────────────────────┐
│                    ExecutorManager                           │
│                                                              │
│  Remote Workers:                                             │
│  ┌───────────────────┐    ┌───────────────────┐            │
│  │ BLUE (current)    │    │ GREEN (new)       │            │
│  │ ├── worker_b1     │    │ ├── worker_g1     │            │
│  │ ├── worker_b2     │    │ ├── worker_g2     │            │
│  │ └── worker_b3     │    │ └── worker_g3     │            │
│  │                   │    │                   │            │
│  │ ◄── 100% traffic  │    │     0% traffic    │            │
│  └───────────────────┘    └───────────────────┘            │
│                                                              │
│  Switch istantaneo: BLUE ↔ GREEN                            │
└─────────────────────────────────────────────────────────────┘
```

- **Deploy nuova versione** su pool GREEN
- **Test** il pool GREEN
- **Switch** tutto il traffico da BLUE a GREEN
- **Rollback** istantaneo se problemi

```text
┌─────────────────────────────────────────────────────────────┐
│                    ExecutorManager                           │
│                                                              │
│  Remote Workers:                                             │
│  ┌───────────────────────────────────────┐                  │
│  │ STABLE (v1.0)                         │                  │
│  │ ├── worker_1                          │                  │
│  │ ├── worker_2      ◄── 90% traffic     │                  │
│  │ └── worker_3                          │                  │
│  └───────────────────────────────────────┘                  │
│                                                              │
│  ┌───────────────────────────────────────┐                  │
│  │ CANARY (v1.1)                         │                  │
│  │ └── worker_canary ◄── 10% traffic     │                  │
│  └───────────────────────────────────────┘                  │
│                                                              │
│  Routing: hash(request_id) % 100 < 10 → canary             │
└─────────────────────────────────────────────────────────────┘
```

- **Deploy nuova versione** su worker canary
- **Routing** percentuale di traffico (es. 10%)
- **Monitoraggio** errori/latenza sul canary
- **Graduale**: aumenta % se tutto ok, rollback se problemi

```yaml
executor_manager:
  remote:
    deployment_strategy: blue_green  # blue_green | canary | simple

# Blue-Green
    blue_green:
      active: blue                   # blue | green
      blue_workers: [worker_b1, worker_b2, worker_b3]
      green_workers: [worker_g1, worker_g2, worker_g3]

# Canary
    canary:
      enabled: true
      percentage: 10                 # % traffico su canary
      canary_workers: [worker_canary]
      stable_workers: [worker_1, worker_2, worker_3]
```

```python
class ExecutorManager:
    # Blue-Green
    async def switch_to_blue(self) -> None: ...
    async def switch_to_green(self) -> None: ...

# Canary
    async def set_canary_percentage(self, percentage: int) -> None: ...
    async def promote_canary(self) -> None:
        """Promuove canary a stable (100% traffico)."""
        ...
    async def rollback_canary(self) -> None:
        """Rimuove canary, torna a stable 100%."""
        ...
```

**Use case**: Deploy zero-downtime di nuove versioni dei worker senza interrompere il servizio.

**Ultimo aggiornamento**: 2025-12-30

## Source: plan_2025_12_29/spa-manager/01-core.md

**Stato**: 📋 DA PROGETTARE
**Priorità**: P1 (Necessario per app interattive)
**Dipendenze**: WebSocket, toolbox (uuid), treedict
**Data**: 2025-12-30

SpaManager gestisce la relazione **User → Connection → Session → Page** a livello server, permettendo comunicazione bidirezionale tra server e client (browser) via **WebSocket**.

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
              │  data: TreeDict    ←── Pagina master + suoi iframe
              │
              ├── Page "abc123" (master)
              │     data: TreeDict    ←── Singola pagina
              │
              ├── Page "def456" (iframe)
              │     data: TreeDict
              │
              └── Page "ghi789" (iframe)
                    data: TreeDict
```

**Nota**: La gerarchia iframe (parent/child) è gestita **lato client**. Il server vede pagine flat raggruppate per `session_id`.

| Livello | Scope | Persistenza | Esempio dati |
|---------|-------|-------------|--------------|
| **user_data** | Tutte le connessioni dell'utente | DB/Redis (futuro) | Preferenze, ruoli, permessi |
| **connection_data** | Tutte le sessioni di un browser | In-memory | Device info, last_activity |
| **session_data** | Tutte le pagine sotto un master | In-memory | Stato wizard, form parziali, contesto lavoro |
| **page_data** | Singola pagina/iframe | In-memory | Scroll position, selezione corrente |

```python
from treedict import TreeDict

@dataclass
class UserInfo:
    identity: str
    connections: set[str]     # connection_id
    data: TreeDict
    created_at: float

users: dict[str, UserInfo] = {
    "mario.rossi": UserInfo(...),
}
```

Mappa `connection_id` → ConnectionInfo.

```python
@dataclass
class ConnectionInfo:
    connection_id: str
    identity: str | None      # None se anonimo
    sessions: set[str]        # session_id
    data: TreeDict
    created_at: float
    last_activity: float
    user_agent: str | None
    remote_addr: str | None

connections: dict[str, ConnectionInfo] = {
    "conn_001": ConnectionInfo(...),
}
```

Mappa `session_id` → SessionInfo.

```python
@dataclass
class SessionInfo:
    session_id: str
    connection_id: str
    pages: set[str]           # page_id
    data: TreeDict
    created_at: float
    last_activity: float

sessions: dict[str, SessionInfo] = {
    "sess_001": SessionInfo(...),
}
```

```python
@dataclass
class PageInfo:
    page_id: str
    session_id: str
    websocket: WebSocket
    data: TreeDict
    created_at: float
    last_activity: float

pages: dict[str, PageInfo] = {
    "page_001": PageInfo(...),
}
```

Ogni livello usa TreeDict per i dati, permettendo accesso con path notation:

```python
from treedict import TreeDict

# Session data - path notation
session.data["wizard.step"] = 3
session.data["wizard.form.name"] = "Mario"
session.data["wizard.form.email"] = "mario@test.com"

# Lettura
step = session.data["wizard.step"]           # → 3
form = session.data["wizard.form"]           # → TreeDict con name, email

# Page data
page.data["editor.cursor.line"] = 42
page.data["editor.selection"] = {"start": 10, "end": 20}
```

**Futuro**: TreeDict sarà sostituito da Bag quando disponibile, con API compatibile.

```python
class SpaManager:
    """Gestisce User → Connection → Session → Page via WebSocket."""

__slots__ = (
        "_server",
        "_users",
        "_connections",
        "_sessions",
        "_pages",
        "_cleanup_interval",
        "_connection_timeout",
        "_session_timeout",
    )

def __init__(
        self,
        server: AsgiServer,
        cleanup_interval: float = 60.0,
        connection_timeout: float = 3600.0,   # 1 ora
        session_timeout: float = 1800.0,      # 30 min senza pagine
    ) -> None:
        self._server = server
        self._users: dict[str, UserInfo] = {}
        self._connections: dict[str, ConnectionInfo] = {}
        self._sessions: dict[str, SessionInfo] = {}
        self._pages: dict[str, PageInfo] = {}
        self._cleanup_interval = cleanup_interval
        self._connection_timeout = connection_timeout
        self._session_timeout = session_timeout
```

```python
    def register_user(self, identity: str) -> UserInfo:
        """Registra un utente (se non esiste)."""
        if identity in self._users:
            return self._users[identity]

info = UserInfo(
            identity=identity,
            connections=set(),
            data=TreeDict(),
            created_at=time.time(),
        )
        self._users[identity] = info
        return info

def register_connection(
        self,
        connection_id: str,
        identity: str | None = None,
        user_agent: str | None = None,
        remote_addr: str | None = None,
    ) -> ConnectionInfo:
        """Registra una nuova connessione (browser/device)."""
        now = time.time()
        info = ConnectionInfo(
            connection_id=connection_id,
            identity=identity,
            sessions=set(),
            data=TreeDict(),
            created_at=now,
            last_activity=now,
            user_agent=user_agent,
            remote_addr=remote_addr,
        )
        self._connections[connection_id] = info

if identity:
            user = self.register_user(identity)
            user.connections.add(connection_id)

def register_session(
        self,
        session_id: str,
        connection_id: str,
    ) -> SessionInfo:
        """Registra una nuova sessione (pagina master)."""
        if connection_id not in self._connections:
            raise ValueError(f"Connection {connection_id} not registered")

now = time.time()
        info = SessionInfo(
            session_id=session_id,
            connection_id=connection_id,
            pages=set(),
            data=TreeDict(),
            created_at=now,
            last_activity=now,
        )
        self._sessions[session_id] = info
        self._connections[connection_id].sessions.add(session_id)
        self._connections[connection_id].last_activity = now

def register_page(
        self,
        page_id: str,
        session_id: str,
        websocket: WebSocket,
    ) -> PageInfo:
        """Registra una nuova pagina con il suo WebSocket."""
        if session_id not in self._sessions:
            raise ValueError(f"Session {session_id} not registered")

now = time.time()
        info = PageInfo(
            page_id=page_id,
            session_id=session_id,
            websocket=websocket,
            data=TreeDict(),
            created_at=now,
            last_activity=now,
        )
        self._pages[page_id] = info
        self._sessions[session_id].pages.add(page_id)
        self._sessions[session_id].last_activity = now

```python
    async def unregister_page(self, page_id: str) -> None:
        """Rimuove una pagina e chiude il WebSocket."""
        if page_id not in self._pages:
            return

info = self._pages.pop(page_id)

try:
            await info.websocket.close()
        except Exception:
            pass

if info.session_id in self._sessions:
            self._sessions[info.session_id].pages.discard(page_id)

async def unregister_session(self, session_id: str) -> None:
        """Rimuove una sessione e tutte le sue pagine."""
        if session_id not in self._sessions:
            return

info = self._sessions.pop(session_id)

for page_id in list(info.pages):
            await self.unregister_page(page_id)

if info.connection_id in self._connections:
            self._connections[info.connection_id].sessions.discard(session_id)

async def unregister_connection(self, connection_id: str) -> None:
        """Rimuove una connessione e tutte le sue sessioni."""
        if connection_id not in self._connections:
            return

info = self._connections.pop(connection_id)

for session_id in list(info.sessions):
            await self.unregister_session(session_id)

if info.identity and info.identity in self._users:
            self._users[info.identity].connections.discard(connection_id)
            if not self._users[info.identity].connections:
                del self._users[info.identity]

async def unregister_user(self, identity: str) -> None:
        """Disconnette un utente da tutte le connessioni."""
        if identity not in self._users:
            return

for connection_id in list(self._users[identity].connections):
            await self.unregister_connection(connection_id)
```

```python
    async def send_to_page(self, page_id: str, message: dict) -> bool:
        """Invia messaggio a singola pagina. Ritorna True se inviato."""
        if page_id not in self._pages:
            return False

info = self._pages[page_id]
        try:
            await info.websocket.send_json(message)
            info.last_activity = time.time()
            return True
        except Exception:
            await self.unregister_page(page_id)
            return False

async def send_to_session(self, session_id: str, message: dict) -> int:
        """Invia messaggio a tutte le pagine di una sessione.
        Ritorna numero di pagine raggiunte."""
        if session_id not in self._sessions:
            return 0

count = 0
        for page_id in list(self._sessions[session_id].pages):
            if await self.send_to_page(page_id, message):
                count += 1
        return count

async def send_to_connection(self, connection_id: str, message: dict) -> int:
        """Invia messaggio a tutte le pagine di una connessione.
        Ritorna numero di pagine raggiunte."""
        if connection_id not in self._connections:
            return 0

count = 0
        for session_id in self._connections[connection_id].sessions:
            count += await self.send_to_session(session_id, message)
        return count

async def send_to_user(self, identity: str, message: dict) -> int:
        """Invia messaggio a tutte le pagine di un utente.
        Ritorna numero di pagine raggiunte."""
        if identity not in self._users:
            return 0

count = 0
        for connection_id in self._users[identity].connections:
            count += await self.send_to_connection(connection_id, message)
        return count

async def broadcast(self, message: dict) -> int:
        """Invia messaggio a tutte le pagine registrate.
        Ritorna numero di pagine raggiunte."""
        count = 0
        for page_id in list(self._pages.keys()):
            if await self.send_to_page(page_id, message):
                count += 1
        return count
```

```python
    # User data
    def get_user_data(self, identity: str) -> TreeDict | None:
        if identity not in self._users:
            return None
        return self._users[identity].data

def set_user_data(self, identity: str, path: str, value: Any) -> bool:
        if identity not in self._users:
            return False
        self._users[identity].data[path] = value
        return True

# Connection data
    def get_connection_data(self, connection_id: str) -> TreeDict | None:
        if connection_id not in self._connections:
            return None
        return self._connections[connection_id].data

def set_connection_data(self, connection_id: str, path: str, value: Any) -> bool:
        if connection_id not in self._connections:
            return False
        self._connections[connection_id].data[path] = value
        return True

# Session data
    def get_session_data(self, session_id: str) -> TreeDict | None:
        if session_id not in self._sessions:
            return None
        return self._sessions[session_id].data

def set_session_data(self, session_id: str, path: str, value: Any) -> bool:
        if session_id not in self._sessions:
            return False
        self._sessions[session_id].data[path] = value
        return True

# Page data
    def get_page_data(self, page_id: str) -> TreeDict | None:
        if page_id not in self._pages:
            return None
        return self._pages[page_id].data

def set_page_data(self, page_id: str, path: str, value: Any) -> bool:
        if page_id not in self._pages:
            return False
        self._pages[page_id].data[path] = value
        return True
```

```python
    def get_user_sessions(self, identity: str) -> list[str]:
        """Ritorna tutti i session_id di un utente."""
        if identity not in self._users:
            return []

sessions = []
        for connection_id in self._users[identity].connections:
            if connection_id in self._connections:
                sessions.extend(self._connections[connection_id].sessions)
        return sessions

def get_session_pages(self, session_id: str) -> list[str]:
        """Ritorna tutti i page_id di una sessione."""
        if session_id not in self._sessions:
            return []
        return list(self._sessions[session_id].pages)

def is_user_online(self, identity: str) -> bool:
        """True se l'utente ha almeno una pagina attiva."""
        if identity not in self._users:
            return False
        for conn_id in self._users[identity].connections:
            if conn_id in self._connections:
                for sess_id in self._connections[conn_id].sessions:
                    if sess_id in self._sessions and self._sessions[sess_id].pages:
                        return True
        return False

def get_online_users(self) -> list[str]:
        """Ritorna lista utenti online."""
        return [u for u in self._users.keys() if self.is_user_online(u)]

def get_counts(self) -> dict[str, int]:
        """Ritorna conteggi per ogni livello."""
        return {
            "users": len(self._users),
            "connections": len(self._connections),
            "sessions": len(self._sessions),
            "pages": len(self._pages),
        }
```

```python
    async def cleanup_stale(self) -> dict[str, int]:
        """Rimuove entità inattive. Ritorna conteggi rimossi."""
        now = time.time()
        removed = {"sessions": 0, "connections": 0, "users": 0}

# Cleanup sessioni senza pagine
        for session_id in list(self._sessions.keys()):
            info = self._sessions[session_id]
            if not info.pages and (now - info.last_activity) > self._session_timeout:
                await self.unregister_session(session_id)
                removed["sessions"] += 1

# Cleanup connessioni senza sessioni
        for connection_id in list(self._connections.keys()):
            info = self._connections[connection_id]
            if not info.sessions and (now - info.last_activity) > self._connection_timeout:
                await self.unregister_connection(connection_id)
                removed["connections"] += 1

```python
# server.py
class AsgiServer:
    def __init__(self, config_path: str) -> None:
        # ...
        self.spa_manager = SpaManager(self)

async def on_startup(self) -> None:
        asyncio.create_task(self._spa_cleanup_loop())

async def _spa_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(self.spa_manager._cleanup_interval)
            await self.spa_manager.cleanup_stale()
```

```text
Client                              Server
   │                                   │
   ├── WS connect ─────────────────►   │
   │   {connection_id,                 │
   │    session_id,                    │
   │    page_id}                       │
   │                                   ├── register_connection() [se nuovo]
   │                                   ├── register_session() [se nuovo]
   │                                   ├── register_page(websocket)
   │   ◄───────────────── WS accept    │
   │                                   │
   │   ◄═══════════════════════════►   │  (messaggi bidirezionali)
   │                                   │
   │── WS close ──────────────────►    │
   │                                   ├── unregister_page()
   │                                   │
```

```python
@route("_ws", websocket=True)
async def websocket_handler(self, websocket: WebSocket) -> None:
    """Handler WebSocket per SpaManager."""
    await websocket.accept()

# Ricevi messaggio iniziale
    init_msg = await websocket.receive_json()
    connection_id = init_msg.get("connection_id")
    session_id = init_msg.get("session_id")
    page_id = init_msg.get("page_id")

if not all([connection_id, session_id, page_id]):
        await websocket.close(code=4000, reason="Missing required IDs")
        return

# Identity da auth se presente
    identity = self.request.auth.get("identity") if self.request.auth else None

# Registra gerarchia
    if connection_id not in spa._connections:
        spa.register_connection(
            connection_id=connection_id,
            identity=identity,
            user_agent=self.request.headers.get("user-agent"),
            remote_addr=self.request.client.host,
        )

if session_id not in spa._sessions:
        spa.register_session(session_id, connection_id)

spa.register_page(page_id, session_id, websocket)

# Conferma registrazione
    await websocket.send_json({
        "type": "registered",
        "page_id": page_id,
        "session_id": session_id,
        "connection_id": connection_id,
    })

try:
        while True:
            message = await websocket.receive_json()
            await self._handle_page_message(page_id, session_id, message)
    except WebSocketDisconnect:
        pass
    finally:
        await spa.unregister_page(page_id)

async def _handle_page_message(self, page_id: str, session_id: str, message: dict) -> None:
    """Gestisce messaggi in arrivo da una pagina."""
    spa = self.server.spa_manager
    msg_type = message.get("type")

if msg_type == "ping":
        await spa.send_to_page(page_id, {"type": "pong"})

elif msg_type == "set_page_data":
        path = message.get("path")
        value = message.get("value")
        spa.set_page_data(page_id, path, value)

elif msg_type == "set_session_data":
        path = message.get("path")
        value = message.get("value")
        spa.set_session_data(session_id, path, value)

elif msg_type == "broadcast_session":
        # Invia a tutte le pagine della stessa sessione
        await spa.send_to_session(session_id, message.get("payload", {}))
```

Gli ID vengono generati usando `uuid` da toolbox:

```python
from toolbox import uuid

# Server-side (se necessario)
connection_id = uuid()
session_id = uuid()
page_id = uuid()
```

Il client genera gli ID e li invia al server nel messaggio iniziale WebSocket.

```yaml
spa_manager:
  enabled: true
  cleanup_interval: 60        # secondi
  connection_timeout: 3600    # 1 ora
  session_timeout: 1800       # 30 minuti senza pagine

websocket:
    path: /_ws
    ping_interval: 30
    ping_timeout: 10
```

```javascript
class SpaConnection {
    constructor(serverUrl) {
        this.serverUrl = serverUrl;
        this.connectionId = this._getOrCreateId('spa_connection_id');
        this.sessionId = this._generateId();  // Nuovo per ogni master page
        this.pageId = this._generateId();     // Nuovo per ogni pagina/iframe
        this.ws = null;
        this.handlers = {};
    }

_generateId() {
        return crypto.randomUUID();
    }

_getOrCreateId(key) {
        // Connection ID persistente in localStorage
        let id = localStorage.getItem(key);
        if (!id) {
            id = this._generateId();
            localStorage.setItem(key, id);
        }
        return id;
    }

async connect() {
        this.ws = new WebSocket(`${this.serverUrl}/_ws`);

this.ws.onopen = () => {
            this.ws.send(JSON.stringify({
                connection_id: this.connectionId,
                session_id: this.sessionId,
                page_id: this.pageId,
            }));
        };

this.ws.onmessage = (event) => {
            const message = JSON.parse(event.data);
            this._handleMessage(message);
        };

this.ws.onclose = () => {
            console.log('WebSocket closed');
            // Reconnect logic...
        };
    }

_handleMessage(message) {
        const handler = this.handlers[message.type];
        if (handler) {
            handler(message);
        }
    }

on(type, handler) {
        this.handlers[type] = handler;
    }

send(message) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(message));
        }
    }

setPageData(path, value) {
        this.send({ type: 'set_page_data', path, value });
    }

setSessionData(path, value) {
        this.send({ type: 'set_session_data', path, value });
    }

broadcastToSession(payload) {
        this.send({ type: 'broadcast_session', payload });
    }
}

// Uso
const spa = new SpaConnection('wss://myapp.com');
spa.on('notification', (msg) => alert(msg.message));
spa.on('registered', (msg) => console.log('Connected:', msg));
spa.connect();
```

```python
class MyApp(AsgiApplication):

@route("notify_user")
    async def notify_user(self, user_id: str, message: str) -> dict:
        """Notifica tutte le pagine di un utente."""
        count = await self.server.spa_manager.send_to_user(
            user_id,
            {"type": "notification", "message": message}
        )
        return {"notified_pages": count}

@route("notify_session")
    async def notify_session(self, session_id: str, message: str) -> dict:
        """Notifica tutte le pagine di una sessione."""
        count = await self.server.spa_manager.send_to_session(
            session_id,
            {"type": "notification", "message": message}
        )
        return {"notified_pages": count}

@route("broadcast")
    async def broadcast(self, message: str) -> dict:
        """Broadcast a tutti."""
        count = await self.server.spa_manager.broadcast(
            {"type": "announcement", "message": message}
        )
        return {"reached_pages": count}

@route("stats")
    def stats(self) -> dict:
        """Statistiche connessioni."""
        return self.server.spa_manager.get_counts()
```

| Componente | Effort |
| ---------- | ------ |
| SpaManager core (4 livelli) | 6h |
| Registri (User, Connection, Session, Page) | 3h |
| WebSocket handler | 3h |
| TreeDict integration | 2h |
| Cleanup task | 1h |
| Tests | 6h |
| Client JS esempio | 2h |
| **Totale** | ~3 giorni |

```text
toolbox (uuid, smartasync)
       │
       ▼
treedict (→ Bag in futuro)
       │
       ▼
WebSocket support (da implementare)
       │
       ▼
SpaManager
```

**Ultimo aggiornamento**: 2025-12-30

