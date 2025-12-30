# genro-routes

Sistema di routing dichiarativo per genro-asgi.

## Overview

genro-routes fornisce:
- `RoutingClass` - Base class per oggetti con routing
- `Router` - Container di routes
- `@route()` - Decoratore per definire routes

## Classi Principali

### RoutingClass

```python
class RoutingClass:
    """Base class per oggetti che partecipano al routing."""

    _routing_parent: RoutingClass | None = None

    def attach_instance(self, instance: RoutingClass, name: str) -> None:
        """Attacca un'istanza figlio."""
        instance._routing_parent = self
```

Sia `AsgiServer` che `AsgiApplication` estendono `RoutingClass`.

### Router

```python
class Router:
    def __init__(self, owner: RoutingClass, name: str): ...

    def node(self, path: str, method: str = "GET", auth_tags: list = None):
        """Find route node for path/method."""
```

### @route Decorator

```python
@route()  # usa router di default
def hello(self):
    return {"message": "Hello!"}

@route("main")  # router esplicito
def public(self): pass

@route("backoffice", auth_tags="admin")
def admin(self): pass
```

## Integrazione con AsgiApplication

```python
class MyApp(AsgiApplication):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)  # crea self.main (Router)

    @route()  # usa self.main automaticamente
    def endpoint(self):
        return {"data": "value"}
```

## Integrazione con AsgiServer

```python
# server.py
for name, (cls, kwargs) in config.get_app_specs().items():
    instance = cls(**kwargs)
    self.router.attach_instance(instance, name=name)
```

## Dispatching

```python
# dispatcher.py
result = await self.server.router.node(
    request.path,
    method=request.method,
    auth_tags=scope.get("auth_tags"),
)
```

## Decisioni

- **Single router default** - `@route()` senza args usa unico router se non ambiguo
- **Auth tags in routing** - Filtro routes per tags direttamente nel router
- **attach_instance** - Pattern genro-routes per parent-child
- **_routing_parent** - Riferimento al parent per navigazione
