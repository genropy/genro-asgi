## Source: plan_2025_12_29/13-swagger-app.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `applications/swagger/main.py` (80 linee)
**Risorse**: `applications/swagger/resources/index.html`
**Data**: 2025-12-29

Il documento originale proponeva:
- SwaggerApp come applicazione standalone per esplorare API OpenAPI
- Struttura `applications/swagger/` con risorse proprie
- Endpoints: `index()` per UI, `openapi()` per schema
- Welcome page con menu dropdown per API predefinite
- Auto-load via param `?url=...`
- Supporto CORS per cross-origin

```
applications/swagger/
├── __init__.py
├── main.py             # SwaggerApp class (80 linee)
├── config.yaml         # Config standalone per sviluppo
└── resources/
    └── index.html      # Swagger UI HTML
```

```python
"""SwaggerApp - OpenAPI/Swagger documentation app."""

from pathlib import Path
from genro_routes import route
from genro_asgi import AsgiApplication

class SwaggerApp(AsgiApplication):
    """Swagger UI and OpenAPI schema app.

Mount in config.yaml:
        apps:
          _swagger:
            module: "applications.swagger:SwaggerApp"
    """

openapi_info = {
        "title": "Swagger UI",
        "version": "1.0.0",
        "description": "OpenAPI/Swagger documentation interface",
    }

@route()
    def index(self):
        """Swagger UI page with toolbar."""
        return self.load_resource(name="index.html")

@route()
    def openapi(self, app: str = "") -> dict:
        """OpenAPI schema."""
        if not self.server:
            return {"openapi": "3.0.3", "info": {"title": "API", "version": "1.0.0"}, "paths": {}}

# Get auth_tags and capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.capabilities if request else ""

if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                paths = instance.api.nodes(
                    mode="openapi",
                    auth_tags=auth_tags,
                    env_capabilities=capabilities,
                ).get("paths", {})
                title = getattr(instance, "title", app)
                version = getattr(instance, "version", "1.0.0")
            else:
                paths = {}
                title = app
                version = "1.0.0"
        else:
            paths = self.server.router.nodes(
                mode="openapi",
                auth_tags=auth_tags,
                env_capabilities=capabilities,
            ).get("paths", {})
            title = "GenroASGI API"
            version = "1.0.0"

return {
            "openapi": "3.0.3",
            "info": {"title": title, "version": version},
            "paths": paths,
        }
```

| Path | Metodo | Descrizione |
|------|--------|-------------|
| `/_swagger/` | GET | Swagger UI HTML |
| `/_swagger/openapi` | GET | OpenAPI schema |
| `/_swagger/openapi?app=shop` | GET | OpenAPI per app specifica |

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `app` | str | "" | Nome app (vuoto = server router) |

L'app usa `self.load_resource()` per caricare risorse:

```python
@route()
def index(self):
    """Swagger UI page with toolbar."""
    return self.load_resource(name="index.html")
```

`load_resource()` è ereditato da `AsgiApplication` e usa il `ResourceLoader` del server con fallback gerarchico.

L'endpoint `openapi()` filtra gli endpoint visibili in base alle credenziali:

```python
# Get auth_tags and capabilities from current request
request = self.server.request
auth_tags = request.auth_tags if request else ""
capabilities = request.capabilities if request else ""

paths = self.server.router.nodes(
    mode="openapi",
    auth_tags=auth_tags,           # ← filtro per permessi
    env_capabilities=capabilities,  # ← filtro per capabilities
).get("paths", {})
```

Un utente senza tag `admin` non vedrà endpoint protetti con `auth_tags="admin"` nello schema OpenAPI.

```yaml
apps:
  shop:
    module: "shop:ShopApp"

_swagger:
    module: "applications.swagger:SwaggerApp"
```

```yaml
# applications/swagger/config.yaml
server:
  host: "127.0.0.1"
  port: 8001
  main_app: _swagger

middleware:
  auth: on
  cors: on

auth_middleware:
  bearer:
    reader_token:
      token: "tk_reader123"
      tags: "read"

apps:
  _swagger:
    module: "main:SwaggerApp"
```

```bash
cd applications/swagger
python -m genro_asgi serve . --port 8001
```

L'HTML in `resources/index.html` usa Swagger UI bundle da CDN:
- Non fa auto-load all'apertura (solo se `?url=` presente)
- Menu include "This server (/_openapi)" come prima opzione
- Supporta selezione da dropdown o campo libero

| Aspetto | SwaggerApp | GenroApiApp |
|---------|------------|-------------|
| UI | Swagger UI standard | Custom explorer |
| Tree view | No | Sì, gerarchico |
| Lazy loading | No | Sì |
| Doc singoli nodi | No | Sì via `getdoc()` |
| Tester | Swagger UI integrato | Custom |
| Uso tipico | Docs standard OpenAPI | Esplorazione avanzata |

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Welcome page | Menzionato | UI via index.html |
| Menu dropdown | Menzionato | Sì, nel HTML |
| Auto-load | `?url=...` | Supportato da Swagger UI |
| CORS | Menzionato | Via middleware CORS |
| App selection | Via `?app=xxx` | ✅ Implementato |
| auth_tags filtering | Non menzionato | ✅ Implementato |

L'app è testata manualmente. Test automatici per:
- Endpoint `index()` ritorna HTML
- Endpoint `openapi()` ritorna schema valido
- Filtraggio per app specifica

**Ultimo aggiornamento**: 2025-12-29

