# Frequently asked questions

## Installation, mounting and configuration

### Which package should I install?

Install `genro-asgi` in a virtual environment with Python 3.11 or newer. The
same distribution supplies `genro_asgi`, `genro_asgi_multiworker_spa` and
`genro_asgi_server_app`; there is no separate `[spa]` extra. These pages describe the development checkout,
so check your installed version when an API differs.

See [Getting started](getting-started.md#installation).

### Why does my application return 404 at `/`?

A routed application needs a route for the requested path: an `index` method
is reached at `/index`, not automatically at `/`. `mount=""` makes the
application the root fallback; it does not create a home-page route. Without
a root application, `default="catalog"` redirects `/` to that application's
mount with status 307.

See [Mounting applications](guides/applications.md).

### What is the difference between `code` and `mount`?

`code` identifies the application in the server registry and configuration.
`mount` is its first URL segment: `code="catalog", mount="shop"` serves it
under `/shop`, and the application receives the remaining path. Use
`mount=""` for the root; `None` selects the default mount derived from the
code. Put deeper routing inside the application.

See [Mounting applications](guides/applications.md).

### Does an explicit constructor argument override my recipe?

Yes, per keyword argument. An explicit mapping replaces the configured
mapping for that argument; it is not a recursive merge. For example, passing
`middleware={...}` replaces the recipe's middleware mapping, so include every
option you intend to retain.

See [Configuration](guides/configuration.md).

### Does changing configuration automatically reconfigure a running server?

No general live reconfiguration mechanism is available. Resolvers can return
new values when read again, but that does not recreate objects or remount
applications already constructed from earlier values. The SPA's supported
profile apply/reload operations are a separate, narrower mechanism.

See [Configuration](guides/configuration.md) and
[Multiworker SPA integration](guides/multiworker-spa.md).

## Requests, authentication and plugins

### When do invalid arguments produce 400, 415, 422 or 500?

Every failure the core judges produces 400: a missing required argument, an
unexpected keyword, a body that is not what its content type declares, a
malformed form or multipart, and — under the default `strict` reading — values
that fit the signature but fail pydantic validation. A content type the core
cannot decode produces 415. An exception inside the handler produces 500 unless
it is an HTTP exception with its own status.

422 is the handler's, for a domain rule, unless the application declares the
FastAPI convention (`request_error_codes = "fastapi"`), which answers 422 to a
rejected value.

See [Requests and errors](guides/requests.md#validation-and-status-codes).

### How do I receive a JSON body as one object?

Declare a `body_data` parameter to receive the hydrated document without
spreading its fields over individual parameters. A handler accepting
`**kwargs` also receives the document under `body_data`. An application
declaring `request_body = "raw"` receives every body as bytes in `body_raw`.
Extra JSON fields are dropped when the document is spread over declared scalar
parameters.

See [Body arguments](guides/requests.md#body-arguments).

### Does the server stream large uploads to my routed handler?

No. `Request.read_body()` buffers the complete body, including multipart
uploads, and has no configurable total body-size limit. Use an ingress limit
or a directly hosted application that controls ASGI `receive` when you need
bounded or streaming upload processing.

See [Requests and errors](guides/requests.md) and
[Streaming and SSE](guides/streaming.md).

### Why do I receive 401 rather than 403?

A denied anonymous caller receives 401; an identified caller lacking the
required permissions receives 403. A browser requesting HTML may instead be
sent through the login flow. Authentication establishes identity; route
authorization rules decide what that identity may access.

See [Authentication](guides/authentication.md).

### Must I enable pydantic or OpenAPI explicitly?

`AsgiServer` automatically arms both plugins on its routed applications.
They cannot be disabled; explicit plugin entries configure their options.
A composition without `PluginMixin` does not supply this pair. For schema
title, version and description, set the application's `openapi_info` class
attribute: the root `openapi` configuration section validates but has no core
consumer.

See [OpenAPI and Swagger](guides/openapi.md).

### Does `channel_channels="mcp"` hide a route from HTTP?

No. It includes the route in the MCP tool surface, but HTTP dispatch does not
apply that channel filter. Use authorization rules to restrict callers.
Conversely, an ordinary unmarked `@route()` is not offered as an MCP tool.

See [MCP](guides/mcp.md#marking-a-route-as-a-tool).

## WebSockets, worker pools and shared state

### Should I use WSX or a raw WebSocket?

Use WSX to send request envelopes through the server's existing application
routing. Define `serve_websocket` when your application needs its own
WebSocket protocol. The raw seam delegates accept/close, Origin checks,
authentication and cleanup to your application; it does not inherit the WSX
gates or registry.

See [WebSockets](guides/websockets.md).

### Why does my WSX connection close with code 1008?

The handshake may have selected no home application, or that application may
require a cookie the request did not carry. A SPA front requires its
`spa_connection_id` cookie. For page RPCs, also complete `openchannel` with the
page's `page_id` before sending page requests; a request before that step is
refused with 409.

See [Handshake and limits](guides/websockets.md#handshake-and-limits) and
[SPA page channels](guides/websockets.md#spa-page-channels-and-push).

### Can I stream an HTTP response through WSX or a SPA worker?

No. WSX requires finite buffered responses, and the SPA worker path collects
both the complete request and the complete response. An endless hosted SSE
response never completes its worker call. Serve incremental HTTP downloads
and SSE directly on the core instead.

See [Streaming and SSE](guides/streaming.md#where-buffering-still-applies).

### Why do my old SPA imports fail after upgrading?

Since 0.44, SPA code lives in `genro_asgi_multiworker_spa`. The old
`genro_asgi.spa` and `genro_asgi.applications.spa_app` paths have no
compatibility re-exports. Update import statements and module-path strings in
configuration and process commands.

See [Multiworker SPA integration](guides/multiworker-spa.md).

### Why is `/_server/...` a 404 after upgrading?

Since 0.46.1 the server application is declared like any other, and its code
lives in `genro_asgi_server_app`. Nothing mounts it for you: pass
`ServerApplication()` in `applications=`, or write it on the `applications`
section with the code `_server`. `genro_asgi` no longer exports
`ServerApplication`, `AuthSection`, `AuthMethod`, `PasswordMethod` or
`OidcMethod`, and there are no compatibility re-exports.

The login policy and the OIDC providers moved with it: they are no longer
`authentication.login` and `authentication.oidc` in a recipe, but the same
three words written under the application's own element. The HTML login page
and the HTML monitor page are gone entirely — those endpoints served pages
that gramlot renders now, and the JSON routes beside them are unchanged.

See the `Server application` page of the API reference.

### Can one named orchestration profile configure two groups?

Not with the current profile mechanism. Named profiles, environment overrides
and the apply/reload/status control surface require exactly one group. A
multi-group recipe must leave those features disabled; declaring valid groups
does not remove that restriction.

See [The pool configuration](guides/configuration.md#the-pool-subtree-orchestration-its-commander-and-its-groups).

### How do I update shared state without losing another worker's change?

Use `worker.global_store.for_update(key)` and change the lease's private
`value`. Use `with` on a pool thread or `async with` on the worker loop; normal
exit publishes the replacement. One lock protects the entire store, including
unrelated keys, so keep the lease short and do not nest leases or call
`get`/`set`/`delete` while holding one.

See [Global store](guides/multiworker-spa.md#global-store).

### Should I retry after `GlobalStoreCommitUnconfirmed`?

Do not blindly retry: the commander may already have published the value
before its reply was lost. The exception reports an uncertain outcome, not a
confirmed abort. The client performs no automatic retry; reconciliation must
account for the possibility that the original update took effect.

See [Global store](guides/multiworker-spa.md#global-store).
