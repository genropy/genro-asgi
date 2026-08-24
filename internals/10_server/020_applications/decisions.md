# Applications — decisions

**Version**: 0.4 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

**The application layer, with the work finished.** Read this as a report from
the day everything described here is running: it says what an application
*is*, and never what it lacks. What the code holds is [status.md](status.md)'s
subject, and the road between the two is written one step at a time under
`steps/`.

Every voice carries its source. A voice sourced to the owner and a date was
decided in conversation before it reached any register.

The **open frictions** are the closing section, and they are the one place
here that compares this arrival with the present. When that section is empty,
this design stands on its own.

---

## 1. The contract is small, and it was born before any application

**Source: D7, SPECIFICATION.md:93.** What the server requires of an
application — an ASGI callable, an identity, a `server` property assigned by
the owner at attach time, and lifecycle hooks that may be written sync or
async — was delivered **before the first real application class existed**, and
was exercised by a throwaway application with one sync route, one async route
and one that raises. **The tests ARE the definition of the contract.**

The order is the point. A contract written after its first implementation
records that implementation; one written before it records the requirement. It
is also what makes an application writable by somebody who has never read the
server: what they must satisfy is those four items, every one of them about
the handover and none about the server's insides.

**Source: owner, 2026-08-23.** The contract stays that small because
everything else is on the other side of a line: what an application
**declares about itself**. A declaration is not a requirement — it has a
default that says *nothing special* — and what makes the set a contract is
that the rest of the system reads it without ever knowing which application it
is reading. Four declarations exist, each with its own source:

- **its configuration vocabulary** — §4 below;
- **who draws it** — the `app_snapshot` / `app_panel` / `panel_source`
  contract (**source: commit `c83f3e6`, 2026-08-14**, "the monitor — one page
  over every mounted app"), which is the general rule that a server-level
  surface grows by CALLING each application rather than by knowing one by name;
- **whether it can be moved while the server runs** — and declaring it means
  guaranteeing the mechanism, reversal included (**source: owner, 2026-08-23**;
  stated in [010 server](../010_server/decisions.md) §4 and
  [015 configuration](../015_configuration/decisions.md) §6);
- **whether its own failure is survivable** at boot, so the server starts
  without it instead of refusing to start (**same source**).

The line matters more than the count. Giving applications a new capability
means adding a declaration, never widening what the server requires of every
application — which is what would break the ones already written.

## 2. Extension is subclassing, and the chain is cooperative

**Source: D16, SPECIFICATION.md:217.** A consumer extends the framework the
same way the framework extends itself: by subclassing. Every class in the
family peels **its own** construction arguments and forwards the rest down the
chain; mixins sit before the base in the resolution order; the end of the
chain refuses an argument nobody claimed, naming it.

The consequence for an application is that adding a construction argument is a
local act. A subclass declares its own, forwards what is not its own, and no
class above or below is edited.

## 3. Identity is declared on the class, overridden per installation

**Source: commit `a1a8f7e`, 2026-07-25.** The identity — the `code` that names
an application and the `mount` that places it — is written as class attributes
a subclass sets declaratively, and either can be overridden per instance at
construction. So one class installed twice is two installations with two
identities, and neither is a copy of the other.

The identity's meaning for routing belongs to
[010 server](../010_server/README.md). What belongs here is the reason the application
side holds it at all: an application that knows its own code can read its own
configuration and name itself in a monitor without being told either.

**Ownership runs one way.** The server assigns itself as the owner and the
application records it; the application never reaches for a server. An
instance that is already owned refuses a second owner rather than changing
hands quietly, because an instance serving two servers would have one identity
and two contexts.

## 4. An application brings its own vocabulary

**Source: Ratified 2026-07-29, SPECIFICATION.md:772.** An application declares
the configuration words it consumes, as a grammar carried on the class. The
site recipe mounts that grammar at the line that installs the application, and
from that node down the site's own dialect steps aside: the words are the
application's, and the site never learned them.

The application reads them back **by address relative to itself**, through the
server's read door. It holds an address, never a copy of a subtree. Two
installations of one class therefore read two different sets of values, and
the class contains nothing that distinguishes them.

This is what makes an application configurable without anything central being
edited when a new one arrives.

## 5. Handlers are pure

**Source: D23 wave ruling, SPECIFICATION.md:413.** A handler is an ordinary
method with ordinary parameters, called with ordinary arguments. There is no
ambient current request a handler reads from the outside — the old
`server.request` / `server.response` pair **never returns**. A handler that
needs the live request **declares it as a parameter**, and it is passed in as
an argument like any other.

Two things follow, and both are worth more than they cost.

A handler is callable from a test with three values and no server. And the
same handler serves every protocol that reads the tree, because nothing in it
knows which one called: what differs between a form submission, a JSON
document and a call from a model is entirely in the fitting of arguments,
never in the handler.

## 6. Authorization is part of finding the handler

**Source: Invariant 3, SPECIFICATION.md:671.** A node that exists but is
denied **answers with its own 401 or 403** and never falls through to
something else. This is recorded as an invariant, from an old implementation
where the fall-through existed.

**Source: commit `5b567a3`, 2026-08-14.** The two answers are different and
the difference is not cosmetic. To a caller the server does not know: *401 —
identify yourself*, which a browser turns into a login. To a caller the server
does know, whose grants are not enough: *403 — not you*, where offering a
login form would be a lie.

The mechanism is that the caller's grants are a **filter on the resolution**,
not a check after it. A handler is therefore never reached by somebody who may
not have it, and a handler contains no authorization code for the framework to
have to trust.

**Source: Invariant 10, SPECIFICATION.md:688, enforced by D25,
SPECIFICATION.md:436.** The route tree is a routing structure and never a
registry of things: something with no routes is not attached to it. An
implementation once attached a route-less login method to the tree, and the
rule exists because of it.

## 7. A sub-tree is described, never wired

**Source: D25, SPECIFICATION.md:436, reaffirming the 2026-07-17 ruling as
non-negotiable.** An application is assembled from independently written
routing classes, and what it states is a **description of a branch**: a name,
the class that serves it, and whatever that class needs to be built — the
parent included, travelling as data rather than as a reference wired in
afterwards.

The distinction is not *when* the statement is made. An application describes
its branches in its own constructor, which is the natural place, and doing so
is not the retired gesture. The distinction is *what* is stated: a description
can be read, listed and published before anything is built, and a class named
in one can be described without being instantiated. An object constructed by
the caller and handed over cannot.

So the destination is the **factory form** — name, class, parameters — and the
retired call is the one that took an already-constructed instance and wired it
in. D25 counted the migration in call sites for exactly that reason.

**And a tree belongs to one application.** Nothing outside adds a route to
somebody else's tree. **Source: D4, SPECIFICATION.md:67** — service endpoints
are never again injected into a hosted application's router, recorded against
an implementation where exactly that happened.

## 8. Capabilities are plugged onto the tree by name

**Source: D26, SPECIFICATION.md:456.** Two capabilities are **fixed
structure**, armed on every application's tree rather than chosen: the one
that reads handler signatures and the one that publishes them. Because they
are always present, a per-route control over them always applies — a control
that only works when a capability happens to be enabled is a control nobody
can rely on.

The rest are named by the site's configuration and armed by the server on
every application it hosts. An application composed on a server that offers no
plugin machinery keeps the ones it arms for itself, and works.

> What a plugin is, and how one is written, is
> [025 routing system](../025_routing-system/README.md).

## 9. The vehicle follows the handler's nature

**Source: D2, SPECIFICATION.md:47.** Blocking work goes to the server's one
thread pool; code written for the loop stays on the loop and never comes near
it.

The application does not choose per call. The tree records what each handler
is, and the dispatch reads that record: an asynchronous handler is awaited, an
ordinary one is handed to the pool. A consumer writes whichever suits their
code and the vehicle follows.

**Source: Invariant 2, SPECIFICATION.md:668; commit `0dff4ed`, 2026-08-12.** A
thread-local resource is released **on the thread that opened it**. So a
synchronous handler is followed, on that same pool thread, by a hook that runs
whether the handler returned or raised — the place to release what only that
thread may release. A database connection belonging to a thread is the case
the invariant was written from. Asynchronous handlers have no such hook and
need none: an asynchronous handler owns its own awaits.

## 10. One answer type, and a sibling for the answers that do not fit

**Source: commit `53b4e38`, 2026-07-21 (core 1c).** The buffered answer is a
**single flat class** — no JSON response, no HTML response, no file response
to choose between. What the handler returned decides the body and the declared
type, and a route may declare a type of its own next to the method.

A single class is a decision about the consumer's day: the alternative is a
family whose members differ in one line, and a choice to be made at every
handler.

**Source: commit `c360f60`, 2026-07-24 (core 1e).** A stream is a **different
shape, not a variant**, so it is a sibling class and not a subclass: it frames
an asynchronous source of chunks onto the wire and deliberately does not carry
the buffered class's turning-a-value-into-bytes. A handler answers with one by
returning it.

**Server-sent events sit on top of streaming and are self-contained.** They
frame any asynchronous source of event records into the text format a browser
already understands. Two properties are the whole reason it survives a real
network: a silent source is kept alive by a periodic comment the receiving
side ignores, and a receiving side that goes away **cancels the source and
waits for it**, so a source holding a subscription releases it instead of
leaking one per closed browser tab.

*(The single-class shape and the sibling shape are recorded from the modules'
own contracts and their delivery commits; no ratified decision states either.
See the friction on where the response shape is ratified.)*

## 11. High-cardinality objects are slotted; the classes are not

**Source: D18, SPECIFICATION.md:249.** There is one request and one answer per
request, and requests are many, so those objects declare their layout. The
application classes themselves are singletons of their installation and do
not.

## 12. One tree, several protocols, one contract test

**Source: D22 scope ruling, SPECIFICATION.md:363.** The complete
machine-readable interfaces — the documented REST face and the tool face for
models — are part of the core, not of something built on it. They are
subclasses reading the same tree through different lenses, and a handler is
written once.

**Source: Invariant 9, SPECIFICATION.md:684.** Every interface with more than
one implementation carries **one contract-test suite run against all of them**.
The lesson is recorded from an implementation where two dispatch engines
diverged because nothing forced them to stay equal. The tree read by two
protocols is exactly that situation.

> [openapi](openapi/README.md) · [mcp](mcp/README.md)

---

# Open frictions

Scaffolding for the interview, not a register. Each voice below is a question
to settle; settling it edits this document — and, where the contradiction
lives upstream, edits the source too. This section shrinks to nothing, and
when it is empty this design can be ratified.

Interview file: `temp/interview_020_applications.md`.

## Upstream — settling these edits SPECIFICATION.md

**S1 — the app-side contract in §4 names a member that does not exist.**
SPECIFICATION.md:643-644 states the contract as "an ASGI callable with
`mount_name`, a `server` property …". There is no `mount_name`: the identity
has been `code` + `mount` since commit `a1a8f7e`. This is the same unlogged
ruling as S1/S2 of [010 server](../010_server/decisions.md), seen on the
application side, and settling it means amending §4 of the specification along
with D2 and D3.

**S2 — the live request reaches only the administrative application.** D23,
SPECIFICATION.md:413, ratifies that a handler needing the live request
"DECLARES a `request` parameter injected by `bind_kwargs`". In the shipped code
the injection exists **only on the administrative application**, and under the
name `_request`; the base reconciliation every hosted application inherits does
not inject anything (call sites in [status.md](status.md)). So the ratified
seam is not available to the applications a consumer writes, and the parameter
is not called what the decision calls it. Two questions in one: where the
injection belongs, and which name is ratified.

## Where the response shape is ratified

**S3 — §10 has delivery commits and no decision.** One flat buffered class
with type dispatch, a streaming sibling rather than a subclass, and the SSE
framing: none of it appears in SPECIFICATION.md, in §3's unopposed list, or in
the `temp/` registers. The record is the modules' own contracts and the two
commits that delivered them. These shapes constrain every application ever
written against this core, so either they are ratified or the fact that they
are conventions is recorded.

## Silent wrong answers

These end in a wrong result with no error anywhere, which is the family the
probability rule refuses outright: an infimum case may be accepted **provided
it ends noisily**, and none of these does.

**S4 — a body sent without a `content-type` header is discarded, and the
request answers 200.** The body is read only when the header is present, so a
caller that omits it has its document dropped and receives an answer computed
from the defaults. Proven live in [status.md](status.md): the same POST
answers `{"sum": 5}` with the header and `{"sum": 0}` without it. The gate is
in `genro_tytx.asgi_data`, so settling it may mean fixing a dependency rather
than this package.

**S5 — a `TypeError` inside a synchronous handler is reported to the caller as
a bad request.** A bug in a handler's own body — an addition between an int and
a string — surfaces as **400 "Invalid request arguments"**, with the internal
exception message in the body. The same bug in an asynchronous handler surfaces
as 500. Proven live in [status.md](status.md). The module's own contract
records the indistinguishability as known; nothing records it as accepted.
There are two halves: a server-side defect blamed on the caller, and an
internal message disclosed to them.

## Gaps in what exists

**S6 — an application cannot answer a WebSocket.** The only WebSocket door is
the server's, and at the base it accepts the connection and closes it politely;
no composition hands a socket to an application, so no application can hold a
long-lived conversation. Meanwhile the ratified delivery design for the SPA
world puts pushed traffic on WebSockets. **Q1**, SPECIFICATION.md:695, foresees
one dispatch engine with two transports, designed so that context, resolution
hooks and cleanups exist on both. The question that belongs here is what the
application contract's WebSocket door looks like, since it is the contract that
would grow the sixth obligation. Recorded in the same wording in
[20_spa/030 channel](../../20_spa/030_channel/README.md), and to be settled once for
both.

**S7 — the request body is never streamed.** It is read whole into memory
before the handler runs, so the size of an upload is bounded by the memory of
the process serving it. The answer side streams; the request side does not.
Nothing records this as a decision. Whether the arrival wants a streaming
request body — and if not, why not — is unanswered, and §1 of
[00 overview](../../00_overview/README.md) requires the reason to be written where the
limit is accepted.

**S8 — the path from a handler to a stream is untested.** The dispatch branch
that recognises a streamed answer and steps aside is the single uncovered
statement of its module, and it is the only route by which a handler's stream
reaches the wire. Its one production consumer is the inspector section. The
streaming and SSE classes are themselves covered; what has no test is the
handover. Line numbers in [status.md](status.md).

**S9 — the same 400 body carries two different things.** The bad-request answer
interpolates the underlying exception's message, which is what makes a genuine
validation failure useful to the caller and is also how S5 leaks an internal
one. Whether the detail is part of the contract or a convenience is not
recorded, and the two halves cannot be settled separately.

## Surface with no consumer

**S10 — three public members of the request nobody reads, and one guard nobody
can reach.** `created_at`, `age` and `scope` on the request have no consumer in
`src/`, in `tests/`, or in the genropy-asgi bridge, and the timestamp behind the
first two is stamped on every request that is served. Separately, the
`effective is None` guard in the response's content-type helper is excluded by
both of its call sites, and exists for a class attribute nothing ever sets.
Line numbers in [status.md](status.md). The rule is that what is left without
readers goes with the mechanism it belonged to; the question is whether these
are owed consumers — an age is what a monitor would show — or leftovers.

## Recorded in more than one entry

These four were found by a reader who had only the documents. Each lives
between two or three entries, is written in the same words in each, and is
settled once for all of them.

**S11 — two documents answer "how does a handler know which request it is
serving" differently.** [010 server](../010_server/README.md) §4 says the registry
answers *which request am I serving right now?*, "asked by code buried deep
inside a handler, which needs the request but was never handed it". §5 above
says there is no ambient current request and that the old pair never returns.
Both describe something real — the registry holds a thin in-flight record, not
the request object — but no document draws that line, so the two pages read as
opposites. Settling it means writing the distinction in both. Recorded in the
same wording in [010 server](../010_server/decisions.md).

**S12 — the application contract has three different lengths across the
dossier.** §1 above splits it four and four. [010 server](../010_server/README.md) §2
states a list of its own and adds that an application declares what may be
done to it. [015 configuration](../015_configuration/README.md) §5 adds the
survivable-failure declaration. A reader who reads the three in order is told
three times that the contract is small and gets three different contracts. The
split above is this entry's proposal, not a ratified shape: settling it means
one list, written here and referred to from the other two. Recorded in the same
wording in [010 server](../010_server/decisions.md) and
[015 configuration](../015_configuration/decisions.md).

**S13 — `BaseConfiguration`'s hooks are used and nowhere documented.** A site
recipe deviates from the package defaults by overriding one hook —
`server_section`, `storage_section`, or the `storage_mounts` that the second
calls. [015 configuration](../015_configuration/README.md) names none of the three, and
describes the class only as the dialect "with the package's own defaults
already written into it".

The cost shows in this entry's recipe, the only one of the three that leans on
the inheritance: its `main` calls two methods it does not define and it defines
a third nothing appears to call. The recipes of 010 and 015 avoid the question
by defining every method they call, which is a coincidence of how they were
written rather than a rule. A reader cannot tell whether the recipe works or is
broken, and the recipes are the one executable thing in each entry. The hooks
belong in 015, and the paragraph added above this entry's recipe is a patch
until they are there. Recorded in the same wording in
[015 configuration](../015_configuration/decisions.md).

**S14 — two exception-to-status mappings, and nothing relates them.** The
resolution maps router failures to the HTTP exceptions the ring answers. The
response class carries a second table of its own, which maps `ValueError` and
`TypeError` to 400, `FileNotFoundError` to 404, `PermissionError` to 403 and
everything else to 500. Both exist; no document says which applies when, or
whether the second is the mechanical cause of S5. The division of labour has to
be stated, and it belongs partly to [030 middleware](../030_middleware/README.md), which
owns the ring. Recorded in the same wording there.

## Half a migration

**S15 — the factory form of §7 is used nowhere.** `attach_instance` is gone
from the package, and every branch in it — four call sites, listed in
[status.md](status.md) — is still declared in the **instance** form, handing
over an already-built object. D25 named exactly those four sites and put their
conversion to `cls` + `params` recipes in a later macro, which has not
happened. So §7's destination is stated and unreached, and the entry's own
recipe shows the interim form because it is the only one in use.

Two things ride on settling it. The library now derives the timing from the
form — a factory branch is built on first traversal, an instance branch is
linked immediately — so converting the four sites also changes *when* those
sub-trees exist, and D25's note that "branches are EAGER BY DEFAULT", verified
against genro-routes 0.28.0, no longer describes the library. And the entry's
recipe teaches whichever form we keep.

## Declared here, absent in the code

**S16 — two of the four declarations of §1 have no member to be made with.**
`BaseApplication` carries nothing by which an application says whether it can be
moved while the server runs, and nothing by which it says its own failure is
survivable — proven in [status.md](status.md), where the search comes back
empty. Both are consequences of the live configuration, which is itself
unbuilt, so the absence is expected rather than surprising.

It is recorded because of the shape §1 gives it: the two are stated with a
source and a date beside them, exactly like the two that do exist, and a source
is a record of a decision rather than of a delivery. A reader cannot tell the
decided from the delivered by looking, and this friction is what tells them.
It closes when the members exist, not by editing §1.

**S17 [cross · unratified] — the fixed pair is stated in two entries and armed
in three moments.** §8 above names two capabilities as fixed structure, on D26's
authority. A booted application's tree carries **three**: the third is the
authorization plugin, which the application arms for itself in its own
constructor rather than receiving it from the server. Nothing states the
division as a rule, so a reader who counts the always-present plugins gets two
from the specification and three from the code. Recorded in the same wording in
[025 routing system](../025_routing-system/decisions.md).

**S18 [cross] — the request id never reaches the log line.** §4 of
[README.md](design.md) says every request carries an id "so one line in a log
can be followed across the whole machine". The only layer that writes a log
line writes the method, the path, the status and the elapsed time, and not the
id. So the identifier's stated purpose is served by nothing. Either the access
line carries it, or the reason given here is rewritten. Recorded in the same
wording in [030 middleware](../030_middleware/decisions.md).

## Settled on 2026-08-24 — no longer open

Recorded here only so the next reader is not surprised by its absence.

- **where the essentials of routing live.** Not here. §2 of
  [README.md](design.md) states that an application *is* a routing class and
  sends the tree, the walk, its three filters and the plugins to
  [025 routing system](../025_routing-system/README.md), which was `025_plugins` and was
  renamed for it. Owner, 2026-08-24.
