# AsgiApplication

Base class per applicazioni montate su AsgiServer.

## Classe

```python
class AsgiApplication(RoutingClass):
    openapi_info: ClassVar[dict] = {}  # title, version, description

    def __init__(self, **kwargs):
        self.base_dir = kwargs.pop("base_dir", None)
        self.main = Router(self, name="main")  # router di default
        self.on_init(**kwargs)
```

## Attributi

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `base_dir` | `Path \| None` | Directory base app |
| `main` | `Router` | Router principale (creato automaticamente) |
| `server` | `AsgiServer \| None` | Property → `_routing_parent` |
| `_mount_name` | `str` | Nome mount (settato dal server) |

## Lifecycle Hooks

| Hook | Quando | Signature |
|------|--------|-----------|
| `on_init` | Dopo `__init__` | `(**kwargs)` - riceve params da config.yaml |
| `on_startup` | Server startup | `()` - sync o async |
| `on_shutdown` | Server shutdown | `()` - sync o async |

## Metodi

| Metodo | Descrizione |
|--------|-------------|
| `load_resource(*args, name=)` | Carica risorsa via ResourceLoader |
| `index()` | Splash page HTML da `openapi_info` |

## Pattern d'Uso

### App minimale
```python
class MyApp(AsgiApplication):
    openapi_info = {"title": "My API", "version": "1.0.0"}

    @route()  # usa self.main (unico router)
    def hello(self):
        return {"message": "Hello!"}
```

### App con setup da config
```python
class ShopApp(AsgiApplication):
    def on_init(self, connection_string="sqlite:shop.db", **kwargs):
        self.db_engine = create_engine(connection_string)

    def on_startup(self):
        self.db = self.db_engine.connect()

    def on_shutdown(self):
        self.db.close()
```

### App con router multipli
```python
class AdminApp(AsgiApplication):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # OBBLIGATORIO
        self.backoffice = Router(self, name="backoffice")

    @route("main")       # esplicito
    def public(self): pass

    @route("backoffice") # altro router
    def admin(self): pass
```

## Come il Server Monta le App

```python
# server.py
for name, (cls, kwargs) in config.get_app_specs().items():
    instance = cls(**kwargs)           # NON passa self
    instance._mount_name = name
    self.apps[name] = instance
    self.router.attach_instance(instance, name=name)  # setta _routing_parent
```

## Decisioni Architetturali

1. **Server NON passato nel costruttore** - usa `attach_instance()` di genro-routes
2. **`@route()` senza args** - usa l'unico router se non ambiguo
3. **`on_init()` vs `__init__`** - kwargs da config vanno in on_init
4. **`super().__init__()` obbligatorio** se si sovrascrive `__init__`
