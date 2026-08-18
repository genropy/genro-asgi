# Notes — orchestration-m3-commander-groups

(Per-phase rationale goes under `## Phase N` headings: why this way, what was
rejected. The `_TBD` names each phase brought to the owner, and the name they
got, belong here too.)

## Phase 4 — the round of the names, and the three amendments it brought

*(2026-08-18, foreman-3. The 12 `_TBD` names of Phases 2 and 4 were put to the
owner one at a time; three of them turned into changes of behaviour.)*

**The names, and why they are these.** `group_map` over `group_handler_map` (the
owner's call: the column of `worker_handler_map` was not worth the length) ·
`requires_beat_ping` over `is_silent` — silence read as a fault, and there is
nothing wrong with a worker nobody has spoken to; `beat` circumscribes the claim
to the round, which answers the objection that `ping_process` has a second caller
(the departure, which beats a worker with no photo whatever its silence) ·
`cleanup_frozen` on both rungs, after `folder` and `disk` were both refused for
naming the MEDIUM: "if tomorrow it were Redis they would not be folders" ·
`mark_user_frozen` / `mark_user_adopted`, after `set_` was judged to read as one
boolean setter with a flag and `record_` as a customer record in a business
application · `drop_users`, because `drop` is the verb of the family (three rungs
plus the ops) and the objection to it — that the plural reached further than the
singular — was answered by removing the difference, not the word.

**The four thin mutators of the vertex stay.** They were weighed against the cost
of a call and of the maintenance ("every call slows things down"): they are not on
the hot path — freeze, adoption, the death of a process, events measured in
minutes — and they buy the single writer, which is what keeps every write of a
row inside `spa_commander.py` and lets the envelope chain not know how a row is
made.

**The storage left the quotas because a disk is not something a pool can grow
into.** A separate quota for the freezer's volume would have been a number to
tune for a resource whose answer is a sysop making room or a bigger volume, not a
placement decision — so the memory alone writes `state`, and the storage gets a
lamp: under `STORAGE_RESERVE_PERCENT` the log says so and `need_resources` is
called (the owner wanted the ask kept, which is what a Kubernetes commander
overrides). It is a constant and not grammar because a full disk is full for
every installation. The gauge measures the FREE share, as the fuel gauge of the
image that named it — and it stays a number rather than a boolean lamp because
the log must carry the figure: "7.4% free tells the sysop how far he can run, «on
reserve» does not".

**The cadence went onto the method because the table presupposed one executor.**
The vertex kept a table of (cadence, task) and the group a modulo in its own body:
the same idea in two shapes, with a third rung still to come. `@every` makes it
one — the number where the knowledge is, each rung giving its periodic methods a
turn. The count could not live on the function: a function object is one per
class, so N groups would share one clock and be checked in a rotation nobody
designed (measured in the shell: `a.m is a.m` is False, writes to a bound method
raise, and `A.m.count` is read by every instance). It lives in `beat_counts`,
one row per method, and the row is also the dashboard — the owner's own addition:
"if I look at the counters table I see who is in error". The wrapper swallows and
logs rather than letting the caller guard, because the isolation must be a
property of the mechanism and not a rule to remember: the case that made it is a
bad disk raising in `drop_expired_users` at every beat, which without isolation
would take down `check_resources` — the one thing that would have said the disk
is bad. The price, accepted: a bare call runs only if due, so a test or a monitor
that wants it now says `now=True` (eight call sites moved).

**The disk entered `drop_user` because that path only ever runs on users who are
leaving for good.** Verified before touching it: the vertex forgets a user when
the worker ANNOUNCES he is gone, and the worker announces it in two cases only —
the `/op/drop_user` order from above and a departure with flag `X`, the user who
leaves without being frozen. In both, the only process that could hold his lock is
the worker doing the announcing. The residual case is an `/op/drop_user` landing
mid-transfer, a window of fractions of a second on an order nobody issues from
outside, and it ends in the loud error the removal already raises when a folder
survives itself.

## Phase 4

**The skip of a group still in its turn cannot happen from the loop, and it was
built anyway because the plan ratifies it.** With ONE loop that awaits every
round, a turn is always finished before the next round starts: the overlap needs
a caller firing rounds out of band — the monitor asking for a fresh photo, the
request chain of Macro 4. So the guard is proved by calling `ping_groups()` twice
CONCURRENTLY, which is the shape those callers will have, and it is LOUD (a
warning line) rather than silent, since a group skipped twice running is a group
whose process is stuck. Its second reason is the wake: the group clears its own
event at the start of its turn, so an event still set while a turn runs is a
fresh ring and gets its own round — but only because a skipped group keeps its
event, which without the guard would be a tight loop of rounds nobody serves.

**The wake is consumed by the GROUP, not by the clock.** `_wait_beat` only
WAITS on the events; `GroupHandler.ping()` reads and clears its own. Two things
follow, both wanted: the group knows it was woken (which is what overrides its
count of beats and reads the shape at once) without the vertex having to tell it,
and a wake rung DURING a turn survives that turn — the event was already cleared
when the turn began, so the ring stands and the next `_wait_beat` returns at
once. Rejected: clearing in the vertex and passing a `woken=True` down to
`ping()`, which would have put a second road to the same fact into the signature.

**The vertex's own tasks are isolated one by one, over and above the loop's own
guard.** The scheduler pattern isolates at the LOOP; here each task is wrapped
too, for a case that is not hypothetical: a disk that has gone bad makes
`drop_expired_users` raise at every beat, and with a single guard that would take
the resource ALARM down with it — the one thing that would have said what is
happening. Four lines, one test (`test_a_task_that_raises_leaves_the_others_of_its_beat_alone`).

**The expiry hours are held by the VERTEX, and the grammar says group.** F44.5
puts `user_expiry_hours`/`guest_expiry_hours` in the group's grammar — the worker
judges the ACTIVE users with them — while the FROZEN are the vertex's, and a
frozen user's row does not say which group he came from (`user_map[user]["group"]`
is written by nobody yet). Reading the group off the header on disk was rejected:
a policy would then be chosen by a file, and the file is diagnostic by ratified
rule. So the vertex carries the two numbers as its own kwargs, and the guest is
told apart by the `GUEST_PREFIX` it already owns. Phase 5, which writes the
grammar, is where the two rungs are reconciled — the same key on two rungs is the
cascade this workflow already uses for `memory_max_percent`.

**The age of a frozen user is read from the header, so the reaper opens the
disk.** There is no timestamp in the ratified row (§6 fixes its six fields) and
inventing one would have been a schema change smuggled into a phase. The header
already carries `ts`, written by whoever froze him, and F18 measured exactly this
— opening the packets — as the expensive part, which is why the reaper has the
slowest cadence of the three and runs `_expired_users` on a thread. A row marked
frozen with nothing on disk has no age to judge: it is left alone here and
answered by `disk_cleanup`, which is the sweep that owns the disagreements
between the indexes and the deposit.

**The sweep of the folders went into the `FreezeHandler`.** The first draft had
the vertex compute the set difference and call a `drop_userkey_folder` per
orphan; but the deposit is the object that talks to the filesystem, and a
set-difference over its own folders is its own work. So it exposes
`drop_unclaimed_folders_TBD(claimed)` — the caller says who is still answered
for, computed FORWARD from its identities, since no identity comes back from a
folder name — and the removal by key is private, shared with `drop_user_folder`.
One public name fewer, four lines fewer at the vertex, and the rule that nobody
else computes a path under the root is kept whole.

**The machine's memory is read from `/proc/meminfo`, and is None where there is
no `/proc`.** The exact precedent is `SpaWorker.rss_bytes`: no dependency is
taken for a gauge a platform may simply not have, and a gauge nobody can read
alarms nobody — an unmeasured machine is not a full one. `os.sysconf` was
examined because it answers on macOS too, and rejected: it gives FREE pages, not
AVAILABLE ones, so a healthy Linux box full of page cache would read as ~95% used
and saturate the pool for ever. The price is six lines this laptop cannot cover;
the ubuntu CI runs them, and the disk half of the same check is proved on every
platform (the alarm line is put at 0.0%, which any real disk is over).

**The line cap, itemised.** 127 executable lines against ~120 for the two files
of the plan. The clock itself is 31 (loop 12, `ping_groups` 10, `_wait_beat` 9);
the three tasks and what they read are 52, of which 14 are the two gauges and 9
the expiry arithmetic; the plumbing (imports, five constants, the four grammar
kwargs and their assignments, the two new maps) is 18; the group's turn is 17.
Cut on the way, after a first draft measured 177: `__all__` back to one line with
the cadence constants left out of it (the `WAIT_POLL_INTERVAL` precedent, an
internal knob nobody imports), the four `#:` blocks of the cadences merged into
one comment over the three numbers, `check_resources` down from 18 lines to 9
(the state written as one expression instead of two branches, the log's numbers
under short keys), `_expired_users` from 14 to 9, the folder sweep moved out to
its owner, and the group's `gather` de-nested. What is left is irreducible
without dropping something the plan asks for.

**`clock` is the fixture and not a method.** The tests create and cancel
`heartbeat_loop` exactly as a lifespan will, which is also the proof that no
`start`/`stop` pair is missing: the coroutine is the whole thing, and whoever
owns the lifespan owns the task.

## Phase 3

**The occupancy formula was transplanted over the gauges that really travel, and
one of the two knobs it needs does not exist in the ratified grammar.** Design #5
reads a worker as the MAX of its clamped components (`memory`, `cpu`,
`executor`), each against a target; the photo the M2 worker actually sends
(`SpaWorker.worker_snapshot`) carries `rss_bytes` and counts, and no cpu or pool
gauge at all. So the shape is the transplant — a list of components, each clamped
to its own full, the fullest winning, expressed in percent so a worker's fullness,
a user's cost and a setpoint are the same number — with ONE component implemented,
and the evaluator's own degrade kept: a component whose gauge or whose ceiling is
missing is simply absent, and a photo with none reads 0.0 (an unmeasured worker
admits, as it does today). Writing the other two now would have been code no
photo can feed. The memory component needs a per-worker ceiling, which F45
neither kept nor replaced (`memory_limit_mb` is the legacy's,
`worker_memory_max_bytes` was on the table in F44.6 and never ratified, and
Phase 5's group grammar does not list it): it was carried to the baptism round as
a placeholder in bytes, so the gap would be VISIBLE there instead of hidden in a
derivation, and the owner closed it with the third rung of the cascade —
`worker_memory_max_percent`, one worker's share of the group's own quota (see the
ruling below). Rejected on the way: reading
each worker against the GROUP's whole quota — it needs no new knob, but then four
workers each under their own setpoint blow the quota fourfold, since the quota
gate only stops new PROCESSES, never new users.

**The group's quota was first held in bytes, and the owner put it back in the
ratified percent.** F45.1 says `memory_max_percent` cascades (the vertex's
concession on the machine, the group's percentage of it), and Phase 5 owns that
grammar while Phase 4 owns the machine sensor that turns a percentage into bytes.
Phase 3 first held the DERIVED number in bytes; at the baptism round it went back
to `memory_max_percent`, with `memory_concession_bytes` as the only total handed
in (see the ruling below). The other half of the ratified gate — "and the machine
under its alarm line" — is read where it already lives, as
`SpaCommander.state == "running"`, which Phase 4's `check_resources()` writes. No
new sensor was built here.

**`restart_worker` comes back with a NEW worker, and this is a declared deviation
from the letter of decision (6).** The plan says "same quit, then
`launch_process`". The quit drains the worker into the freezer, and the freezes
announced while it drains ride the replies to the pings — except the last ones,
which die with the wire the worker closes behind itself (the M2 e2e says so out
loud). Those users are rescued by ONE thing only, the death worker event, which
reads the last photo's `T` flags; and nobody composes that event for a handler
that goes quitted → starting → running inside one coroutine. So `restart_worker`
plays the death (`report_death`) between the quit and the birth — which is
also what settles the placements — and since `GroupEnvelopeHandler.on_process_quitted`
ends in `drop_worker`, the handler leaves the group and a fresh one takes its
place. The stability of the handle is not lost by it: after a full drain nobody
points at that worker any more. The alternative — a second settlement path
written by hand for the restart alone — was rejected as the invention it would be.

**The two placement writes went into the chain, and two `_TBD` names died.**
`record_placement_TBD` / `forget_placement_TBD` were the Phase 2 stub's contract;
the real group would have carried them as two methods each wrapping ONE dict
write, which the simplification round ruled out. `user_worker_map` is a bare
public map (the shape that round ratified), so `GroupEnvelopeHandler` writes it
directly, exactly as `CommanderEnvelopeHandler` writes `page_connection_map`. The
two names are gone from `GroupStub` too, and the four SETUP lines in
`test_orchestration_envelope_chain.py` that used them now write the map (no
assertion touched).

**`WorkerHandler.assign_user` writes NOTHING, and that is what keeps
`hosted_users` honest.** The first draft had it add the user to `hosted_users`,
which would have given that set a writer with no remover — the announcements are
what fill and empty it, and a user frozen or dropped would have stayed on board
for ever, so the next death would have "frozen" somebody the vertex had already
purged (a `KeyError` inside the fold). The placement is recorded where decision
(8) puts it, in the group's `user_worker_map`; who is INSIDE a process stays what
that process announces. So the census of v4 §3 is untouched, and the M2 e2e —
whose driver is the one saying who is on board — keeps meaning what it says.

**A worker that has not presented itself yet refuses with the BASE.** The
ratified family has three children and none of them fits `starting`: it is not
restarting (nothing died) and not quitting (it is arriving). Raising
`WorkerQuittingError` for it would have made the class lie, so it raises
`AssignmentRefused` itself, which the group catches like any other — the reason
is in the message, and the family stays as ratified. `quitted` and `aborted` do
raise `WorkerQuittingError` (they will never take anybody again), though the
group's own walk never offers them: `living_workers` leaves them out.

**The closure margin is what keeps the ladder from oscillating.** "Capacity
wasted" cannot be "somebody is empty": with two workers at 78% and 0%, closing
the empty one leaves a group that admits nobody, and the next round grows it back
— for ever. So the group closes a worker only while the others, read as if they
shared what it holds, would still take a newcomer:
`total / (living - 1) + new_user_occupancy_percent <= occupancy_max_percent`. The
same number that decides the growth decides the shrink, so the two cannot cross,
and no new knob was invented for the hysteresis. Test:
`test_a_closure_that_would_undo_a_growth_is_not_made`.

**FINDING, outside this phase's files: the photo riding the answer to `/op/quit`
may not exist.** `SpaWorker._outbound` attaches the photo only when one is DUE
(the population changed, or `worker_snapshot_ttl` ran out), and
`plan_transfers` — which is what poses every `T` at the quit — does NOT mark it
due. So a worker whose photo is fresh and whose population has not changed
answers the order to leave with NO photo, and the handler settles the death on a
picture taken BEFORE the flags: everybody reads as kept, so everybody is purged
instead of parked. The M2 e2e does not see it because it pins
`worker_snapshot_ttl` to 0. The guard this phase owes is the plan's contract note
(b) — the no-photo case, which `_order_quit` covers with a beat — and the one-line
cure for the staleness (a flag change marks the photo due) lives in
`spa_worker.py`, which Phase 3 must not touch. The scripted child of
`test_orchestration_group_handler.py` models the case (`photo_on_quit`), which is
also what makes the guard's test bite: without the beat, the user is purged.

**`start()` was not born.** A boot verb whose whole body is
`await self.start_worker()` is a wrapper delegating 1:1, which the volume
rule forbids; the boot IS that call, and Phase 4's lifespan makes it. Same
reasoning for `stop()`: shutting a group down is the lifespan's, and building it
here with only a test fixture asking for it would have been code without a
requester — the two test files close their own workers, as the M1/M2 fixtures do.
`check_occupancy` on an empty group grows one by itself, which is the same boot
by another road.

**The names this phase brought to the owner, and what he ruled.** `start_worker`
(the group's own verb for bringing a worker into being — the sibling of the
ratified `drop_worker` / `restart_worker`); `get_worker_cap` (how full a given
worker takes users up to, the reception's reserve already deducted) — BARE, the
owner refused the unit suffix the placeholder carried; `worker_settings`,
confirmed as it stood, because it is the VALUES dict and not the grammar (the bag
of everything a `WorkerHandler` of this group is built with, splatted verbatim —
it keeps eight pass-through parameters out of the constructor); and, inherited
from Phase 2, `report_death` — the handler REPORTS a fact, and the word
"announce" left the prose that spoke of that method, the worker-events vocabulary
untouched. `start` and `stop` were not coined; `living_workers`, `reception`,
`check_occupancy`, `assign_user`, `drop_worker`, `restart_worker`, `ping_now` /
`ping_now_event`, `user_worker_map` and the three `state` values are the plan's
own, verbatim.

**Two of them died unborn, and the whole memory reading moved into percent
space.** `memory_max_bytes` and `worker_memory_max_bytes` never got a name: the
owner ruled that the cascade F45.1 already ratifies is read percent against
percent all the way down. So the constructor takes ONE total —
`memory_concession_bytes`, what the machine concedes, the denominator and nothing
else — and two percentages: `memory_max_percent`, this group's share of the
concession, and `worker_memory_max_percent`, what ONE worker may hold as a share
of the group's own quota. That second one carries the SAME grammar key as the
first one rung down (vertex % of machine → group % of concession → worker % of
quota); the prefix exists only because two rungs of the cascade meet in one
Python constructor. The growth gate now reads the new property
`memory_occupied_percent` — the summed rss of the living workers over the
concession — against `memory_max_percent`, and the occupancy formula normalises a
worker's rss against its share of the quota, the transplanted design #5 shape
untouched. Everything unmeasurable still reads 0.0, so a group nobody has
measured is ungated by construction rather than by a `None` branch.

**`snapshot_is_urgent` was killed rather than baptised.** It had exactly one
caller, `GroupEnvelopeHandler.on_worker_snapshot`, and its whole body was one
comparison against `restart_occupancy_max_percent`; the comparison now stands
where it is read, and the method is gone. `GroupStub` follows: it no longer
answers a question about urgency, it answers `get_occupancy_percent` and carries
the setpoint, which is what the real group does.

**The photo-due finding of this phase got its biting test.** The staleness
declared above was cured in `spa_worker.py` by 08cc20a — `plan_transfers` marks
the photo due the moment it poses a flag — but nothing failed when that line was
taken away. `test_a_flag_posed_puts_the_photo_on_the_next_envelope_out` (in the
departures file, where the flags live) pins `worker_snapshot_ttl` to an hour,
sends one envelope so the photo is fresh, poses a `T`, and demands the photo on
the next envelope out. Neutralized: without the line it fails on
`KeyError: 'worker_snapshot'`.

## Phase 2

**The three binding corrections of the owner** (2026-08-17, at the gate): (1) no
version number travels — the M1 contract «no delta and no version number: the
master replaces the replica entire» stands, so the wire carries the whole store or
nothing (the `revision` this correction allowed as server-side bookkeeping died
later in the phase, with the flow that was its only reader: «se una cosa non serve
deve sparire»); (2) `GlobalRegister` is a
new class in the subpackage and imports NOTHING from `spa/global_store.py` (no
`CapturingGlobalStore`) — the legacy dies at M6 and no thread may start from the
new machine; (3) the descent is composed by the CHAIN, not by the wire:
`WorkerConnector.call()` attaches nothing and stays ignorant of content, and the
`CommanderEnvelopeHandler` is the author of what rides an envelope going down,
including when the CALL starts at the vertex.

**The shape of a layer is written in the layer** (owner, at the naming round:
«mi sembra un giro inutilmente complicato»). The first draft had `__call__` written
once in the base plus a `hand_up_TBD` hook the vertex overrode to NOT hand up — a
template-method dance whose central name lied. Now the base carries ONE method, the
reading of its own share (the photo, then the `on_<announcement>` dispatch), and
each layer writes its own two-line `__call__`: read my share, then the layer above —
or, at the vertex, read my share and answer with the store. Gone with the dance:
`hand_up_TBD` and two of the three `NotImplementedError` stubs; the one left says
that every layer reads the photo, which is true of all three.

**The vocabulary of Phase 1's decision (9) landed here, and I had to be reminded.**
The plan deferred `worker_events` / `add_worker_event` to «the `_TBD` round at the
end of Phase 2», and I did not put it on the list of names to settle — the owner
did («abbiamo fatto una sessione dicendo che erano worker_event»). Applied across
the whole subpackage: the list is `worker_events`, the verb `add_worker_event`, the
wire slot `"worker_events"`, the chain's constant `WORKER_EVENTS_KEY`, the two death
names in `DEATH_WORKER_EVENTS`, and in prose the thing is a *worker event*, not an
«announcement». The legacy machine (`spa/worker.py`, its tests) keeps its own
words, as always. Lesson for the next round: a name postponed by an earlier phase
belongs on the list, and the list is read off the plan, not off memory.

**The envelope may in principle be ALTERED by a layer, and the name of the base's
method says so.** Asked at the naming round whether a group can add something for
the vertex, the owner ruled that the door stays open «se un domani serve»: on the
way from the worker up, each layer must be able to see, add, remove and modify. So
the method is `work_on_envelope` — not a `read_*`, which would have closed it — and
today no layer changes anything (what arrives is what the worker said, and mixing
the two would make an announcement indistinguishable from an addition). Rejected on
the way: `pop_my_share`, because `pop` promises remove-and-return and the envelope
is neither consumed nor sliced — SOME announcements are read by two or three levels
(`drop_user`, `user_frozen`, the photo), so the belt has to arrive whole at every
level. Noted defect of the accepted name: `process_envelope`, the first choice, can
be read as «the envelope of the process», which is why `work_on_envelope` won.

**The basket, as a shape for the future** (owner's metaphor, same round): the
initiative is always the vertex's, so an exchange should be ONE basket created at
the top, going down through the levels — each adding what it has to say — and
coming back up through the same levels, each taking what concerns it. Coherent with
the ratified rules if the down pass is synchronous, the wire is awaited at the
bottom, and the up pass is synchronous again. NOT built here: today the descent has
no content at all (the one thing it carried was the invented store flow), and the
open question is which ladder carries the basket down — the objects
(`SpaCommander` → `GroupHandler` → `WorkerHandler`, which is already the beat's own
cascade) or the layers. To be decided when the descent has something to carry: the
request chain, and the update sent to everybody.

**Where the vertex's maps are written** (the second question of the gate, answered
by «procedi come hai proposto»): the mutators live on `SpaCommander` and the
`on_<announcement>` methods of the chain call them. The reading taken is the plan's
own `Pattern:` line — `subscription_index.py`, the class that owns the maps and
exposes the verbs, nothing outside touching them — and correction (3)'s spirit: a
layer does its own job and reaches into nobody else's state.

**The single door of arrival is the WIRE, not `ping_process`.** The plan's Details
say the payload `ping_process` returns is handed to the chain; it is handed one
line earlier, in `WorkerConnector._dispatch`, so an announcement riding the answer
to a `drop_user` or to an http request climbs too — the hole Phase 1 declared was
never only the beat's. `call()` still returns the whole payload verbatim, which is
why the M1/M2 tests that read `reply["events"]` are untouched: they photograph the
wire, not the fold.

**A fold that raises does not sever the wire.** `_take_envelope` logs the refusal
and the parked caller is answered anyway — the discipline `_fire` already declared
in M1 for the handler's callbacks, and the reason is the same: a bug one level up
must not kill a process and make its users log in again. The price is that a
refused announcement is LOST, so the refusal is loud and the e2e asserts it
(`test_a_real_child_announces_and_the_vertex_learns_it`). The case that produces
it today is an announcement about a user the vertex never minted, which cannot
happen once the request chain exists (M4): the vertex writes the rows before
anything descends.

**How a change of the store reaches a LIVE replica is not decided, and Phase 2
does not decide it.** The first version of this phase invented a workflow: a
per-handler revision as a staleness sensor, a second entry point on the chain
(`descending_payload_TBD`), and the change riding the next beat. The owner stopped
it — «è un flusso di lavoro mai deciso» — and it was: the ratified text (v4 §3,
F42.3) says only that the `CommanderEnvelopeHandler` adds the store to the RETURN
of the chain, and the only return that reaches the wire is the answer to a
presentation, because the child makes no CALLs any more. So the whole invention was
removed: no revision anywhere — neither on the handler nor on the register — no
second entry point, and `ping_process` and `quit_process` send their orders naked
again.

What stays is the ratified rule alone: **the chain answers with the whole store**,
and the wire writes it where there is an envelope going down — the presentation.
The mechanism the owner dictated for a change, to be built when the vertex has its
groups (Phase 3/4): the write CLIMBS as an announcement in the envelope, the vertex
updates the master, and then sends an update CALL to every worker — detached, since
the fold is synchronous and cannot await inside the receive loop. Until then a
change made after a birth does not reach that process, and the e2e says so out
loud.

**The death is classified ONCE, by whoever composes the announcement.**
`report_death` splits the users into `frozen_users` (the ones the last photo
had flagged for cession, and only for a `quitted`) and `lost_users`, so neither the
group nor the vertex re-reads the photo: an orderly departure freezes whoever it
had promised the freezer even if his own announcement died with the wire, a wild
death saves nobody (C3). Both layers therefore read the two lists and the two
announcements differ only in who is in which — which is also why each layer's two
`on_process_*` methods delegate to one private.

**The orders logger replaces its handlers instead of appending.** A process has ONE
vertex, so `genro_asgi.orchestration.orders` is that object's; without this a
second `SpaCommander` in the same process — which only a test builds — would write
every row twice.

**The group of the tests is a real chain over a real vertex.** `GroupStub` moved
into `tests/orchestration/group_stub.py`, shared by four test files, and it carries
the real `GroupEnvelopeHandler` over a real `SpaCommander`: what it stands in for
is only the group's OWN verbs, which is exactly the contract Phase 3 owes —
`ping_now`, `get_occupancy_percent` (`snapshot_is_urgent` was killed at the
baptism round and its threshold inlined at the caller), `record_placement_TBD`,
`forget_placement_TBD`, `drop_worker` (which also takes away the placements that
pointed at the dead handler).

**`exceptions.py` is born here with `UserOnHold` alone**, one phase earlier than
the plan's file list says: `resolve_user` cannot raise what does not exist. Phase 3
adds the `AssignmentRefused` family to the same module.

**The M2 e2e now closes on the vertex.** It was going to be touched anyway (the
placeholder property it read is gone), so the story mints its two people at the
vertex the way the login will, and asserts what the fold does at each step: the
births are no-ops, the flagged user lands in the waiting room, the freeze writes
the mark and the placement to be assigned, the adoption turns the mark off, and
the round the driver plays turns the ended state into the announcement the two
levels above consume.

## Phase 1

**The unit judgement of decision (7): `worker_snapshot_ttl` and
`deposit_lock_retry_interval` KEPT as they are.** `user_idle_freeze_delay` was
renamed because the number's unit really changes — it is a policy of the
installation and Phase 5 puts it in the group grammar as
`user_idle_freeze_minutes`, with the conversion at the one comparison that reads
it (`SECONDS_PER_MINUTE`). The other two are technical times in seconds, and they
live in a family of four the plan itself preserves unchanged in Phase 5's
constants list (`PROCESS_PING_INTERVAL`, `PROCESS_PING_TIMEOUT`,
`TRANSFER_START_DELAY`, `DEPOSIT_LOCK_WAIT_LIMIT`) — none of which spells its
unit either. Renaming two of six would fragment the family for no reader's
benefit, and renaming all six was not in this phase. Reversible with one
search-and-replace if the owner wants the suffix everywhere.

**`QUIT_TIMEOUT_SECONDS` is a module constant, not a kwarg** (Phase 5 decision 4
lists it among the constants). Value 30.0 s, the order of `DEPOSIT_LOCK_WAIT_LIMIT`
— it has to cover a real drain (the gate plus one freeze per user). Tests that
need the timeout to fire monkeypatch the module attribute, which works because the
method reads the global at call time; no test-only kwarg was invented for it.

**The order to leave is answered BEFORE the departures run.** `quit()` ends by
closing the wire, so a reply composed after it could never leave the process: the
op poses the flags synchronously, answers (the photo on that reply is the one
showing every user `T`), and only then drains. The M2 e2e used to get there with
`create_task` + `sleep(0)`; the synchronous head (`_flag_everybody_for_departure`,
shared with `quit()` and idempotent because a departure plan takes nobody back
off it) makes it deterministic instead of a race that happens to be won.

**The wait for an ordered death is parked BEFORE the order is sent**, not after
the answer comes back: the child of the drill answers and closes in the same
breath, so a wait parked after the reply would miss its own EOF and turn an
orderly departure into a kill. The known price is the mirror case — `quit_process`
on a wire whose child is already gone raises `ConnectionError` and leaves the wait
parked, so a later wild death of a successor on that same handler would read as
`quitted`. Accepted: a quitting handler does not come back by construction, and
the group reads the state before ordering.

**The REPLY lane DOWN went with `SpaWorker.call()`.** Decision (6) kills the verb;
its parking lot (`_pending`, `_resolve_reply`, `_fail_pending`) and the REPLY
branch of `handle_frame` are that verb's mechanism and had no other producer — a
REPLY arriving at the worker is now denounced as an envelope with no lane, which
is what the asymmetric protocol says it is. The presentation's own reply is read
inline by `send_presentation` and never went through that lane.

**The store change now rides an order going down** (the beat is the one that
always comes), because the EVENT lane that used to carry it is dead. The M2 test
that pushed it with `send_event` was rewritten on a CALL, not deleted: the
behaviour under test — the replica replaced whole — is unchanged.

**No `_TBD` names survive this phase.** Everything new was either already
baptised in the plan (`quit_process`, `ping_now`, the six `state` values,
`QUIT_TIMEOUT_SECONDS`, the three op paths) or private
(`_answer_then_quit`, `_flag_everybody_for_departure`, `_park_death_wait`,
`_settle_death_wait`). `SECONDS_PER_MINUTE` is the only new public constant: it is
a unit conversion, not a decision, and it is named after what it is.

## Simplification round (2026-08-17, foreman-2, after phases 1-2)

Owner's criterion, now a standing rule: excess code IS a defect ("150
lines where 70 suffice is shit"). Adversarial review found ~20% code
excess + docstring bloat vs the ratified triplet; fix round applied
R1-R9: bare public maps (pattern subscription_index), one-dict-write
methods inlined, global_register.py deleted (bare Bag on the
commander, TYTX at the consumer), store attached ONLY to presentation
envelopes (gate: top-level "pid"), worker_handler parameter removed
from all chain signatures (drop_worker takes the NAME), base-class
ceremony deleted, on_process_aborted = on_process_quitted alias (the
worker event already distinguishes: frozen_users empty on aborted),
DEATH_WORKER_EVENTS dict -> f-string, docstring triplet pass.
Re-review (adversarial, 9 neutralization probes): LANDABLE; restored
the orders-logger detach loop + its test (R9 had deleted real
behavior: cross-commander log pollution); killed 2 tautological tests
left by R3. Executable code of the new modules 298 -> ~250.
Contract notes for phases 3-4: the real GroupHandler.drop_worker must
be LOUD on an unknown name (the stub is silent); an ordered quit
whose photo never arrived purges everybody as quitted — the caller
(the group) must ensure a photo preceded the order.
