# Getting Started

> **Status:** 🔴 DA REVISIONARE

Welcome to **genro-asgi**. This page takes you from installation to a running
server that answers real HTTP requests, then explains the hello-world line by
line so you know *why* each piece is there before you reach for anything more
advanced.

## What genro-asgi is

genro-asgi is a **minimal ASGI server core**. You build one server object, mount
your applications on it, and it routes incoming requests to `@route`-decorated
methods on those applications. Everything else — authentication, sessions,
background tasks, OpenAPI, MCP, streaming — grows on the same core by
composition, turned on through constructor keyword arguments.

Two ideas shape the whole design:

- **The server is an object.** You construct an `AsgiServer`, call `.serve()`,
  and throw it away. There are no global variables and no module-level state; a
  test can spin up a fresh isolated server on every run.
- **Configuration is data.** Features do not appear and disappear — the objects
  always exist. What changes is the config you hand them (a backend, a set of
  credentials, a middleware option). You never flip a feature on by monkey-
  patching; you describe it.

If you come from Starlette or FastAPI, the decorate-a-handler workflow will feel
familiar; the differences are covered in
[Coming from Starlette / FastAPI](coming-from-fastapi.md).

## Installation

```bash
pip install genro-asgi
```

Requires Python 3.11+.

## Hello world

One file. A `RoutedApplication` subclass with two `@route` handlers, served by
an `AsgiServer`:

```python
# hello.py
from genro_asgi import AsgiServer, RoutedApplication
from genro_routes import route


class Hello(RoutedApplication):
    mount = ""          # this app answers the site root

    @route()
    def index(self) -> dict[str, str]:
        return {"hello": "world"}

    @route()
    def greet(self, name: str = "world") -> dict[str, str]:
        return {"hello": name}


if __name__ == "__main__":
    server = AsgiServer(applications=[Hello()])
    server.serve(host="127.0.0.1", port=8000)
```

Run it:

```bash
python hello.py
```

And call it:

```console
$ curl http://127.0.0.1:8000/index
{"hello": "world"}
$ curl "http://127.0.0.1:8000/greet?name=genro"
{"hello": "genro"}
$ curl "http://127.0.0.1:8000/greet"
{"hello": "world"}
$ curl -i http://127.0.0.1:8000/nowhere
HTTP/1.1 404 Not Found
```

## Line by line

Every line above earns its place. Here is what each one does.

### The application

```python
class Hello(RoutedApplication):
```

`RoutedApplication` is the base class for an application whose behaviour is
described by `@route`-decorated methods. Your subclass *is* the application: its
methods are its endpoints.

### The `@route` decorator

```python
from genro_routes import route

@route()
def index(self) -> dict[str, str]:
    return {"hello": "world"}
```

`route` is imported from **genro-routes**, the protocol-neutral routing library
genro-asgi builds on. It is *not* re-exported from `genro_asgi`, so import it
directly from `genro_routes`.

Marking a method with `@route()` publishes it as an endpoint. The method name
becomes the URL segment: `index` answers `GET /index`, `greet` answers
`GET /greet`. Returning a `dict` produces a JSON response automatically.

### Query parameters bind to the signature

```python
@route()
def greet(self, name: str = "world") -> dict[str, str]:
    return {"hello": name}
```

Parameters in the method signature bind to the request's query string, typed and
with defaults. `GET /greet?name=genro` calls `greet(name="genro")`; `GET /greet`
with no query string uses the default `"world"`. The annotation drives coercion —
declare `max_price: float` and the incoming string is converted to a float
before your method runs.

### Building and serving

```python
server = AsgiServer(applications=[Hello()])
server.serve(host="127.0.0.1", port=8000)
```

`AsgiServer(applications=[...])` builds the server with the applications it
serves. Each application carries its own placement in its `mount`, and
`mount = ""` is the site root: that app answers `/` and every path no other
mount claims.

`server.serve(host=..., port=...)` boots a programmatic uvicorn loop and
**blocks** until the process stops. The server object *is* the ASGI application
handed to uvicorn — there is no separate app callable to wire up.

> There is no `.run()` method and there is no command-line launcher. You start
> the server by calling `.serve()` from your own Python entry point. Passing
> `port=0` lets the OS assign a free port, which is handy in tests.

## Responding with JSON or HTML

A handler that returns a `dict` answers **JSON**. To answer **HTML**, declare the
media type on the route and return a string:

```python
class Pages(RoutedApplication):
    @route()
    def data(self) -> dict:
        return {"ok": True}          # application/json

    @route(media_type="text/html")
    def home(self) -> str:
        return "<h1>Welcome</h1>"    # text/html
```

## The automatic 404

You did not write a handler for `/nowhere`, yet the server answered `404` cleanly
rather than crashing. That is the **error middleware**, which is on by default. It
maps an unmatched path to `HTTPNotFound` and turns raised HTTP exceptions into
proper responses. You will meet the rest of the middleware chain in the
[middleware guide](guides/middleware.md).

## The always-present `_server` app

Every server, even a hand-built one like the hello-world above, automatically
mounts an internal `_server` application at `/_server/`. It exposes system
endpoints — login, task management, and (on request) a Swagger view of those
endpoints. You do not configure it; it is always there. See the
[authentication](guides/authentication.md) and [tasks](guides/tasks.md) guides
for what lives under it.

## Next steps

- **[Core concepts](concepts.md)** — the server/application model, the demux
  rule, routing, and the design principles behind them.
- **[How-to guides](guides/index.md)** — task-focused recipes:
  [authentication](guides/authentication.md),
  [sessions](guides/sessions.md),
  [OpenAPI & Swagger](guides/openapi.md),
  [MCP](guides/mcp.md),
  [background tasks](guides/tasks.md),
  [streaming & SSE](guides/streaming.md),
  [middleware](guides/middleware.md).
- **[Coming from Starlette / FastAPI](coming-from-fastapi.md)** — a concept
  mapping and side-by-side example if you already know those frameworks.
