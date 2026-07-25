# Sessions

> **Status:** 🔴 DA REVISIONARE

## What it does

Gives a caller continuity across requests: a session cookie identifies a stored
`Session` that can hold an `Avatar` and arbitrary data, reconnected on every
request through the cookie.

## When to use it

When callers need to stay logged in, or when you want to carry per-user state
between requests without re-authenticating each time. Arm the session subsystem
and it keeps a store, sets the cookie, and rehydrates the session for you.

## Setup

Sessions are a mixin capability of `AsgiServer` (`SessionMixin`). Arming it wires
the session middleware automatically. The relevant constructor kwargs are:

- `session_store` — the backing store; `None` defaults to `MemorySessionStore`.
- `session_ttl` — the session lifetime.

```python
from genro_asgi import AsgiServer, RoutedApplication, MemorySessionStore
from genro_routes import route


class App(RoutedApplication):
    mount = ""

    @route()
    def index(self) -> dict:
        return {"ok": True}


server = AsgiServer(applications=[App()], session_store=MemorySessionStore())
server.serve(host="127.0.0.1", port=8000)
```

## Choosing a store

Two stores ship with genro-asgi:

- **`MemorySessionStore`** — sessions live in the process. Simple, fast, lost on
  restart. Good for development and single-process deployments.
- **`FileSessionStore`** — sessions persist on disk, backed by a `LocalStorage`:

  ```python
  from genro_asgi import FileSessionStore
  # FileSessionStore(LocalStorage(...))
  ```

Both are importable from `genro_asgi`.

## The session cookie

Cookie behaviour is controlled through the `session` middleware options:

```python
server = AsgiServer(
    applications=[App()],
    session_store=MemorySessionStore(),
    middleware={"session": {
        "cookie_name": "session_id",
        "secure": True,
        "samesite": "lax",
    }},
)
```

The session cookie is **always** `HttpOnly`. `secure` and `samesite` are yours to
set; `cookie_name` renames the cookie.

## The Session object

A `Session` carries:

- `.id` — the session identifier.
- `.data` — a `Bag` of arbitrary session data.
- `.meta` — session metadata.
- `.avatar` — the attached identity, if any.
- `.dirty` — whether the session has unsaved changes.
- `.attach_avatar(...)` — bind an `Avatar` to the session; this is what a login
  does.

## Attaching an avatar at login

At the point a caller proves who they are, attach their avatar to the session so
subsequent requests carry the identity:

```python
from genro_asgi import Avatar

# inside a handler that has verified the credentials:
session.attach_avatar(Avatar("alice", tags="admin,ops"))
```

From then on, requests bearing the session cookie resolve to that avatar — no
`Authorization` header needed. (Remember from the [auth
guide](authentication.md) that a valid `Authorization` header still takes
precedence over the session.)

## How to verify it

The first response sets the cookie; a second request replaying it reconnects the
same session:

```console
$ curl -i http://127.0.0.1:8000/index
HTTP/1.1 200 OK
set-cookie: session_id=...; HttpOnly; ...

$ curl -b "session_id=..." http://127.0.0.1:8000/index
{"ok": true}
```

## Gotchas

- `MemorySessionStore` loses everything on restart and does not share across
  processes — use `FileSessionStore` (or another backend) for anything
  persistent.
- The cookie is always `HttpOnly`; you cannot turn that off. You *can* set
  `secure` and `samesite`.
- Configure the cookie under `middleware={"session": {...}}`, not under the
  `session_store` / `session_ttl` kwargs — those control the store and lifetime,
  the middleware controls the cookie.
- `SessionMixin`, `Session`, `MemorySessionStore` and `FileSessionStore` are all
  importable from `genro_asgi`.
