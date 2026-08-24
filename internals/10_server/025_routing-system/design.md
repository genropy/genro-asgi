# Routing system — design

**Version**: 0.5 · **Last Updated**: 2026-08-24 · **Status**: 🔴 DA REVISIONARE

**The routing system, with the work finished.** Read this as a report from the
day everything described here is running: it says what a routing class, a walk
and a plugin *are*, and never what they lack. What the code holds is
[status.md](status.md)'s subject.

Every voice carries its source. A voice sourced to the owner and a date was
decided in conversation before it reached any register.

The **open frictions** are the closing section, and they are the one place here
that compares this arrival with the present. Each carries a **family tag** in
brackets, because these frictions are settled in one grouped pass across the
server skeleton rather than one entry at a time (owner, 2026-08-23).

---

## 1. Routing is a library, and this entry is where it is explained

**Source: owner, 2026-08-24.** The tree, the walk, the filters and the plugins
come from genro-routes; the core composes them and adds one dialect. They are
explained **here**, after applications rather than before, on a reading order
the owner chose: *an application is a routing class*, and once that is said,
what a routing class is can be explained in full without an application having
to be described twice.

The consequence for [020 applications](../020_applications/) is deliberate.
That page states the inheritance and two facts its own blocks need — a route
may carry options nobody in the handler reads, and a tree can describe itself —
and sends the mechanism here. An application page that also explained trees
would be two subjects in one, which is what it was until this entry took the
second.

## 2. A tree is read off the class, never declared beside it

**Source: the library's design, composed by this package.** A method carrying
the route marker becomes a node named after the method. There is no table of
paths, no registration call, no file to keep in step.

The property this buys is the one that matters months later: **a route cannot
drift from its handler**, because there is no second place where the route is
written. Renaming the method renames the path, and a path that answers is a
method that exists.

## 3. Options travel beside a route, prefixed by who reads them

**Source: the library's convention.** An option written at a route is named for
the plugin that reads it — the plugin's code, an underscore, the option. A
prefix nobody armed is ignored rather than refused.

Two things follow. A handler stays **pure**: the options are about the route,
not about the computation, and no handler body reads its own options. And a
tree remains readable by a consumer that does not exist yet — a face nobody has
written can be added later and find the words it needs already written beside
the routes.

## 4. The walk is filtered on three independent axes

**Source: the library's three bundled filter plugins; owner, 2026-08-24 for
recording all three here.** Resolving a path is not *does this node exist* but
*does this node exist for this caller, on this installation, through this
channel*:

- **tags** (`auth_rule`) — who is calling;
- **capabilities** (`env_requires`) — what this installation is able to do,
  **accumulated down the tree**, so a branch inherits its parents' and adds its
  own;
- **channel** (`channel_channels`) — the surface the request arrived through.

They are independent, and the design point is that **all three are answered
during the walk rather than after it**. A node excluded is never reached, so no
handler contains a check the framework has to trust, and no face publishes a
route the caller could not have called.

**Source: Invariant 3, SPECIFICATION.md:671.** A node that exists but is
withheld answers with its own status and never falls through to something else.
The invariant is recorded from an implementation where the fall-through existed.

**Channel is what makes one tree serve several consumers**, and it is not a
promise: the tool face walks the tree with its own channel set, so a route
marked for one surface does not appear on the other. A route callable by a model
and not by a browser says so once, beside itself, and both faces are built from
the same tree — which is the mechanism behind the claim
[020 applications](../020_applications/) makes about its several protocols.

The asymmetry is worth stating, because it is the one a reader gets wrong: the
**HTTP dispatch passes no channel at all**. Every route is reachable over HTTP
unless its tags say otherwise, and the channel filter narrows only the faces
that choose to use it.

## 5. A tree can be read as well as walked

**Source: the library's neutral description; D22 scope ruling,
SPECIFICATION.md:363.** A tree describes itself — nodes, declared parameters,
options beside them, branches below — in terms that name no protocol.

That neutrality is the seam the whole core turns on. Every face that presents
an application to an outside consumer is built by reading the description, so a
new face is a new reader and never a new obligation on the routes. It is also
why the two faces this core ships live in it rather than in the library:
publishing is not a routing concern, and the library should not learn one
publishing format after another.

## 6. The capability is a mixin, and the base does not know it

**Source: D17, SPECIFICATION.md:229; D2, SPECIFICATION.md:42.** The base server
owns a closed list, and plugins are not on it. The capability arrives as a
**mixin composed before the server class**, peeling its own construction
arguments and forwarding the rest — the cooperative chain of D16.

The consequence is stated rather than implied: a composition without the mixin
**exposes no arming surface at all**, and a routed application on such a server
runs with only what it armed for itself. That is a working server, not a
degraded one.

## 7. A plugin is armed on a tree, not wrapped around a dispatch

**Source: owner, 2026-08-23.** The two extension points of this framework are
often confused, and the difference is where they attach.

A **middleware** wraps the dispatch: it sees every request the server serves,
including those bound for applications that have no routes. A **plugin** is
armed on the route tree of one application: it sees the tree's own description
and no traffic at all. One is a ring around the door; the other is a property
of the map.

So a plugin can say things about routes that do not exist yet, and a middleware
cannot; and a middleware can answer a request no route matched, and a plugin
cannot.

> The ring is [030 middleware](../030_middleware/).

## 8. Nothing registers itself at import

**Source: the coding rule against module-level state; recorded in the module's
own contract.** Importing this package registers **no plugin** against the
routing library. Registration is an explicit act performed while arming, and
the default mapping of codes to classes is produced by a call rather than held
at module level, so each server gets its own and no two share one they can both
write.

The rule buys exactly one thing, and it is worth being precise about which.
Every server decides for itself **which class it would offer** under a code.
What it does not decide is **which class a code resolves to** once armed: that
is the routing library's own registry, it is process-wide, and the first arming
wins it. So the rule keeps two servers from corrupting each other's intentions,
and does not keep the second one from being overruled — which is friction S2
below, and the reason this section stops where it does.

## 9. Two plugins are structure, and cannot be switched off

**Source: D26, SPECIFICATION.md:456** — "as part of #6, `pydantic` and
`openapi` became FIXED server structure (armed on every router), so per-entry
OpenAPI controls always apply".

The clause after the comma is the whole argument, and it is worth stating on
its own. A per-route control that only applies when a capability happens to be
enabled is a control nobody can rely on: the same words beside a route would
mean one thing on one installation and nothing on another, and reading a route
would stop telling you how it behaves.

So asking to disable one of the two is an **error**, not an opt-out. A site
tunes them and adds to them; it does not remove them.

## 10. Arming is late, once, and safe to repeat

**Source: owner, 2026-08-23.** An application is built before it belongs to a
server, so while it is being built there is nobody to ask which plugins to arm.
Arming therefore happens at the **first look at the tree after installation**,
which is the earliest moment the answer exists.

Repeating it is safe, and by design rather than by luck: a tree already
carrying a plugin does not receive it a second time, and a class the routing
library already knows is not registered again. So nothing anywhere has to
remember whether a given look was the first one, and a debugging line that
touches a tree cannot change what an installation does.

The lateness has one visible consequence, and it belongs in the design rather
than in a footnote: **a server that has finished booting has armed nothing
yet.** The set arrives when something first looks. An installation inspected
before that shows each tree carrying only what its application armed for
itself.

## 11. A code names a plugin, and an unknown code is refused loudly

**Source: owner, 2026-08-23.** A site writes a **code** and nothing else. Three
sources fill it — the routing library's own plugins, the dialect plugins this
package ships, and a class a site brings — and they share one namespace.

A code nobody can resolve **stops the arming with an error naming it and
listing what is available**. It is never a silent no-op, because a capability
that failed to arm is discovered by the absence of an effect nobody was
watching for: a filter that does not filter looks exactly like a tree with
nothing to hide.

## 12. A dialect is a plugin, and lives outside the routing library

**Source: D22 scope ruling, SPECIFICATION.md:363; the package layout.** The
routing library ships the five plugins that are about *routing* —
authorization, signature reading, logging, and two more. A **dialect** — a way of publishing a tree to an
outside consumer — is a different kind of thing and lives here, because
publishing is not a routing concern and the routing library should not learn
one publishing format after another.

There is one dialect plugin today, and a second face reads the same neutral
description without being a plugin at all. Both are described where they are
consumed.

> [020 applications / openapi](../020_applications/openapi/) ·
> [020 applications / mcp](../020_applications/mcp/)

---

# Open frictions

Scaffolding for the interview, not a register. Each voice carries a **family
tag**: the frictions of the server skeleton — 010, 015, 020, 025, 030 — are
settled in one grouped pass by family, because forty voices turned out to be
about eight problems (owner, 2026-08-23).

Interview file: `temp/interview_025_routing-system.md`.

**S1 [placement] — the dossier's own index promises entry points that do not
exist.** The one-line description of this entry in
[00 overview](../../00_overview/) reads "capabilities plugged by name,
genro-routes entry points". There is **no entry-point mechanism**: not in this
package, not in the routing library, and not in either `pyproject.toml`
(searched for `entry_point`/`entry-points`, nothing). A plugin a site brings
arrives as a class handed to the server, which is a different thing. Either the
line means the library's own plugin registry and is misleading, or it describes
something intended and unbuilt. Settling it edits the overview.

**S2 [silent] — two servers in one process, one plugin code, two classes: the
first one wins, and nobody is told.** The registration behind a code is the
routing library's, and it is **class-level and process-wide**. The first server
to arm a code registers its class; a second server that brought a different
class under the same code has its own ignored, silently, and its trees carry
the first server's plugin. Proven live in [status.md](status.md), where the
second server asks for one class and gets the other.

Two servers in one process is a real shape here — the tests do it, and so does
a composition that hosts an internal server. Two *different* classes under one
code is rare. By the probability rule the case may be accepted, **provided it
ends noisily**, and this one does not.

**S3 [undocumented] — a plugin of one's own cannot be declared in a
configuration.** The class travels as a construction argument, and the
configuration has no counterpart for it: the section names codes only. So a
site with a plugin of its own must build its server in Python, and the promise
that a description plus one command is a complete deployment unit
(SPECIFICATION.md:817) does not hold for it. It also sits against
[015 configuration](../015_configuration/) §2, which says a new capability
brings its own words with it and nothing central is edited. The failure is at
least loud — §11 above — which is why this is a gap and not a defect.

**S4 [unread] — the shipped dialect plugin computes a block nobody reads, and
that is why six of its seven options have no test.** Its `entry_metadata`
repackages the per-route publishing options and the description carries the
result under the plugin's own code. The OpenAPI reader does not look there: it
reads the raw configuration from a different key of the same description, so
the plugin's contribution is a duplicate with no consumer. Proven in
[status.md](status.md), which names both keys.

The untested half follows from it rather than standing beside it: only the
method override is exercised, and tags, summary, description, deprecated,
security scheme and the explicit security override are uncovered — because
there was nothing to assert them against. Settling this decides whether the
reader moves to the contributed block or the method goes.

**S5 [unratified] — plugins are server-wide, and nothing records the decision.**
The section belongs to the server, so what it names is armed on **every** routed
application the server hosts. A site cannot arm one plugin on one application
only — logging on the administrative surface but not on the shop, for instance.
Whether that is the design or a limit is written nowhere, and §2 above, which
insists that a plugin attaches to *one tree*, reads as promising the opposite.

**S6 [cross · unratified] — the fixed pair is stated in two entries and armed in
three moments.** The pair is D26's, but the third always-present plugin —
authorization, which the application arms for itself — is named in
[020 applications](../020_applications/) §2 and here, and nothing states the
division as a rule. A reader who counts the always-present plugins gets two
from D26 and three from the code. Recorded in the same wording in
[020 applications](../020_applications/design.md).

**S7 [silent] — a published verb is a description that nothing enforces.** A
route declaring itself a `DELETE` is published as one, and the dispatch does not
read the verb: the same route answers a `GET` that reaches it. Proven live in
[status.md](status.md). So the document handed to a consumer states a
constraint the server does not apply, and a client that respects it and a client
that ignores it both succeed — which is the shape of a defect nobody discovers
until something depends on the constraint being real. Whether the verb should
gate the dispatch, or the document should stop implying it does, is not
recorded anywhere.

## Settled on 2026-08-24 — no longer open

Recorded here only so the next reader is not surprised by its absence.

- **where the essentials of routing live.** They live here: this entry was
  `025_plugins` and became the routing system, with the plugins after the
  routing rather than instead of it, on the owner's decision. Its counterpart
  in [020 applications](../020_applications/) is settled the same way — that
  page states that an application *is* a routing class and sends the mechanism
  here. The answer is §1 above.
