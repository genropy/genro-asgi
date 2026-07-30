# How-to Guides

> **Status:** 🔴 DA REVISIONARE

Task-focused recipes for the capabilities genro-asgi grows on top of the core.
Each one assumes you have read [Getting started](../getting-started.md) and
[Core concepts](../concepts.md).

```{toctree}
:hidden:

authentication
sessions
openapi
mcp
tasks
streaming
middleware
configuration
cli
```

## The guides

- **[Authentication](authentication.md)** — configure basic / bearer / JWT
  backends and API keys, protect routes with `auth_rule`, and work with the
  `Avatar` identity.
- **[Sessions](sessions.md)** — arm the session subsystem, choose a memory or
  file store, control the session cookie, and attach an avatar at login.
- **[OpenAPI & Swagger](openapi.md)** — turn `@route` methods into an OpenAPI 3.1
  schema and a Swagger UI under the `_meta` prefix, direct or mounted.
- **[MCP](mcp.md)** — expose routes as tools an AI agent can call over MCP
  Streamable HTTP, standalone or side-by-side with REST.
- **[Background tasks](tasks.md)** — arm the task backbone, fire off
  fire-and-forget work, schedule interval/cron jobs, and manage them over HTTP.
- **[Streaming & SSE](streaming.md)** — return chunked bodies with
  `StreamingResponse` and Server-Sent Events with `SseStream`.
- **[Middleware](middleware.md)** — the built-in chain, its order and defaults,
  how to arm each stage, and how to register a custom middleware.
- **[Configuration](configuration.md)** — write the recipe a server reads itself
  from, keep secrets out of it with resolvers, and read values back through the
  server and its applications.
- **[The `genro-asgi` command](cli.md)** — boot a server from a `config.py` or a
  single application, manage the named ones with `apps`/`stop`/`remove`, and
  reload on source changes.

## How each guide is structured

Every how-to follows the same six-part shape, so you can skim to the part you
need:

1. **What it does** — the capability in one or two sentences.
2. **When to use it** — the situation that calls for it.
3. **Setup** — the constructor kwargs or base class you need in place.
4. **Minimal snippet** — the smallest copy-pasteable example that works.
5. **How to verify it** — a concrete check (a `curl`, a request, an observed
   effect) that proves it is working.
6. **Gotchas** — the sharp edges worth knowing before you hit them.
