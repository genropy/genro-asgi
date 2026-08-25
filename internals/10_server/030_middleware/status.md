# Middleware — current state

**Version**: 0.3 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

What exists TODAY on `develop`. Every claim below carries its `file:line` or
the test that proves it. Coverage figures are from the full suite
(`pytest tests/`, 1463 passed) run on 2026-08-23 at `eb2f840`.

## The modules

| Module | Lines | Stmts | Miss | Cov | Uncovered |
|---|---|---|---|---|---|
| `src/genro_asgi/middleware/__init__.py` | 112 | 31 | 0 | 100% | — |
| `src/genro_asgi/middleware/base.py` | 162 | 66 | 3 | 95% | 81-82, 125 |
| `src/genro_asgi/middleware/errors.py` | 183 | 79 | 1 | 99% | 130 |
| `src/genro_asgi/middleware/cors.py` | 141 | 73 | 3 | 96% | 39, 99, 105 |
| `src/genro_asgi/middleware/session.py` | 137 | 44 | 0 | 100% | — |
| `src/genro_asgi/middleware/authentication.py` | 48 | 10 | 0 | 100% | — |
| `src/genro_asgi/middleware/logging.py` | 89 | 41 | 6 | 85% | 65, 71, 83-86 |
| `src/genro_asgi/middleware/wellknown.py` | 53 | 17 | 0 | 100% | — |

## `MiddlewareMixin` — [middleware/\_\_init\_\_.py:80](../../../src/genro_asgi/middleware/__init__.py)

**Composition.** Peels `middleware` and `middleware_registry` (`:90-91`), runs
the chain, merges the extras over `default_registry()` (`:93-95`), and builds
the chain **once** around `_base_call` (`:96`). Composed before `BaseServer` in
`AsgiServer` ([asgi_server.py:91-100](../../../src/genro_asgi/asgi_server.py)).

`_base_call` (`:103-105`) is the innermost target: it delegates to the next
`__call__` in the MRO, which is the base dispatch.

**Only HTTP walks the chain.** `__call__` (`:107-112`) sends every other scope
type straight to `super().__call__`. Proven by `test_middleware.py:174`
(`test_lifespan_scope_bypasses_the_chain`).

**A composition without the mixin has no chain at all** — not a disabled one.
Proven by `test_middleware.py:197`
(`test_plain_base_server_lacks_the_mixin_attrs`).

`default_registry()` (`:68-78`) returns a **fresh** mapping of the six per
call: `errors`, `wellknown`, `logging`, `cors`, `auth`, `session`. It lives in
the package module rather than in `base.py` because `base.py` cannot import
the concrete classes without a cycle (`:33-35`).

## The chain — [base.py:128](../../../src/genro_asgi/middleware/base.py)

`build_chain(config, innermost, server, registry)` (base.py:128-162) takes
every input explicitly. It refuses a configured name the registry does not
know with a `ValueError` naming it (`:141-143`, proven by
`test_middleware.py:141`); a registry entry the config does not name follows
its own `middleware_default` (`:147-149`); a dict value becomes the
constructor options (`:151-152`); a falsy value drops the layer (`:155-156`,
proven by `test_middleware.py:145`). It then sorts by `middleware_order` and
wraps innermost-out (`:157-161`), so the lowest number is outermost. Proven by
`test_middleware.py:126` (`test_chain_invokes_middlewares_in_order`).

**The declared order, as shipped:**

| Layer | `middleware_order` | `middleware_default` | Declared at |
|---|---|---|---|
| `ErrorMiddleware` | 100 | **True** | errors.py:71-72 |
| `WellKnownMiddleware` | 150 | False | wellknown.py:39-40 |
| `LoggingMiddleware` | 200 | False | logging.py:40-41 |
| `CORSMiddleware` | 300 | False | cors.py:46-47 |
| `SessionMiddleware` | 400 | False | session.py:58-59 |
| `AuthMiddleware` | 450 | False | authentication.py:42-43 |

Errors is the only one on by default. Driven live on the recipe at the foot of
[README.md](design.md), walking `server.middleware_chain` outwards gives
exactly that order.

**Both ends at construction.** `BaseMiddleware.__init__`
(base.py:98-106) stores the next app and the owning server and refuses an
unclaimed option by name (`:102-106`, proven by `test_middleware.py:205`).
`app` and `server` are plain properties (`:108-116`); nothing walks wrappers.
`base.py:125` — the `NotImplementedError` of the abstract `__call__` — is
uncovered.

**Two shared readers.** `headers_dict(scope)` (base.py:51-64) parses the ASGI
headers once and caches them at `scope["_headers"]`; proven by
`test_middleware.py:114` and `:118`. `cookie_value(scope, name)`
(base.py:67-84) reads one cookie **pair by pair**, so a malformed sibling does
not cost the request its well-formed cookies — **`base.py:81-82`, the
`CookieError` branch that skips a bad pair, is uncovered**: no test ships a
malformed cookie.

## `ErrorMiddleware` — [errors.py:68](../../../src/genro_asgi/middleware/errors.py)

**The outermost try/except.** `__call__` (errors.py:74-93) wraps `send` to
record whether `http.response.start` has passed (`:78-82`), runs the chain, and
on an exception either re-raises (when the answer had started, `:87-91`) or
builds the response (`:92-93`). Proven by `test_middleware_std.py:191`
(`test_error_after_start_is_reraised_not_double_sent`).

**Error responses.** `_error_response` (errors.py:140-166): a `Redirect`
becomes its status plus a `Location` (`:142-146`, proven by
`test_middleware_std.py:175`); an `HTTPException` becomes its own status
(`:148-155`, proven by `:158`); anything else is logged and becomes a 500 whose
body never carries the internal message (`:156-164`, proven by `:167` and
`:246`). An exception's own headers are forwarded onto the response
(`:180-183`, proven by `:183`).

**Content negotiation.** `_wants_json` (errors.py:168-178): no `Accept`, or an
`Accept` naming `text/html`, keeps `text/plain`; `application/json` or `*/*`
gets the JSON document. Proven by `test_middleware_std.py:213`, `:222`, `:230`,
`:238`.

**Challenge negotiation.** `_response_for` (errors.py:95-99) diverts a 401 to
`_challenge_response` only when `server.login_enabled` (`:101-107`).
`_challenge_response` (errors.py:109-125) answers a browser navigation with a
302 to `/_server/login_page` carrying a `safe_next_path`-validated `next`, and
anything else with the bare 401 plus a `{"login_url": …}` body. Proven by
`test_middleware_std.py:262`, `:270`, `:279` (login off leaves the 401 alone),
`:287` (path and query survive the validation).

**`errors.py:130` is uncovered**: the early return of `_is_browser_navigation`
for a non-GET method. No test sends a POST that ends in a 401 while a login
surface is active.

**The response class's own error table is never consulted here.**
`set_error` is called at errors.py:151, inside the `isinstance(exc,
HTTPException)` branch — and `Response.set_error`
([response.py:248-251](../../../src/genro_asgi/response.py)) reads its
`ERROR_MAP` only when the exception is **not** an `HTTPException`. Searched:
`set_error` has exactly one production caller in the package, this one. So the
mapping of `ValueError`/`TypeError` to 400, `FileNotFoundError` to 404 and
`PermissionError` to 403 is reached by `tests/test_response.py` alone
(`:282`, `:288`, `:291`, `:296`, `:301`). See [design.md](decisions.md), friction
S1.

## `WellKnownMiddleware` — [wellknown.py:36](../../../src/genro_asgi/middleware/wellknown.py)

Raises `HTTPNotFound` for `/robots.txt`, `/sitemap.xml` and anything under
`/.well-known/` (wellknown.py:45-53), and delegates everything else. It builds
no response: the raise travels out to `ErrorMiddleware`. Proven by
`test_middleware_std.py:67` and `:72`. 100% covered.

## `CORSMiddleware` — [cors.py:43](../../../src/genro_asgi/middleware/cors.py)

Preflight headers are precomputed in `__init__`; `_response_headers`
(cors.py:90-108) builds the per-response set, echoing the origin with a `Vary`
when credentials are allowed and answering nothing for an origin that is not
allowed. Proven by `test_middleware_std.py:82` (preflight), `:94` (a simple
GET), `:102` (credentialed wildcard echoes with `Vary`), `:112` (a foreign
origin is refused), `:122` (a disallowed preflight is a 400).

**Three uncovered statements.** `cors.py:39` is the branch of the option parser
that passes a **list** through instead of splitting a comma-separated string —
every test configures strings. `cors.py:99` and `:105` are the
`allow_credentials` and `expose_headers` additions on the non-wildcard path.
See [design.md](decisions.md), friction S7.

## `SessionMiddleware` — [session.py:55](../../../src/genro_asgi/middleware/session.py)

Reads the cookie (`session.py:76-78`), reconnects the session it names or
creates a new anonymous one, and leaves it at `scope["session"]`
(`session.py:108-137`). The `Set-Cookie` is added **only on the branch that
created the session** (`:129-136`); `Max-Age` is the TTL times
`COOKIE_LIFETIME_FACTOR = 24` (session.py:52, `:80-95`), because the
server-side TTL slides with every request while the cookie's does not.

`_write_back` (session.py:97-106) saves only a session that is dirty. Proven by
`test_middleware_std.py:364` (a read-only request does not save), `:370` (a
mutating one saves once), `:376` (the flag is cleared). 100% covered.

## `AuthMiddleware` — [authentication.py:39](../../../src/genro_asgi/middleware/authentication.py)

Ten statements: it calls `server.authenticate(scope)` and stores the answer at
`scope["auth"]` (authentication.py:45-48). Nothing else. 100% covered.

Its order — 450, inside the session's 400 — is what makes the session-based
identity fallback reachable (authentication.py:21-23).

## `LoggingMiddleware` — [logging.py:37](../../../src/genro_asgi/middleware/logging.py)

One line in, one line out, with method, path, status and elapsed milliseconds
(logging.py:57-89). Proven by `test_middleware_std.py:312`
(`test_records_one_entry_per_request`).

**Six uncovered statements, and two of them matter.** `logging.py:65` is the
query-string branch; `:71` the `include_headers` debug line; **`:83-86` is the
whole exception path** — the log line written when the wrapped chain raises,
before re-raising. Nothing tests that a failing request is logged.

**`level` names the severity, not a threshold.** `__init__` resolves it with
`getattr(logging, level.upper(), logging.INFO)` (logging.py:51) and passes it
to `self.logger.log(self._level, …)` (`:71`, `:89`), so `level="WARNING"` makes
every access line a warning rather than quietening the log. Driven live: the
values `WARNING` and `debug` resolve as expected, and **`verbose` and
`nonsense` both silently become INFO**. See [design.md](decisions.md), frictions
S4 and S5.

## The configuration section

`middleware` is declared at
[elements.py:141-154](../../../src/genro_asgi/config/elements.py) with **six
keyword parameters and no `**kwargs`** — one per core middleware. So a name
outside the six is refused by the grammar itself, and the element's docstring
says so: "one registered through `middleware_registry=` is not configurable
here".

`ConfigurationHandler.middleware_config` turns the section into the
`{name: bool | dict}` switches and `AsgiServer._configured_kwargs` maps it to
the `middleware` kwarg (asgi_server.py:160-166). **`middleware_registry` has no
configuration counterpart**: searched across `src/`, it occurs only in the
mixin and in `AsgiServer`'s own docstring (asgi_server.py:41). See
[design.md](decisions.md), friction S3.

## Driven live on the recipe

All five rows of the table at the foot of [README.md](design.md) are the
probe's own output:

| Request | Answer |
|---|---|
| `GET /home` | 200 `{"shop":"open"}` + `set-cookie: session_id=…` |
| `GET /takings`, `Accept: application/json` | 401 `{"login_url":"/_server/login_page"}` |
| `GET /takings`, `Accept: text/html` | 302 `location: /_server/login_page?next=%2Ftakings` |
| `GET /robots.txt` | 404 `Not found: /robots.txt` |
| `OPTIONS /home` from the allowed origin | 200, `access-control-allow-origin: https://shop.example.com` |

The chain walked outwards is `ErrorMiddleware · WellKnownMiddleware ·
LoggingMiddleware · CORSMiddleware · SessionMiddleware · AuthMiddleware`.

## Test inventory

Every test is a **contract test**; `tests/x/` holds only `__init__.py`.

| File | Items | Covers |
|---|---|---|
| `tests/test_middleware.py` | 12 | the shared header reader, chain assembly and ordering, the three error mappings, scope routing, composition |
| `tests/test_middleware_std.py` | 27 | wellknown, cors, the error wire shapes, content negotiation, challenge negotiation, logging, session write-back, the defaults |

`tests/conftest.py` carries the ASGI-level helpers these use, promoted out of
`test_middleware_std.py` (conftest.py:15-33).

## Decisions that shaped what exists

- **D17** (SPECIFICATION.md:229) — capabilities are mixins. `MiddlewareMixin`
  is one, and it is what closes **Q2** (SPECIFICATION.md:698) in the general.
- **D7** (SPECIFICATION.md:100) — middleware is explicitly out of phase 0.
- **D24** (SPECIFICATION.md:421) — login attaches an identity in place and the
  session id never changes; the middleware issues a cookie only for a session
  it created. Held exactly.
- **`5b567a3`** (2026-08-14) — 401 for the anonymous, 403 for the known; the
  challenge negotiation the middleware chain performs.
- **Invariant 4** (SPECIFICATION.md:674) — an origin gate on WebSocket
  handshakes. **Not held here and not holdable here**: the chain never sees a
  WebSocket scope. See [design.md](decisions.md), friction S2.
- The `Accept`-driven error body carries a citation to "D4 error-body
  reconciliation" (errors.py:25) that **D4 does not contain** — D4
  (SPECIFICATION.md:67) is about the administrative application. See
  [design.md](decisions.md), friction S8.

## Three things driven live that the design leans on

**Two of the six are armed by their own capability, not by the section.**
`AuthMixin` and `SessionMixin` each `setdefault` their own name into the
`middleware` kwarg they forward
([auth/mixin.py:83-85](../../../src/genro_asgi/auth/mixin.py),
[session/mixin.py:21-24](../../../src/genro_asgi/session/mixin.py)), so on an
`AsgiServer` the session and identity layers are in the middleware chain
whether or not the description names them — and an explicit `False` still wins,
because `setdefault` never overrides. Driven live: the recipe at the foot of
[README.md](design.md) names three layers and the chain carries six.

So the `middleware_default = False` on those two classes is true of the class
and misleading about the shipped composition.

**An error response bypasses every inner layer's outgoing half.**
`ErrorMiddleware` answers with `await response(scope, receive, send)`
(errors.py:93) — the `send` it received, which is outside every other layer, not
the wrapped one it passed inwards. Driven live on one server with `cors` and
`session` armed, one request each way:

| Request | status | `access-control-allow-origin` | `set-cookie` |
|---|---|---|---|
| `GET /home` with `Origin` | 200 | `https://a.example` | present |
| `GET /boom` with `Origin` (handler raises `HTTPNotFound`) | 404 | **absent** | **absent** |

See [design.md](decisions.md), friction S9.

**`errors=False` is accepted and leaves nothing to answer.** The element takes
it like any of the six, `build_chain` drops the layer, and a raised
`HTTPNotFound` then **escapes the server uncaught** — driven live, the call to
the server raises instead of returning a response. Nothing in the grammar, the
mixin or `build_chain` treats it as structure. See [design.md](decisions.md),
friction S10.

**A middleware of one's own works, end to end.** Driven live: a
`BaseMiddleware` subclass declaring `middleware_order = 250` and wrapping
`send` to add a header, installed as
`AsgiServer(config=…, middleware={"stamp": {"machine": "web-01"}},
middleware_registry={"stamp": StampMiddleware})`. The chain becomes
`ErrorMiddleware · StampMiddleware · SessionMiddleware · AuthMiddleware` and
every answer carries `x-served-by: web-01`. The block is in
[README.md](design.md) §7.
