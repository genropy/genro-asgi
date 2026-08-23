# Middleware — design

**Version**: 0.4 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

**The ring, with the work finished.** Read this as a report from the day
everything described here is running: it says what the chain *is*, and never
what it lacks. What the code holds is [status.md](status.md)'s subject.

Every voice carries its source. A voice sourced to the owner and a date was
decided in conversation before it reached any register.

The **open frictions** are the closing section. Each carries a **family tag**
in brackets: the frictions of the server skeleton are settled in one grouped
pass by family rather than one entry at a time (owner, 2026-08-23).

---

## 1. The chain is a capability, and the base has none

**Source: D17, SPECIFICATION.md:229; D7, SPECIFICATION.md:100.** Middleware is
explicitly outside the base server, by decision rather than by omission, and
arrives as a **mixin composed before the server class** — the same shape every
capability takes.

**Source: Q2, SPECIFICATION.md:698** — *"Middleware chain: in the base or only
on the public server?"* — is answered by D17 in the general: it is a
capability, so it is wherever a composition puts it. A server built without
the mixin does not have a disabled chain; it has no chain, and no attribute
where one would be. That is the difference between a composition and a flag,
and it is why the question stopped being open.

## 2. Order is declared, never arranged

**Source: owner, 2026-08-23.** Each layer states **one number**, and the chain
sorts itself: lowest outermost. There is no ordered list to maintain, no
dependency declaration, and no significance to the order in which layers were
registered.

The alternative — an explicit list somewhere — puts the knowledge of where a
layer belongs in a different file from the layer, and every new layer becomes
an edit to a shared thing. A number on the class travels with the class.

Three positions carry an argument rather than a convention, and the arguments
are the design:

- **errors outermost**, because it must be able to answer what anybody inside
  raised, another layer included;
- **session outside identity**, because the identity may be read from the
  session; reversed, the fallback would silently never fire;
- **cross-origin outside session**, because a preflight is a question about
  permission to send, and answering it must not mint a session for a request
  that carries no user.

## 3. Raising is how a layer answers

**Source: owner, 2026-08-23.** No layer inside the ring builds an error
response.
It **raises**, and the outermost layer turns the exception into an answer.

This is what makes the whole ring composable. A probe filter that wanted to
answer a 404 itself would need to know the body format, the negotiation, and
the headers; raising, it needs to know none of them, and the answer it
produces is identical to the one the route resolution produces for an unknown
path. One exception type, one answer, wherever it came from.

It is also what lets a handler raise a 404 from three frames deep and get the
right answer without touching a response object.

## 4. The error body follows the caller

**Source: the module's own contract; no ratified decision states it.** An
error's body is negotiated on the caller's `Accept`: a caller
asking for JSON gets the JSON document, a browser and a caller that asked for
nothing get plain text.

The default is text **because it was text before the negotiation existed**.
Widening a default silently is how a client that parsed one shape starts
receiving another, and the cost of an inelegant default is smaller than the
cost of that.

## 5. A 401 is a question, and the form of the question depends on who is asked

**Source: D24, SPECIFICATION.md:421; commit `5b567a3`, 2026-08-14.** Where the
installation has a login surface, a 401 is the server asking the caller to
identify themselves. Asking a browser and asking a program are different acts.

A **browser navigation** — a GET whose `Accept` asks for HTML — is redirected
to the login page, carrying where it was going so the login can put it back
there. Anything else keeps the bare 401 with its challenge header and gains a
body naming the login URL, so a program can drive the login itself rather than
parsing a page.

With no login surface the 401 is answered like any other error: the
negotiation exists to serve a login that exists, and it does not invent one.

**The destination carried back is validated, never echoed.** A `next` that
came in from outside is the classic open redirect, and it is checked before it
is used.

## 6. An answer that has begun cannot be replaced

**Source: the module's own contract.** The outermost layer watches the
outgoing side and knows whether the response has started. An exception raised
after the first byte of the answer has gone cannot be answered: a second start
would corrupt a stream the client is already reading. It is logged and
re-raised, and the transport tears the connection down.

This is a boundary of what the ring can promise, and it is stated so that
nobody reads "errors is outermost" as "nothing can escape". What escapes is
exactly the class of failure that happens too late to be answered.

## 7. The ring carries HTTP, and says so

**Source: D7, SPECIFICATION.md:100; the mixin's own contract.** The chain is
walked only by HTTP scopes. The lifespan conversation and WebSocket
connections go straight to the server.

For the lifespan this is right and needs no defence: start-up and shutdown are
not requests and have no caller.

For WebSocket it is a **limit that is inherited rather than chosen**: two of
the layers in this ring are exactly what a handshake needs — the origin check
before accepting, the identity resolved before the conversation starts — and
**Invariant 4, SPECIFICATION.md:674** requires an origin gate on WebSocket
handshakes. Where those live when this core grows long-lived conversations is
[20_spa/030 channel](../../20_spa/030_channel/)'s to decide, and until it does,
this page records that the ring does not reach them.

## 8. The ring is the machine's, not an application's

**Source: owner, 2026-08-23.** The chain runs before the demux, so no layer can
be armed for one application and not another. That is deliberate: the questions
the ring answers — who is calling, may this origin read the answer, what does a
raised exception become — must have one answer per machine, or two applications
on one server would disagree about them, and a caller would learn which by
trying.

What an application wants for itself goes in its own tree, where a plugin is
the instrument. The two extension points differ in scope and that is the whole
distinction.

> [025 plugins](../025_plugins/).

---

# Open frictions

Scaffolding for the interview, not a register. Each voice carries a **family
tag**; the skeleton's frictions — 010, 015, 020, 025, 030 — are settled in one
grouped pass by family (owner, 2026-08-23).

Interview file: `temp/interview_030_middleware.md`.

**S1 [unread · cross] — the second exception-to-status table has no production
reader.** The response class carries a mapping of `ValueError` and `TypeError`
to 400, `FileNotFoundError` to 404 and `PermissionError` to 403. Its only
production caller is this ring, and it calls it **inside a branch that already
knows the exception is an HTTP one** — which carries its own status, so the
mapping is never consulted. Every other exception takes the explicit 500 path
beside it. Proven in [status.md](status.md); the table is exercised by tests
alone.

So this is not two competing mechanisms, as it first reads: it is one live path
and one table nothing reaches. Either the non-HTTP branch starts consulting it —
which would turn a handler's `ValueError` into a 400, and that is the same
decision as
[020 applications](../020_applications/design.md) S5 — or the table goes.
Recorded in the same wording in
[020 applications](../020_applications/design.md), friction S14.

**S2 [placement · cross] — the WebSocket origin gate has nowhere to live.**
Invariant 4 (SPECIFICATION.md:674) requires an origin gate on WebSocket
handshakes, recorded from an implementation that had one. The ring is the
natural home for it and the ring does not see WebSocket scopes. §7 states the
boundary; nothing states where the gate goes. Recorded in the same wording in
[20_spa/030 channel](../../20_spa/030_channel/), and it is the same subject as
[020 applications](../020_applications/design.md) S6 seen from the ring.

**S3 [undocumented · cross] — a middleware of one's own cannot be named in a
description, and here the grammar refuses the word.** The class travels as a
construction argument. Unlike the plugins section, which accepts any code, the
middleware element declares **six keyword parameters and no more**, so a
seventh name is rejected by the grammar itself. The element's own docstring
records this ("one registered through `middleware_registry=` is not
configurable here"), which makes it a statement rather than an oversight — but
no ratified decision says it, and
[015 configuration](../015_configuration/) §2 promises the opposite shape for
capabilities generally. Recorded in the same wording in
[015 configuration](../015_configuration/design.md) S6 and
[025 plugins](../025_plugins/design.md) S3.

**S4 [silent] — a misspelled log level becomes INFO without a word.** The
access-log layer resolves its `level` option by looking the name up on the
logging module and falling back to INFO when it is not found, so `"verbose"`
and `"nonsens"` both silently produce INFO. Proven in
[status.md](status.md). A configuration value nobody validates is the shape the
probability rule refuses: rare, cheap to check, and silent.

**S5 [unratified] — `level` names the severity, not a threshold.** The option
sets the level the access lines are *emitted at*, so `level="WARNING"` does not
quieten the log — it makes every request a warning. A reader configuring
`level` almost certainly means the other thing. Nothing records which was
intended, and the two readings differ in what an operator's log looks like.

**S6 [unratified] — nothing states that the ring is uniform per machine.** §8
is written from the shape of the code, not from a decision: no source says a
middleware may not be per-application, and the same question is open one entry
away for plugins ([025 plugins](../025_plugins/design.md) S5). The two should
be answered together, because the answer decides whether the switches stay in
the server's vocabulary or move into each application's.

**S7 [untested] — the cross-origin layer's list-valued options and its
credentialed path.** Three statements of that module are uncovered: the branch
that accepts an option already given as a list rather than a comma-separated
string, and two of the header-building branches. Line numbers in
[status.md](status.md). The layer is the one whose misconfiguration is a
security finding rather than a bug, which is why its untested branches are
worth naming.

**S8 [unratified] — the error negotiation cites a decision that does not
contain it.** The module attributes the `Accept`-driven error body to "D4
error-body reconciliation". D4 (SPECIFICATION.md:67) is about the
administrative application being automatic rather than configured, and says
nothing about error bodies; the negotiation appears in no D-entry, in no
unopposed voice of §3, and in no register. §4 above therefore carries no source
but the code. Either the negotiation is ratified, or the citation is corrected
to say it is a convention — leaving a wrong citation in place is worse than
either, because it makes an unratified choice look settled.

**S9 [silent] — an error response loses everything the inner layers add on the
way out.** The outermost layer answers on the `send` it was handed, which is
the one outside every other layer — so no inner layer's outgoing half runs for
an error. Proven live in [status.md](status.md) with one request each way: the
same route, same origin, same new session, answers 200 **with** the
cross-origin header and the session cookie and 404 **with neither**.

The cross-origin half is the one that costs. A browser cannot read a response
that carries no allow-origin header, so an application that asked for its
errors as JSON — which §4 exists to give it — receives a network failure
instead of the 404 the ring carefully negotiated. The negotiation is honoured
and then made unreadable.

**S10 [silent] — `errors=False` is accepted, and then nothing answers.** The
switch is a plain member of the six, so a description may turn the outermost
layer off. With it off, an `HTTPNotFound` raised by the route resolution
**escapes the server uncaught** — proven live in [status.md](status.md).

Compare [025 plugins](../025_plugins/design.md) §4, where disabling one of the
fixed pair is an error rather than an opt-out, on the argument that a control
nobody can rely on is not a control. The same argument applies here with more
force: every other layer in the ring, and every raise in the codebase, is
written on the assumption that this one is present.

**S11 [cross] — the request id never reaches the log line.**
[020 applications](../020_applications/) §4 says every request carries an id
"so one line in a log can be followed across the whole machine". The only layer
that writes a log line writes the method, the path, the status and the elapsed
time, and not the id. So the identifier's stated purpose is served by nothing.
Either the access line carries it, or 020's reason is rewritten. Recorded in the
same wording in [020 applications](../020_applications/design.md).
