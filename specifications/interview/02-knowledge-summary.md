# Riassunto conoscenze dalle specifiche legacy

**Data**: 2025-12-13
**Fonte**: Documenti in `specifications/legacy/`

---

## 1. Documenti analizzati

| File | Contenuto | Stato |
|------|-----------|-------|
| `architecture.md` | Multi-App Dispatcher, ServerBinder, Executors dettagliati | Molto dettagliato ma non allineato al codice |
| `configuration.md` | Formato TOML con sezioni server/static/apps | OBSOLETO - ora si usa YAML |
| `genro-asgi-complete-en.md` | Guida implementazione base (Request, Response, Router, Middleware) | Generico, non specifico per genro |
| `genro_asgi_execution.md` | ThreadPool, ProcessPool, TaskManager | NON IMPLEMENTATO |
| `wsx-protocol.md` | Protocollo WSX per RPC transport-agnostic | FUTURO - non implementato |
| `legacy-migration/` | Migrazione da WSGI/Tornado/gnrdaemon | Contesto storico |

---

## 2. Architettura descritta nei doc legacy

### 2.1 Multi-App Dispatcher (architecture.md)

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

### 2.2 Server-App Integration (architecture.md)

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

### 2.3 Executors (architecture.md)

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

### 2.4 Lifespan (architecture.md)

Ordine startup: Config → Logger → Executors → Sub-apps (mount order)
Ordine shutdown: Sub-apps (reverse) → Executors → Logger → Config

### 2.5 Configurazione (configuration.md) - OBSOLETO

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

---

## 3. WSX Protocol (wsx-protocol.md) - FUTURO

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

---

## 4. Execution System (genro_asgi_execution.md) - NON IMPLEMENTATO

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

---

## 5. Legacy Migration Context

Migrazione da:
- gnrdaemon (Pyro) → In-process PageRegistry + NATS
- Tornado (WebSocket) → Native ASGI WebSocket
- Gunicorn (WSGI) → Uvicorn (ASGI)
- Nginx routing → AsgiServer dispatcher

Fasi: 0 → 3 → 4 → 5 → 6 → 7 (1-2 deferred)

---

## 6. Codice attuale vs Specifiche

### Presente nel codice (`__init__.py` exports):

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

### Discrepanze identificate:

1. **Routing**: Doc descrive path-prefix mount, codice usa genro_routes.Router
2. **Config**: Doc dice TOML, codice usa YAML
3. **Executors**: Doc molto dettagliato, codice ha struttura base
4. **WSX Protocol**: Doc dettagliato, probabilmente non implementato
5. **AsgiServer**: Doc descrive mount(), codice usa attach_instance()

---

## 7. Dipendenze attuali (da codice)

```python
from genro_toolbox import SmartOptions
from genro_routes import RoutedClass, Router, route
```

- **genro-toolbox**: SmartOptions per configurazione
- **genro-routes**: Router, RoutedClass per routing
- **uvicorn**: ASGI server
- **pyyaml**: Config loading

---

## 8. Prossimi passi

1. Rispondere alle domande in `01-questions.md`
2. Consolidare le risposte verificate
3. Riscrivere `specifications/01-overview.md` basato su fatti verificati
4. Popolare `architecture/` con specifiche accurate
5. Popolare `guides/` con guide d'uso
