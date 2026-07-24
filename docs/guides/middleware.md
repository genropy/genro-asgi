# Middleware

> **Status:** 🔴 DA REVISIONARE

## What it does

Wraps request handling in an ordered chain of cross-cutting stages — error
handling, CORS, logging, sessions, auth, and well-known endpoints. Each stage is
an object that always exists; you arm it through config.

## When to use it

Whenever you need behaviour that applies across routes rather than inside a single
handler: turning exceptions into clean responses, adding CORS headers, logging
requests, and so on. Most stages are off by default and armed with the
`middleware` kwarg.

## The built-in chain

The registry ships these middleware, with a priority and a default state.
**Lower priority number = more outer** (runs first on the way in, last on the way
out):

| Name        | Priority | Default | Notes                                        |
|-------------|----------|---------|----------------------------------------------|
| `errors`    | 100      | **on**  | maps exceptions and unmatched paths to status codes |
| `wellknown` | 150      | off     | `.well-known` endpoints                       |
| `logging`   | 200      | off     | request logging                              |
| `cors`      | 300      | off     | CORS headers                                 |
| `session`   | 400      | off     | armed automatically by `SessionMixin`        |
| `auth`      | 450      | off     | armed automatically by `AuthMixin`           |

Only the `http` scope is processed by the chain.

Two of these arm themselves as a side effect: passing `session_store`/`session_ttl`
arms `session`, and passing `auth=...` arms `auth`. You rarely toggle those two
directly.

## Setup — arming a stage

Pass the `middleware` kwarg. A value of `True` arms a stage with its defaults; a
dict arms it with options; `False` disarms it.

```python
from genro_asgi import AsgiServer, RoutedApplication
from genro_routes import route


class App(RoutedApplication):
    @route()
    def index(self) -> dict:
        return {"ok": True}


server = AsgiServer(
    primary=App(),
    middleware={
        "cors": True,
        "logging": True,
    },
)
server.serve(host="127.0.0.1", port=8000)
```

## CORS options

`cors` accepts an options dict:

```python
server = AsgiServer(
    primary=App(),
    middleware={"cors": {
        "allow_origins": ["https://example.com"],
        "allow_credentials": True,
        "max_age": 600,
    }},
)
```

## Custom middleware

Register your own middleware class in the registry, then arm it like any built-in
stage:

```python
from genro_asgi import BaseMiddleware


class StampMiddleware(BaseMiddleware):
    ...


server = AsgiServer(
    primary=App(),
    middleware_registry={"stamp": StampMiddleware},
    middleware={"stamp": {...}},
)
```

- `middleware_registry={"stamp": StampMiddleware}` teaches the server the new
  name.
- `middleware={"stamp": {...}}` arms it (and passes its options).

The individual built-in middleware classes are importable from
`genro_asgi.middleware` (e.g. `from genro_asgi.middleware import
CORSMiddleware`), and `BaseMiddleware` / `MiddlewareMixin` from `genro_asgi`.

## How to verify it

With `cors` armed, a request carrying an `Origin` gets CORS headers back:

```console
$ curl -i -H "Origin: https://example.com" http://127.0.0.1:8000/index
HTTP/1.1 200 OK
access-control-allow-origin: https://example.com
```

With `logging` armed, requests appear in the server's log output.

## Gotchas

- `errors` is the only stage on by default — it is why an unknown path is a clean
  `404` in the hello-world. The rest are off until you arm them.
- An unknown middleware name in `middleware={...}` raises `ValueError`. If you are
  arming a custom stage, register it in `middleware_registry` first.
- Ordering is by priority, lower = more outer. A custom stage lands according to
  its own priority in the chain.
- Do not hand-arm `session`/`auth` when you are already passing
  `session_store`/`auth` — those kwargs arm the respective middleware for you.
