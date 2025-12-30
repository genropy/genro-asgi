# AsgiServer

> **STATUS**: ~~Tutto integrato in `specifications/02_server_foundation/`~~
>
> - ~~Principio Architetturale~~ → `01_asgi_server.md`
> - ~~Classe e Attributi~~ → `01_asgi_server.md`
> - ~~Flusso Request~~ → `04_dispatcher.md`
> - ~~Endpoint di Sistema~~ → `01_asgi_server.md`
> - ~~Come Monta le App~~ → `01_asgi_server.md`
> - ~~Config YAML~~ → `02_configuration.md`
> - ~~Avvio~~ → `01_asgi_server.md`
> - ~~Decisioni Architetturali~~ → `01_asgi_server.md`
>
> **Può essere eliminato dopo revisione finale.**

---

~~## Principio Architetturale~~

~~**Server come istanza isolata, non funzione globale.**~~

~~```python
server = AsgiServer()      # istanza con proprio stato
del server                 # → tutto garbage collected, zero residui
```~~

~~**Pattern Dual Parent-Child**: ogni oggetto creato dal parent mantiene riferimento semantico:~~
~~```python
self.dispatcher = Dispatcher(self)  # Dispatcher.server = self
```~~

~~## Classe~~

~~```python
class AsgiServer(RoutingClass):
    def __init__(self, server_dir=None, host=None, port=None, reload=None, argv=None):
        self.config = ServerConfig(server_dir, host, port, reload, argv)
        self.router = Router(self, name="root")
        self.apps: dict[str, AsgiApplication] = {}
        self.request_registry = RequestRegistry()
        self.storage = LocalStorage(self)
        self.resource_loader = ResourceLoader(self)
        self.lifespan = ServerLifespan(self)
        self.dispatcher = middleware_chain(...)
```~~

~~## Attributi~~

~~| Nome | Tipo | Descrizione |
|------|------|-------------|
| `config` | `ServerConfig` | Configurazione YAML + CLI |
| `router` | `Router` | Router root |
| `apps` | `dict[str, AsgiApplication]` | App montate |
| `request_registry` | `RequestRegistry` | Registry request in-flight |
| `storage` | `LocalStorage` | File system asincrono |
| `resource_loader` | `ResourceLoader` | Loader risorse gerarchico |
| `lifespan` | `ServerLifespan` | Gestione startup/shutdown |
| `dispatcher` | `Middleware` | Chain middleware + dispatcher |~~

~~## Flusso Request~~

~~```
Browser
  │
  ▼
AsgiServer.__call__(scope, receive, send)
  │
  ├── lifespan → self.lifespan
  └── http/ws  → self.dispatcher
                    │
                    ├── ErrorMiddleware
                    ├── CorsMiddleware
                    ├── AuthMiddleware → scope["auth_tags"]
                    └── Dispatcher
                          │
                          ├── request = registry.create(scope, receive, send)
                          ├── node = router.node(path, auth_tags=...)
                          ├── result = await smartasync(node)(**query)
                          └── response.set_result(result)
```~~

~~## Endpoint di Sistema~~

~~| Endpoint | Descrizione |
|----------|-------------|
| `index()` | Default page, redirect a main_app |
| `_openapi(*args)` | Schema OpenAPI |
| `load_resource(*args, name=)` | Caricamento risorse |
| `_create_jwt(...)` | Creazione JWT (richiede superadmin) |~~

~~## Come Monta le App~~

~~```python
for name, (cls, kwargs) in config.get_app_specs().items():
    instance = cls(**kwargs)
    instance._mount_name = name
    self.apps[name] = instance
    self.router.attach_instance(instance, name=name)  # _routing_parent = server
```~~

~~## Config YAML~~

~~```yaml
server:
  host: "0.0.0.0"
  port: 8000
  reload: true
  main_app: shop

apps:
  shop:
    module: "main:ShopApp"
    connection_string: "sqlite:shop.db"
```~~

~~## Avvio~~

~~```python
server = AsgiServer(server_dir="./myapp")
server.run()  # → uvicorn.run(self, host=..., port=...)
```~~

~~## Decisioni Architetturali~~

~~1. **Istanza isolata** - no stato globale, `del server` pulisce tutto~~
~~2. **RoutingClass** - usa genro-routes per routing~~
~~3. **Router "root"** - nome del router principale (vs "main" nelle app)~~
~~4. **Middleware chain** - ordine: Errors → CORS → Auth → Dispatcher~~

## Proposta Futura: Separazione Server/ServerApp

Proposta non implementata per separare:
- `AsgiServer` → orchestratore puro (config, lifespan, registry)
- `ServerApp` → root application con endpoint sistema

Vedi decisioni architetturali per dettagli.

> **NOTA**: Questa proposta futura NON è stata integrata - va valutata se includerla in un capitolo futuro o scartarla.
