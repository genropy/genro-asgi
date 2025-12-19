# genro-routes - Sintesi per genro-asgi

**Status**: 🟢 Verificato da README ufficiale
**Versione**: 0.9.0 (Beta)
**Documentazione**: https://genro-routes.readthedocs.io

---

## Cos'è genro-routes

**Instance-scoped routing engine** - espone metodi Python come "endpoint" senza blueprint globali o registri condivisi. Ogni istanza crea i propri router con stato isolato.

---

## Caratteristiche Chiave

1. **Instance-scoped routers** - `Router(self, ...)` crea router con stato isolato per istanza
2. **@route decorator** - Registra metodi con nomi espliciti e metadata
3. **Gerarchie semplici** - `attach_instance(child, name="alias")` connette RoutingClass
4. **Plugin pipeline** - `BasePlugin` con hook `on_decore`/`wrap_handler`, ereditati dai parent
5. **Configurazione runtime** - `routedclass.configure()` per override globali o per-handler
6. **Extra opzionali** - Plugin logging, pydantic; core con dipendenze minime

---

## Concetti Core

| Concetto | Descrizione |
|----------|-------------|
| **Router** | Runtime router bound a un oggetto: `Router(self, name="api")` |
| **@route("name")** | Decorator che marca metodi per un router specifico |
| **RoutingClass** | Mixin che traccia router per istanza |
| **BasePlugin** | Base per plugin con hook `on_decore` e `wrap_handler` |
| **routedclass** | Proxy per gestire router/plugin senza inquinare il namespace |

---

## Esempio Base

```python
from genro_routes import RoutingClass, Router, route

class OrdersAPI(RoutingClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="orders")

    @route("orders")
    def list(self):
        return ["order-1", "order-2"]

    @route("orders")
    def retrieve(self, ident: str):
        return f"{self.label}:{ident}"

orders = OrdersAPI("acme")
orders.api.get("list")()          # ["order-1", "order-2"]
orders.api.get("retrieve")("42")  # "acme:42"
```

---

## Routing Gerarchico

```python
class UsersAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

    @route("api")
    def list(self):
        return ["alice", "bob"]

class Application(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.users = UsersAPI()
        self.api.attach_instance(self.users, name="users")

app = Application()
app.api.get("users/list")()  # ["alice", "bob"]
```

---

## Plugin System

Plugin = middleware a livello di singolo metodo, configurabili a runtime.

### Caratteristiche

- **Per-instance state**: ogni router ha istanze plugin indipendenti (no stato globale)
- **Due hook principali**: `on_decore()` (registrazione), `wrap_handler()` (esecuzione)
- **Ereditarietà**: plugin dei parent si applicano ai child router
- **Composizione**: più plugin lavorano insieme automaticamente

### Plugin Built-in

- **LoggingPlugin** (`"logging"`) - logging chiamate
- **PydanticPlugin** (`"pydantic"`) - validazione input/output con modelli Pydantic

### Attivazione

```python
# Fluent API
self.api = Router(self, name="api").plug("logging").plug("pydantic")

# Con configurazione iniziale
self.api = Router(self, name="api").plug("logging", level="debug")
```

### Hook Disponibili

| Hook | Quando | Scopo |
|------|--------|-------|
| `configure()` | Init e runtime | Schema configurazione |
| `on_decore()` | Registrazione handler | Metadata, validazione signature |
| `wrap_handler()` | Invocazione handler | Middleware (logging, auth, cache) |
| `allow_entry()` | `members()` | Filtra handler visibili |
| `entry_metadata()` | `members()` | Aggiunge metadata plugin |

### Creazione Plugin Custom

```python
from genro_routes.plugins._base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    plugin_code = "my_plugin"           # Identificatore unico
    plugin_description = "Description"  # Descrizione

    def __init__(self, router, **config):
        self.my_state = []              # Stato per-istanza
        super().__init__(router, **config)

    def configure(self, enabled: bool = True, level: str = "info"):
        """Schema configurazione (body può essere vuoto)."""
        pass

    def wrap_handler(self, router, entry, call_next):
        def wrapper(*args, **kwargs):
            # Before
            result = call_next(*args, **kwargs)
            # After
            return result
        return wrapper

# Registrazione globale
Router.register_plugin(MyPlugin)
```

### Configurazione Runtime

Sintassi: `<router>:<plugin>/<selector>`

```python
# Globale - tutti gli handler
svc.routedclass.configure("api:logging/_all_", threshold=10)

# Per handler specifico
svc.routedclass.configure("api:logging/foo", enabled=False)

# Glob pattern
svc.routedclass.configure("api:logging/admin_*", level="debug")

# Batch update (JSON-friendly)
svc.routedclass.configure([
    {"target": "api:logging/_all_", "enabled": True},
    {"target": "api:logging/foo", "limit": 5},
])

# Introspection
info = svc.routedclass.configure("?")  # Albero completo
```

### Accesso Diretto al Plugin

```python
# Via attributo router
svc.api.logging.configure(level="debug")
cfg = svc.api.logging.configuration("handler_name")
```

---

## Limitazioni

- **Solo metodi di istanza** - no static/class method, no funzioni libere
- **Plugin system minimale** - intenzionalmente semplice

---

## Uso in genro-asgi

```python
class AsgiServer(RoutingClass):
    def __init__(self):
        self.router = Router(self, name="root")

    @route("root")
    def index(self):
        return HTMLResponse(...)

# Il Dispatcher converte path HTTP in selettore:
# /shop/products → selector = "shop/products" → router.get("shop/products")
```

Le app montate con `attach_instance(app, name="shop")` diventano sotto-alberi del router.

---

## Struttura Repository

```
genro-routes/
├── src/genro_routes/
│   ├── core/               # Router, decorators, RoutingClass
│   │   ├── router.py
│   │   ├── decorators.py
│   │   └── routed.py
│   └── plugins/            # LoggingPlugin, PydanticPlugin
├── tests/                  # 99% coverage, 100 tests
├── docs/                   # Sphinx documentation
└── examples/
```

---

## Dipendenze

- `genro-toolbox>=0.1.0`
- `pydantic>=2.0.0`

---

## Link

- **Documentazione**: https://genro-routes.readthedocs.io
- **Repository**: https://github.com/genropy/genro-routes
- **Quick Start**: docs/quickstart.md
- **FAQ**: docs/FAQ.md
