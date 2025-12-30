# 0001 - Server App Separation

**Stato**: 📋 PROPOSTA
**Data**: 2025-12-30
**Target**: `server.py`, nuovo `_server_app/`

---

## Problema Attuale

`AsgiServer` mescola due responsabilità:

1. **Orchestratore ASGI** (config, lifespan, dispatcher, request_registry)
2. **Endpoint di sistema** (index, _openapi, _resource, _create_jwt)

Inoltre non c'è distinzione tra app utente e app di sistema.

---

## Proposta

### Nuova Struttura Slots

```python
class AsgiServer(RoutingClass):
    __slots__ = (
        "config",
        "router",
        "dispatcher",
        "lifespan",
        "request_registry",
        "storage",
        "resource_loader",
        "app_loader",
        "openapi_info",
        # NUOVI
        "server_app",    # ServerApp - endpoint di sistema
        "sys_apps",      # dict[str, AsgiApplication] - app di sistema (monitor, admin)
        "apps",          # dict[str, AsgiApplication] - app utente
    )
```

### Separazione Responsabilità

| Slot | Contenuto | Mount Path | Esempio |
|------|-----------|------------|---------|
| `server_app` | Endpoint sistema | `_server` | `/_server/_openapi` |
| `sys_apps` | App di sistema | `_sys/<name>` | `/_sys/monitor/status` |
| `apps` | App utente | `<name>` | `/shop/products` |

**Note importanti:**

- `server_app` è **sempre presente** - creata automaticamente dal server
- `sys_apps` sono **opzionali** - configurabili in `config.yaml` sotto `sys_apps:`
- `apps` sono le app utente - configurabili in `config.yaml` sotto `apps:`

### Struttura Directory

```
src/genro_asgi/
├── _server_app/              # NUOVO - ServerApp package
│   ├── __init__.py           # Esporta ServerApp
│   ├── app.py                # class ServerApp(AsgiApplication)
│   └── resources/            # Risorse specifiche (HTML, etc.)
│       └── html/
│           └── default_index.html
├── server.py                 # AsgiServer (senza endpoint)
├── application.py            # AsgiApplication
└── ...
```

---

## Implementazione

### server.py (modificato)

```python
from genro_asgi._server_app import ServerApp

class AsgiServer(RoutingClass):
    def __init__(self, server_dir=None, ...):
        # ... config, router come ora ...

        # Server app - endpoint di sistema
        self.server_app = ServerApp(server=self)
        self.router.attach_instance(self.server_app, name="_server")

        # System apps container - montato come _sys/
        self.sys_apps: dict[str, RoutingClass] = {}
        # Creiamo un container RoutingClass per _sys
        self._sys_container = RoutingClass()
        self._sys_container.main = Router(self._sys_container, name="main")
        self.router.attach_instance(self._sys_container, name="_sys")

        for name, (cls, kwargs) in self.config.get_sys_app_specs().items():
            instance = cls(**kwargs)
            self.sys_apps[name] = instance
            self._sys_container.main.attach_instance(instance, name=name)

        # User apps - come ora
        self.apps: dict[str, RoutingClass] = {}
        for name, (cls, kwargs) in self.config.get_app_specs().items():
            instance = cls(**kwargs)
            self.apps[name] = instance
            self.router.attach_instance(instance, name=name)

        # Router default entry punta a server_app.index
        self.router.default_entry = "_server/index"
```

### _server_app/app.py (nuovo)

```python
from genro_asgi import AsgiApplication
from genro_asgi.exceptions import Redirect, HTTPNotFound
from genro_routes import route

class ServerApp(AsgiApplication):
    """System endpoints for AsgiServer."""

    def __init__(self, server):
        super().__init__()
        self._server = server  # Riferimento semantico

    @property
    def config(self):
        return self._server.config

    @property
    def main_app(self) -> str | None:
        """Return main app name: configured or single app."""
        configured = self.config["main_app"]
        if configured:
            return configured
        apps = self.config["apps"]
        return next(iter(apps)) if len(apps) == 1 else None

    @route(meta_mime_type="text/html")
    def index(self):
        """Default index page. Redirects to main_app if configured."""
        if self.main_app:
            raise Redirect(f"/{self.main_app}/")
        html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
        return html_path.read_text()

    @route(meta_mime_type="application/json")
    def _openapi(self, *args):
        """OpenAPI schema endpoint."""
        basepath = "/".join(args) if args else None
        paths = self._server.router.nodes(basepath=basepath, mode="openapi")
        return {
            "openapi": "3.1.0",
            "info": self._server.openapi_info,
            **paths,
        }

    @route(name="_resource")
    def load_resource(self, *args, name: str):
        """Load resource with hierarchical fallback."""
        result = self._server.resource_loader.load(*args, name=name)
        if result is None:
            raise HTTPNotFound(f"Resource not found: {name}")
        content, mime_type = result
        return self.result_wrapper(content, mime_type=mime_type)

    @route(auth_tags="superadmin&has_jwt")
    def _create_jwt(self, jwt_config=None, sub=None, tags=None, exp=None, **extra):
        """Create JWT token via HTTP endpoint."""
        if not jwt_config or not sub:
            return {"error": "jwt_config and sub are required"}
        # TODO: implement with genro-toolbox
        return {"error": "not implemented - waiting for genro-toolbox"}
```

---

## Config YAML

```yaml
server:
  host: "0.0.0.0"
  port: 8000

# System apps (opzionali) - stessa sintassi di apps
# Montate sotto /_sys/<name>/
sys_apps:
  monitor:
    module: "genro_asgi.contrib:MonitorApp"
  admin:
    module: "genro_asgi.contrib:AdminApp"
    secret_key: "admin-secret"

# User apps - come sempre
apps:
  shop:
    module: "main:ShopApp"
    db: "shop.db"
  api:
    module: "api:ApiApp"
```

**Nota:** `server_app` NON è configurabile in YAML - è sempre presente e creata internamente dal server.

---

## Routing Tree Risultante

```
AsgiServer.router (root)
│
├── shop/                     # apps["shop"] - app utente
│   └── products()           → /shop/products
│
├── office/                   # apps["office"] - app utente
│   └── documents()          → /office/documents
│
├── api/                      # apps["api"] - app utente
│   └── users()              → /api/users
│
├── _server/                  # server_app - endpoint di sistema
│   ├── index()              → /_server/index (o redirect)
│   ├── _openapi()           → /_server/_openapi
│   ├── _resource()          → /_server/_resource
│   └── _create_jwt()        → /_server/_create_jwt
│
└── _sys/                     # sys_apps container
    ├── monitor/             → /_sys/monitor/status
    ├── admin/               → /_sys/admin/users
    └── logs/                → /_sys/logs/tail
```

**Convenzione path:**
- App utente: `/shop/...`, `/office/...`, `/api/...`
- Server app: `/_server/...`
- System apps: `/_sys/<name>/...`

---

## Vantaggi

1. **Separazione netta**: Server orchestratore vs ServerApp endpoint
2. **Nessun breaking change**: Server resta RoutingClass
3. **Estensibilità**: sys_apps per aggiungere funzionalità di sistema
4. **Testabilità**: ServerApp testabile indipendentemente
5. **Risorse dedicate**: `_server_app/resources/` per asset di sistema
6. **Convenzione chiara**: `_` prefix per app di sistema

---

## Svantaggi

1. **Path più lunghi**: `/_server/_openapi` invece di `/_openapi`
2. **Un livello in più**: ServerApp intermediaria

---

## Backward Compatibility

Per mantenere i vecchi path:

```python
# In server.py - alias opzionali
@route("root")
def _openapi(self, *args):
    """Alias per backward compatibility."""
    return self.server_app._openapi(*args)
```

Oppure configurare redirect nel middleware.

---

## File da Modificare

| File | Azione |
|------|--------|
| `src/genro_asgi/_server_app/__init__.py` | Creare |
| `src/genro_asgi/_server_app/app.py` | Creare |
| `src/genro_asgi/_server_app/resources/html/default_index.html` | Spostare |
| `src/genro_asgi/server.py` | Rimuovere endpoint, aggiungere slots |
| `src/genro_asgi/server_config.py` | Aggiungere `get_sys_app_specs()` |
| `src/genro_asgi/__init__.py` | Esportare ServerApp |
| `tests/` | Aggiornare test |

---

## Piano di Implementazione

1. [ ] Creare `_server_app/` con ServerApp
2. [ ] Spostare `resources/html/default_index.html`
3. [ ] Spostare endpoint da server.py a ServerApp
4. [ ] Aggiungere slots `server_app`, `sys_apps`
5. [ ] Aggiungere `get_sys_app_specs()` a ServerConfig
6. [ ] Aggiornare test
7. [ ] Documentare in specifications

---

## Decisione

**Stato**: 📋 PROPOSTA - In attesa di approvazione

---

**Ultimo aggiornamento**: 2025-12-30
