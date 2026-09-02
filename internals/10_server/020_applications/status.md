# Applications — current state

**Version**: 0.3 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

What exists TODAY on `develop`. Every claim below carries its `file:line` or
the test that proves it. Coverage figures are from the full suite
(`pytest tests/`, 1463 passed) run on 2026-08-23 at `f0a4673`.

## The modules

| Module | Lines | Stmts | Miss | Cov | Uncovered |
|---|---|---|---|---|---|
| `src/genro_asgi/application.py` | 182 | 51 | 0 | 100% | — |
| `src/genro_asgi/routed_application.py` | 293 | 98 | 5 | 95% | 129, 190, 265, 287, 289 |
| `src/genro_asgi/request.py` | 292 | 138 | 6 | 96% | 185, 190, 195, 249, 264, 292 |
| `src/genro_asgi/response.py` | 254 | 111 | 1 | 99% | 130 |
| `src/genro_asgi/streaming.py` | 111 | 34 | 1 | 97% | 72 |
| `src/genro_asgi/sse.py` | 142 | 52 | 0 | 100% | — |

Every uncovered spot is named individually in the sections below.

## `BaseApplication` — [application.py:86](../../../src/genro_asgi/application.py)

**Construction.** `code` and `mount` are peeled in `__init__`
(application.py:101-102) over the class attributes (application.py:95-97); an
empty `code` falls back to the class name lowercased (application.py:101) and a
`mount` of `None` falls back to the code (application.py:106). The fallback is
written `code if mount is None else mount` and never `mount or code`
(application.py:104-106): `mount=""` IS the site root, and truthiness would
silently move a root application to `/<code>`. Leftover kwargs raise `TypeError`
naming them (application.py:108-112) — the end of the D16 chain.

Proven by `test_contract.py:95` (code defaults to the class name), `:98` (mount
defaults to the code), `:103`
(`test_an_empty_mount_is_the_root_not_a_missing_value`), `:113` (class
attributes are the defaults) and `:57` (the leftover kwarg).

**Ownership channel.** `server` is a property over `_server`
(application.py:115-118) with a setter that raises `RuntimeError` on a second
assignment (application.py:120-125). Proven by `test_contract.py:67`, `:70`,
`:81` and `:87` (`test_serving_the_same_app_on_a_second_server_raises`).

**The configuration seam.** `config(path, default)` (application.py:127-150)
prefixes `applications.<code>.` and delegates to the server's own read door.
With no server, or a server built with no configuration, the call-site default
answers and its absence raises a `KeyError` naming the full path
(application.py:141-147). Proven by `test_config_env.py:310` (each application
reads only its own prefix), `:327`-`:341` (unconfigured and detached).

**The grammar.** `ApplicationGrammar` (application.py:71) declares one element,
`parameters` (application.py:80-83), and is the class attribute `grammar`
(application.py:97) the site recipe mounts by reference. Proven by
`test_config.py:905` (the app's own subtree read through the handler), `:919`
(the envelope attributes are the constructor kwargs), `:929` (an undeclared
child raises).

**The monitor contract.** `app_snapshot` (application.py:152-160) returns
class, code and mount; `app_panel` (application.py:162-172) returns
`{"panel": "generic"}`. A third member, `panel_source`, is **not declared
here**: the monitor reads it with `hasattr`/`getattr` off whatever the
contributor happens to expose
([monitor_section.py:192, :210](../../../src/genro_asgi/applications/server_sections/monitor_section.py)).

**Lifecycle and the ASGI callable.** `on_startup`/`on_shutdown` are no-ops
(application.py:174-178); `__call__` raises `NotImplementedError` naming the
class (application.py:180-182). Proven by `test_contract.py:161` and `:166`.
Nothing checks the ASGI callable at install time: `register_application` validates
only the code and the mount ([server.py:126-141](../../../src/genro_asgi/server.py)),
so a class that does not implement it mounts and fails at its first request.

**Two of the four declarations of the design do not exist.** `BaseApplication`
has no member by which an application says whether it can be moved while the
server runs, and none by which it says its own failure is survivable — searched
for `movable`/`removable`/`reversible`/`survivable`/`optional`/`tolerant` in
`src/`, none found. Both are consequences of the live configuration, which is
itself unbuilt: see [015 configuration](../015_configuration/status.md), "What
does NOT exist".

## `RoutedApplication` — [routed_application.py:96](../../../src/genro_asgi/routed_application.py)

`RoutedApplication(BaseApplication, RoutingClass)` — the app-side contract
composed with the genro-routes routing class.

**Construction.** Peels `db_name` (routed_application.py:122), runs the chain,
then plugs `auth` on its own router (routed_application.py:124). The `db_name`
property (routed_application.py:126-129) is read in production by the
`request.db` seam through `getattr` ([request.py:250](../../../src/genro_asgi/request.py))
and **`routed_application.py:129` is uncovered**: the database tests use
`BaseApplication` subclasses carrying a plain attribute
(`test_request.py:205`, `:221`), so no test reads the property.

**Two arming moments, and they are different mechanisms.** The `auth` plug is
the application's own and takes effect immediately in `__init__`
(routed_application.py:124). The **server's** plugins are armed later: the
`route` property (routed_application.py:143-156) calls
`server.arm_router(router)` on the first access made once a server owns the
app, guarded by `_armed`. An access made before attachment finds no
`arm_router` — `self.server` is `None` — so it skips the branch and **leaves
`_armed` untouched**, which is why the constructor's own use of `route` costs
nothing later. A composition whose server has no `PluginMixin` exposes no
`arm_router` at all, and then the application runs with `auth` alone.

`pydantic` and `openapi` are the ones a server arms, unconditionally:
`FIXED_PLUGINS` at
[plugin_mixin.py:61](../../../src/genro_asgi/plugin_mixin.py), and disabling
one in the `plugins` section is a configuration error, not an opt-out
(plugin_mixin.py:106-110).

Driven live on the recipe at the foot of [README.md](design.md): `_armed` is
`False` after the server has booted the application, `True` after the first
access that follows, and the router then carries
`['auth', 'openapi', 'pydantic']`.

**Sub-trees.** Every branch in the package goes through `add_branches`, and
**every one of them uses the instance form** — `{"name": …, "instance": …}`,
an already-built object — at four call sites:
[openapi.py:86](../../../src/genro_asgi/applications/openapi.py) and `:124`,
[server_app.py:185](../../../src/genro_asgi/applications/server_app.py),
[auth_section.py:97](../../../src/genro_asgi/applications/server_sections/auth_section.py).
Proven by `test_routed_application.py:321`
(`test_attached_instance_reachable_under_its_name`).

**The D25 migration is half done.** `attach_instance` has **zero occurrences**
in `src/` and `tests/`, so the retired call is gone. The form D25 named as its
replacement — `{"name", "cls", "params"}` — is used **nowhere**: `"cls"` has
zero occurrences in `src/` and `tests/` too. Those are the same four call sites
D25 listed for conversion in a later macro. See [design.md](decisions.md), open
friction S15.

`add_branches` accepts three mutually exclusive forms and **derives the timing
from the form**: `cls` + `params` is lazy (built on first traversal),
`instance` is eager (linked immediately), `alias` is a symlink
(`genro-routes/src/genro_routes/core/base_router.py:592-650`). There is no
`lazy` flag, so D25's note that "branch specs default to `lazy=False`",
verified against genro-routes 0.28.0, no longer describes the library.

**The dispatch.** `__call__` (routed_application.py:158-195), in order: refuse
without an owner (`:172-174`), build the `Request` and `await request.init()`
(`:175-176`), resolve the node with the router errors and the auth filters
(`:177-178`), build the callable (`:179`), run it on the loop or through
`server.run_sync` by the node's own nature (`:181-184`), map an invalid-argument
failure to `HTTPBadRequest` (`:185-187`), then answer.

| Branch | Code | Test |
|---|---|---|
| no owner → `RuntimeError` | routed_application.py:172-174 | `test_routed_application.py:238` |
| async handler on the loop | :181-182 | `test_routed_application.py:338` |
| sync handler through the pool | :183-184 | `test_routed_application.py:333` |
| invalid arguments → 400 | :185-187 | `test_routed_application.py:275`, `:280` |
| a `StreamingResponse` short-circuits | :188-190 | **none** |
| a result wrapper merges its metadata | :191-192 | `test_routed_application.py:230` |
| a plain value with the node metadata | :193-195 | `test_routed_application.py:222` |

**`routed_application.py:190` — the `return` that ends the streaming branch —
is uncovered: no test drives a handler answering with a `StreamingResponse`.**
The only production consumer of that path is
[inspector_section.py:101](../../../src/genro_asgi/applications/server_sections/inspector_section.py).

**Router errors.** `ROUTER_ERRORS` (routed_application.py:113-118) maps the
genro-routes string codes: `not_found`/`not_available` → `HTTPNotFound`,
`not_authenticated` → `HTTPUnauthorized`, `not_authorized` → `HTTPForbidden`.
Proven by `test_routed_application.py:215` (404 through the error middleware),
`:287` (anonymous → 401), `:293` (wrong tags → 403), `:298` (matching tag →
200).

**Auth filters.** `auth_filters` (routed_application.py:197-208) turns an
`Avatar` on `scope["auth"]` into a comma-separated `auth_tags`; no identity —
key absent or `None` — passes no filter, and the plugin still denies every
ruled entry. Proven by `test_routed_application.py:304` (an untagged entry
stays public without the middleware) and `:311` (a ruled entry is still
denied).

**The vehicle and the thread hook.** `make_callable`
(routed_application.py:210-236) reads `asyncio.iscoroutinefunction(node)` — and
not `inspect`'s, because on 3.11 genro-routes falls back to the asyncio
sentinel (routed_application.py:221-222). The sync branch wraps the call in a
`try/finally` that runs `route_cleanup` on the pool thread
(routed_application.py:230-236); the async branch never calls it.
`route_cleanup` (routed_application.py:238-247) is a no-op here. Proven by
`test_routed_application.py:368` (it runs on the handler thread), `:378` (it
runs when the handler raises), `:387` (the async path never cleans).

**Its production consumer is outside this repository**: the bridge fills it to
release the site's per-thread database connection
(`genropy-asgi/src/genropy_asgi/proxy/genropy_proxy.py:69`).

**Argument reconciliation.** `bind_kwargs` (routed_application.py:249-274)
starts from `request.handler_kwargs()`, and when a hydrated body dict meets a
handler declaring scalar parameters it spreads the dict over them
(`:272-273`); the body is kept whole when the handler declares `body_data` or
accepts `**kwargs` (`:270-271`). Proven by `test_routed_application.py:252`
(spread) and `:260` (kept whole).

`spread_over_params` (routed_application.py:276-293) is the shared half, and
its second caller is the MCP engine
([mcp.py:150](../../../src/genro_asgi/applications/mcp.py)) — the same method
serving a second wire dialect, per Invariant 9.

**Three uncovered guards, and why.** `routed_application.py:265` and `:287`
are the `fields is None` branches — reachable only where the `pydantic` plugin
is absent, which on any `AsgiServer` it never is (`FIXED_PLUGINS`). `:289` is
`spread_over_params`'s own `**kwargs` guard, unreachable from `bind_kwargs`
(which already returned at `:270`) and live only for the MCP caller, which does
not pre-check.

**Request injection is not here.** The base `bind_kwargs` injects nothing. The
only injection in the package is
[server_app.py:200-215](../../../src/genro_asgi/applications/server_app.py),
which binds the live `Request` to a declared `_request` parameter — and it is
the administrative application's override, inherited by nothing a consumer
writes.

## `Request` — [request.py:61](../../../src/genro_asgi/request.py)

Slotted per D18 (request.py:64-80). Built by the owning application
(routed_application.py:175) with `server=` and `application=`; the `Response`
is constructed with it and bound back (request.py:104), proven by
`test_request.py:85`.

**Parsing, once.** `init()` (request.py:151-169) reads the request by itself —
headers, cookies, query, and the body drained from `receive` until `more_body`
is false (`read_body`, `:201`), decoded by content-type (`decode_body`, `:224`;
`multipart/form-data` into fields and `UploadedFile` parts, `:247`) — then
derives the TYTX mode from `x-tytx-transport` (`:162-165`), the request id from
`x-request-id` or a fresh uuid4 (`:167`) and the client correlation id from
`x-external-id` (`:169`). genro-tytx is used only as a deserializer
(`from_tytx`, `from_qs`); nothing is imported from `genro_tytx.http` (landed
2026-09-02). Proven by
`test_request.py:67`, `:90` (numeric id headers coerced to `str`), `:141`,
`:145`, `:149`, `:154`.

**Handler kwargs.** `handler_kwargs()` (request.py:267-289): the query is the
base; a form body is merged and wins on a clash (`:282-284`); a hydrated body
becomes `body_data` (`:288`); opaque bytes become `body_raw` (`:286`); an empty
body adds nothing (`:279-280`). Proven by `test_request.py:101`, `:111`,
`:124`, `:134`.

**Identity and session ride the scope.** `avatar()` (request.py:209-220) reads
`scope["auth"]` for the root slot and delegates any other key to the session;
`auth_tags` (request.py:222-226); `session` (request.py:228-231). Proven by
`test_request.py:161`, `:167`, `:172`, `:178`, `:182`.

**The database seam.** `db` (request.py:234-258) resolves
`server.databases[app.db_name or "default"]` once and registers
`handler.closeConnection` as a request cleanup on the current registry item
(`:255-257`); `get_db(name)` (request.py:260-265) looks up without registering.
Proven by `test_request.py:252`, `:264`, `:275`, `:283`, `:294`.

**Three public properties with no reader anywhere.** `created_at`
(request.py:182-185), `age` (request.py:187-190) and `scope`
(request.py:192-195) are the three uncovered lines, and the reason is that
`grep` finds no consumer in `src/`, in `tests/`, or in the genropy-asgi bridge.
`_created_at` is still stamped on every request (request.py:103). The other
uncovered lines are the two `server is None` early returns (`:249`, `:264`) and
`__repr__` (`:292`).

**A body without a `content-type` header is read and kept raw** (friction S4,
settled 2026-09-02). `read_body` (request.py:201) drains `receive` whatever
the headers say; the bytes reach the handler as `body_raw`. Proven by
`test_request.py:200`; the chunked read by `:206`.

## `Response` — [response.py:56](../../../src/genro_asgi/response.py)

One flat slotted class (response.py:70), no subclass hierarchy, buffered:
`__call__` (response.py:148-157) sends exactly `http.response.start` and one
`http.response.body`. Proven by `test_response.py:105`, `:109`, `:118`.

**Type dispatch.** `set_result` (response.py:191-227): mapping/list → JSON, or
the request's TYTX transport when it is in TYTX mode (`:201-211`); `Path` →
file bytes (`:212-214`); `bytes` → as-is (`:215-217`); `str` → text
(`:218-220`); `None` → empty (`:221-223`); anything else → its `str`
(`:224-226`). A `media_type` in the node metadata overrides the default
(`:200`). All nine paths are proven: `test_response.py:172`, `:178`, `:183`,
`:191`, `:197`, `:203`, `:209`, `:214`, `:219` (headers replaced, not
duplicated). The TYTX branch: `test_response.py:229`, `:237`, `:244`, `:250`,
`:256`.

**Error mapping.** `set_error` (response.py:241-254): an `HTTPException`
carries its own status (`:248-249`); otherwise `ERROR_MAP`
(response.py:76-81) gives 400 for `ValueError`/`TypeError`, 404 for
`FileNotFoundError`, 403 for `PermissionError`, and anything else is 500 and
logged (`:250-253`). Proven by `test_response.py:264` through `:311`.

**Headers and cookies.** `set_cookie` (response.py:163-189) URL-encodes the
value and appends the named attributes; `SameSite` defaults to `lax` and is
omitted when set to `None`. Proven by `test_response.py:134`, `:140`, `:158`,
`:164`.

**`response.py:130` is unreachable, not merely untested.** It is the
`effective is None` guard of `_get_content_type`, and both call sites exclude
it: `__init__` calls it only when the media type is not `None`
(response.py:109-113), and `_update_content_headers` is called only from
`set_result`, which always assigns one. The class attribute the guard exists
for (`media_type`, response.py:72) is never set by anything.

## `StreamingResponse` — [streaming.py:41](../../../src/genro_asgi/streaming.py)

A sibling of `Response`, not a subclass, slotted (streaming.py:52) and with
**no `set_result`** — asserted as such by `test_streaming.py:111`.

`__call__` (streaming.py:95-111) sends one `http.response.start`, one
`http.response.body` with `more_body=True` per chunk, and a terminal empty body
with `more_body=False` — never omitted, even for an empty iterator. Proven by
`test_streaming.py:58`, `:66`, `:72`. Headers and status:
`test_streaming.py:80`, `:85`, `:90`, `:97`.

**`streaming.py:72` — headers given as a mapping rather than a list — is
uncovered.** `Response` has the same branch and it is covered
(`test_response.py:84`).

## `SseStream` — [sse.py:50](../../../src/genro_asgi/sse.py)

Slotted (sse.py:59), bound to one source as a dual parent-child (sse.py:78).
100% covered.

`frame` (sse.py:82-93) writes the `id:`/`event:`/`data:` lines, splitting
`data` across lines on newlines and JSON-encoding a non-string payload; each
record ends with a blank line. Proven by `test_sse.py:43`, `:47`, `:51`, `:55`,
`:59`.

`__aiter__` (sse.py:95-130) emits an optional `retry:` once, then framed
events; a source silent past `keepalive_seconds` (default 15.0, sse.py:46)
yields `: keepalive` while the pending read is **shielded** across the timeout
(sse.py:115-119). Proven by `test_sse.py:67`, `:72`, `:79`, `:88`, `:99`,
`:104`.

**Consumer departure is handled and tested.** The `finally`
(sse.py:126-130) cancels the pending read and awaits it, so the source's own
`finally` runs and a subscription is released. Proven by `test_sse.py:111`
(`test_source_finalized_on_cancel`).

`response()` (sse.py:132-142) wraps the stream with `text/event-stream`,
`cache-control: no-cache` and `connection: keep-alive`. Proven by
`test_sse.py:140`.

## No application answers a WebSocket

`on_websocket` has exactly one definition in the package,
[server.py:253](../../../src/genro_asgi/server.py), and it consumes the
connect and closes with code 1000. No composition overrides it and no code
path hands a socket to an application. `RoutedApplication.__call__` does not
read `scope["type"]` at all: it is only ever called for `http`.

## Test inventory

Every test of this entry is a **contract test** — `tests/test_*.py`. `tests/x/`
still contains only `__init__.py`.

| File | Items | Covers |
|---|---|---|
| `tests/test_routed_application.py` | 23 | dispatch, body binding, argument errors, auth, sub-trees, execution vehicle, the thread hook |
| `tests/test_request.py` | 22 | parsing, handler kwargs, identity metadata, auth/session accessors, the db seam |
| `tests/test_response.py` | 40 | construction, the ASGI wire, headers and cookies, the type dispatch, TYTX, the error map |
| `tests/test_streaming.py` | 9 | the message sequence, headers, and that `Response` stayed untouched |
| `tests/test_sse.py` | 13 | framing, iteration, the heartbeat, consumer departure, the response wrapper |

The app-side contract itself is proven in `tests/test_contract.py` (21 items,
shared with [010 server](../010_server/README.md)), and `tests/throwaway_app.py` is the
D7 phase-0 fixture kept out of `src/`.

Every request in `test_routed_application.py` drives a real `AsgiServer`
composition at the ASGI level — no uvicorn, but the middleware chain armed and
sync handlers crossing the server pool.

## The subclasses that live elsewhere

Four applications ship in the package and none of them is this entry's
subject; they are listed so the class chain is visible in one place.

| Class | Base | Entry |
|---|---|---|
| `OpenApiApplication` ([openapi.py:64](../../../src/genro_asgi/applications/openapi.py)) | `RoutedApplication` | [openapi](openapi/README.md) |
| `McpApplication` ([mcp.py:274](../../../src/genro_asgi/applications/mcp.py)) · `McpOpenApiApplication` (`:328`) | `RoutedApplication` · `OpenApiApplication` | [mcp](mcp/README.md) |
| `ServerApplication` ([server_app.py:115](../../../src/genro_asgi/applications/server_app.py)) | `OpenApiApplication` | [090 server-application](../090_server-application/README.md) |
| `SpaApplication` ([spa_app.py:228](../../../src/genro_asgi/applications/spa_app.py)) | `RoutedApplication` | [20_spa/010 spa-application](../../20_spa/010_spa-application/README.md) |

`SpaApplication` is the only one that declares a grammar of its own
(`SpaApplicationGrammar`, spa_app.py:103); the other three inherit
`ApplicationGrammar`.

## Decisions that shaped what exists

- **D7** (SPECIFICATION.md:93) — the app-side contract born in phase 0 and
  defined by its tests. Holds; the member it names is `mount_name`, which the
  code does not have — see [design.md](decisions.md), open friction S1.
- **D16** (SPECIFICATION.md:217) — cooperative init. Held by
  `BaseApplication.__init__` and `RoutedApplication.__init__`.
- **D18** (SPECIFICATION.md:249) — slots on high-cardinality objects.
  `Request`, `Response`, `StreamingResponse` and `SseStream` are slotted; the
  application classes are not.
- **D23 wave ruling** (SPECIFICATION.md:413) — handlers are pure, and one
  declaring the live request gets it from `bind_kwargs`. The purity holds; the
  injection exists only on `ServerApplication` and under a different name — see
  [design.md](decisions.md), open friction S2.
- **D25** (SPECIFICATION.md:436) — declarative branches, `attach_instance`
  retired. **Half held**: the retired call has zero occurrences left, and the
  `cls` + `params` form that was to replace it has zero occurrences too — see
  [design.md](decisions.md), open friction S15.
- **D26** (SPECIFICATION.md:456) — `pydantic` and `openapi` are fixed server
  structure. Implemented as `FIXED_PLUGINS` (plugin_mixin.py:61).
- **Invariant 2** (SPECIFICATION.md:668) — thread-correct teardown. Implemented
  as `route_cleanup`, delivered by `0dff4ed`.
- **Invariant 3** (SPECIFICATION.md:671) — a denied node answers natively.
  Implemented as auth filters on the resolution, with 401/403 restored by
  `5b567a3`.
- **Invariant 10** (SPECIFICATION.md:688) — never routing as registry. Enforced
  by D25.
- **`53b4e38`** (2026-07-21, core 1c) — request, response, plugins and the
  OpenAPI/MCP applications. **`c360f60`** (2026-07-24, core 1e) — SSE over
  streaming. **`a1a8f7e`** (2026-07-25) — `code` + `mount`.
