# Coming from Starlette / FastAPI

> **Status:** 🔴 DA REVISIONARE

If you already know Starlette or FastAPI, genro-asgi will feel familiar in the
small — you still decorate a callable to make a route, params still bind to the
signature, and you still get OpenAPI and Swagger for free. It differs in the
large: in *what you build* and *how features appear*. This page maps the two so
you can carry your intuition across and know where it stops.

## The mental model, side by side

**FastAPI** gives you an application object; you attach path operations to it with
function decorators, and a dependency-injection container supplies each operation
with what it declares. Middleware and security are attached to the app; you run it
under uvicorn.

**genro-asgi** gives you a *server that mounts applications*. An application is a
class whose `@route`-decorated **methods** are its endpoints. The server itself is
a **composition of capability mixins** — auth, sessions, tasks, plugins — that
always exist and are fed by **config data** rather than switched on structurally.
There is no dependency-injection container: a handler reaches what it needs
through the object graph (its application, the server, the request), not through
declared dependencies. You start the server by calling `.serve()` from your own
entry point, or with the `genro-asgi` command
(see [the CLI guide](guides/cli.md)).

The other pivotal difference is that routing is **protocol-neutral**. In FastAPI a
path operation is an HTTP thing. In genro-asgi a `@route` describes an operation
independently of transport, which is exactly why the *same* method tree can be
served as REST, as an OpenAPI schema, and as MCP tools without being rewritten.

## Concept mapping

| Task | FastAPI / Starlette | genro-asgi |
|------|---------------------|------------|
| Create the app | `app = FastAPI()` | subclass `RoutedApplication` (or `OpenApiApplication`); build `AsgiServer(applications=[App()])` |
| Define a route | `@app.get("/greet")` on a function | `@route()` on a **method** (name = URL segment), imported from `genro_routes` |
| Path / query params | function args + `Path`/`Query` | method args bind to the query string, typed, with defaults |
| Request body / validation | pydantic model as a param | the `pydantic` plugin (`plugins={"pydantic": True}`) |
| JSON response | `return {...}` / `JSONResponse` | `return {...}` (dict → JSON) |
| HTML response | `HTMLResponse` | `@route(media_type="text/html")` returning a string |
| Dependency injection | `Depends(...)` | no DI container — reach through the object graph (`self.server`, the request) |
| Middleware | `app.add_middleware(...)` | `middleware={...}` kwarg on `AsgiServer`; ordered built-in chain |
| Auth / security | `Security(...)`, security schemes | `auth={...}` kwarg + `@route(auth_rule="...")`, default-deny, `Avatar` |
| Sessions | `SessionMiddleware` (Starlette) | `SessionMixin` via `session_store`/`session_ttl`; `Session` + `Avatar` |
| Mount a sub-app | `app.mount("/api", subapp)` | secondary mounts (dict by URL prefix); demux on first path segment |
| OpenAPI / Swagger | automatic at `/docs`, `/openapi.json` | `OpenApiApplication` + plugins; `/_meta/docs`, `/_meta/schema_json` |
| Start the server | `uvicorn.run(app, ...)` / `uvicorn app:app` | `server.serve(host=..., port=...)` (programmatic uvicorn, blocking) |
| Start it from a shell | `fastapi run main.py` / `uvicorn main:app --reload` | `genro-asgi serve ./config.py [--reload]` |
| WebSocket / streaming | `WebSocket`, `StreamingResponse` | `StreamingResponse` (from `genro_asgi.streaming`), `SseStream` (from `genro_asgi.sse`) |
| Tools for an AI agent | (not built in) | `@route(channel_channels="mcp")` on an `McpApplication` / `McpOpenApiApplication` |

## The same endpoint, side by side

A tiny search endpoint with a typed query parameter, returning JSON, documented in
OpenAPI.

**FastAPI** — shown *for comparison only*, illustrative:

```python
# For comparison — this is FastAPI, not genro-asgi.
from fastapi import FastAPI

app = FastAPI(title="Shop API", version="1.0.0")


@app.get("/search")
def search(q: str = "", max_price: float = 100.0) -> dict:
    return {"query": q, "hits": []}

# uvicorn module:app --port 8000
```

**genro-asgi** — real, verified API:

```python
from genro_asgi import AsgiServer, OpenApiApplication
from genro_routes import route


class Shop(OpenApiApplication):
    mount = ""
    openapi_info = {"title": "Shop API", "version": "1.0.0"}

    @route()
    def search(self, q: str = "", max_price: float = 100.0) -> dict:
        return {"query": q, "hits": []}


server = AsgiServer(applications=[Shop()], plugins={"openapi": True, "pydantic": True})
server.serve(host="127.0.0.1", port=8000)
```

Both answer `GET /search?q=moka&max_price=30`. The FastAPI version documents at
`/docs` and `/openapi.json`; the genro-asgi version at `/_meta/docs` and
`/_meta/schema_json`. The visible difference is small — a method on a class
instead of a free function, and a server that mounts the app instead of *being*
the app. The invisible difference is the one that matters: switch the base class
to `McpOpenApiApplication` and mark `search` with
`@route(channel_channels="mcp,rest")`, and the same method is now both a REST
endpoint and an MCP tool.

## Honest notes on the differences

- **No dependency-injection container.** There is no `Depends`. Handlers reach
  collaborators through the object graph — the application holds `self.server`, the
  request holds `self.application`. If you lean heavily on FastAPI's DI for
  wiring, that pattern does not port; you compose objects instead.
- **The CLI serves a config, not an app object.** `fastapi run main.py` and
  `uvicorn main:app` both point at an ASGI callable in a module. `genro-asgi
  serve ./config.py` points at a **configuration recipe** — the file declaring
  the whole site — and the server builds itself from it; `genro-asgi serve
  application=./hello.py:Hello` is the closer analogue, for when there is one
  application and no config. The registry (`--name`, then `apps`/`stop`/`remove`)
  has no FastAPI counterpart. There is still no `.run()` method: programmatically
  you build the server and call `.serve()`, which boots a uvicorn loop and blocks
  (`port=0` asks the OS for a free port, useful in tests). See
  [the CLI guide](guides/cli.md).
- **Routing is protocol-neutral by design.** A `@route` is not inherently an HTTP
  operation. That is the reason REST, OpenAPI and MCP share one route tree — and
  the reason a method only becomes an MCP tool when you opt it in with
  `channel_channels`. The flip side: think of a route as "an operation", not "an
  HTTP verb on a path".
- **Features are config, not construction.** You do not add a capability by
  restructuring code; auth, sessions, tasks and plugins already exist on
  `AsgiServer` and are fed by kwargs (`auth=...`, `middleware=...`, `tasks=...`,
  `plugins=...`). A capability you did not configure is present but idle, not
  absent.
- **The OpenAPI prefix is `_meta`.** Not `/docs` and `/openapi.json` — the Swagger
  UI is at `/_meta/docs` and the schema at `/_meta/schema_json`.
- **An internal `_server` app is always mounted.** Login, task management and the
  system OpenAPI live under `/_server/...` with no setup on your part — there is no
  FastAPI equivalent you need to wire up.

## Where to go next

- **[Getting started](getting-started.md)** — the runnable hello-world.
- **[Core concepts](concepts.md)** — the server/application model and the demux
  rule in full.
- **[How-to guides](guides/index.md)** — auth, sessions, OpenAPI, MCP, tasks,
  streaming, middleware.
