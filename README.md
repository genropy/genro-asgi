# genro-asgi

**A minimal ASGI server core** — one instance-isolated server that mounts your
applications, routes requests through [genro-routes](https://pypi.org/project/genro-routes/),
and grows authentication, sessions, background tasks, OpenAPI and MCP by
composition. No globals, no module state: the server is an object you build,
run, and throw away.

[![PyPI version](https://img.shields.io/pypi/v/genro-asgi.svg)](https://pypi.org/project/genro-asgi/)
[![Python versions](https://img.shields.io/pypi/pyversions/genro-asgi.svg)](https://pypi.org/project/genro-asgi/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

> **Status: Beta.** Feature-complete core, API stabilizing. This repository is a
> spec-first redesign — see [`SPECIFICATION.md`](SPECIFICATION.md) for the
> founding decision log.

## What it does

- **Serves applications** — each app declares its `mount`, the URL prefix it
  answers under (`""` is the site root); the server demultiplexes on the first
  path segment.
- **Routes requests** — handlers are `@route`-decorated methods on your
  application class; query and body parameters bind to the signature, typed.
- **Authenticates** — basic / bearer / JWT credentials, API keys (`gak_…`),
  and OIDC providers; per-route `auth_rule` filtering, default-deny.
- **Manages sessions** — in-memory or file-backed store, cookie reconnection,
  `Avatar` identity (tags + extensible Bag data).
- **Applies middleware** — errors, CORS, logging, auth, session, well-known —
  composed as an ordered chain, each turned on by config.
- **Runs background tasks** — a spool + executor + cron/interval scheduler,
  managed over `/_server/tasks`.
- **Generates OpenAPI & Swagger** — subclass `OpenApiApplication` and the same
  `@route` methods yield an OpenAPI 3.1 schema and a Swagger UI.
- **Speaks MCP** — subclass `McpApplication` (or `McpOpenApiApplication`) and
  your routes become tools an AI agent can call, over MCP Streamable HTTP.
- **Streams** — `StreamingResponse` for chunked bodies, `SseStream` for
  Server-Sent Events.

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

```bash
python hello.py
```

```console
$ curl http://127.0.0.1:8000/index
{"hello": "world"}
$ curl "http://127.0.0.1:8000/greet?name=genro"
{"hello": "genro"}
```

A handler that returns a `dict` answers JSON; the query string binds to the
method signature (`name` above), with defaults and type coercion. An unknown
path answers `404` through the always-on error middleware.

## REST + OpenAPI + Swagger from one class

Subclass `OpenApiApplication` instead of `RoutedApplication`, declare
`openapi_info`, and enable the plugins — the same `@route` methods now expose an
OpenAPI 3.1 schema and a Swagger UI, generated from their signatures:

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
server.serve(port=8000)
```

- `/search?q=moka&max_price=30` — the endpoint, params typed and coerced
- `/_meta/docs` — the Swagger UI
- `/_meta/schema_json` — the OpenAPI 3.1 document

If you know FastAPI, this is the same decorate-a-method workflow. The difference
is where the route description lives: genro-routes keeps it protocol-neutral, so
other transports read the same tree. Switch the base class to
`McpOpenApiApplication` and the app grows an MCP face on `/mcp` — the routes you
mark with `@route(channel_channels="mcp")` become tools an agent can call, with
the same parameter handling as REST. See
[Coming from Starlette / FastAPI](docs/coming-from-fastapi.md) for a full
concept mapping.

## Architecture at a glance

The server is an instance with its own state — no global variables. Every
component is an isolated object connected by a semantic parent reference (an app
holds `self.server`, a request holds `self.application`).

```text
uvicorn → AsgiServer → middleware chain (errors → cors → auth → session)
  → demultiplex on first path segment → application
    → @route handler(**params) → Response → ASGI send
```

`AsgiServer` is the shipped composition: it stacks the capability mixins
(communication, auth, session, middleware, plugins, storage, tasks) over
`BaseServer` in one MRO. You turn features on through constructor kwargs
(`auth=…`, `middleware=…`, `tasks=…`, `plugins=…`) — objects always exist,
their backends come from config.

## Documentation

Full documentation (guides, architecture, API reference) is built with Sphinx
under [`docs/`](docs/) and published on Read the Docs.

- [Getting started](docs/getting-started.md)
- [Coming from Starlette / FastAPI](docs/coming-from-fastapi.md)
- [Architecture overview](docs/architecture/overview.md)
- [`SPECIFICATION.md`](SPECIFICATION.md) — the founding decision log

Build it locally:

```bash
pip install -e ".[docs]"
sphinx-build -b html docs docs/_build/html
```

## Development

```bash
git clone https://github.com/genropy/genro-asgi.git
cd genro-asgi
pip install -e ".[dev]"

pytest                    # run tests
ruff check src/           # lint
mypy src/                 # type check (advisory)
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full workflow.

## License

Copyright © 2025 **Softwell S.r.l.**

Licensed under the [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0).
This project may include third-party components under separate open-source
licenses; see the [`NOTICE`](NOTICE) file for attribution.

## Links

- **GitHub**: <https://github.com/genropy/genro-asgi>
- **PyPI**: <https://pypi.org/project/genro-asgi/>
