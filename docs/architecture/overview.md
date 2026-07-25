# Architecture overview

> **Status:** 🔴 DA REVISIONARE

This page explains how genro-asgi is put together and the principles behind it.
It is *explanation*, not a how-to: read it to understand why the pieces are
shaped the way they are. The normative source is
[`SPECIFICATION.md`](https://github.com/genropy/genro-asgi/blob/main/SPECIFICATION.md)
(the decision log, D1…); this page summarizes it and never contradicts it.

## Core principles

These are the guiding principles of the redesign (SPECIFICATION.md §1). They
explain most of the design decisions you will meet in the code.

- **No globals.** The server is an instance with its own state — no module-level
  variables, no singletons. `del server` garbage-collects everything it owns.
  State lives in objects, connected by semantic parent references.
- **Config is data, not structure.** What a server *is* comes from a
  configuration recipe rendered onto it; the code shape does not change with the
  deployment.
- **Objects always exist; backends come from config.** There is no `X | None`
  attribute flipped on by a flag. The session store, the auth core, the task
  manager are always there — their *backend* is what configuration selects.
- **Work at the time of use.** Expensive machinery (the thread pool, the task
  manager) is provisioned lazily, on first use.
- **Routes are static from boot.** The routing tree is built once; routing is
  never used as a mutable registry.
- **Extension by subclassing; capabilities as mixins.** You add behaviour by
  subclassing an application, and the server composes capabilities (auth,
  session, tasks…) as mixins over a base.

## The request flow

```text
uvicorn
  → AsgiServer                      the server IS the ASGI app
    → middleware chain              errors → cors → auth → session (ordered)
      → demultiplex                 first path segment → mount, else root app
        → application               a RoutedApplication (or a subclass)
          → @route handler(**params)
            → Response              buffered, or a StreamingResponse
              → ASGI send
```

Middleware order is a number, not a class trait: the chain sorts by it, smaller
is more outer. Only `errors` is on by default; `session` and `auth` are armed by
their mixins when you configure them.

## The two layers: server and application

genro-asgi separates *what the server owns* from *what an application does*.

### BaseServer

`BaseServer` is the common substrate of every server (SPECIFICATION.md §4, D2).
It owns: one uvicorn loop, one monitored thread pool for blocking work, the
**applications** it was composed with (a dict keyed by each app's `code`, plus
an index by `mount` — the URL prefix each one answers under, `""` being the site
root), the lifespan (ordered startup/shutdown), and the request registry. At the
base, `authenticate()` and `session()` answer "nobody / none" — auth and sessions
are capabilities layered on top, not built into the base.

The one dispatch rule (D3) is: **first path segment → the app mounted there;
else the app on the site root; else, for `/` with a `default` declared, a 307 to
it; else 404.** A single-app server is just a base server whose only app sits on
the root — there is no separate mechanism.

### AsgiServer

`AsgiServer` is the shipped composition (D22): it stacks every capability mixin
over `BaseServer` in one MRO — communication, auth, session, middleware,
plugins, storage, tasks. This is the complete mono-process async server. You
turn a capability on through a constructor kwarg (`auth=…`, `middleware=…`,
`tasks=…`, `plugins=…`); the mixin peels the kwargs it understands and forwards
the rest down the cooperative `__init__` chain.

Because auth is a mixin and not part of the base, an internal (non-public)
server can compose the *same* base **without** the auth mixin — its auth and
sessions are `None` by design, and whoever fronts it owns them (D1, D6).

### BaseApplication and RoutedApplication

`BaseApplication` is the app-side contract: an ASGI callable with a `code` (its
identity), a `mount` (the URL prefix it answers under) and a `server` reference
assigned once by the owning server at attach time (a second assignment raises).
`RoutedApplication` wires
[genro-routes](https://pypi.org/project/genro-routes/) into it: handlers are
`@route`-decorated methods, resolved through the app's own router. The
`OpenApiApplication`, `McpApplication` and `McpOpenApiApplication` subclasses add
protocol faces (OpenAPI/Swagger, MCP) over the *same* route tree — which is why
one decorated method can serve REST and MCP at once.

## The automatic `_server` application

Every `AsgiServer` auto-mounts a `ServerApplication` at `/_server` (D4). It
exposes the server's own management surface — login, users, tokens, tasks —
under `/_server/…`, and its OpenAPI schema at `/_server/_meta/schema_json`. It
is *automatic, not configured*: a hand-built server has it exactly like a
config-materialized one.

## Where to go next

- [Getting started](../getting-started.md) — install and run.
- [Concepts](../concepts.md) — the model in more practical terms.
- [`SPECIFICATION.md`](https://github.com/genropy/genro-asgi/blob/main/SPECIFICATION.md) — the full decision log.
