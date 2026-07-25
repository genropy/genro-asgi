# MCP

> **Status:** 🔴 DA REVISIONARE

## What it does

Exposes your `@route` methods as **tools an AI agent can call** over the Model
Context Protocol (MCP), served as JSON-RPC over Streamable HTTP. Because
genro-routes is protocol-neutral, the same route tree can answer REST and MCP at
once.

## When to use it

When you want an AI agent to invoke your application's operations as tools —
either as a pure MCP endpoint or side-by-side with a REST/OpenAPI face.

## Setup

Two base classes cover the two shapes:

- **`McpApplication`** — the whole application is a single JSON-RPC MCP endpoint.

  ```python
  from genro_asgi import McpApplication
  app = McpApplication(routing_class=..., code="mcp")
  ```

- **`McpOpenApiApplication`** — a dual-faced application: a REST/OpenAPI face
  *and* an MCP face served on `/mcp`. The MCP segment is configurable via
  `mcp_name_segment="mcp"`.

  ```python
  from genro_asgi import McpOpenApiApplication
  # subclass of OpenApiApplication: REST + OpenAPI + MCP on /mcp
  ```

Both are importable from `genro_asgi`.

## Marking a route as a tool

Expose a method as an MCP tool with `channel_channels`:

```python
from genro_routes import route


class Calc(McpOpenApiApplication):
    openapi_info = {"title": "Calc", "version": "1.0.0"}

    @route(channel_channels="mcp")
    def add(self, a: int = 0, b: int = 0) -> dict:
        return {"result": a + b}

    @route(channel_channels="mcp,rest")
    def mul(self, a: int = 0, b: int = 0) -> dict:
        return {"result": a * b}
```

- `channel_channels="mcp"` — the method is an MCP tool only.
- `channel_channels="mcp,rest"` — the method is **both** an MCP tool and a REST
  endpoint (dual). This is the point of protocol-neutral routing: one method,
  two transports, one parameter-handling path.

## The `/mcp` endpoint

The MCP face speaks JSON-RPC on `/mcp`, protocol version `2025-11-25`:

- `initialize`
- `tools/list`
- `tools/call`
- `ping`

Parameter handling for `tools/call` is the same as for REST: the arguments bind
to the method signature, typed and with defaults.

A `GET` on `/mcp` opens an SSE push stream (see [streaming](streaming.md)). It
returns `405` if the server has no task backbone armed.

## How to verify it

List the tools with a JSON-RPC call:

```console
$ curl -X POST http://127.0.0.1:8000/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Call one:

```bash
curl -X POST http://127.0.0.1:8000/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":2,"method":"tools/call",
         "params":{"name":"add","arguments":{"a":2,"b":3}}}'
```

## Gotchas

- Only routes carrying `channel_channels` that includes `"mcp"` appear as tools.
  A plain `@route()` is REST-only and is not offered to the agent.
- `GET /mcp` (the SSE push stream) is `405` unless the server has tasks armed —
  see the [tasks guide](tasks.md).
- The MCP JSON-RPC lives on `/mcp` (segment configurable via
  `mcp_name_segment`), separate from the OpenAPI `_meta` prefix.
- `McpApplication`, `McpOpenApiApplication`, `McpEngine` and `McpError` are
  importable from `genro_asgi`.
