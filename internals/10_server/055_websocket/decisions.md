# Websocket — decisions

**Version**: 0.1 · **Last Updated**: 2026-09-06 · **Status**: 🔴 DA REVISIONARE

**The websocket, with the work finished.** Read this as a report from the day
everything described here is running: it says what the transport *is*, and
never what it lacks. What the code holds today is [status.md](status.md)'s
subject.

Every voice carries its source. A voice sourced to the owner and a date was
decided in conversation before it reached this file. Two working documents hold
those conversations: the decision register of the investigation opened on
2026-09-05, which carries the `W-1`…`W-13` questions and the namings from `N14`
on, and the investigation's diary, which carries the namings `N1`…`N13` decided
on 2026-09-05 turn by turn. The tags are their own numbering, kept here so a
later reader can find the conversation that produced a line.

---

## 1. The server holds the connection

**Source: owner, 2026-09-05 (W-1), «ok. primario quello e websocket alta
frequenza solo un domani».** `BaseServer.on_websocket` is the one place a
websocket is accepted, read, written and closed. The server is the only party
that sees every application and every connection, so the questions with one
machine-wide answer are answered there once: the Origin gate, the identity, the
registry of live connections, the refusal while the server is not `RUNNING`.

Each message is then handed to the application its `path` names, through the
same demux an HTTP request goes through. So one websocket per browser serves
every mounted application, and an application that lives in the server process
is reachable on the same socket as the SPA.

The alternative — every application holding its own socket, the old
`serve_websocket` shape — makes a page that talks to two applications open two
websockets, and rebuilds identity, Origin, registry and the refusal per
application, which is this decision again one level down.

**Deliberately not built**: a direct browser → worker channel for
high-frequency traffic. It is reopened only on a measurement (owner,
2026-09-05): how many messages per second the server sustains with the lane in
between.

## 2. Every message is a request, and the SPA's road to the worker is a CALL

**Source: owner, 2026-09-05 (W-2), the third road.** A message for the SPA
becomes an ordinary CALL on the worker's lane, in the `http` form the worker
already serves. The wire keeps its two lanes, CALL and REPLY: no third envelope
type, no port in the worker, no client websocket opened from the server.

What this buys is everything the core already built for a request: the message
is served on a task of its own with a request slot, the worker's events ride
its REPLY, the photo and the fold see it like any other call. It is also what
the old repo's `WsxHandler` did with every WSX message — one message, one
request.

What it costs is one round trip on the lane per message, and a map from
connection to `send` held at the server.

**Deliberately not built**: the worker holding its own websocket behind a port
of its own — the shape that would give a Django Channels application a native
websocket. It stays a future extension, reached by naming a different worker
class in the recipe, never a switch between two transports both built (owner,
2026-09-05: «potremmo immaginare di decidere a livello di configurazione?» →
yes, as the choice of the class).

## 3. What the websocket carries, and what stays pull

**Source: owner, 2026-09-05 (W-3), «a», widened; owner, 2026-09-06 (W-11).**
On the websocket travel the page's rpc — every call the client chooses to send
this way, its own data synchronisation included — the commands addressed to one
page, and the shared object when it exists.

What does NOT travel here is the unsolicited delivery of what happens
elsewhere: another user's writes, a table's dbevents. That delivery stays
**pull**, as ratified on 2026-08-29 — a queue per page, collected on the page's
next call. The owner's words, 2026-09-06: «sul websocket viaggia ciò che una
pagina chiede (rpc, anche di sincronizzazione dei suoi dati) e ciò che il
server manda a UNA pagina con un comando indirizzato via `send_message`; non
viaggia la consegna non sollecitata di ciò che accade altrove». A page-level
synchronisation protocol — revisions, a save barrier — belongs to whoever
writes the pages.

So a dbevent waits for the next call, seconds, exactly as it does today.
Pushing it the moment it happens would put the ordering of the push against the
ordering of the reply's queue, and would make the freeze decide what becomes of
what was in flight. Neither was asked for.

## 4. The protocol is WSX, and TYTX carries the values

**Source: owner, 2026-09-05 (W-4), «a».** A message is the text prefix
`WSX://` followed by JSON: `id` (optional), `method`, `path`, `data`,
`page_id` (optional), `reply_path` (optional). An answer is `id`, `status`,
`data`. The prefix is what tells a WSX message from any other text on the
socket, and the four fields are the ones the lane's own `Frame` already
carries, so a message copies into a CALL one field at a time.

`data` is the TYTX string — what `to_tytx(value, "json")` produces, placed in
the envelope as a JSON string; the receiver calls `from_tytx(envelope.data,
"json")`. Dates, Decimals and Bags survive that round trip in both languages,
which was proven end to end before this was written. Bytes travel as the `RAW`
type of genro-tytx.

The form must be producible by any client with no library of ours: the owner
asked for it with Django in view (2026-09-05).

### 4a. An application does not learn a new method

**Source: owner, 2026-09-05 (W-4c), «abbiamo delle request che generiamo per
GET, POST, PUT, DELETE e ora per WSK. Se una app usa websocket in questo modo
(emulazione rpc) accetta la convenzione».** The server builds a synthetic HTTP
request from the message and calls the application the ordinary way. The signal
is the METHOD: `WSK`. There is no translation to POST — the hosted site sees
`WSK` — and no new method on any application class.

### 4b. A message with no `id` is an event

**Source: owner, 2026-09-05 (W-4d), «se non c'è id NON rispondiamo».** It is
executed and nothing is answered; a failure goes to the log. A page that wants
to be called back later carries `reply_path`, a common field of the envelope
rather than a per-application convention — chosen so «che venga gestita in modo
anarchico» could not happen — and whoever served the message calls
`SpaWorker.send_message(page_id, reply_path, data)` when the work is done.

An event is also NOT registered in the server's `RequestRegistry` (owner,
2026-09-05, W-4f): the shutdown does not wait for it, and a handler that opens
a database closes what it opens.

### 4c. `page_id` and `reply_path` reach the hosted code as environ keys

**Source: owner, 2026-09-05 (W-4e), «Le chiavi si chiamano `genro.page_id` e
`genro.reply_path`, documentate in `spa/environ.py` accanto a
`genro.identity`. Su una request http vera sono assenti, non `None`».**
Synthetic headers were refused: they are forgeable from outside. `page_id`
travels in the CALL's payload too, because the per-page queue is read before
the stitching.

## 5. Identity is judged once; every message is placed again

**Source: owner, 2026-09-05 (W-5), «a+».** The handshake is the only HTTP
request of the connection, so it is where the avatar is resolved — header
first, then session, the way the chain does for HTTP — and a refusal closes the
socket there. For the SPA the identity is the connection id in the cookie, and
a login changes the owner of that id exactly as it does over HTTP.

Every message is then placed like a request: the barrier, the index, the worker
of the moment. The worker does not know a websocket exists — no CALL announces
an opening or a closing, nothing is frozen, nothing is moved. After a transfer
the next message goes to the new worker and the browser never notices.

What is given up is presence: the worker cannot tell whether the browser is
still there. Whoever wants presence builds it with a message of its own — the
server's registry already knows who is connected.

## 6. Order: parallel with a ceiling, and the queue belongs to the page

**Source: owner, 2026-09-05 (W-8), «sì, mi pare bello», revised the same day.**
At the server every message is a task, with a per-connection ceiling
(`max_concurrent`) and the control ping outside it; the client correlates on
the `id`. The ceiling is **configurable, default 16** (owner, 2026-09-06:
«configurabile default 16»). It exists because a client that floods must not
sink the server, and it is a setpoint because how many calls a page fires at
once is an installation's own business. This is the semantics the HTTP calls of the same page already have —
a page fires dozens of calls at once — and a slow message blocks neither the
others nor the ping.

Whether a page is served one message at a time is the PAGE's own declaration.
The owner's words: «ragioniamo su un `page_id` specifico: una pagina di ordini,
lì mi va bene che tutte le chiamate websocket vadano in parallelo; poi ho una
pagina che fa monitoraggio eventi su un dispositivo e lì dico che tutta la
pagina deve essere serializzata come eventi». The declaration lives in the
`wsx` field of the page's row — absent, `True`, or a dict whose `sequential`
key is the flag — written by the page's first WSX message, the mandatory
`openchannel` command, and enforced by the WORKER through the row's own lock. A
message for a page that never opened its channel is refused with a clear error.

A route-level metadatum was considered and WITHDRAWN: the grain is the page.

## 7. The handshake cookie gate

**Source: owner, 2026-09-06 (W-13), «a».** The path of the handshake names the
socket's home application through the server's demux, and that application's
`handshake_cookie` property says which cookie the handshake must carry —
`None` for an application that requires none. The owner's words: «assente →
accept e 1008 "connection cookie required"». A handshake on a path no
application serves is accepted and closed 1008, «no application at this path».
With no home application there is no gate at all.

Per message the rule holds independently: a message addressed to the SPA from a
socket carrying no connection id is answered with status 403.

## 8. The server speaks first in the shape of a request

**Source: owner, 2026-09-05 (W-4b), «a»; refined 2026-09-06 (W-12).** A
message the server sends by itself has the shape of a request — `method`,
`path`, `data`, `page_id` — and the client routes it on the `path`, the way the
server routes the client's own. One codec serves both directions, and the path
names the sending application.

`send_message` is fire-and-forget (owner, 2026-09-06): its reply says «written
on the socket» or «no websocket for this page», and nothing more. «Delivered»
means the ASGI `send` returned — never «executed by the page». Server messages
carry no `id`; an answer from the browser is a client rpc on `reply_path` or on
a path of its own. Waiting on a future with a timeout, and the space the
server's own ids would live in, are a registered extension and are not built.

## 9. One websocket per index page

**Source: owner, 2026-09-05 (W-9), «la connessione è della index page e tutte
le sottopagine lo devono comunque mettere. Potenzialmente potrei avere 3 index
page e ognuna 6 sub pages e avere 3 websocket e non 18».** The envelope carries
an OPTIONAL `page_id`, message by message, in both directions — absent for a
client that has no pages. The socket belongs to the root page; a subpage sends
through it and puts its own `page_id` in every message. How the client
channels that is the page framework's business.

## 10. The worker serves ASGI applications, through one seam

**Source: owner, 2026-09-06.** The first target of this transport is a worker
hosting an ASGI application, with the same user, connection and page rows and
the same pool as today. `SpaWorker.asgi_app` is the seam a consumer assigns;
`AsgiSeam` builds the ASGI scope from the `http` dict a CALL carries, hands the
body whole in one `http.request`, and collects the answer. The identity in the
scope is the SPA's rule — the user resolved for THAT message — never the avatar
fixed at a handshake: an ASGI application inside the worker is served by the
SPA, it is not an application of the server.

The seam is served INSIDE the same `_serve_request`: same pendings, same row
put in order, same request slot, same events riding the REPLY. Synchronous work
— a legacy database built by the group's engine — runs on the traffic pool
through `SpaWorker.run_sync(work)`, which copies the CALL's context so the
thread finds the same slot.

There is no streaming, deliberately, exactly as for WSGI: an application that
never finishes never finishes its CALL.

## 11. Mixed applications: one seam in the core, the routing in the consumer

**Source: owner, 2026-09-06, form B.** A worker that hosts both a legacy WSGI
site and new ASGI pages has ONE seam in the core, `asgi_app`. The legacy enters
through `WsgiSeam`, which is an ASGI application around the WSGI callable and
runs inside the already-accepted request, on the traffic pool, with that
request's slot — no second CALL, no duplicated prologue — and keeps the
legacy's own view of the URLs: `SCRIPT_NAME` from `root_path`, `PATH_INFO` from
what is left of the path, the query, the body, `Set-Cookie` and the redirects.

`wsgi_app` remains as the shortcut for whoever hosts WSGI only, and the core
serves it through that same adapter: one road, not two. Assigning both is an
explicit error — the shortcut is an alternative, not an addition — and
assigning neither is an error as well; `SpaWorker.hosted_app_seam` is where
both are judged, and a badly configured worker dies at boot rather than at its
first request.

The mixed routing lives in the CONSUMER's ASGI router, which calls the adapter
for the legacy paths and serves the new ones itself. The core knows no path
prefixes: a rule on the path inside the core was the alternative, and it was
refused. Which family a page belongs to is a metadatum of the consumer on its
own row; `wsx` stays the channel and never doubles as that discriminator.

## 12. Nothing is carried over as code

**Source: owner, 2026-09-05 (W-7), «pensavo che, capito il problema,
riscrivessi ex novo con nomi giusti e convenzioni attuali».** The facade, the
envelope, the per-connection object and the registry are written new here, with
the names the owner baptised and today's conventions: classes rather than
module-level functions, no demo block, genro-tytx as a hard dependency, the
core's own `Request` on a synthetic scope instead of the old `MsgRequest`.

The old repo stays a REFERENCE: the cases its 71 websocket tests covered are
the list of behaviours the new tests must cover, written before the code, and
one of its points is cited with `file:line` when a comparison is needed. The
pipe that copied frames towards a worker is not rewritten in any form.

## 13. The async process of genropy falls

**Source: owner, 2026-09-05 (W-6), «diciamo che sotto genro-asgi gnrasync è
tutto nuovo» and «ovviamente gnrasync è compito del bridge rifarlo e fare in
modo che venga importato lui, magari con una modesta modifica a genropy».**
Under genro-asgi there is no separate async process. Its functions — rpc over
websocket, commands to a page, the shared object — are rebuilt by the
genropy-asgi bridge, which gets itself imported in its place. The deployment
loses a process to govern.

## 14. The names

Every name below was baptised by the owner, one per turn, on 2026-09-05 and
2026-09-06.

| What it is | Name |
|---|---|
| The per-connection object that speaks WSX | `WsxConnection` |
| The neutral facade over the ASGI websocket, used by both modes | `WebSocket` |
| The registry of the server's live connections, with the `page_id → socket` association | `WebSocketRegistry` |
| The WSX envelope as a class (the lane's `Frame` untouched) | `WsxEnvelope` |
| The method admitted for a raw websocket handed to an application | `serve_websocket` |
| The page row's channel declaration, and the command that writes it | field `wsx` + `openchannel` |
| The flag inside the `wsx` dict that puts a page's messages in single file | `sequential` |
| The config element, with its `origins` and its per-connection ceiling | `server/websocket`, `max_concurrent`, default 16 |
| The reserved first segment of a control message | `_wsx` |
| The commander branch the worker's push arrives on | `/commander/websocket/send` |
| The worker verb that addresses one page | `SpaWorker.send_message(page_id, path, data)` |
| The field a page names to be called back on | `reply_path` |
| The worker branch that opens a page's channel | `/wsx/openchannel` |
| The environ and scope keys, beside `genro.identity` | `genro.page_id`, `genro.reply_path` |
| The worker's seam for a hosted ASGI application | `asgi_app` |
| The sister of `WsgiSeam` that builds the ASGI scope | `AsgiSeam`, in `spa/environ.py` |
| The worker's way of running synchronous work with the request's slot | `SpaWorker.run_sync(work)` |
| The application property that says which cookie the handshake must carry | `handshake_cookie` |
| The property that yields the seam onto the hosted application | `SpaWorker.hosted_app_seam` |
| The WSGI → ASGI adapter | `WsgiSeam` itself, with `__call__(scope, receive, send)` |
| How the ASGI application reaches the worker | the consumer binds it, in its own worker class |

Two of them carry a reason worth keeping:

- **`hosted_app_seam`** (owner, 2026-09-06): the word «seam» stays, because
  `WsgiSeam` already carries it and the family is not rebaptised. Its docstring
  says «the one seam a consumer assigned», not «whichever of the two is
  assigned», because it raises when both are.
- **`WsgiSeam` as the adapter** (owner, 2026-09-06): the same class, with the
  ASGI entrance replacing the dict entrance, which goes away with its two
  readers. No new name, `__all__` unchanged. Its constructor takes the worker
  and holds it as `self.worker`, for `run_sync`.

And one of them is deliberately NOT a convention of the core: **how the
application reaches the worker** (owner, 2026-09-06). The consumer binds them
in its own worker class, at construction or as an attribute afterwards — the
road the genropy bridge already takes when it writes `site.spa_worker = self`.
The core adds nothing and writes NO live object into the scope, which stays the
JSON-safe facts the front packed.

## 15. What is deliberately absent

- No pipe and no port in the worker (§2).
- No push of datachanges or dbevents (§3).
- No shared object yet: where it lives was postponed by the owner on
  2026-09-05, «non è nelle priorità attuali. Però dobbiamo tenerlo presente
  come problema di fondo per evitare decisioni che poi alzino il livello di
  difficoltà». The decisions above are the ones that keep it possible: a socket
  that can serve an application living in the server process, a `path` in every
  message, an identity resolved at the handshake, and a way for the server to
  address a connection outside any request.
- No NATS, no pub/sub, no streaming, no binary frames.
- No direct browser → worker channel (§1).
- The monitor is NOT the first consumer: it is under review, and the owner
  postponed it on 2026-09-05. The first live proof is a test application.
