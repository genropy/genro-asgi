# Block 00: AsgiServer & AsgiApplication

**Purpose**: Definire il fondamento architetturale - il singleton di processo su cui tutto si appoggia.
**Status**: 🔴 DA REVISIONARE

---

## Motivazione

Tutti i moduli già implementati (types, datastructures, exceptions, request, response) funzionano ma manca il **collante centrale**.

Il pattern collaudato (usato in WSGI per anni):
- Un **Server** che gestisce il processo, config, infrastruttura
- Un'**Application** ASGI che gestisce request/response

---

## Architettura

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

---

## Uso Tipico

```python
# main.py
from genro_asgi import AsgiServer

server = AsgiServer(config_path='server.ini')

if __name__ == '__main__':
    server.run()
```

---

## Config File (server.ini)

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

---

## Componenti Principali

### 1. EnvelopeRegistry

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

### 2. EnvelopeMiddleware (built-in, primo della catena)

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

### 3. Watchdog Task

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

### 4. Error Handler Centralizzato

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

### 5. Remote Debug Server (opzionale)

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

Flusso debug remoto:

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

---

## AsgiApplication

```python
class AsgiApplication:
    """Applicazione ASGI - gestisce routing e middleware."""

    def __init__(self, server: AsgiServer):
        self.server = server
        self.routes: list[Route] = []
        self.middleware: list[Middleware] = []

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """Entry point ASGI."""

        scope_type = scope['type']

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

---

## AsgiServer

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

---

## Struttura File

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

---

## Flusso Completo

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

---

## Decisioni Prese

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

---

## Componenti Aggiuntivi da Considerare

### Executors (da definire)

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

---

## Piano di Implementazione

### Fase 1: Core (Implementazione Immediata)

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

---

### Fase 2: Monitoring & Observability

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| Prometheus metrics | Counter, Histogram, export `/metrics` | P1 |
| Watchdog task | Rileva request piantate, log warning | P1 |
| Error handler | Log strutturato, metrics per errore | P1 |

---

### Fase 3: Routing & Middleware

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| SmartRoute integration | Routing avanzato da genro-libs | P1 |
| Middleware chain | Stack configurabile | P1 |
| CORS middleware | Headers CORS | P2 |
| Compression middleware | Gzip response | P2 |

---

### Fase 4: Executors & Concurrency

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| ThreadPoolExecutor | Task sync in thread pool | P2 |
| ProcessPoolExecutor | Task CPU-bound in process pool | P2 |
| `run_in_executor()` | API unificata | P2 |
| Graceful shutdown | Coordinamento shutdown completo | P2 |

---

### Fase 5: Development Tools

| Componente | Descrizione | Priorità |
|------------|-------------|----------|
| Remote debug server | pdb via WebSocket | P3 |
| Hot reload | Ricarica codice in sviluppo | P3 |
| Request inspector | Visualizza request in-flight | P3 |

---

## Prossimi Passi (Fase 1)

1. ✅ Decisioni prese
2. Docstring dettagliata per `server.py` (solo componenti Fase 1)
3. Test
4. Implementazione
5. Commit

---

## Dipendenze

**Fase 1** (zero dipendenze esterne):
- Solo stdlib Python
- uvicorn (già in uso)

**Fase 2+**:
- `prometheus_client` (metriche)
- `smartroute` (routing)

---

## File Fase 1

```
src/genro_asgi/
├── server.py             # AsgiServer (base)
├── application.py        # AsgiApplication
├── registry.py           # EnvelopeRegistry
├── middleware/
│   └── envelope.py       # EnvelopeMiddleware
└── ... (esistenti)
```
