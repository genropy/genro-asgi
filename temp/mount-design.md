# Mount Intelligente - Design Document

**Status**: 🔴 DA REVISIONARE
**Data**: 2025-12-03

---

## Obiettivo

Un solo metodo `mount()` che gestisce tutti i tipi di app:
- App ASGI esterne (FastAPI, Starlette, qualsiasi ASGI)
- RoutingClass interne (genro_routes)
- Funzioni/handler semplici

## API

```python
server = AsgiServer()

# 1. App ASGI esterna (FastAPI, Starlette, etc.)
server.mount("/api", fastapi_app)

# 2. RoutingClass interna
server.mount("/docs", MyDocsApp())

# 3. Handler semplice (funzione)
server.mount("/health", health_handler)

server.run()
```

## Comportamento mount()

```python
def mount(self, path: str, app: Any) -> None:
    """Mount any app type at path."""

    if isinstance(app, RoutingClass):
        # Usa router interno
        name = path.strip("/").replace("/", "_") or "root"
        self.router.attach_instance(app, name=name)

    elif _is_asgi_app(app):
        # App ASGI esterna (FastAPI, Starlette, etc.)
        self.apps[path] = {"app": app, "type": "asgi"}

    elif callable(app):
        # Funzione semplice → wrap come handler
        self.apps[path] = {"app": _wrap_handler(app), "type": "handler"}

    else:
        raise TypeError(f"Cannot mount {type(app)}")
```

## Dispatch in __call__

```python
async def __call__(self, scope, receive, send):
    if scope["type"] == "lifespan":
        await self.lifespan(scope, receive, send)
        return

    path = scope.get("path", "/")

    # 1. Cerca in apps (ASGI esterni, handler)
    app_handler = self._find_app_handler(path)
    if app_handler:
        await app_handler["app"](scope, receive, send)
        return

    # 2. Fallback al router (RoutingClass)
    await self.router(scope, receive, send)
```

## Vantaggi

1. **API unificata**: un solo metodo per tutto
2. **Drop-in Starlette**: mount() funziona come Starlette
3. **FastAPI compatibile**: FastAPI monta direttamente
4. **Flessibile**: supporta RoutingClass, ASGI, handler

## Esempi d'uso

### FastAPI sotto genro-asgi

```python
from fastapi import FastAPI
from genro_asgi import AsgiServer

api = FastAPI()

@api.get("/users")
def get_users():
    return [{"id": 1, "name": "Alice"}]

server = AsgiServer()
server.mount("/api", api)  # FastAPI su /api/*
server.run()
```

### Mix di app

```python
from genro_asgi import AsgiServer
from myapp import DocsApp, AdminApp  # RoutingClass

server = AsgiServer()
server.mount("/api", fastapi_app)      # ASGI esterno
server.mount("/docs", DocsApp())       # RoutingClass
server.mount("/admin", AdminApp())     # RoutingClass
server.mount("/health", lambda: "ok")  # Handler semplice
server.run()
```

### Starlette-like

```python
from genro_asgi import AsgiServer
from genro_asgi.routing import Route

# Come Starlette
server = AsgiServer(routes=[
    Route("/", homepage),
    Route("/users", users),
])
server.run()
```

## Domande aperte

1. **Priorità dispatch**: apps prima o router prima?
2. **Path matching**: esatto o prefix?
3. **Lifespan propagation**: come propagare startup/shutdown alle app montate?
4. **RequestRegistry**: dove si integra?

## Refactoring da fare

### `_result_to_response` → BaseRequest

Spostare `_result_to_response()` da AsgiServer a BaseRequest.
La request sa creare la response appropriata:

```python
class BaseRequest:
    def make_response(self, result: Any) -> Response:
        """Convert handler result to Response."""
        if isinstance(result, Response):
            return result
        if isinstance(result, dict):
            return JSONResponse(result)
        if isinstance(result, str):
            return PlainTextResponse(result)
        # etc.
```

Questo elimina logica dal server e la mette dove ha senso.

---

**Prossimi passi**: Approvazione design → Implementazione
