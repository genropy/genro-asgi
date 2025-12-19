# AsgiPublisher - Memorandum per Sviluppo Futuro

**Data**: 2025-12-03
**Stato**: 📝 MEMO (non implementare ora)

---

## Obiettivo

Creare **AsgiPublisher** come estensione di **AsgiServer** con funzionalità di publishing ispirate a SmartPublisher.

---

## Gerarchia

```
AsgiServer (base - implementare ora)
    │
    └── AsgiPublisher (estensione - futuro)
```

---

## AsgiServer (Base) - Requisiti per Compatibilità

Per permettere ad AsgiPublisher di estendere AsgiServer, la base deve:

### 1. Struttura Estendibile

```python
class AsgiServer:
    def __init__(self):
        self.apps: dict[str, RoutingClass] = {}
        self.router: Router = Router(self)
        self._middleware: list = []

        # Hook per estensioni
        self._configure()

    def _configure(self):
        """Override point per sottoclassi."""
        pass
```

### 2. Mount Semplice ma Completo

```python
def mount(self, path: str, app: RoutingClass):
    """Monta app. AsgiPublisher potrà aggiungere logica extra."""
    self.apps[path] = app
    self.router.attach_instance(app, name=path.strip("/"))
```

### 3. Dispatch Separato dal __call__

```python
async def __call__(self, scope, receive, send):
    if scope["type"] == "lifespan":
        await self._handle_lifespan(scope, receive, send)
    elif scope["type"] == "http":
        await self._handle_http(scope, receive, send)
    elif scope["type"] == "websocket":
        await self._handle_websocket(scope, receive, send)

async def _handle_http(self, scope, receive, send):
    """Override point - AsgiPublisher aggiungerà system routes."""
    await self._dispatch_router(scope, receive, send)
```

### 4. NO Logica Hardcoded per System Routes

AsgiServer NON deve avere `/system/*` hardcoded. Sarà AsgiPublisher ad aggiungerli.

---

## AsgiPublisher (Futuro) - Features Pianificate

### 1. Channel Registry

```python
class AsgiPublisher(AsgiServer):
    def _configure(self):
        self.channels = {
            "http": HttpChannel(self),
            "ws": WsChannel(self),
            "cli": CliChannel(self),
        }
```

### 2. System Endpoints

```python
# Gestiti in _handle_http override
/system/health    → {"status": "healthy", "apps": [...]}
/system/openapi   → auto-generated OpenAPI spec
/system/members   → router.members() tree
/system/metrics   → basic metrics
```

### 3. CLI Channel

```python
class CliChannel:
    def run(self, args=None):
        # Parse argv
        # Dispatch to router
        # Format output
```

### 4. OpenAPI Generation

```python
def _build_openapi(self) -> dict:
    """Genera OpenAPI da router.members()"""
    tree = self.router.members()
    # ... trasforma in OpenAPI spec
```

### 5. Channel Filtering

```python
@route("api", metadata={"channels": ["HTTP"]})
def http_only_method(self): ...
```

---

## Checklist Compatibilità AsgiServer

Prima di considerare AsgiServer "completo", verificare:

- [ ] `_configure()` hook chiamato da `__init__`
- [ ] `_handle_http()` separato e sovrascrivibile
- [ ] `_handle_websocket()` separato e sovrascrivibile
- [ ] `self.apps` come dict semplice
- [ ] `self.router` accessibile
- [ ] `mount()` pulito senza side effects strani
- [ ] NO system routes hardcoded
- [ ] NO dipendenze da canali specifici

---

## Non Fare Ora

- ❌ Implementare CliChannel
- ❌ Implementare system endpoints
- ❌ Implementare OpenAPI generation
- ❌ Creare AsgiPublisher

**Focus attuale**: AsgiServer base funzionante e pulito.

---

## File Correlati

- [restart.md](restart.md) - Stato corrente lavoro
- [server-design.md](server-design.md) - Design AsgiServer
- [smartpublisher-analysis.md](smartpublisher-analysis.md) - Analisi SmartPublisher
