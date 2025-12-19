# Analisi SmartPublisher - Concetti da Integrare in genro-asgi

**Data**: 2025-12-03
**Stato**: 🔴 DA REVISIONARE

---

## 1. Cos'è SmartPublisher

SmartPublisher è un **coordinatore di applicazioni** basato su SmartRoute che:

1. **Registra applicazioni** dinamicamente a runtime
2. **Espone interfacce multiple** (CLI, HTTP) con lo stesso codice
3. **Gestisce lo stato** (persistenza, autosave, snapshot)
4. **Separa trasporti da business logic**

### Pattern Chiave

```
RoutingClass (business logic) → Publisher (coordinatore) → Channels (trasporti)
```

---

## 2. Architettura SmartPublisher

### 2.1 Publisher (Coordinatore Centrale)

```python
class Publisher(RoutingClass):
    def __init__(self):
        # Router principale per comandi business/system
        self.api = Router(self, name="api").plug("pydantic").plug("publish")

        # Manager per applicazioni
        self.app_manager = AppManager(self)

        # Registry per canali (CLI/HTTP)
        self.chan_registry = ChanRegistry(self)

        # State manager (persistenza)
        self.state_manager = StateManager(self)

        # Attach sub-managers come children del router
        self.api.attach_instance(self.chan_registry, name="channel")
        self.api.attach_instance(self.app_manager, name="apps")
```

**Responsabilità**:
- Orchestrazione generale
- Comandi root (`/add`, `/serve`, `/start`)
- Delega a sub-manager per funzionalità specifiche

### 2.2 AppManager (Gestione Applicazioni)

```python
class AppManager(RoutingClass):
    def __init__(self, publisher):
        self.publisher = publisher
        self.api = Router(self, name="api").plug("pydantic")
        self.applications: dict[str, Any] = {}      # app instances
        self.apps_restart_dict: dict[str, dict] = {} # restart metadata

    def add(self, name, spec, app_args, app_kwargs):
        # 1. Parse spec (file_path:ClassName)
        # 2. Dynamic import
        # 3. Instantiate
        # 4. Register + attach to router

    def remove(self, name):
        # Detach from router + cleanup

    def snapshot(self):
        # Return restart info for persistence
```

**Responsabilità**:
- Caricamento dinamico classi da file Python
- Registro applicazioni in memoria
- Mount/unmount dal router
- Metadata per restart

### 2.3 ChanRegistry (Gestione Canali)

```python
class ChanRegistry(RoutingClass):
    def __init__(self, publisher):
        self.publisher = publisher
        self.api = Router(self, name="api").plug("pydantic")
        self._channels = self._register_channels()  # {"cli": CLIChannel, "http": HTTPChannel}

    def get(self, name) -> BaseChannel:
        return self._channels[name]

    def run(self, name, port=None, **options):
        # Start a channel
```

**Responsabilità**:
- Autodiscovery canali disponibili
- Factory per canali
- Run/stop canali

### 2.4 BaseChannel (Astrazione Trasporto)

```python
class BaseChannel(RoutingClass):
    CHANNEL_CODE: str = ""  # "CLI", "HTTP"

    def __init__(self, registry):
        self.registry = registry

    @property
    def publisher(self):
        return self.registry.publisher

    def run(self, **kwargs):
        raise NotImplementedError

    def members(self):
        # Filtra per channel code
        return self.publisher.api.members(channel=self.CHANNEL_CODE)
```

**Responsabilità**:
- Accesso filtrato all'API (per channel)
- Lifecycle canale (run/stop)
- Helper per lookup handler

### 2.5 Canali Concreti

**CLIChannel**:
- Parse argv
- Dispatch a router
- Output formatting
- Completion suggestions

**PublisherHTTP**:
- Wraps FastAPI
- Dynamic dispatch (`/{path:path}` → router)
- System endpoints (`/system/health`, `/system/openapi`)
- OpenAPI generation da members()

---

## 3. Concetti Chiave da Importare in genro-asgi

### 3.1 Channel Abstraction

SmartPublisher separa nettamente:
- **Business Logic** (RoutingClass con `@route`)
- **Trasporto** (Channel che espone il router)

**Per genro-asgi**:
- Il server deve supportare più canali (HTTP, WebSocket, NATS)
- Ogni canale traduce il suo protocollo in chiamate al router

### 3.2 Channel Registry

Pattern: registro centrale dei canali disponibili.

```python
# SmartPublisher
registry.get("http").run(port=8000)
registry.get("cli").run()
```

**Per genro-asgi**:
```python
server.channels.get("http")  # uvicorn
server.channels.get("ws")    # websocket handler
server.channels.get("nats")  # nats client
```

### 3.3 Dynamic Dispatch

SmartPublisher usa `/{path:path}` per catturare tutto e fare dispatch dinamico al router:

```python
@app.api_route("/{full_path:path}")
async def dynamic_dispatch(full_path: str, request: Request):
    segments = full_path.split("/")
    method_callable = publisher.api.get(".".join(segments))
    result = method_callable(**payload)
```

**Per genro-asgi**: Già pianificato con `router.dispatch(path)`

### 3.4 Members Tree per Introspection

SmartPublisher usa `router.members()` per generare:
- Help CLI
- OpenAPI schema
- Completion suggestions

**Per genro-asgi**: Servira per:
- Auto-generare OpenAPI
- Debug/introspection endpoint

### 3.5 Channel Filtering (Metadata)

```python
@route("api", metadata={"channel_allowed": ["CLI"]})
def start(self):
    # Solo CLI può chiamare questo metodo
```

**Per genro-asgi**: Utile per:
- Metodi solo HTTP
- Metodi solo WebSocket
- Metodi solo internal (NATS)

### 3.6 System Endpoints vs Business Endpoints

SmartPublisher separa:
- `/system/*` - health, metrics, openapi (trasporto-specifici)
- `/*` - business logic (agnostici al trasporto)

**Per genro-asgi**:
```python
# System (gestiti dal server)
/system/health
/system/metrics
/system/openapi

# Business (dispatch a RoutingClass)
/shop/products
/accounting/invoices
```

---

## 4. Differenze Chiave SmartPublisher vs genro-asgi

| Aspetto | SmartPublisher | genro-asgi |
|---------|---------------|------------|
| **Base** | FastAPI (opzionale) | ASGI puro |
| **Router** | SmartRoute | SmartRoute |
| **HTTP Server** | Uvicorn via FastAPI | Uvicorn diretto |
| **WebSocket** | Non supportato direttamente | WSX nativo |
| **CLI** | Integrato | Non previsto |
| **Dynamic Loading** | Sì (SourceFileLoader) | No (app montate esplicitamente) |
| **State Persistence** | Sì (JSON snapshot) | No (stateless) |
| **Focus** | Multi-interface publishing | High-perf ASGI server |

---

## 5. Proposta di Integrazione

### 5.1 Cosa NON copiare

- **CLI Channel**: genro-asgi è un server, non ha CLI
- **Dynamic Loading**: le app sono montate esplicitamente
- **State Persistence**: il server è stateless
- **FastAPI wrapper**: usiamo ASGI puro

### 5.2 Cosa adottare

1. **Channel Abstraction**
   ```python
   class BaseChannel:
       CHANNEL_CODE: str
       def __init__(self, server): ...
       def run(self, **kwargs): ...
   ```

2. **Channel Registry** (semplificato)
   ```python
   server.channels = {
       "http": HttpChannel(server),
       "ws": WsChannel(server),
   }
   ```

3. **System Endpoints**
   ```python
   # Gestiti dal server direttamente
   GET /system/health → {"status": "healthy"}
   GET /system/openapi → auto-generated spec
   GET /system/members → router.members()
   ```

4. **Channel Metadata per Filtering**
   ```python
   @route("api", metadata={"channels": ["HTTP", "WS"]})
   def my_method(self): ...
   ```

5. **Members-based Introspection**
   - OpenAPI generation da `router.members()`
   - Debug endpoint per vedere struttura API

### 5.3 Architettura Proposta genro-asgi

```
AsgiServer
├── router: Router           # SmartRoute per dispatch
├── channels: dict           # Registry canali
│   ├── http: HttpChannel    # ASGI HTTP handling
│   ├── ws: WsChannel        # ASGI WebSocket handling
│   └── nats: NatsChannel    # NATS client (futuro)
├── apps: dict[str, RoutingClass]  # App montate
├── middleware: list         # Middleware chain
└── system_routes            # /system/* endpoints
```

**Flow HTTP**:
```
uvicorn → AsgiServer.__call__
  → scope["type"] == "http"
  → path.startswith("/system/") ? handle_system() : dispatch_to_router()
```

**Flow WebSocket**:
```
uvicorn → AsgiServer.__call__
  → scope["type"] == "websocket"
  → WsChannel.handle(scope, receive, send)
```

---

## 6. Prossimi Passi

1. **Definire BaseChannel** per genro-asgi (senza dipendenza da SmartPublisher)
2. **Implementare HttpChannel** che fa dispatch al router
3. **Aggiungere system endpoints** (/health, /openapi, /members)
4. **Implementare WsChannel** per WebSocket
5. **Opzionale**: NatsChannel per NATS integration

---

## 7. Domande Aperte

1. **genro-asgi dovrebbe dipendere da smartroute?**
   - Pro: routing già implementato
   - Contro: dipendenza esterna

2. **Channels come classi separate o metodi del server?**
   - SmartPublisher: classi separate
   - Alternativa: metodi del server (`server.handle_http()`, `server.handle_ws()`)

3. **System endpoints hardcoded o configurabili?**
   - SmartPublisher: hardcoded in http_channel
   - Alternativa: configurabili via mount speciale

---

**File correlati**:
- [temp/restart.md](restart.md) - Stato precedente
- [temp/server-design.md](server-design.md) - Design server
