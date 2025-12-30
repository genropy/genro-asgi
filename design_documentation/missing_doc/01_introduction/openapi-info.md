## Source: plan_2025_12_29/14-openapi-info.md

**Stato**: ⚠️ PARZIALMENTE IMPLEMENTATO
**File**: `src/genro_asgi/server.py`, `src/genro_asgi/application.py`
**Data**: 2025-12-29

Il documento originale proponeva:
- `openapi_info` come dict su ogni RoutingClass
- Merge automatico dalla catena parent (child eredita campi mancanti)
- Property `self.routing.openapi_info` su `_RoutingProxy`
- Server popola `openapi_info` da config.yaml
- Endpoint `_openapi/shop` → info di Shop con merge dal parent

```python
# application.py
class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer."""

openapi_info: ClassVar[dict[str, Any]] = {}
```

Le app definiscono le proprie info:

```python
class ShopApp(AsgiApplication):
    openapi_info = {
        "title": "Shop API",
        "version": "1.0.0",
        "description": "E-commerce API"
    }
```

```python
# server.py
class AsgiServer(RoutingClass):
    def __init__(self, ...):
        # ...
        # OpenAPI info from config (plain dict via property)
        self.openapi_info: dict[str, Any] = self.config.openapi
```

```yaml
openapi:
  title: "Demo Shop API"
  version: "1.0.0"
  description: "A sample e-commerce API"
  contact:
    name: "Genropy Team"
```

```python
# server.py
@route("root", meta_mime_type="application/json")
def _openapi(self, *args: str) -> dict[str, Any]:
    """OpenAPI schema endpoint."""
    basepath = "/".join(args) if args else None
    paths = self.router.nodes(basepath=basepath, mode="openapi")
    return {
        "openapi": "3.1.0",
        "info": self.openapi_info,  # ← usa info del server
        **paths,
    }
```

Il piano proponeva merge automatico child → parent:

```python
# PIANO (NON implementato)
@property
def openapi_info(self) -> dict:
    """OpenAPI info con merge dalla catena parent."""
    result = {"title": "API", "version": "0.1.0"}
    chain: list[dict] = []
    current: RoutingClass | None = self._owner
    while current is not None:
        info = getattr(current, 'openapi_info', None)
        if info:
            chain.append(info)
        current = getattr(current, '_routing_parent', None)
    for info in reversed(chain):
        result.update(info)
    return result
```

Attualmente ogni livello usa solo le proprie info, senza merge.

Il piano proponeva:
- `_openapi` → info del Server
- `_openapi/shop` → info di Shop (con merge)
- `_openapi/shop/article` → info di Article (con merge)

Attualmente `_openapi` con args filtra solo i paths, non cambia le info.

Il metodo per risolvere un basepath a una RoutingClass non è implementato.

```
GET /_openapi
    │
    ▼
AsgiServer._openapi()
    │
    ├── basepath = None
    ├── paths = self.router.nodes(mode="openapi")
    └── return {"openapi": "3.1.0", "info": self.openapi_info, **paths}

GET /_openapi/shop
    │
    ▼
AsgiServer._openapi("shop")
    │
    ├── basepath = "shop"
    ├── paths = self.router.nodes(basepath="shop", mode="openapi")
    └── return {"openapi": "3.1.0", "info": self.openapi_info, **paths}
                                           ↑
                                    Info del SERVER, non di Shop!
```

Le app usano `openapi_info` per la splash page di default:

```python
# application.py
@route(meta_mime_type="text/html")
def index(self) -> str:
    """Return HTML splash page. Override for custom index."""
    info = getattr(self, "openapi_info", {})
    title = info.get("title", self.__class__.__name__)
    version = info.get("version", "")
    description = info.get("description", "")
    # ... genera HTML ...
```

E in GenroApiApp/SwaggerApp per l'endpoint `openapi()`:

```python
# swagger/main.py
if app and app in self.server.apps:
    instance = self.server.apps[app]
    title = getattr(instance, "title", app)  # NON usa openapi_info!
    version = getattr(instance, "version", "1.0.0")
```

**Nota**: SwaggerApp non usa `openapi_info` ma cerca `title`/`version` direttamente.

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Demo Shop API",
    "version": "1.0.0",
    "description": "A sample e-commerce API"
  },
  "paths": {
    "/shop/products": {...},
    "/shop/orders": {...}
  }
}
```

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Shop API",           // ← da ShopApp.openapi_info
    "version": "1.0.0",            // ← ereditato
    "description": "E-commerce API", // ← da ShopApp.openapi_info
    "contact": {...}               // ← ereditato da server
  },
  "paths": {...}
}
```

```yaml
openapi:
  title: "Demo Shop API"
  version: "1.0.0"
  description: "A sample e-commerce API"
  contact:
    name: "Genropy Team"
    email: "info@genropy.org"
  license:
    name: "Apache 2.0"
  servers:
    - url: "https://api.example.com"
      description: "Production server"
```

Tutti questi campi vengono passati a `self.openapi_info` nel server.

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| `openapi_info` su RoutingClass | ✅ Su AsgiApplication | ✅ Class variable |
| `openapi_info` da config.yaml | ✅ Su AsgiServer | ✅ `self.config.openapi` |
| Merge gerarchico | Proposto | ❌ Non implementato |
| `_openapi/{basepath}` con info diverse | Proposto | ❌ Usa sempre info server |
| `_RoutingProxy.openapi_info` | Proposto | ❌ Non implementato |
| `_resolve_routing_class` | Proposto | ❌ Non implementato |

1. [ ] Implementare `openapi_info` property in `_RoutingProxy` (genro-routes)
2. [ ] Implementare `_resolve_routing_class(basepath)` nel server
3. [ ] Aggiornare `_openapi()` per usare info del target, non del server
4. [ ] Aggiornare SwaggerApp per usare `openapi_info` invece di `title`/`version`
5. [ ] Test per merge gerarchico

**Ultimo aggiornamento**: 2025-12-29

