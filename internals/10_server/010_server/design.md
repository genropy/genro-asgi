# Server — design

**Version**: 0.5 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

**The ground floor, with the work finished.** Read this document as a report
from the day everything described here is running: it says what the server
*is*, in the present tense, and never what it lacks. What the code holds at
any given moment is [status.md](status.md)'s subject, and the road between the
two is written one step at a time under `steps/`.

Every voice carries its source. A voice sourced to the owner and a date was
decided in conversation before it reached any register.

The **open frictions** are the closing section, and they are the one place
here that compares this arrival with the present — because settling them is
what lets this document be ratified. When that section is empty, the design
stands on its own.

---

## 1. The principle: static only where dynamic cannot be had

**Source: owner, 2026-08-23.** Staticity is **never a presupposition and
never a goal**. It is accepted where we have not managed to make something
dynamic — and where it is accepted, the reason is written down. A design voice
may not celebrate a fixed set, a boot-time-only decision or a restart-to-change
behaviour as if immobility were a virtue.

This principle governs the rest of this document and, being a principle,
governs the other entries too — see the friction on where it gets written.

## 2. The base owns a small, closed list

**Source: D2, SPECIFICATION.md:42.** The common substrate of *every* server:
one uvicorn loop, one monitored thread pool for blocking work (async handlers
never touch it), the applications, the ordered lifespan, the request registry,
and `authenticate()`/`session()` answering "nobody / none".

Closed means *this list and no more*: a capability that is not on it is a
mixin, not a member of the base. It does not mean immobile — what the base
owns is fixed, what it holds is not (§4).

**Source: D17, SPECIFICATION.md:229.** The channel clause of D2 is amended:
the base is born WITHOUT channels, and communication is the first capability
*mixin*. This is what makes the list closed in practice rather than in
principle.

**Source: D2, SPECIFICATION.md:45.** Serving is implemented **once** —
recorded against the old repository, where it existed twice, written
differently.

## 3. An application is a triplet, and its identity is stable

**Source: commit `a1a8f7e`, 2026-07-25.** An application is
**code + instance + mount**. `code` names it and is the key everything else
refers to — the configuration path `applications.<code>.`, the monitor entry,
the `default` name. `mount` is the URL prefix, and `mount=""` IS the site
root: a deliberate value, so every default check is `is None` and never
truthiness, which would silently move a root application to `/<code>`.

Both are class attributes a subclass sets declaratively and a constructor
kwarg overrides per instance, so one class can be served twice under two
codes.

**Source: owner, 2026-08-23.** The identity is stable *for the life of the
instance*, which is not the life of the process: an instance may be mounted
and unmounted (§4) without its code ever meaning something else.

## 4. The installed set changes while the server runs

**Source: owner, 2026-08-23; direction parked by D23,
SPECIFICATION.md:418-419** ("the two-stage live-config architecture — config
as live object, `apply_configuration`, hot/cold changes — stays parked as a
future macro").

Which applications are installed is a fact of the **site configuration**, and
the site configuration is a live document. Mounting an application,
unmounting one, moving one to a different prefix: each is an operation an
administrator performs on a running server, never a reason to restart it.

The mechanism is the configuration itself:

1. The site configuration is a **Bag** — a tree that is read, written, and
   that notifies whoever watches it.
2. The **`_server` application carries the commands** that write into it: add
   an application entry, remove one, change one. The command surface is a
   section of that application and belongs to
   [090 server-application](../090_server-application/).
3. The write **fires the Bag's own trigger**, and the server — subscribed to
   the branch that lists the applications — brings the installed set in line
   with what the tree now says.

The command edits a document; the running system follows. Nothing is
materialized from outside, in keeping with §12: the class that needs the
values reads them, and here it also watches them.

**A change that cannot be honoured is refused loudly.** Two applications
claiming one `code`, two claiming one `mount`, a `default` naming an
application that is not installed: each is answered with an error the
administrator reads. A collision is never absorbed into a silent misroute
that surfaces later as a request arriving in the wrong place.

**An application declares what may be done to it.** Being installed or removed
while the server runs is not something the server may assume: an application
that holds live state — users, pages, open connections — says whether it can be
taken away and put back, and by saying so it **guarantees the mechanism that
makes that possible**. One that cannot does not claim it can, and then the
change waits for a restart. Equally, an application may declare that a failure
of its own mount is survivable, so the server starts without it rather than
refusing to start.

**Accepting a change and completing it are two different moments.** The change
is taken on atomically — it lands or it does not. What follows may take time: an
application with people using it warns them, waits for them to finish, and
lets go only then. So a change reports itself as accepted and in progress, and
an administrator is never told "refused" while something was in fact removed.
The mechanism is [015 configuration](../015_configuration/)'s; what each
application does when its own entry changes is its own.

**The same shape at every level.** A command changes the configuration, the
trigger fires, the thing adapts — for the SPA groups and their worker
processes exactly as for the applications here. The groups' own design is
[020 orchestration](../../20_spa/020_orchestration/)'s.

**Site configuration is not plugins.** Two different mechanisms at two
levels, never to be folded together: the site configuration declares *which*
applications, databases and groups exist (the `applications`, `databases`,
`commander` sections of the tree); a **plugin** is a genro-routes router
plugin armed onto the router of one routed application, and is
[025 plugins](../025_plugins/)'s subject. Installing an application is a
configuration change; enabling a plugin is a router change.

## 5. One demux rule

**Source: D3, SPECIFICATION.md:61.** *First path segment → secondary mount if
it exists, otherwise primary app.* One rule for every server. **Mono-app is a
usage, not a mechanism**: the internal server is a base server used with only
one application. This explicitly kills the old dual `get_app` semantics
(finding C5), and it "must never be reintroduced by package layering".

**Source: commit `a1a8f7e`, 2026-07-25.** The rule stays single and grows
fallbacks: first segment → that mount with the segment stripped; else the
application on the site root; else, for `/` with a `default` declared, a
**307** to that application's mount preserving the query string; else 404.
307 and not 301/302 so that method and body survive the hop. A server with
nothing on the root is a legitimate shape, and `default=<code>` **elects
nothing** — it is a redirect target and no more.

## 6. Two servers, one base, distinguished by composition

**Source: D1, SPECIFICATION.md:36.** The official pair is **public server**
and **internal server**. The public server is the exposed face and owns auth,
sessions and origin gates. The internal server is never exposed: auth and
sessions are `None` *by design*, because whoever fronts it owns them.

**Source: D6, SPECIFICATION.md:89.** The internal server has no auth **by
construction** — a class property, never a configuration. A wrong
configuration must not be able to arm auth on a process that must never be
exposed.

**Source: D17, SPECIFICATION.md:229.** Public server = base + communication +
auth + …; internal server = base + communication. And **the sub-commander is
the public server class with `parent=` armed** — no new class.

**Source: D19, SPECIFICATION.md:263.** Four usage levels, each usable on its
own: bare base server (embed an application, no channels) → public server
(config, auth, `_server`) → orchestration (groups, SPA, batch) →
multi-machine hierarchy. A consumer enters at the level they need and extends
with the same gesture the framework itself is built with.

## 7. The registry: one mechanism, two duties, different consumers

**Source: D5, SPECIFICATION.md:73.** Two duties, identical on every server:
(1) create the right request from the scope and make it reachable by the
running handler — the "current request"; (2) keep the picture of in-flight
requests. What differs between servers is the **consumer** of the picture: the
monitor on the public server, the occupancy sensor on the internal one.

**Source: D5, SPECIFICATION.md:80.** One mechanism only for "current
request", owned by the registry **instance**. The old repository tracked it
twice in parallel — the registry's ContextVar and a module-level global — and
the module-level global goes away.

**Source: D5, SPECIFICATION.md:86.** The ledger of **forwarded** requests (the
commander's QUIESCE bookkeeping) is a different thing with a different name:
it tracks work the server did NOT execute locally, and belongs to the
commander application, **never** to the base. See
[020 orchestration](../../20_spa/020_orchestration/).

**Source: D18, SPECIFICATION.md:249.** `__slots__` only on high-cardinality
objects — requests, register items, events/frames, config nodes — and NEVER on
servers, managers, commanders or applications. The old repository had it
backwards (a 21-slot singleton server).

## 8. Requests carry their own end of life

**Source: docstring of `RequestRegistry`, and its one consumer at
request.py:257.** Whatever a request opened, the request closes: code holding
the current item queues a zero-argument callback, and the server drains them
at the end of the dispatch, whether the handler returned or raised. The
server never learns what the resource was: a database connection closing
itself is the plain case.

*(Recorded as a docstring source, not a decision: it describes a mechanism
whose ratification was not found. See the friction on the `error` argument.)*

## 9. The application contract is the deliverable

**Source: D7, SPECIFICATION.md:93.** What the server requires of an
application — ASGI callable, its identity, its `server` property, lifecycle
hooks — is born before any real application class and is exercised by a
throwaway test application with one sync route, one async route and one that
raises. **The tests ARE the definition of the contract.** For WebSocket, only
the socket in `__call__` is present, and it is empty.

**Source: D16, SPECIFICATION.md:217.** Extension is subclassing, made real by
contract: every class peels its own kwargs and forwards the rest, mixins go
BEFORE the base in the MRO, and the end of the chain raises `TypeError`
naming any leftover.

**Ownership, one direction.** The server assigns `app.server = self` at
registration and the application-side setter accepts it once; the server
writes, the application reads. What "once" should mean when an application can
be unmounted and remounted (§4) is an open friction.

## 10. Lifespan: in order, in reverse, isolated

**Source: D2, SPECIFICATION.md:42, and the `Lifespan` docstring.**
`on_startup` in registration order, `on_shutdown` in reverse, so a thing
built on top of another is torn down first. Hooks may be sync or async. A
hook that raises is **logged and the sequence continues**: one application's
broken startup never prevents the others, and the ASGI acknowledgement is
always sent. Application errors are isolated; they never abort the protocol.

## 11. One thread pool, provisioned only if needed

**Source: D2, SPECIFICATION.md:47.** One monitored thread pool per server for
blocking work; async handlers stay on the loop and never touch it; lazily
provisioned, gauges exposed.

The gauges answer a question about pressure, so `busy` counts **demand, not
slots held**: every call entered and not yet returned, which past saturation
exceeds the slot count. Consumers clamp; the gauge does not flatter.

## 12. The installed composition, and self-configuration

**Source: D22, SPECIFICATION.md:351.** The core is the **complete
mono-process async server** — that is the cut.

**Source: D4, SPECIFICATION.md:67.** The `_server` application is
**automatic, not configured**. Service endpoints are never again injected
into the hosted application's router — recorded against old finding F3.

**Source: Ratified 2026-07-29, SPECIFICATION.md:772.** Nothing materializes a
server from the outside: the class that needs the values reads them.
Explicitly passed kwargs win over configured ones, **wholesale per kwarg**.
Detail in [015 configuration](../015_configuration/).

## 13. Restart is a target, not an afterthought

**Source: D21, SPECIFICATION.md:280.** Parity with the old daemon achieved
WITHOUT a daemon: **live pages survive ANY restart** — state survives process
*generations*, not inside an eternal process.

**Source: D20, SPECIFICATION.md:273.** Dev runs the shape of prod with
minimal numbers; the internal server runs STANDALONE from the same
configuration — no special inline mode, ever.

Both are owned by [120 restart](../120_restart/). They appear here because
they constrain what the base may hold that is not serializable — and because
§4 reduces how often a restart is the answer at all.

## 14. Deliberately outside the base

**Source: D7, SPECIFICATION.md:100.** By decision, not by omission: the
config builder, middleware, real auth and sessions, `_server`, WSX. Each
arrives as its own capability, in its own entry of this world.

---

# Open frictions

Scaffolding for the interview, not a register. Each voice below is a question
to settle; settling it edits this document — and, where the contradiction
lives upstream, edits the source too. This section shrinks to nothing, and
when it is empty this design can be ratified.

Interview file: `temp/interview_010_server.md`.

## Upstream — settling these edits SPECIFICATION.md

**S1 — D2 says the primary application is always present.** D2,
SPECIFICATION.md:54: "**the primary app, always present** — answers `/` and
everything no mount claims". §5 above says a server with nothing on the root
is legitimate, and the code agrees (status.md). The overturn's only record is
commit `a1a8f7e`, never appended to the log, although **D23**
(SPECIFICATION.md:398) exists precisely to reinstate "every ratified decision
is APPENDED here". Settling it means amending D2.

**S2 — D3 states the rule in two branches.** D3, SPECIFICATION.md:62, has
mount-or-primary; §5 has four branches, and neither the 307 nor the `default`
application appears anywhere in SPECIFICATION.md. Arguably still *one* rule
with fallbacks, which is why it is a question and not a defect. Same missing
log entry as S1. Settling it means amending or annotating D3.

**S3 — D5 gives the registry a duty nobody executes.** D5,
SPECIFICATION.md:74, duty (1) is "create the right request from the scope".
The registry creates a thin in-flight record; the `Request` handlers receive
is built by the owning application (status.md has the call sites). No source
for the reassignment was found in SPECIFICATION §2/§8, the `temp/` registers
or the `codex/` documents. Settling it means amending D5.

**S4 — where the principle of §1 gets written.** "Static only where dynamic
cannot be had" governs all 31 entries, not this one. If it lives only here,
the next entry does not inherit it. Candidate homes: the rules list in
`internals/00_overview/README.md`, a new D-entry in SPECIFICATION.md, or the
coding rules of the meta CLAUDE.md.

## Consequences of §4 to be decided

**S5 — what hot mount/unmount does to three properties.** Today's immobility
is load-bearing in three places, and §4 touches each:

- the demux reads the mount index with no lock, no snapshot and no
  invalidation, because nothing can change under it between two requests;
- `default` is validated completely at construction, because no later
  registration can make a name valid that is invalid now;
- the ownership channel is exactly-once, which is the natural meaning only
  while an application is never detached.

Are these properties to **keep** — so the hot command is built around them —
or consequences of immobility that fall with it?

*Partly answered on 2026-08-23: the second one survives, because accepting a
change is atomic and validated by the attempt, so `default` is never valid
against a tree nobody accepted. The first and the third are still open, and the
third has grown a second half — what "exactly once" means for an application
that is legitimately removed and put back.*

**S6 — who watches, and at what granularity.** *The "refused when" half was
settled on 2026-08-23: accepting is atomic and encloses the notification, so a
failure changes nothing, and feasibility is not pre-computed — the attempt is
the check. See [015 configuration](../015_configuration/design.md) §6.*

What remains: whether the server watches on behalf of the applications or each
application watches its own entry, and what becomes of one watching an entry
that is deleted wholesale.

## Defects and gaps in what exists

These are settled by fixing the code, not by amending a document; they are
listed here so the interview can order them against the rest.

**S7 — a multi-segment `mount` registers and is unreachable, silently.** No
validation that a mount is a single path segment; the demux only ever matches
the first. Proven live in status.md: the application is installed, listed,
visible to the monitor, and dead — no error at boot, no error at request
time. `mount="/api"` fails the same way. The coding rules want an explicit
error for an impossible case; the probability rule accepts an infimum case
**provided it ends noisily**. This one is silent.

**S8 — `default=` alongside a root application is accepted and inert.**
Validated as a name, never consulted, because the root application always
wins first. Proven live in status.md. A configuration that says something and
gets nothing, without a word. Milder than S7, same family.

**S9 — `run_cleanups(error=...)` has no caller and no reader.** The parameter
is declared and documented as carrying the terminating exception for
error-aware cleanups; the body never reads it, the only production caller
passes nothing, no test passes it. Either the argument goes, or §8's mechanism
grows the error-aware half it promises.

**S10 — two untested paths.** `AsgiServer.serve()`'s host/port precedence
(the only uncovered statements of its module, and the path every deployment
takes) and the `ValueError` on an unsupported ASGI scope type. Details and
line numbers in status.md. The first is shared with
[110 cli](../110_cli/) and [015 configuration](../015_configuration/).

**S11 — accepted risk: the pool teardown blocks the loop.** The lifespan
branch joins the worker threads synchronously on the event loop, after the
shutdown acknowledgement has been sent — so the loop has nothing left to
serve. Recorded as accepted pending confirmation; draining off the loop buys
nothing at that point.

**S12 — repo-wide: `tests/x/` is empty.** The coding rules mandate contract
tests and implementation/edge tests split by folder; the edge folder holds
only `__init__.py`, so every test is classified contract and every failure is
a STOP. Either correct as it stands, or a reclassification is owed — its own
task, never smuggled into another change. Not the server's to resolve;
recorded here because the server is the first subject to meet it.

## Recorded in more than one entry

Found by a reader who had only the documents. Each lives between two or three
entries, is written in the same words in each, and is settled once for all of
them.

**S13 — two documents answer "how does a handler know which request it is
serving" differently.** §4 of [README.md](README.md) says the registry answers
*which request am I serving right now?*, "asked by code buried deep inside a
handler, which needs the request but was never handed it".
[020 applications](../020_applications/design.md) §5 says there is no ambient
current request and that the old pair never returns. Both describe something
real — the registry holds a thin in-flight record, not the request object — but
no document draws that line, so the two pages read as opposites. Settling it
means writing the distinction in both. Recorded in the same wording in
[020 applications](../020_applications/design.md).

**S14 — the application contract has three different lengths across the
dossier.** [020 applications](../020_applications/design.md) §1 splits it four
and four. §2 of [README.md](README.md) states a list of its own and adds that
an application declares what may be done to it.
[015 configuration](../015_configuration/) §5 adds the survivable-failure
declaration. A reader who reads the three in order is told three times that the
contract is small and gets three different contracts. The split in 020 is that
entry's proposal, not a ratified shape: settling it means one list, written
there and referred to from the other two. Recorded in the same wording in
[020 applications](../020_applications/design.md) and
[015 configuration](../015_configuration/design.md).
