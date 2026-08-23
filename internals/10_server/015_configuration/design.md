# Configuration — design

**Version**: 0.3 · **Last Updated**: 2026-08-23 · **Status**: 🔴 DA REVISIONARE

**Configuration, with the work finished.** Read this as a report from the day
everything described here is running: it says what a configuration *is*, and
never what it lacks. What the code holds is [status.md](status.md)'s subject.

Every voice carries its source. A voice sourced to the owner and a date was
decided in conversation before it reached any register.

The **open frictions** are the closing section — the one place here that
compares this arrival with the present. When it is empty, the design stands on
its own.

---

## 1. An installation is described once, and reads itself

**Source: D15, SPECIFICATION.md:171.** One configuration is the whole site;
each process materializes the projection of its own role.

**Source: Ratified 2026-07-29, SPECIFICATION.md:772.** Nothing materializes a
component from the outside: **the class that needs the values reads them.** A
value passed explicitly at construction wins over the configured one,
**wholesale per value** — so a configured installation runs on another port
without a word of its description changing.

The consequence worth stating: there is no builder, no factory, no assembler
that knows the whole system. There is a description, and each part reads its
own part of it.

## 2. The description is a recipe: code, not data

**Source: Ratified 2026-07-29, SPECIFICATION.md:772** (the config layer
refounded on genro-builders `contrib/config`).

A description is a **class with one method**, calling a grammar to build a
document. Being executed rather than parsed is what makes it possible to hand
over **objects** — an application class is imported and passed as itself, so a
name that does not exist fails at boot with an import error rather than at
first use with a lookup miss.

**Source: owner, 2026-08-23.** A description too long to read at a glance is
split into methods, one per section, each taking the parent node. The recipe
orchestrates; the sections describe.

**Secrets never appear in a recipe.** A value that comes from outside — the
environment, a file, a vault — is written as a **resolver** placed exactly
where the literal would have gone, and resolved when it is read. Words whose
only legitimate source is outside **refuse a literal at the recipe line**: the
bootstrap administrator password cannot be typed into a description at all.

## 3. Every part declares its own words

**Source: owner, 2026-08-23; the mechanism is the subbuilder-by-reference of
contrib/config.**

There is no central vocabulary. **Each part declares the words it consumes,
next to the code that reads them**, and the description is validated against
the union of those declarations. Adding a capability or an application adds its
words with it; nothing central is edited and nothing central learns.

The declarations compose three ways, and the difference matters:

- **the server's own sections** — the top level, a closed list;
- **a capability's words**, attached to the branch they belong to: the part
  that owns a subject declares that subject's vocabulary and hangs it where it
  reads it;
- **an application's whole vocabulary**, which the site's grammar does not know
  and does not validate. A description names the application *class*, and from
  that node down the application's own grammar governs. The envelope's
  attributes stay with the site; the children belong to the application.

**Source: elements.py:55-58 (the pool clause); R11 amended and R12
superseded on 2026-08-18 by the owner —
`temp/design_m4_2026-08-18.md:5`, :186, :201.** So a pool is not a section of the site: it
belongs to the application that owns it, and its words live under that
application's entry. The same rule sends storage mounts to whoever manages
volumes: this dialect declares no storage vocabulary of its own, it declares a
mount point.

**Validation happens when the description is executed**, not when a value is
used. A word that does not exist, a section in the wrong place, a required
attribute missing, a singleton written twice: each stops the boot, naming
itself. A description that runs is a description whose every word was
understood by whoever will read it.

## 4. Three layers, and the site wins

**Source: Ratified 2026-07-29, SPECIFICATION.md:772; layering policy in
`default_config.py`'s own contract.**

The same installation is described at three levels, folded lowest first:

1. **the package's defaults** — written as a recipe like any other, not as
   fallbacks buried in constructors, so they read in the same language and a
   site overrides them one value at a time;
2. **the machine's layer** — what a system administrator owns: a volume that
   exists only on this host, where key material comes from, the listener. Set
   once, inherited by every installation on that machine;
3. **the site's own description** — always last, always winning.

**A recipe governs its own inheritance.** It declares where its middle layer
comes from, and it may decline the layer entirely and sit straight on the
package defaults. The runtime takes no argument for it: the description decides.

**An explicit choice that cannot be honoured is an error.** A defaults file
that is named and missing stops the boot; it is never a silent skip.

**The layering is on the tree, not on the class hierarchy.** Each recipe is
executed and the results are folded, so what a description inherits does not
depend on which class it happened to subclass.

## 5. One door, four layers of fallback

**Source: Ratified 2026-07-29, SPECIFICATION.md:772** (the inherited four-layer
read stack).

A value is asked for by **path**, through one call, and the answer is resolved
in order: the written value (a resolver there resolves now, so a value coming
from the environment is read when asked and not frozen when the recipe ran) →
the default declared by the word's own grammar, also read now → the caller's
own default → a **noisy error naming the path**.

The third layer is what makes the door usable everywhere; the fourth is what
makes a typo loud. A path nobody wrote and nobody defaulted is a mistake, and
it says so.

**A part holds an address, never a copy.** An application asks with paths
relative to itself and the door prefixes them with its own identity, so an
application can read only its own words — and the same class installed twice
reads two different sets without either installation knowing.

## 6. The description is alive

**Source: owner, 2026-08-23; direction parked by D23,
SPECIFICATION.md:418-419** ("the two-stage live-config architecture — config as
live object, `apply_configuration`, hot/cold changes — stays parked as a future
macro").

The description is **not read once at boot and discarded.** It stays as a tree
the running system holds: it can be read, it can be **written**, and it
**notifies** whoever asked to be told (the notification is the tree's own —
`Bag.subscribe`).

### At boot: valid, or no boot

The grammar is checked first. A description that is grammatically wrong does
not run. A description that is grammatically right but **not actionable** —
a mount claimed twice, an application class that will not import, a default
naming something absent — **also does not run**: the installation is described
wrongly, and the right moment to say so is before serving the first request.

One exception, and it is **declared by the part itself**: an application may
say that a failure of its own mount is tolerable, and then the server starts
without it rather than refusing to start at all. The application decides what
may be survived, not the server.

### While running: accept, then converge

A change has **two phases, and they are different in kind.**

**Accepting** is atomic and immediate. The grammar validates the words,
feasibility is checked, and the write happens **inside a boundary that
encloses the notification too**: if anything raises while the change is being
taken on, the description is not changed at all. So the tree is never left
saying something the installation never accepted.

**Converging** is not a transaction. Once a change is accepted, the tree holds
the **state that is wanted**, and each part brings itself into line with it at
its own pace and by its own procedure. A part that holds nothing swaps
immediately. A part that holds live state does what its own nature requires —
warning the people using it, waiting for them to finish, and only then letting
go. That can take minutes, so it cannot sit inside the boundary above: a change
reports itself as *accepted and in progress*, not as done.

The consequence worth stating plainly: an administrator is never told "refused"
while something was in fact taken away. Either the change was not accepted and
nothing happened, or it was accepted and what follows is a declared procedure
running in the open.

### Reversibility is the declaring part's obligation

**Source: owner, 2026-08-23.** Whoever declares that something of theirs can be
changed while running is **guaranteeing the mechanism that makes it possible** —
including undoing it. A part that cannot be taken away and put back does not
declare that it can.

So the boundary above promises what it can actually deliver: only what is
reversible takes part in it. This is what keeps the promise honest rather than
aspirational, and it is why the guarantee belongs to the part rather than to
the configuration.

### Foreseen everywhere, guaranteed nowhere in particular

**Source: owner, 2026-08-23.** Changing a value while running is an option the
design **foresees for the whole description**, and **guarantees for no part of
it in advance**. Whether a given word can be changed hot depends on what reads
it and how much state that reader holds — which only that reader knows.

So the capability is **declared where the word is declared**: a candidate
placement is an attribute of the element declaration itself, alongside the
word's type and default, which would put the answer next to the question. Not
settled, and deliberately not settled here.

The mechanism arrives in later steps, and it will be built **on the
collaboration of the individual parts** — not as a central engine that knows
how to change everything. This design records the shape and the obligation;
it does not invent the machinery.

## 7. The server's own sections

**Source: elements.py, the grammar as declared.** The top level is a closed
list of sections, each at most once, so every path is stable and can be written
by hand.

**`server`** carries the runtime. The **listener** — where to bind — and the
**public address** — what the server calls itself when it hands its own URL to
a third party — are two different words, because behind a proxy they are two
different values and only one of them means anything to an outside caller. The
public address is **declared, not derived from a request**: it must match what
the third party was told, and a value taken from a client-supplied header would
be a value that party rejects. A provider that needs it and does not find it is
a boot error, not an obscure failure at the first login.

Its children are the words that are server-domain rather than
application-domain: how long a session lives, and the task backbone's own
vocabulary, declared by the task backbone.

The other sections — middleware, identity, storage, applications, databases,
plugins — are named at the top level and described by the entry that owns each.

## 8. What it is not

**Not a settings file.** No free-form keys, no untyped values, no section
nobody declared.

**Not a service registry.** The description says what is installed, not where
to find something at runtime.

**Not a secret store.** It names where a secret comes from; it never holds one.

---

# Open frictions

Scaffolding for the interview, not a register. Settling a voice edits this
document — and, where the contradiction lives upstream, edits the source too.
This section shrinks to nothing before the design can be ratified.

Interview file: `temp/interview_015_configuration.md`.

## Settled on 2026-08-23 — no longer open

Recorded here only so the next reader is not surprised by their absence. The
answers are in §6.

- **when a change is refused** — at boot, an unactionable description does not
  run; while running, accepting is atomic and encloses the notification, so a
  failure leaves the description unchanged. Feasibility is not pre-computed by
  the writer: **the attempt is the check**, which keeps the knowledge with the
  part that has it.
- **what a partially applied change means** — the question dissolves:
  reversibility is the obligation of whoever declares their own thing
  changeable, so only what can be undone takes part. The earlier fear (the tree
  rolls back, the world does not) presumed parts that had made no such promise.
- **whether every word is hot-changeable** — no: foreseen everywhere,
  guaranteed nowhere in advance, declared where the word is declared.

## Still open

**S1 — the whole of §6 is unbuilt.** The code has a read door and no more:
`apply_configuration` has zero occurrences in `src/` and `tests/`, the handler
declares no mutator, and nothing subscribes to anything (searches in
[status.md](status.md)). The machinery it would stand on exists and is unused —
the tree is already a `Bag` subclass and `Bag.subscribe` already exists.

This is the largest distance between arrival and present here, and it is the
same subject as S5/S6 of [010 server](../010_server/design.md) seen from the
other side: there the question is what falls away when immobility goes, here it
is what has to be built.

**S2 — where the capability is declared.** §6 names one candidate — an
attribute of the element declaration, next to the word's type and default — and
deliberately leaves it unsettled. It needs deciding before any word claims to
be hot-changeable, because it decides where a reader looks to find out.

**S3 — a convergence that does not finish.** A part waiting for the people
using it may wait for people who never leave. Wait indefinitely, force after a
declared grace period, or give up and revert: not decided, and deferred with
the mechanism. It belongs with the restart liturgy
(`temp/liturgia_riavvio_orientamenti_2026-08-20.md`), which has the same
question about the same kind of waiting.

**S4 — a visible convergence state.** §6 distinguishes *accepted and in
progress* from *done*, and nothing in the system can currently express that
difference. Whatever shows it belongs to the monitor
([090 server-application](../090_server-application/)), but the state itself
has to exist first, and nobody owns it yet.

## Vocabulary and ownership

**S5 — `openapi` is grammar with no reader.** The section is declared and
validated by the grammar (elements.py:362) and **no code consumes it**: the
only other mention in the package is the handler's own docstring saying so
(handler.py:49). A word nobody reads is either an obligation not yet met or a
word that should go; §3 above quietly assumes the first.

**S6 — the middleware switches name a closed registry.** Only the core's own
middleware can be configured; one registered from outside cannot be. Whether
that is the design or a limit is not recorded anywhere — and §3 says every part
declares its own words, which reads as promising the opposite.

## Owed, not a defect

**S7 — the recipe in this page must stay executable.** The rule is that every
entry closes with a complete configuration and that those are run, never
proof-read. Writing this one found **two real defects in it** that reading had
not: a non-existent module in the imports, and a storage path the backend
refuses because it does not exist. The test that executes all of them is
decided and deferred (owner, 2026-08-23), so until it exists these recipes are
kept honest by hand.
