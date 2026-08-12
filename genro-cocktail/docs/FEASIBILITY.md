# Feasibility — HTMX + genro-builders + a database on genro-asgi

**Question**: can a server-rendered HTMX UI, generated with genro-builders,
served by genro-asgi, backed by a real database, carry a small polished
product (genro-cocktail)?

**Verdict: yes, and the pairing is unusually natural.** Every claim below was
verified by running code against genro-asgi 0.28.0 / genro-builders 0.23.1
(the `prototype/` in this kit is the living proof). The stack needs four small
local workarounds (§3) and one self-written component (the sqlite adapter, §4)
— nothing structural.

---

## 1. Why the pairing fits

HTMX's contract is: *the server returns HTML — pages first, fragments after*.
That maps 1:1 onto what genro-asgi already does well and onto what
genro-builders was built for:

| HTMX needs | The stack provides |
|---|---|
| HTML responses | `@route(media_type="text/html")` + return `str` |
| Fragment endpoints | any handler; fragments are genro-builders' default (everything is a fragment unless you build `<html>` yourself) |
| Form POSTs | form bodies bind to the handler signature (with the §3.1 decode fix) |
| Response headers (`HX-Trigger`, `HX-Redirect`) | `_request.response.set_header(...)` |
| POST/Redirect/GET | `raise Redirect("/", status=303)` |
| Safe HTML generation | genro-builders escapes text and attributes; containment rules raise at insertion (`div.tr()` is a `ValueError`) |
| Reusable UI pieces | `@component` (render-time expansion, `iterate=`), `@container` (fillable panes), mixins via `include_components` |
| Live updates (later) | `SseStream` at the ASGI level; HTMX SSE extension client-side |

Measured cost of a genro-builders fragment (build + render, small page):
**~0.7 ms** — irrelevant next to a request round-trip.

The deeper fit is philosophical: genro-builders makes the HTML a **typed,
validated object tree built in Python** — the same "grammar + recipe" idea the
config layer already uses. The UI layer of genro-cocktail is then the same
gesture as its config: subclass a builder, write `main(self, root)`.

## 2. The genro-builders HTML dialect — what we rely on

`genro_builders.contrib.html.HtmlBuilder` (`_name="html"`):

- **117 HTML5 tags** with real containment rules (from the W3C schema);
  Python-keyword clashes use trailing underscore (`del_`); names shadowed by
  the node API use the `html_` prefix escape (`node.html_label(...)`).
- Text escaping (`& < >`) and attribute escaping (`& < > "`) built in.
  `<script>`/`<style>` bodies are emitted **verbatim** — never interpolate
  user data there.
- Inline-CSS kwargs (`color=`, `padding_top=4`) fold into `style`; macros
  (`rounded=`, `shadow=`, `gradient=`, `transition=`) available.
- Boolean attributes per spec (`required=True` → bare `required`).
- `render(pretty=True, xml=False)` → string; `target=` writes files.
- **No DOCTYPE support** — prepend `"<!DOCTYPE html>\n"` yourself.
- **Hyphenated attributes are not auto-converted**: `hx_get=` emits literally
  `hx_get="…"`. Fix: a 12-line renderer subclass (in `prototype/ui/htmx.py`)
  that kebab-cases `hx_*`, `data_*`, `aria_*`, `sse_*`, `ws_*` — after which
  `button("Load", hx_get="/rows", hx_target="#list")` reads exactly like
  idiomatic HTMX.

## 3. The four genro-asgi workarounds (all local, all small)

### 3.1 Form bodies are not URL-decoded (the one real bug)

genro-tytx's `from_qs` deliberately skips percent-decoding, so
`title=hello%20world` binds as the literal `hello%20world`. Until fixed
upstream, the app overrides `bind_kwargs` and re-decodes string values of
urlencoded POST bodies with `urllib.parse.unquote_plus`. ~8 lines, one place
(`prototype/app.py`). **Action item: file the issue on genro-tytx.**

### 3.2 The `_request` seam

Handlers are pure; the live request arrives only if the app injects it. Copy
the `ServerApplication` idiom into the app base class (~5 lines in
`bind_kwargs`): a handler that declares an unannotated `_request` parameter
gets the `Request` (headers, cookies, session, response). Unannotated keeps it
out of the OpenAPI schema.

### 3.3 No HTTP-method dispatch

Every route answers GET and POST. Mutating handlers guard:
`if _request.method != "POST": raise HTTPBadRequest(...)`. One helper in the
app base class.

### 3.4 No static files

One `static` route with a resolved-path traversal guard and
`mimetypes.guess_type`, returning a `Path` via
`result_wrapper(path, media_type=...)`. Fine for a showcase (CSS + htmx.js);
production puts assets behind nginx/CDN.

## 4. The database: introducing SQLite through the `databases` seam

The core's contract (verified in `tests/test_db.py` and at
`asgi_server.py:180-193`):

```python
# config.py
dbs = cfg.databases()
dbs.database(code="default", db_class=CocktailDb, path="cocktail.db")
# boot: server.databases["default"] = AsgiDbHandlerBase(CocktailDb(path="cocktail.db"))
```

What the consumer must know (all encoded in `prototype/db.py`):

1. **One `db_class` instance is shared by every request and every pool
   thread** → connections must be thread-local inside the adapter (sqlite3
   with `check_same_thread=True` per thread, WAL mode).
2. **`closeConnection` cleanup runs on the event-loop thread**, not the pool
   thread that ran a sync handler → don't rely on the automatic cleanup for
   thread-local connections; commit/close in the handler path itself. The
   prototype wraps every mutation in an explicit `commit()` and keeps
   per-thread connections open (sqlite is happy with that; `closeConnection`
   remains correct for the loop thread).
3. Transactions, migrations, pooling are ours. For the showcase: a
   `schema.sql`-style bootstrap executed at adapter construction, explicit
   transactions where a mutation touches several tables (batch production).

**Why SQLite is the right call here**: single file, zero ops, honest SQL,
perfect for a single-process showcase; the adapter surface (`query/execute/
transaction`) is small enough that a later PostgreSQL adapter is a drop-in
replacement behind the same config entry.

## 5. WebSockets: not in the core, easy on a subclass (verified)

The core ships `on_websocket` as an empty hook (D7/Q1: consume the connect,
close 1000) — but uvicorn delivers the full ASGI websocket message stream to
it, so a **server subclass** is the whole story:

```python
class CocktailServer(AsgiServer):
    async def on_websocket(self, scope, receive, send):
        await receive()                                # websocket.connect
        await send({"type": "websocket.accept"})
        while (msg := await receive())["type"] != "websocket.disconnect":
            reply = handle(json.loads(msg["text"]))
            await send({"type": "websocket.send", "text": json.dumps(reply)})
```

This is exactly the D16 extension gesture ("the class says WHO you are"), and
it forces one deviation: the server class is chosen at boot, never in config,
so the app ships its own launcher (`python serve.py`) instead of the generic
`genro-asgi serve config.py`. Facts learned doing it:

- **uvicorn needs a protocol library** — `pip install websockets` (or
  `wsproto`); the core's dependency set does not include one.
- **The middleware chain is http-only** — no session, no auth on the
  handshake. Read the session cookie from the scope by hand
  (`genro_asgi.middleware.base.cookie_value`) and look it up in
  `server.session_store`.
- Verified end to end in a real browser (Playwright): slider → ws frame →
  sqlite write → stats reply → DOM update, with reconnect/backoff and
  bad-frame resilience covered by the smoke suite.

## 6. Social login (OAuth/OIDC): Google now, Apple with a caveat

genro-asgi's OIDC is authorization-code + PKCE S256, one `provider(code=…)`
per identity source, routes auto-mounted at
`/_server/auth/oidc:<code>/{start,callback}`, and the stock login page
builds itself from the registered methods — **zero custom login UI needed**.
Requirements: `server(external_url=…)` (the callback base), and the
provider's `client_id`/`client_secret` via `EnvResolver`.

- **Google**: plain OIDC (`issuer="https://accounts.google.com"`), works with
  the shipped `OidcMethod` as-is. Register
  `<external_url>/_server/auth/oidc:google/callback` in the Google console.
- **Apple**: OIDC too, but its `client_secret` must be a **short-lived
  ES256-signed JWT** (max 6 months) minted from your Apple Developer key —
  not a static string. The config seam accepts a resolver, so a
  `BagResolver` that mints/caches the JWT slots in cleanly; needs a paid
  Apple Developer account. Parked as a later milestone.
- **GitHub is NOT OIDC** (plain OAuth2, no `id_token`) — it would need a
  custom `AuthMethod`, so it's not a quick win here.

The session behaviour matters for the toy: login **attaches** the identity
to the running session (D24, id unchanged), so what an anonymous visitor
mixed stays on screen after signing in. (Migrating anonymous creations to
the new identity at login is an easy later feature: one UPDATE on `owner`.)

## 7. The user-sticky pool (`spa/`): the strength, and when we ride it

The distinguishing feature of genro-asgi — per Giovanni, and the code agrees —
is the **user-dedicated process system**: `SpaApplication` (the mountable
front) + `UserStickyCommander` (pool owner: spawn, supervise, probe,
occupancy sensing, rebalance, user move, evidence-based recycling, register
dump/restore) + `UserStickyWorker` (the execution unit, one channel, no HTTP
port). Routing is sticky by user (the `sticky_cid` cookie): the same person
always lands on the same worker process, whose in-memory state is theirs.
The architecture's two primitives (D22): the USER as load-partition key,
PAGE_ID as the unit of living state.

What riding it would buy genro-cocktail: each user's bar living in a
dedicated process (working state in memory, not re-read per gesture),
isolation (one user's crash touches nobody), per-group rolling
reload/canary — and the "single role" (`workers=0, local_worker=True`)
gives the whole machine with zero extra processes for dev.

Why v1 does NOT ride it (verified, 2026-08-12):

1. **The hosted-site seam speaks WSGI, not ASGI.** The worker serves site
   requests through `wsgi_app` (PEP 3333, whole-body, via `WsgiSeam`) — a
   seam built to host the legacy Genropy site during the transition. Our
   `RoutedApplication` is ASGI; hosting it today means a `UserStickyWorker`
   subclass with a custom `serve_http` (the e2e test does exactly this) —
   a fine experiment, not a foundation.
2. **Not public API yet**: nothing re-exported top-level, zero docs pages,
   14 `PROVISIONAL` tuning constants, naming still churning. The spec parks
   it as the phase-2 orchestration package, split "when the contract
   stabilizes".
3. **WebSockets do not cross the pool — by design.** D21: "the WebSocket
   stays up on the public server, invisible to the browser"; worker events
   fold upward on the channel. Our `CocktailServer.on_websocket` on the
   public server is already in the right place for that future.

So the pool is a LATER milestone, not a blocker — and genro-cocktail is the
natural **first real consumer**: see PROJECT-PLAN, "the laboratory track".

## 8. What we deliberately do NOT use (yet)

- **`spa/` orchestration** — see §7: a deliberate later milestone, the
  laboratory track. v1 is a plain mounted application on the public server.
- **MCP face** — not needed for the UI, but it is a one-line base-class swap
  (`McpOpenApiApplication`) and would make the bar queryable by an AI agent
  ("mix me something bitter under €2"). Flagged as a wow-feature
  (PROJECT-PLAN M4).

## 9. Risk table

| Risk | Severity | Mitigation |
|---|---|---|
| genro-tytx form decoding bug | high (breaks every form) | §3.1 workaround now; upstream fix |
| API still "stabilizing" (Beta) | medium | pin `genro-asgi>=0.28,<0.29`; the kit's idioms are all on ratified seams |
| No db layer beyond the seam | medium | own adapter (§4); scope = sqlite |
| XSS via hand-built strings | medium | genro-builders everywhere; never f-string HTML |
| Session store is memory-only | low | acceptable for showcase; file/db store later |
| uvicorn ws lib is an extra dep | low | `pip install websockets`, documented |
| TYTX typing surprises (`"123"` → int) | low | annotate handler params |

## 10. Conclusion

The stack is ready for exactly this class of application: a mono-process,
server-rendered, form-driven product with islands of interactivity. HTMX +
genro-builders is arguably the *first* UI story that fits genro-asgi's current
shape (no websockets needed, no SPA machinery needed, HTML as data). The
prototype in this kit is the proof; PROJECT-PLAN.md turns it into the
showcase.
