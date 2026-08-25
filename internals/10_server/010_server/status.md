# Server — current state

**Version**: 0.3 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

What exists TODAY on `develop`. Every claim below carries its `file:line` or
the test that proves it. Coverage figures are from the full suite
(`pytest tests/`, 1463 passed) run on 2026-08-22 at `caf9dd2`.

## The modules

| Module | Lines | Stmts | Miss | Cov | Uncovered |
|---|---|---|---|---|---|
| `src/genro_asgi/server.py` | 280 | 118 | 1 | 99% | 211 |
| `src/genro_asgi/asgi_server.py` | 281 | 93 | 3 | 97% | 279-281 |
| `src/genro_asgi/lifespan.py` | 84 | 35 | 0 | 100% | — |
| `src/genro_asgi/pool.py` | 126 | 41 | 0 | 100% | — |
| `src/genro_asgi/request_registry.py` | 164 | 65 | 1 | 98% | 116 |
| `src/genro_asgi/types.py` | 33 | 8 | 0 | 100% | — |

The three uncovered spots are named individually below; none is a behaviour
without a test, except `asgi_server.py:279-281`.

## `BaseServer` — [server.py:65](../../../src/genro_asgi/server.py)

**Composition.** `applications`, `default` and `max_threads` are peeled in
`__init__` (server.py:76-78); any leftover kwarg raises `TypeError` naming it
(server.py:79-83) — the end of the D16 cooperative chain. Proven by
`test_contract.py:61` (`test_server_leftover_kwarg_raises_naming_it`) and
`test_contract.py:51` for the chain itself.

Applications are held in two indexes: `_applications` by `code`, `_by_mount`
by mount (server.py:85-86). `register_application` (server.py:126-141) assigns
`app.server = self`, then raises `ValueError` on a claimed code
(server.py:135-136) or a claimed mount (server.py:137-138). Proven by
`test_contract.py:124` and `test_contract.py:128`.

`default` is validated at construction: a code naming no served application
raises `ValueError` (server.py:95-96), proven by `test_contract.py:142`.

**Ownership channel.** One direction, exactly once — the app-side setter
raises `RuntimeError` on a second assignment
([application.py:120-125](../../../src/genro_asgi/application.py)). Proven by
`test_contract.py:70`, `:81` and `:87`
(`test_serving_the_same_app_on_a_second_server_raises`).

**Accessors.** `applications` (server.py:98), `root_application` — the app at
mount `""`, **`None` when there is none** (server.py:103-111),
`default_application` — `None` unless `default` was declared
(server.py:113-120), `application_at(mount)` (server.py:122-124).
`test_contract.py:137` proves a server of mounts only has
`root_application is None`.

**Demux.** Four branches in `demux()` (server.py:213-239), exactly as drawn
in [README.md](design.md):

| Branch | Code | Test |
|---|---|---|
| segment matches a mount → app, segment stripped | server.py:228-232 | `test_demux.py:81` |
| else the root application, path unchanged | server.py:233-235 | `test_demux.py:69`, `:75` |
| else `/` with a `default` → 307 | server.py:236-238 | `test_demux.py:151` |
| else 404 | server.py:239 | `test_demux.py:143`, `:147` |

The forwarded path is rebuilt from the same remainder used to find the
segment, so `//api/x` forwards `/x` (server.py:226-231, proven by
`test_demux.py:95`). `redirect_to_default` (server.py:241-251) emits **307**
and carries the query string over (proven by `test_demux.py:156`).
`test_demux.py:160` proves an unclaimed path is still a 404 even when a
`default` is declared.

**ASGI dispatch.** `__call__` (server.py:186-211) branches on `scope["type"]`:
`http` registers the request, demuxes, and in a `finally` runs the item's
cleanups and unregisters it (server.py:195-202); `websocket` calls
`on_websocket` (server.py:203-204); `lifespan` runs the handler and then tears
the pool down (server.py:205-209). **`server.py:211` — the `ValueError` on an
unsupported scope type — is the single uncovered line of the module**: no test
drives a fourth scope type.

`on_websocket` (server.py:253-260) is the empty socket: consume the connect,
close with code 1000. Proven by `test_demux.py:167`.

**Thread pool seam.** `run_sync` (server.py:169-176) delegates to
`WorkPool.run`. `pool`, `requests`, `lifespan`, `databases` are plain
properties over the members built in `__init__` (server.py:88-91).

**Base answers.** `authenticate()` and `session()` both return `None`
(server.py:178-184) — D6 by construction: the base never learned about the
chain.

**Databases.** `databases` and `add_database(code, handler)` live on the base
(server.py:143-152); a claimed code raises `ValueError` (server.py:150-151).
The handlers themselves belong to [065 db](../065_db/README.md).

**Boot.** `serve(host, port)` builds `uvicorn.Config`/`uvicorn.Server` and
runs it, blocking (server.py:272-279); `uvicorn_server` exposes the built
server so a caller booting in a background thread can read the bound port
(server.py:262-270). `test_demux.py:38` and `:56` boot a real uvicorn this
way.

## `Lifespan` — [lifespan.py:42](../../../src/genro_asgi/lifespan.py)

Constructed with the server it manages, held as a dual parent-child
(`self.server`, lifespan.py:45-47) — proven by `test_lifespan.py:89`.

`__call__` (lifespan.py:49-59) drives the protocol: `lifespan.startup` →
`startup()` → `startup.complete`; `lifespan.shutdown` → `shutdown()` →
`shutdown.complete`, then returns.

`startup()` runs `on_startup` in registration order (lifespan.py:61-64);
`shutdown()` runs `on_shutdown` in **reverse** order (lifespan.py:66-69).
Proven by `test_lifespan.py:96` and `:112`.

Hooks may be sync or async, detected with `inspect.iscoroutinefunction` at
call time (lifespan.py:79-82). A raising hook is logged and the sequence
**continues** (lifespan.py:83-84); proven by `test_lifespan.py:130` (sync
startup) and `:147` (async shutdown). 100% covered.

## `WorkPool` — [pool.py:41](../../../src/genro_asgi/pool.py)

One `ThreadPoolExecutor` per server, held as a dual parent-child
(pool.py:51-52). Threads are named `genro-pool*` (pool.py:98) so a test can
assert a handler ran off the loop — `test_pool.py:38` and `:43` do exactly
that.

**Lazy provisioning.** The executor is built on first access to the
`executor` property (pool.py:93-99), never at boot; `provisioned`
(pool.py:58-61) reports whether it exists. Proven by `test_pool.py:62`.
`shutdown()` (pool.py:117-126) is a no-op when unprovisioned and resets the
lazy slot so a later dispatch re-provisions — proven by `test_pool.py:68`.

**Context.** `run()` copies the caller's context into the worker thread
(pool.py:110-113), so a sync handler sees the loop-side ContextVars. Proven
by `test_pool.py:101` (`test_sync_handler_sees_its_own_current_request`).

**Gauges.** `metrics` returns `{"total": 0, "busy": 0}` until provisioned
(pool.py:78-79) and the resolved pair after (pool.py:80). `total` is frozen at
provision from our own argument resolution, mirroring the stdlib default
(pool.py:94-95); `busy` counts calls entered and not yet exited
(pool.py:111-115) — **demand, not slots held**, so it can exceed `total`. All
five behaviours are covered: `test_pool.py:120`, `:125`, `:130`, `:136`,
`:146`. 100% covered.

## `RequestRegistry` / `RegisteredRequest` — [request_registry.py:122](../../../src/genro_asgi/request_registry.py)

**Single writer.** The server is the only writer: `register(scope)` on entry
(request_registry.py:149-155), `unregister(item)` on exit
(request_registry.py:157-160), both called from `BaseServer.__call__`
(server.py:196, :202).

**The item.** `RegisteredRequest` is slotted (request_registry.py:64) per D18,
carrying `request_id`, `scope_type`, `path`, `started_at` — proven by
`test_request_registry.py:105`. `_cleanups` is lazy: allocated only when the
first callback is queued (request_registry.py:95-97), so an item that queues
none pays nothing.

**Current request.** A `ContextVar` on the registry **instance**, never at
module level (request_registry.py:135-137). `register` keeps the reset token
and `unregister` resets it (request_registry.py:154, :160). Two concurrent
requests each see their own `current` while `in_flight` counts both — proven
by `test_request_registry.py:123`, with `snapshot()` listing them
(`:141`) and the registry empty after both complete (`:154`).

**Cleanups.** `add_cleanup` queues (request_registry.py:93-97);
`run_cleanups` drains LIFO and isolates each callback's exception
(request_registry.py:99-113). Proven by `test_request_registry.py:184`
(LIFO), `:192` (one failure does not stop the rest), `:205` (it is logged),
`:221` (no-op when empty). The error path is covered end to end: a request is
unregistered even when the handler raises (`:167`) and the cleanups still
drain (`:174`).

The one production consumer today is `request.db` closing its connection
([request.py:257](../../../src/genro_asgi/request.py)).

**`request_registry.py:116` — `__repr__` — is the module's single uncovered
line.**

## `AsgiServer` — [asgi_server.py:91](../../../src/genro_asgi/asgi_server.py)

The shipped mono-process composition (D22). MRO, in order:
`CommunicationMixin, AuthMixin, SessionMixin, MiddlewareMixin, PluginMixin,
StorageMixin, TaskMixin, BaseServer` (asgi_server.py:91-100). `TaskMixin`
sits after `StorageMixin` because it needs `server.storage`, and before
`BaseServer` because its lifespan hook must wrap the base `Lifespan`
(asgi_server.py:20-23).

Kwargs peeled here (asgi_server.py:113-121): `config`, `host`, `port`,
`external_url` (trailing slash stripped), `server_app`. Everything else flows
down the D16 chain.

`__init__` then, in order (asgi_server.py:122-126): runs the chain, registers
the automatic `_server` app, checks the OIDC precondition, registers the
configured databases over the live server.

- `_build_config` (asgi_server.py:128-148) accepts a ready handler, a
  `config.py` path, a recipe class or instance; a bare `AsgiServer(...)` has
  `config is None`.
- `_configured_kwargs` (asgi_server.py:150-178) maps one read-door helper per
  section; **applications are instantiated here**, so a recipe error is a boot
  error.
- `_register_server_app` (asgi_server.py:205-215) is idempotent — it only
  registers when `_server` is absent.
- `_check_oidc_external_url` (asgi_server.py:217-236) raises `ValueError` when
  a provider is configured without `external_url`. Covered by
  `test_oidc.py`.
- `login_enabled` (asgi_server.py:238-249) reports whether the `_server` app
  carries a registered auth method; `ErrorMiddleware` reads it.

**`asgi_server.py:279-281` — the host/port resolution inside
`AsgiServer.serve()` — is uncovered: no test calls it.** The precedence it
implements (explicit argument, else the configured value, else `127.0.0.1`
and port 0) is asserted nowhere.

## Test inventory

Every test of the server is a **contract test** — `tests/test_*.py`. `tests/x/`
contains only `__init__.py`: there are no implementation/edge tests at all.

| File | Items | Covers |
|---|---|---|
| `tests/test_contract.py` | 21 | cooperative chain, ownership channel, application identity, server contract |
| `tests/test_demux.py` | 12 | the four branches, mounts-only server, empty websocket |
| `tests/test_lifespan.py` | 5 | handler wiring, ordering, error isolation |
| `tests/test_pool.py` | 12 | dispatch, max_threads, provisioning, context, gauges |
| `tests/test_request_registry.py` | 11 | the item, concurrency, error path, cleanups |

`tests/throwaway_app.py` is the D7 phase-0 fixture: a `BaseApplication` with
one sync route, one async route and one that raises, deliberately kept out of
`src/`.

## Decisions that shaped what exists

- **D2** (SPECIFICATION.md:42) — what the base owns. Honoured for the pool,
  the lifespan, the registry and the `authenticate()`/`session()` base
  answers; **amended** for the channel by D17 (which moved it to
  `CommunicationMixin`, verified at
  [communication.py:55](../../../src/genro_asgi/communication.py)); its
  "primary app, always present" clause is **contradicted** by the shipped code
  — see [design.md](decisions.md), open friction S1.
- **D3** (SPECIFICATION.md:61) — one demux rule for every server. The single
  rule survives; the shipped form has four branches, not two — see
  [design.md](decisions.md), open friction S2.
- **D5** (SPECIFICATION.md:73) — one request registry in the base. Duty (2),
  the in-flight picture, is implemented here; duty (1) is not — see
  [design.md](decisions.md), open friction S3.
- **D7** (SPECIFICATION.md:93) — phase 0 is the base server plus the app-side
  contract, exercised by a throwaway app; the websocket socket left empty.
  Both hold.
- **D16** (SPECIFICATION.md:217) — cooperative init. Held by every class
  listed above.
- **D18** (SPECIFICATION.md:249) — slots only on high-cardinality objects.
  `RegisteredRequest` is slotted; `BaseServer`, `WorkPool`, `Lifespan` and
  `RequestRegistry` are not.
- **D22** (SPECIFICATION.md:351) — core is the complete mono-process async
  server. `AsgiServer` is that composition.
- **`a1a8f7e`** (2026-07-25, `refactor!: application identity (code + mount)
  and the four-branch demux`) — the source of `code`/`mount`, the fixed
  application set, and all four demux branches. Recorded in the commit
  message only.

## What §4 of the design would stand on

The live-configuration mechanism the design describes needs no new library:
the pieces exist and are unused here.

- The configuration tree is a `SourceBag`, a `Bag` subclass (genro-builders
  `src/genro_builders/builder/source_bag.py:636`), reachable through the
  handler that owns it (`ConfigHandler.builder`).
- `Bag.subscribe(subscriber_id, update=…, insert=…, delete=…, any=…,
  transaction=…)` exists (genro-bag `src/genro_bag/bag/_events.py:161`), and a
  write can fire or suppress the trigger (`set_item(..., do_trigger=…)`).
- Nothing in genro-asgi uses either: `apply_configuration` has zero
  occurrences in `src/` and `tests/`, and `config/handler.py` declares no
  mutator — the handler is a read door only.

So what is absent is the mutator on `_server` and the subscriber that
reacts, not the machinery underneath.

