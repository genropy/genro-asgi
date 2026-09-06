# Websocket — current state

**Version**: 0.1 · **Last Updated**: 2026-09-06 · **Status**: 🔴 DA REVISIONARE

What exists TODAY on the branch, with its `file:line`. Update it in the same
change that alters the behaviour. Opened at phase 0 of
[#68](https://github.com/genropy/genro-asgi/issues/68) on `develop` = `a434a23`;
phase 1 has landed since, and the two objects it built are below. Nothing yet
USES them: the server still answers a handshake with the empty socket.

## What phase 1 built

**The facade** — [websocket.py](../../../src/genro_asgi/websocket.py), 100%
covered by `tests/test_websocket_facade.py` (27 contract tests). `WebSocket`
wraps scope, `receive` and `send`: `accept()` consumes the connect and answers
it (with a subprotocol and with response headers, the one place a websocket can
carry a `Set-Cookie`), `close()` writes once and refuses to run before an
accept, the reads refuse the wrong payload kind and raise
`WebSocketDisconnect` when the client is gone, the writes refuse a socket
nobody accepted, and iterating yields the incoming texts until that disconnect.
`connected` is the whole state, one boolean, and the handshake facts — path,
headers, cookies, offered subprotocols — are read off the scope in the
constructor, the way `Request` reads an HTTP request.

**The envelope** — [wsx.py](../../../src/genro_asgi/wsx.py), 100% covered by
`tests/test_wsx_envelope.py` (29 contract tests). `WsxEnvelope(text)` reads a
message, `WsxEnvelope(id=…, method=…, path=…, data=…)` builds one, and
`encode()` gives the wire text. A field nobody set does not reach the wire, so
an event has no `id` and a request has no `status`. `data` is a Python value
here and the TYTX string inside the JSON body there: the round-trip tests are
executable examples over Decimal, date, datetime, null, bytes, a Bag with
attributes, a nested Bag, and a string full of characters JSON must escape. A
text without the prefix, a body that is not JSON and a body that is not an
object all raise `ValueError` — one answer for the read loop: this is not a
message of ours.

**The disconnect** — `WebSocketDisconnect` in
[exceptions.py](../../../src/genro_asgi/exceptions.py), with `code` and
`reason`. It sits beside the HTTP exceptions and is not one: a disconnect is
not a value a read can return, so it arrives as an exception.

**The dependency.** genro-tytx is pinned `>=0.14.0`
([pyproject.toml:34, 50](../../../pyproject.toml)), the release that carries
the `RAW` type: bytes in a message travel base64 under `::RAW` on JSON and
native on msgpack, and the page encodes nothing by hand.

## What the code held before it

**The empty socket.** `BaseServer.on_websocket`
([server.py:287-294](../../../src/genro_asgi/server.py)) consumes the connect
and closes with code 1000. Its docstring names the reason: it is the D7 socket,
and the motor of Q1 overrides this hook. The websocket branch of
`BaseServer.__call__` (`server.py:237-238`) reaches it, and does NOT read the
server's `state`: the 503 with `Retry-After` is on the HTTP branch only
(`server.py:220-229`).

Covered by `tests/test_demux.py:166-178` (`TestEmptyWebsocket`), which drives
`__call__` at the ASGI level with no websocket client: it calls the server, and
the websocket branch takes it from there. It is the only test of the whole
repository that reaches `on_websocket` — no test names it.

**The middleware chain does not see it.** `MiddlewareMixin.__call__`
([middleware/\_\_init\_\_.py:107-112](../../../src/genro_asgi/middleware/__init__.py))
routes only `http` scopes through the chain; every other scope passes straight
through. So at the handshake `scope["auth"]` and `scope["session"]` are NOT
already there — which is why the handshake resolves the identity itself
([decisions.md](decisions.md) §5).

**The front has no websocket branch.** `SpaApplication.__call__`
([spa_app.py:837-844](../../../src/genro_asgi/applications/spa_app.py))
demultiplexes between its own router and the hosted site on the PATH, and never
reads the scope's type. It sees no websocket scope today because the server
takes that branch first (`server.py:237-238`) and never reaches the demux.

**The pieces the motor will stand on already exist.** The demux
(`server.py:247-273`), the request registry (`server.py:95`, registered in the
HTTP cycle at `:225-240`), the identity (`auth/core.py:160-179`,
`auth/mixin.py:151-163`), the session from the cookie
(`middleware/session.py:76-78, 118-127`), the routing tree with its filtered
walk (`routed_application.py:173-218`), and the lane's own envelope, which
already speaks WSX with the same four fields (`channel/frame.py:15-23,
94-100`).

## What is not there

No per-connection object, no registry, no config
element, no `handshake_cookie` on any application, no `asgi_app` on the worker,
no `hosted_app_seam`, no ASGI entrance on `WsgiSeam`, no `openchannel`, no
`wsx` field on `PageRow`, no `send_message`. `SpaWorker.wsgi_app`
([spa_worker.py:557-559](../../../src/genro_asgi/spa/orchestration/spa_worker.py))
is the one consumer seam of the http CALL form, and `_serve_request` builds a
`WsgiSeam` around it per request (`:2134`).

`SPECIFICATION.md` §6 Q1 is marked RESOLVED as of this phase: the design it
asked for is [decisions.md](decisions.md) and [design.md](design.md), and the
code follows in phases 1 to 5.

## The order of the work

| Phase | What lands |
|---|---|
| 0 | **DONE** — this folder, Q1 resolved, the namings — no code |
| 1 | **DONE** — the `WebSocket` facade, `WsxEnvelope`, `WebSocketDisconnect` |
| 2 | `WsxConnection`, `WebSocketRegistry`, `on_websocket`, the config element |
| 3 | the server speaks first, proven on a test application |
| 4a | `asgi_app`, `AsgiSeam`, `hosted_app_seam`, `WsgiSeam` as the adapter, `run_sync` |
| 4 | the SPA: message → CALL, `openchannel`, the per-page queue, the push |
| 5 | `serve_websocket`, the admitted raw seam |
| 6 | documents |
| 7 | release 0.43.0 |

Tests first in every phase, one commit per phase, the suite green. The working
plan of the phases is local to the machine this work runs on and is not
committed; what it decides lands here.
