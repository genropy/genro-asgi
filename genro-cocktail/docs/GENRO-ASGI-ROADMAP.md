# genro-asgi — state of the platform (roadmap survey)

**Surveyed**: 2026-08-12, at version **0.28.0** (branch `main`, commit `753452d`).
**Method**: full read of `README.md`, `SPECIFICATION.md` and the guides; code
survey of every subsystem; the complete test suite executed locally
(**1568 passed, 96% coverage, 41s**).

This document answers "what is there and how does it work" from the point of
view of a consumer about to build an application (genro-cocktail) on top of it.

---

## 1. What genro-asgi is

A **minimal ASGI server core**, spec-first rewrite of the old genro-asgi
(now `genro-asgi-legacy`). One instance-isolated server object mounts your
applications, routes requests through genro-routes, and grows capabilities by
mixin composition — no globals, no module state.

```text
uvicorn → AsgiServer → middleware chain (errors → wellknown → logging → cors → session → auth)
  → demux on first path segment → application
    → @route handler(**typed params) → Response → ASGI send
```

Design principles (ratified in `SPECIFICATION.md`, the founding decision log):
routes static from boot; config is data, not structure; objects always exist,
backends come from config; extension by subclassing; the class says WHO you
are, the config says WHAT you are made of.

The package continues the PyPI `genro-asgi` line (decision **D-rename**,
2026-07-24: the earlier plan of a `genro-asgi-core` split was reversed; the
old repo froze as `genro-asgi-legacy`, this repo is *the* code repo).

## 2. Subsystem map

### 2.1 Server & dispatch (mature)

- `BaseServer` — uvicorn loop, lazy thread pool (`WorkPool`), request
  registry, lifespan, demux. `AsgiServer` = Communication + Auth + Session +
  Middleware + Plugin + Storage + Task mixins over it, in one cooperative MRO.
- **One demux rule**: first path segment → secondary mount if it exists,
  otherwise the primary app (`mount = ""`). `/` with a declared `default` →
  307. The `_server` app is auto-mounted at `/_server` — automatic, never
  configured (D4).
- **Sync handlers run on the thread pool; async handlers on the loop.**
- **No HTTP-method dispatch**: one `@route` entry answers GET and POST alike
  (`openapi_method=` affects only the schema). Method guards are the app's job.

### 2.2 Routing & applications (mature)

- `RoutedApplication` = genro-routes `RoutingClass` + ASGI dispatch. Handlers
  are `@route()`-decorated methods; query params, form bodies and JSON bodies
  bind to the signature with TYTX type coercion; extra path segments bind to
  `*parts`.
- `OpenApiApplication` adds `_meta/schema_json` (OpenAPI 3.1), `_meta/docs`
  (Swagger UI). `McpApplication` / `McpOpenApiApplication` expose the same
  routes as MCP tools (Streamable HTTP, protocol 2025-11-25); per-route opt-in
  with `@route(channel_channels="mcp")`.
- Handlers are **pure**: no ambient request. A handler that needs the live
  request declares an unannotated `_request` parameter — but the injection
  currently lives only on `ServerApplication.bind_kwargs`; a consumer app must
  replicate it (a 5-line override; see FEASIBILITY §3).

### 2.3 Response model (minimal by design)

- Two classes only: `Response` (buffered; dict/list→JSON, str→text/plain,
  bytes/Path→octet-stream) and `StreamingResponse` (chunked). **No**
  HTMLResponse/RedirectResponse/FileResponse classes.
- HTML is `@route(media_type="text/html")` + returning a `str`, or
  `self.result_wrapper(html, media_type="text/html")` per call.
- Control flow by exception: `Redirect(location, status=302)`,
  `HTTPBadRequest`, `HTTPNotFound`, `HTTPUnauthorized`, `HTTPForbidden` —
  turned into responses by the always-on `errors` middleware.
- Handlers **cannot return a Response/StreamingResponse object** (it would be
  stringified) — headers/status/cookies are set by mutating
  `_request.response`; SSE requires overriding `__call__` (the MCP app is the
  reference pattern).

### 2.4 Middleware (mature)

Ordered chain, http scope only: `errors` (100, always on) → `wellknown` (150)
→ `logging` (200) → `cors` (300) → `session` (400) → `auth` (450). Session and
auth arm themselves when `session_store=`/`auth=` are configured. The errors
middleware also owns the **login challenge**: a 401 on a browser navigation
becomes a 302 to `/_server/login_page?next=…` (open-redirect-guarded).

### 2.5 Sessions & auth (mature, well tested ≈170 tests)

- Anonymous session created by middleware, cookie `HttpOnly`, sliding TTL.
  Session `data` is a genro-bag `Bag`; **writes require `session.mark_dirty()`**.
- Login = `session.attach_avatar(avatar)` **in place** — the session id never
  changes (D24); anonymous state (a cart) survives login.
- Credentials: basic / bearer / JWT lists, API keys (`gak_…`, sha256-stored,
  revocable), scrypt-hashed user store (one encrypted JSON per user on
  genro-storage), OIDC per provider (PKCE S256, lazy discovery). Store-backed
  login lockout with exponential backoff.
- Per-route `auth_rule="admin&!guest"` (boolean tag expressions), default-deny.
- Identity precedence: Authorization header wins over session; invalid header
  → 401, no fallback.

### 2.6 Config (mature, distinctive)

A `config.py` is a **builder recipe**: one `AsgiConfigBuilder` subclass whose
`main(self, root)` writes a typed tree (genro-builders `contrib/config`
dialect). Closed section list: `server`, `middleware`, `authentication`,
`storage`, `applications`, `databases`, `plugins`, `openapi`. Secrets are
`EnvResolver` objects resolved at read time (a literal `admin_password` is a
boot error). The server is self-configuring: `AsgiServer(config=path)`;
explicit kwargs win wholesale per kwarg. Apps read their own subtree via
`self.config("parameters.title")`.

### 2.7 Databases (a seam, not a layer)

The core ships a **contract only** (`db.py`, 65 lines): a config `database`
entry names an imported `db_class`; at boot the server builds
`db_handler_class(db_class(**params))` into `server.databases[code]`. The
handler proxies everything and owns one method the core calls:
`closeConnection`, registered as a request cleanup by the `request.db` seam.
**No adapter exists in the ecosystem** — no genro-sqldb, no driver dependency;
transactions, pooling and migrations are the consumer's job. genro-storage is
*file* storage (fsspec-backed mounts), not a database. This is the biggest
"missing piece" for data-driven apps, and it is missing **by design** at this
phase — see FEASIBILITY §4 for the working sqlite pattern.

### 2.8 Tasks (mature core)

Spool (state = folder position, atomic moves), executor, cron/interval
scheduler; recurring tasks declared on the route itself
(`@route(task="cleanup", task_every="1h")`); managed over `/_server/tasks/*`
(JSON only). Runs in-process.

### 2.9 Streaming / SSE / WebSocket

`StreamingResponse` + `SseStream` (keepalives, retry, clean cancel) work at
the ASGI level (override `__call__`). **WebSocket is an empty hook** — the
base closes every websocket scope with code 1000; the motor is future work
(Q1). The `spa/` channel machinery is inter-**process** framing, not browser
websockets.

### 2.10 The `spa/` subsystem (phase-2 orchestration, in-repo, NOT public API)

7,185 lines — the largest thing in the repo, where nearly all recent commits
land. User-sticky worker-pool orchestration (commander / workers / registers /
global store / occupancy evaluator), the modernization of the legacy Genropy
daemon. Explicitly inert until mounted; nothing re-exported at top level; no
docs page; 14 `PROVISIONAL` tuning constants. **A consumer app today should
treat it as not-yet-available** and build on the core (2.1–2.9).

## 3. Maturity assessment

| Signal | Reading |
|---|---|
| 1568 tests / 96% coverage / CI green | strong |
| README: "feature-complete core, API stabilizing" | Beta is honest |
| All 12 doc pages banner "🔴 DA REVISIONARE" | docs lag the code |
| Zero TODO/FIXME in src (decisions live in the spec) | deliberate practice |
| spa/: heavy churn, provisional constants | avoid depending on it yet |

**Phases delivered**: 0 (base server) and 1a–1e (config, middleware,
auth/sessions, storage+db seam, OpenAPI/MCP apps, full `_server`, local
tasks) — i.e. the complete mono-process async server that D22 scoped as the
Starlette/FastAPI territory. **Phase 2+** (orchestration) is being built
in-repo under `spa/`.

## 4. Known gaps and drifts (relevant to consumers)

1. **No static-file serving** — no StaticFiles app, no FileResponse, no
   mimetypes handling. A consumer writes a small asset route (traversal guard
   included) or fronts with nginx/CDN.
2. **No template engine and no HTML escaping** in the core — by design; pair
   with genro-builders (which escapes) rather than f-strings.
3. **Form bodies are not URL-decoded** (genro-tytx `from_qs` does no
   percent-decoding): `hello%20world` arrives literally. Any browser form with
   spaces/punctuation is corrupted, including the shipped login page for
   non-trivial passwords. Needs an upstream fix in genro-tytx; workaround in
   FEASIBILITY §3. **Worth reporting upstream.**
4. **`_request` injection** exists only on `ServerApplication` — consumers
   copy a 5-line `bind_kwargs` override. Candidate for promotion into
   `RoutedApplication`.
5. **TYTX typing on form/query values**: `"12345"` arrives as `int` — annotate
   handler params (`str`) so pydantic coerces, or handle types.
6. **Docs drift**: `docs/concepts.md` and `docs/guides/streaming.md` claim a
   handler may return a `Response`/`StreamingResponse` — false against the
   current dispatcher.
7. **Spec drift**: D24 names `promote_session`, code implements
   `session.attach_avatar` (the spec name never landed); the D23 "profile
   flag" wave record was superseded by D26 (subclass) — recorded, but easy to
   misread.
8. **Session persistence**: only `MemorySessionStore` ships; the CLI's
   `--name` pickle snapshot is a dev convenience. Fine for the showcase.

None of these blocks the cocktail project; items 3 and 4 are the two we must
carry workarounds for from day one (both are small and locally contained).
