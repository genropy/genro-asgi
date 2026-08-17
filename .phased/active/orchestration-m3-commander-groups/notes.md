# Notes — orchestration-m3-commander-groups

(Per-phase rationale goes under `## Phase N` headings: why this way, what was
rejected. The `_TBD` names each phase brought to the owner, and the name they
got, belong here too.)

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
`announce_death_TBD` splits the users into `frozen_users` (the ones the last photo
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
`ping_now`, `snapshot_is_urgent_TBD`, `record_placement_TBD`,
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
