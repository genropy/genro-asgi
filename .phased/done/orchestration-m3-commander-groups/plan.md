# Context: wf/orchestration-m3-commander-groups
Parent: main
Mode: interactive

## Objective
Build the two upper levels of the SPA orchestration rebuild (design v4,
Macro 3): the envelope chain (`WorkerEnvelopeHandler` /
`GroupEnvelopeHandler` / `CommanderEnvelopeHandler`), the vertex
(`SpaCommander` — the three indexes, the minting of the newcomer, the
parking gate, the global register master, the orchestration log) and the
group (`GroupHandler` — the user→worker map, EAFP placement on occupancy,
the manoeuvres, the crisis states), driven by ONE heartbeat at the vertex.
The request chain and the login are Macro 4; the legacy machine
(`spa/commander.py`, `spa/worker.py`) stays untouched until Macro 6.

Authority order on any doubt: `temp/interview_handler_2026-08-15.md`
(decision register, F1–F47) > `temp/design_orchestrazione_v4_2026-08-17.md`
(spec) > `temp/design_orchestrazione_v3_2026-08-16.md` (the sections v4 does
not touch: deposit/freezer §8, login §11, boot §12, data plane §9, deaths
and pushbacks §14–15) > this plan.

**This plan amends the v4 on four points**, all ratified by the owner during
this planning session (2026-08-17, afternoon). They are recorded here because
no register entry carries them yet:

1. **Vocabulary.** `heartbeat` names the FREQUENCY only; `ping` is the
   ACTION. So the cascade is `ping_groups()` → `ping()` → `ping_workers()` →
   `ping_process()`, and `on_heartbeat` does NOT exist: `on_` stays exclusive
   to the announcements that climb. Each level names the object it acts on
   (the group is not a dog, it is the owner of dogs).
2. **One cadence, counters below.** The vertex has ONE clock. It pings every
   group every beat; the group counts its own beats and runs its own
   `check_occupancy()` when due. `MEDIUM_URGENCY_EVERY` /
   `LOW_URGENCY_EVERY` as vertex constants do NOT exist: the number lives
   where the knowledge is. A round is one-per-group: a group whose previous
   round is still open skips its turn, the others go (a mute process delays
   its own group only, never the machine).
3. **The group has no target.** `target_workers` DIES. At boot the reception
   is born; the group grows on demand (nobody admits → wake → a process is
   born, if the memory quota has room) and shrinks when capacity is wasted.
   With it die `launch_missing_workers`, the `target − 1` of F46 step 1, the
   `target` restored at step 6, and the `vivi == target` reconcile.
4. **The death is a state, not a pocket.** The `WorkerHandler` carries
   `state` among six values; `_governed_death` and every mark posed from
   outside dissolve, and no announcement is stored waiting for a turn.

**Naming rule for this workflow** (ratified 2026-08-17, replaces
"every baptism in planning"): a new public name whose baptism is not settled
is born with the `_TBD` suffix (`accept_offer_TBD`). At the END of each phase
the executing chat brings the owner ONLY the surviving `_TBD` names — one at
a time, semantics plus 2–3 candidates — and the rename is a search-and-replace
in its own commit. A name whose code turned out unnecessary dies with it and
is never brought up. No `_TBD` survives the end of the workflow.

**Names already baptised, in this session** (the executor invents none of
them, and asks nobody):
`WorkerQuittingError` · `heartbeat_loop()` · `ping_groups()` · `ping()` ·
`ping_workers()` · `ping_now()` / `ping_now_event` · the six `state` values
on `WorkerHandler` (`starting` / `running` / `quitting` / `restarting` /
`quitted` / `aborted`) · `resolve_user(cid)` · `assign_user` (the same word
on the three rungs) · `check_occupancy()` · `drop_expired_users()` ·
`check_resources()` · `log_order()` · `GlobalRegister` · the three `state`
values on `GroupHandler` and `SpaCommander` (`running` / `saturated` /
`broken`).
Inherited from F42–F47 and still valid: `SpaCommander` · `user_map` /
`connection_user_map` / `page_connection_map` · `user_worker_map` ·
`WorkerEnvelopeHandler` / `GroupEnvelopeHandler` / `CommanderEnvelopeHandler` ·
`on_<announcement>` · `AssignmentRefused` / `NoRoomError` /
`WorkerRestartingError` · `UserOnHold` · `quit_process` · `restart_worker` ·
`drop_worker` · `process_quitted` / `process_aborted` · `/op/quit`,
`/op/drop_user`, `/op/drop_connection` · `user_is_frozen(user)` ·
`occupancy_percent` · `need_resources`.
Baptised at the close of Phase 4 (round of 2026-08-18, foreman-3): `group_map` ·
`requires_beat_ping` · `hold_user` · `mark_user_frozen` / `mark_user_adopted` ·
`drop_users` · `cleanup_frozen` (the freezer's sweep AND the vertex task that
calls it — homonymy in cascade, and it replaces the `disk_cleanup` of the
register: the medium does not belong in the name) · `CHECK_OCCUPANCY_BEATS` /
`CHECK_RESOURCES_BEATS` / `DROP_EXPIRED_USERS_BEATS` / `CLEANUP_FROZEN_BEATS` ·
`storage_free_percent` · `STORAGE_RESERVE_PERCENT` · `every(beats)` /
`every_beats` / `beat_counts` / `now=` (the decorator, the owner's own coinage).

**Excluded words** (from names AND prose): parcel, deposit, judgment, budget,
valvola, relaunch, seat/posto, and the names of the dead. Say instead:
register item, freezer, check, timeout, restart, congelamento per inattività.

## Work Plan

- [x] **Phase 1**: Retrofit M1/M2 to the v4 — the death becomes a state
  > Done: `WorkerHandler.state` (six values) replaces `_governed_death`,
  > `_wait_ordered_death_seen` and the mark in `restart_process`; the
  > classification is the parked wait an EOF resolves, and `on_child_lost` now
  > only writes the state and rings `group.ping_now()`. `quit_process()` born
  > (`/op/quit`, `quitting`, `QUIT_TIMEOUT_SECONDS`, timeout = loud abort);
  > `ping_process()` returns the REPLY payload instead of discarding it. On the
  > worker: the three ops `/op/quit` (answered at once, photo all `T`, drain
  > after), `/op/drop_user`, `/op/drop_connection`; `SpaWorker.call()`, the whole
  > EVENT lane in both directions and `on_child_message` removed, and with them
  > the REPLY-down parking lot they were the only producer of;
  > `user_idle_freeze_delay` → `user_idle_freeze_minutes` with the conversion at
  > the comparison. `worker_snapshot_ttl` and `deposit_lock_retry_interval` judged
  > and KEPT (rationale in notes.md). The M2 e2e now closes the seam it declared:
  > that departure is `quitted`, not a WILD death.
  > Verified: `pytest tests/ -q` 1841 passed / 2 skipped (was 1838/2);
  > `ruff check src/ tests/` clean; the `Done:` grep returns nothing; coverage of
  > the three touched modules up (worker_handler 91% → 98%, worker_connector
  > 91% → 92%, spa_worker 98%). No `_TBD` name survives the phase.
  > Files: src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/worker_connector.py,
  > src/genro_asgi/spa/orchestration/spa_worker.py,
  > tests/orchestration/test_orchestration_worker_handler.py,
  > tests/orchestration/test_orchestration_worker_connector.py,
  > tests/orchestration/test_orchestration_spa_worker_process.py,
  > tests/orchestration/test_orchestration_spa_worker_departures.py,
  > tests/orchestration/test_orchestration_m2_e2e.py,
  > tests/orchestration/test_orchestration_foundations_e2e.py,
  > tests/orchestration/child_stub.py,
  > .phased/active/orchestration-m3-commander-groups/notes.md
  > Verified: the unit judgement of decision (7) was put to the owner and RULED on
  > 2026-08-17: the technical seconds keep their names — `worker_snapshot_ttl` and
  > `deposit_lock_retry_interval` stay as they are, with the four siblings Phase 5
  > preserves unchanged. The `_seconds` suffix stays reserved for the policy keys
  > of the grammar, where the unit is part of the installation's decision. No
  > `_seconds` sweep over M1/M2 is owed.
  - Run: opus / medium
  - Pattern: `.phased/done/orchestration-m2-worker-process/plan.md` Phase 1
    (the same job, done once already: rename + remove, no new behaviour);
    the M1/M2 modules themselves.
  - Files: src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/worker_connector.py,
    src/genro_asgi/spa/orchestration/spa_worker.py,
    src/genro_asgi/spa/orchestration/__init__.py,
    tests/orchestration/test_orchestration_worker_handler.py,
    tests/orchestration/test_orchestration_worker_connector.py,
    tests/orchestration/test_orchestration_spa_worker_process.py,
    tests/orchestration/test_orchestration_spa_worker_departures.py,
    tests/orchestration/test_orchestration_m2_e2e.py,
    tests/orchestration/child_stub.py
  - Decisions:
    (1) **The state machine.** `WorkerHandler.state` holds one of
    `starting` (process spawned, not yet presented) · `running` ·
    `quitting` (`/op/quit` sent, draining, will not come back) ·
    `restarting` (dead and awaiting its successor, will come back) ·
    `quitted` (died as ordered, the group has yet to consume it) ·
    `aborted` (died with nobody waiting — the wild death, C3 bonifica).
    The classification is the PURE WAIT: `quit_process()` parks a future,
    the EOF resolves it; EOF with a live wait = `quitted`, without =
    `aborted`. REMOVED: `_governed_death`, `_wait_ordered_death_seen`, and
    the marking inside `restart_process`.
    (2) **`quit_process()`** is born: sends `/op/quit`, sets `quitting`,
    awaits the seen death with `QUIT_TIMEOUT_SECONDS`; a timeout is a loud
    abort. `restart_process` keeps its own name (M1) and sets `restarting`.
    (3) **`on_child_lost`** no longer classifies and no longer calls
    `on_worker_abort`: it writes the state and calls `ping_now()` on its
    group — the group learns at its (anticipated) round, reading the state.
    (4) **`ping_process` returns the REPLY payload** instead of discarding
    it (today `await self.connector.call(PING_OP_PATH, ...)` throws away
    everything the child announced — the producer exists since M2 and the
    consumer does not, so every announcement riding a ping's REPLY dies
    silently). Phase 2 hands that payload to the chain; in this phase the
    return value is asserted by the tests.
    (5) **The op contracts on `SpaWorker`**: `/op/quit`, `/op/drop_user`,
    `/op/drop_connection` (key = the verb of `SpaWorker`); the reply to the
    quit carries the photo with every flag `T`.
    (6) **What dies**: `SpaWorker.call()` and the whole EVENT lane in both
    directions (the channel protocol is asymmetric: CALL down, the
    presentation at birth and then REPLY only up), `on_child_message`.
    (7) **Unit renames**: `user_idle_freeze_delay` →
    `user_idle_freeze_minutes` (with the conversion at the call sites);
    `worker_snapshot_ttl` and `deposit_lock_retry_interval` are judged in
    the same pass and renamed only if the unit is missing from the name.
    (8) `global_register_item_tytx` stays as the placeholder it is: it moves
    to the vertex in Phase 2.
    (9) The `event` word keeps its M2 spelling. The rename proposed in
    planning (`worker_events` / `add_worker_event`) is NOT part of this
    phase: the owner declined the strategy of naming ahead of the code, and
    whatever survives the chain gets its `_TBD` round at the end of Phase 2.
  - Details: mechanical, one commit. `GroupStub` in the tests grows
    `ping_now()` and loses `on_worker_abort`; the tests that photographed
    the wild-death denunciation of a quit are rewritten on the state (a
    failing one here is a real regression, not a test to adapt).
  - Done: `pytest tests/ -q` green (the count may drop with the tests of
    the removed mechanics); `ruff check src/ tests/` clean;
    `grep -rn "_governed_death\|_wait_ordered_death_seen\|on_worker_abort\|on_child_message\|EVENT_METHOD\|user_idle_freeze_delay" src/genro_asgi/spa/orchestration/ tests/orchestration/`
    returns nothing.

- [x] **Phase 2**: The envelope chain and the vertex
  > Done: the chain (`EnvelopeHandler` + the three layers) reads every envelope
  > that arrives from a child — the photo first, then the announcements in the
  > order they were made — and gives back what goes down. The single door is the
  > WIRE: `WorkerConnector` hands the whole envelope to
  > `WorkerHandler.take_envelope_TBD` (presentation AND every REPLY), writes the
  > chain's answer as the presentation reply, and reads nothing itself;
  > `global_register_item_tytx` left the handler as declared. `SpaCommander` owns
  > the three indexes, the minting of a cid never seen (`resolve_user`, guest rows
  > written before anything descends), the predicates, the waiting room as
  > `raise UserOnHold`, the mutators the fold calls, the C3 bonifica through the
  > `FreezeHandler`, the aggregate counters and `log_order` on its own rotating
  > file. `GlobalRegister` is a new class (no import from the legacy store): master
  > Bag and TYTX form, and the chain answers every envelope with that store WHOLE —
  > the wire writes it where there is an envelope going down, the presentation.
  > [SUPERSEDED at the simplification round, commit 36c8900, rationale in
  > notes.md: `global_register.py` was DELETED — the master is a bare Bag on
  > `SpaCommander.global_register`, the TYTX form is made at the consumer, and
  > the chain answers ONLY the presentation with the store, not every envelope.
  > The baptism `GlobalRegister` in this plan's list died with the class.]
  > How a change reaches a process already alive is NOT decided here (see the
  > pending point below). The death climbs as `process_quitted` /
  > `process_aborted` from `report_death`, which splits the users ONCE into
  > frozen and lost. Every census row of v4 §3 is covered by a test.
  > Verified: `pytest tests/ -q` 1877 passed / 2 skipped (was 1841/2);
  > `ruff check src/ tests/` clean; `mypy src/` unchanged and ZERO findings in the
  > four new modules; coverage of the new code 100% (envelope_handler,
  > spa_commander, global_register, exceptions), worker_handler 99%. The
  > end-to-end with a REAL child shows an announcement born in the child landing
  > in the vertex's indexes, and a fold that refuses an envelope denounced without
  > severing the wire. The M2 story now closes on the vertex: births as no-ops, the
  > flagged user in the waiting room, the freeze mark plus the placement to be
  > assigned, the adoption, and the round that consumes the death.
  > PENDING (ruled by the owner at the end of this phase, 2026-08-17): the delivery
  > of a store CHANGE to a live replica. The mechanism dictated: the write climbs
  > as an announcement in the envelope, the vertex updates the master, then it
  > sends an update CALL to every worker — built when the vertex has its groups,
  > i.e. Phase 3/4. The invented workflow of the first draft (a revision as
  > staleness sensor on the handler and on the register, a second entry point on
  > the chain, the change riding the beat) was REMOVED whole: Phase 2 keeps only
  > the ratified rule, that the chain answers with the whole store.
  > Files: src/genro_asgi/spa/orchestration/envelope_handler.py,
  > src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/global_register.py,
  > src/genro_asgi/spa/orchestration/exceptions.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/worker_connector.py,
  > src/genro_asgi/spa/orchestration/__init__.py,
  > tests/orchestration/test_orchestration_envelope_chain.py,
  > tests/orchestration/test_orchestration_spa_commander.py,
  > tests/orchestration/group_stub.py,
  > tests/orchestration/child_stub.py,
  > tests/orchestration/test_orchestration_worker_handler.py,
  > tests/orchestration/test_orchestration_worker_connector.py,
  > tests/orchestration/test_orchestration_spa_worker_process.py,
  > tests/orchestration/test_orchestration_foundations_e2e.py,
  > tests/orchestration/test_orchestration_m2_e2e.py,
  > .phased/active/orchestration-m3-commander-groups/notes.md
  > Verify: now — read `spa_commander.py` and the three EnvelopeHandler as prose:
  > does the ladder read as one mechanism, or does a layer look like it is doing
  > somebody else's job?
  > Verify: now — the `_TBD` round: in progress, one at a time.
  > `take_envelope_TBD` → **`read_envelope`** (ruled 2026-08-17);
  > `descending_payload_TBD` and `hand_up_TBD` died with the code they belonged to
  > (the invented store workflow, and the template-method dance the owner cut);
  > the base's own step → **`work_on_envelope`** (ruled 2026-08-17: a name that
  > leaves a layer free to add, remove and modify, not only to read); the
  > vocabulary Phase 1 decision (9) postponed to this round applied at last —
  > `worker_events` / `add_worker_event` / `"worker_events"` on the wire, and
  > *worker event* in prose; 10 left.
  - Run: opus / high
  - Pattern: `src/genro_asgi/middleware/base.py:87` (`BaseMiddleware` — the
    callable chain, both ends handed in at construction, never discovered by
    walking wrappers: the shape the three EnvelopeHandler take);
    `src/genro_asgi/spa/orchestration/spa_worker.py` (the registers, the
    single-mutator discipline under one lock);
    `src/genro_asgi/spa/subscription_index.py` (the single mutator that
    keeps two directions in step); the legacy `src/genro_asgi/spa/commander.py`
    for the indexes being rethought — DEEP RETHINK, never a verbatim
    transplant.
  - Files: src/genro_asgi/spa/orchestration/envelope_handler.py (new),
    src/genro_asgi/spa/orchestration/spa_commander.py (new),
    src/genro_asgi/spa/orchestration/global_register.py (new),
    src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/worker_connector.py,
    src/genro_asgi/spa/orchestration/__init__.py,
    tests/orchestration/test_orchestration_envelope_chain.py (new),
    tests/orchestration/test_orchestration_spa_commander.py (new)
  - Decisions:
    (1) **Three classes, one per level, CALLABLE**, each holding the next:
    `WorkerEnvelopeHandler` (one per handler) → `GroupEnvelopeHandler` (one
    per group) → `CommanderEnvelopeHandler` (one). The `WorkerHandler` does
    `return self.envelope_handler(envelope)`. Dispatch by name inside each
    layer: `on_<announcement>` methods, homonymy cascading across layers
    (cite `Class.method` when in doubt).
    (2) **Up for nested calls, down for the return.** Every layer may
    ENRICH what descends: the `CommanderEnvelopeHandler` adds
    `global_register_item_tytx` when the master has changed. The primary
    answer of a REPLY is handed to the parked caller as today. Rule: whoever
    orchestrates calls, whoever owns executes and returns — no level
    forwards on its own initiative.
    (3) **The announcement census is v4 §3** (F47, ratified "all good, we
    will refine if needed"): `worker_snapshot` (handler annotates → group
    thresholds → vertex T/X flags into `on_hold`) · `new_user` /
    `new_connection` (no-op, the minting already wrote them) · `new_page` ·
    `drop_page(s)` · `drop_connection(s)` (the vertex drops its pages and
    leaves `connection_user_map` intact — the cookie is eternal, A7) ·
    `drop_user` · `user_frozen` (group: "to be assigned"; vertex: the mark
    plus `occupancy_percent`) · `user_adopted` · `process_quitted` /
    `process_aborted` (group: `drop_worker`; vertex: prune, or bonifica).
    (4) **`SpaCommander`** in `spa/orchestration/spa_commander.py` (the
    legacy `UserStickyCommander` untouched until Macro 6). It owns
    `user_map` — `{group, frozen, on_hold, occupancy_percent,
    pending_dbevents, pending_datachanges}` — `connection_user_map`
    (cid → user) and `page_connection_map` (page → cid, immutable). Reading
    goes through predicates (`user_is_frozen(user)`); `on_hold` is read ONLY
    as `except UserOnHold`.
    (5) **`resolve_user(cid)`**: the reception desk. Resolves the identity,
    MINTS the entries of a cid never seen before (F47: the front mints the
    cookie, the vertex writes the rows before descending — it cannot route
    whom it has not written; the guest is named `guest_<cid>`), and raises
    `UserOnHold` when the row carries a cause. The placement is the separate
    step (`assign_user`, Phase 3).
    (6) **`GlobalRegister`** (new class): holds the master, exposes the
    TYTX-encoded form, knows it has changed and spreads the change to the
    replicas. The lock grant is Macro 4. The placeholder property leaves
    `WorkerHandler`.
    (7) **`SpaCommander.state`**: `running` / `saturated` / `broken` — the
    machine-level crisis, written by `check_resources()` in Phase 4.
    [Outcome, review round 2026-08-18: `check_resources()` writes `running`
    and `saturated` only — no vertex code ever writes `broken`, so the
    docstring says two values; the third returns with its writer.]
    (8) **`log_order(...)`**: composes ONE structured row per order (who
    decided, what, on whom, when, the numbers it had in front, the outcome)
    over a dedicated rotating handler; a wild death gets a row too. The
    group does not know the file: it calls the vertex. Path, size and
    backup count are grammar (Phase 5).
  - Details: the chain is synchronous (RAM writes) and runs inline at the
    point of arrival, so FIFO by construction. This phase closes the hole
    Phase 1 declares: the payload `ping_process` now returns is handed to
    `WorkerEnvelopeHandler` and climbs.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; an
    end-to-end test with a REAL child process (the M2 child stub) shows an
    announcement born in the worker landing in the vertex's indexes, and the
    global register change riding the descending envelope; every census row
    of v4 §3 covered by a test.
  - Verify: now — read `spa_commander.py` and the three EnvelopeHandler as
    prose: does the ladder read as one mechanism, or does a layer look like
    it is doing somebody else's job?
  - Verify: now — the `_TBD` round: the surviving placeholders, one at a
    time, semantics plus candidates.

- [x] **Phase 3**: GroupHandler — placement, manoeuvres, the two crises
  > Done: `GroupHandler` is born (179 executable lines, cap ~200) and it owns the
  > three things nobody else does — `user_worker_map` (`None` = to be assigned,
  > written by the chain straight into the bare map), the manoeuvres on its own
  > workers, and its own shape. NO TARGET: the first `start_worker` is the
  > reception (the oldest living worker, succeeded silently), growth is on demand
  > and shrinking is by waste. The placement is EAFP: `assign_user` walks the
  > candidates from the FULLEST down and `WorkerHandler.assign_user(user,
  > occupancy_percent)` judges itself on its own last photo and refuses by raising
  > — `NoRoomError` (projected over the setpoint), `WorkerRestartingError`,
  > `WorkerQuittingError`, and the base for a worker that has not presented itself
  > yet; candidates exhausted, the base rises and the wake rings on the way out.
  > The estimate is read from the user's row at the vertex, `new_user_occupancy_percent`
  > when nobody has ever measured him, and the overshoot of two placements judged on
  > one photo is accepted (F15). The occupancy is the transplant of design #5 read
  > over the photo the M2 worker really sends: one clamped component per measurable
  > gauge (`rss_bytes` against what one worker of the group may hold), the fullest
  > wins, in percent. `check_occupancy` takes ONE picture and does the FIRST thing
  > it calls for — restart past `restart_occupancy_max_percent`, grow when nobody
  > has room for a newcomer left, close the worker whose share the others can
  > absorb AND still admit (the margin that keeps a closure from undoing a growth).
  > The crises: `saturated` when the memory quota (or the vertex's own state)
  > refuses the growth, left the moment there is room again; `broken` when a
  > `launch_process` fails, left by the first process that starts. `drop_worker(name)`
  > is LOUD on a name the group does not carry, takes the wire away detached and
  > releases the placements that still pointed at it; the ordered quit photographs
  > the worker first, so a departure is never settled on nothing.
  > Verified: `pytest tests/ -q` 1900 passed / 2 skipped (was 1877/2, +25 tests);
  > `ruff check src/ tests/` clean; `mypy src/` unchanged (94, the baseline) and ZERO
  > findings in `group_handler.py` and `exceptions.py`; coverage of the new module
  > 100%, `envelope_handler` 100%, `worker_handler` 99%. TEN NEUTRALIZATION PROBES,
  > each removing one mechanism and each breaking its own test: the photo before the
  > order, the reception's reserve, the closure margin, the loudness of `drop_worker`,
  > the quota gate, the fullest-first order of the walk, the wake when nobody admits,
  > the `restarting` refusal, the urgency threshold, and the walk's sort direction.
  > The closure runs its six steps over a REAL child process, end to end.
  > Files: src/genro_asgi/spa/orchestration/group_handler.py (new),
  > src/genro_asgi/spa/orchestration/exceptions.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/spa/orchestration/envelope_handler.py,
  > src/genro_asgi/spa/orchestration/__init__.py,
  > tests/orchestration/test_orchestration_group_handler.py (new),
  > tests/orchestration/test_orchestration_placement.py (new),
  > tests/orchestration/group_stub.py,
  > tests/orchestration/test_orchestration_envelope_chain.py,
  > .phased/active/orchestration-m3-commander-groups/notes.md
  > Verify: DONE — the baptism round of this phase: the group's verb for bringing
  > a worker into being (`start_worker`), the placement setpoint
  > (`get_worker_cap`), the group's memory quota and the per-worker ceiling (both
  > died unborn, replaced by the percent cascade), the bag of worker settings
  > (`worker_settings`), and the two inherited from Phase 2 that survived (the
  > urgency of a photo — killed and inlined — and the death of a process,
  > `report_death`).
  > Verified: the owner's rulings, applied as one search-and-replace.
  > `start_worker` is the group's verb (the sibling of `drop_worker` /
  > `restart_worker`); `get_worker_cap` is the placement setpoint, BARE — the
  > owner refused the unit suffix; `worker_settings` is confirmed as it stood, it
  > is the VALUES dict and not the grammar; `report_death` is the handler
  > REPORTING a fact, and the word "announce" left the prose that spoke of that
  > method (the worker-events vocabulary is untouched). TWO DIED UNBORN, both
  > byte-denominated: `memory_max_bytes` and `worker_memory_max_bytes` are gone,
  > and the ratified cascade is read in PERCENT space — `memory_concession_bytes`
  > is the only total handed in, `memory_max_percent` is this group's share of
  > it, `worker_memory_max_percent` (the same grammar key one rung down, the
  > deliberate homonymy) is one worker's share of the group's quota. So the
  > growth gate reads the new property `memory_occupied_percent` against
  > `memory_max_percent`, percent against percent, and the occupancy formula
  > normalises a worker's rss against its share of the quota — the transplanted
  > design #5 shape untouched. ONE KILLED OUTRIGHT: `snapshot_is_urgent`, whose
  > threshold check is now inline at its single caller,
  > `GroupEnvelopeHandler.on_worker_snapshot`.
  > `pytest tests/ -q` 1903 passed / 2 skipped (was 1900/2, +3 tests); `ruff check
  > src/ tests/` clean; `group_handler.py` back to 100%.
  > Verify: now — the reading declared in notes.md: `restart_worker` settles the
  > departure through the death and comes back with a NEW worker, not the same
  > handler relaunched (the plan's decision (6) says `launch_process`).
  > Verify: now — the finding declared in notes.md: the M2 photo throttle can leave
  > the answer to `/op/quit` carrying no photo, so a departure would be settled on a
  > picture taken BEFORE the flags. Outside this phase's files; the guard covers only
  > the no-photo case, as the plan's contract note says.
  > Verified: the staleness itself was cured in `spa_worker.py` by 08cc20a
  > (`plan_transfers` marks the photo due the moment it poses a flag), and the
  > baptism pass gave it the biting test it had none of —
  > `test_a_flag_posed_puts_the_photo_on_the_next_envelope_out`, on a worker whose
  > `worker_snapshot_ttl` is pinned to an hour and whose photo has already gone
  > out. Proved by neutralization: with the line removed the third envelope
  > carries no photo and the test fails on `KeyError: 'worker_snapshot'`.
  - Run: opus / high
  - Pattern: `src/genro_asgi/spa/orchestration/worker_handler.py` (the twin
    level: how a handler owns its own and asks the level above nothing);
    `src/genro_asgi/spa/evaluator.py:130` (`build_targets`,
    `worker_saturation`, `worker_components` — the occupancy formula is
    TRANSPLANTED from design #5, per component with its clamp, never
    reinvented); the legacy `spa/commander.py` pool logic as a source to
    rethink, never to copy.
  - Files: src/genro_asgi/spa/orchestration/group_handler.py (new),
    src/genro_asgi/spa/orchestration/exceptions.py (new, or the existing
    `genro_asgi/exceptions.py` if the family belongs there),
    src/genro_asgi/spa/orchestration/spa_commander.py,
    src/genro_asgi/spa/orchestration/worker_handler.py,
    src/genro_asgi/spa/orchestration/__init__.py,
    tests/orchestration/test_orchestration_group_handler.py (new),
    tests/orchestration/test_orchestration_placement.py (new)
  - Decisions:
    (1) **No target.** At boot the group brings the RECEPTION into being —
    a role, not a count. It grows only on demand: nobody admits → the wake
    rings → at the round `check_occupancy()` sees everybody at the setpoint
    and brings a process into being, IF the group's memory quota has room
    (sum of the group's rss ≤ quota × concession, AND the machine under its
    alarm line). The stranger got a 503 with `Retry-After` and enters on his
    retry. Nothing in grammar says how many processes there are.
    (2) **EAFP placement.** `GroupHandler.assign_user(user)` walks the
    candidates from the fullest down and calls
    `WorkerHandler.assign_user(user)`, which judges itself from its
    annotated photo and REFUSES BY RAISING. Family: `AssignmentRefused`
    (base) ← `NoRoomError` (the projected count `mine + estimate(incomer) >
    occupancy_max_percent`), `WorkerRestartingError` (state `restarting`),
    `WorkerQuittingError` (state `quitting` — it will never come back).
    Candidates exhausted → the base rises → the vertex answers 503 and the
    wake rings. `decide_worker` and any admission predicate are NOT born.
    (3) **The incomer's estimate**: computed by the worker that hosted him,
    normalised into occupancy, travelling in `user_frozen`, living in the
    `occupancy_percent` field of the `user_map` row; whoever has no estimate
    (first login, guest) gets `new_user_occupancy_percent`. Overshoot
    accepted (F15).
    (4) **`check_occupancy()`** — ONE input (the occupancy picture), THREE
    outputs: a process is born (group at the setpoint, quota has room), a
    worker is closed (capacity wasted), a worker is restarted (over
    `restart_occupancy_max_percent`). It ACTS on state, and its docstring
    says so. Called by `ping()` when the group's own counter is due, and
    IMMEDIATELY when the group was woken (the wake overrides the counter).
    (5) **The closure**, F46 rewritten without the target: the group decides
    a worker may die → `quit_process()`; the worker answers at once with the
    photo all `T` → the vertex parks his users; the worker drains, freezing
    one at a time, the announcements riding the ping replies; emptied, it
    leaves by itself → the EOF was awaited → state `quitted` → at the round
    the group does `drop_worker` (socket closed, out of the list) — the same
    verb the wild-death bonifica uses. Past `QUIT_TIMEOUT_SECONDS` the abort
    is loud and counted.
    (6) **`restart_worker(handler)`** stays the ratified coroutine: same
    quit, then `launch_process`. The why lives in the caller's stack, never
    in a map of orders.
    (7) **`GroupHandler.state`**: `running` / `saturated` (the memory quota
    is full — a 503 that hopes somebody leaves) / `broken` (a
    `launch_process` failed — a 503 that says we are working on it). Both
    warn the sysop through `log_order`. There is no `crisis_policy` and no
    `fallback_group`: a user does not change group.
    (8) **`user_worker_map`** lives here, `None` meaning "to be assigned",
    written by the single mutator that the announcements go through.
    (9) **`reception_reserved_percent`**: the reception's placement setpoint
    is DEDUCED (max − reserve), never configured.
  - Details: the group is the level that owns the manoeuvres; it never
    touches an index of the vertex and never opens the freezer.
    CONTRACT NOTES from the simplification round (2026-08-17, binding):
    (a) `GroupHandler.drop_worker(name)` is LOUD on an unknown name — the
    test stub is silently idempotent, the real one must not be;
    (b) an ordered quit whose photo never arrived purges everybody as
    quitted — the group ensures a photo preceded the order (the quit
    REPLY itself carries one; the guard is about the degenerate path).
    LINE CAP (the owner's rule: excess code IS a defect): the new
    `group_handler.py` stays around ~200 executable lines (the twin
    `worker_handler.py` runs ~200); method docstrings are the TRIPLET,
    narrative lives in the module docstring only. The phase review
    judges volume as a defect class, same as correctness.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; tests
    covering: boot brings up the reception; the fullest-first walk; each of
    the four refusals raised and caught; growth on demand inside the quota
    and refused outside it; the six steps of the closure with a real child;
    `saturated` and `broken` reached and left.
  - Verify: now — the `_TBD` round of this phase.
  - Verify: deferred: needs Phase 5 — with a real installation, the group
    grows and shrinks under load in a way that looks sane in the
    orchestration log.

- [x] **Phase 4**: The heartbeat — one clock, counters below
  > Done: the machine has ONE clock. `heartbeat_loop` waits on `timer OR any
  > wake`: the timer is a full round (`ping_groups()` — one turn per group, all
  > at once, `gather(..., return_exceptions=True)`, a group whose previous turn
  > is still open skipped and said so out loud) plus whichever of the vertex's
  > own tasks its count of beats has come round for; a wake is an anticipated
  > round on THAT group alone and is not a beat. `GroupHandler.ping()` is the
  > turn: it counts its own beats, consumes its own wake (which is what lets a
  > group that rings during its turn be given another one), calls `ping_workers()`
  > on the SILENT ones only — `WorkerHandler.silent_TBD`, read off the instant
  > every envelope stamps — and runs `check_occupancy()` when its own count says
  > so or the wake said now. The three tasks nobody below can do:
  > `drop_expired_users` (the frozen judged each on the clock of his own kind,
  > `guest_expiry_hours` for a guest and `user_expiry_hours` for a person, then
  > `purge_users_TBD` — row and disk with verification, the declared F24
  > exception), `disk_cleanup` (the deposit swept of every folder no row claims,
  > counted and named in the log) and `check_resources` (machine memory against
  > `machine_memory_alarm_percent`, the deposit's disk against
  > `frozen_users_disk_alarm_percent` → `state`, and `need_resources()`, base
  > empty, which a subclass really overrides). Each task is isolated: one that
  > raises leaves its line and the others of that beat still run. Every reading of
  > the disk goes through `asyncio.to_thread` (F17), and the sweep of the folders
  > moved INTO the `FreezeHandler`, which is the only object that talks to the
  > filesystem. No caretaker object was born: the probe IS the beat.
  > Verified: `pytest tests/ -q` 1917 passed / 2 skipped (was 1903/2, +14 tests);
  > `ruff check src/ tests/` clean; `mypy src/` unchanged (94, the baseline) and
  > ZERO findings in `spa_commander.py` and `group_handler.py`; coverage
  > `group_handler` 100%, `spa_commander` 97% (the six lines are the
  > `/proc/meminfo` parse, which no macOS runs and the ubuntu CI does),
  > `freeze_handler` 99%, `worker_handler` 99%. FIVE NEUTRALIZATION PROBES, each
  > breaking its own test: the wake serving only the group that rang
  > (`ping_groups(woken)` → `ping_groups()`: the second group takes a turn it was
  > never given), the loop surviving a raising round (the `try` removed: the clock
  > dies at the first beat and the test times out), the skip of a group still in
  > its turn, the beating of the silent only, and the wake consumed at the turn.
  > EXECUTABLE LINES ADDED: 110 `spa_commander.py` + 17 `group_handler.py` = 127
  > against the ~120 cap of the two files (13 `freeze_handler.py` + 6
  > `worker_handler.py` besides); the itemisation and what was cut is in notes.md.
  > Files: src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/group_handler.py,
  > src/genro_asgi/spa/orchestration/freeze_handler.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > tests/orchestration/test_orchestration_heartbeat.py (new),
  > .phased/active/orchestration-m3-commander-groups/notes.md
  > Verified: DECLARED DEVIATION — `applications/spa_app.py` is NOT touched, and
  > `start`/`stop` were not born. That front owns the LEGACY commander, which
  > dies at Macro 6; wiring the new vertex into it is the Macro 4 the plan's own
  > Notes reserve, and a lifecycle pair whose only caller would have been a test
  > fixture is code without a requester (the same judgement Phase 3 made on
  > `GroupHandler.start`). `heartbeat_loop` is the plain coroutine a lifespan
  > creates and cancels, which is exactly what the tests do to it.
  > Verified: the `_TBD` round CLOSED on 2026-08-18 (12 names, one at a time), and
  > on the way it brought THREE amendments the owner ratified — each landed as its
  > own commit, suite green at every step, rationale in notes.md:
  > (a) **the storage left the quotas** — a disk is nothing the pool can grow into,
  > so the MEMORY alone writes `state`; the gauge is flipped to the free share
  > (`storage_free_percent`) and a level under `STORAGE_RESERVE_PERCENT` (10.0, a
  > constant: a full disk is full for every installation) is said out loud and calls
  > `need_resources`. The grammar key `frozen_users_disk_alarm_percent` is never
  > born — "too many parameters do harm; it is enough that somebody is told when
  > less than 10% is left".
  > (b) **the cadence is declared on the method** — `@every(beats)`
  > (`spa/orchestration/beats.py`, exported from the package) counts the turns of a
  > periodic method on the INSTANCE (`beat_counts`, one row per method: `turns`,
  > `runs`, `errors`, `last_error`), logs and swallows what it raises, and runs
  > regardless when called with `now=True`. With it die `_run_due_tasks` and the
  > group's `_beats`: ONE mechanism for the three rungs, instead of a table at the
  > vertex and a modulo in the group's body.
  > (c) **forgetting a user takes his freezer state with him** — the disk entered
  > `drop_user`, so `drop_users` is genuinely its plural and the one-letter
  > difference hides no wider reach; the orphan sweep keeps its population, which is
  > a row lost WITHOUT a drop (a server killed before its dump, a restore older than
  > the freezer).
  > Verified: 1918 passed / 2 skipped; ruff clean; mypy 94 (the baseline, plus one
  > scoped `attr-defined` override for the wrapper's own marker); `beats.py` 100%,
  > `group_handler` 100%, `spa_commander` 97%. FOUR MORE NEUTRALIZATION PROBES, each
  > breaking its own tests: the reserve lamp pinned off, the cadence pinned open, the
  > wake no longer overriding the count, the disk call pinned out of `drop_user`.
  > Files: src/genro_asgi/spa/orchestration/beats.py (new), spa_commander.py,
  > group_handler.py, freeze_handler.py, __init__.py, pyproject.toml,
  > tests/orchestration/test_orchestration_heartbeat.py,
  > test_orchestration_spa_commander.py, test_orchestration_group_handler.py,
  > test_orchestration_envelope_chain.py
  - Run: opus / high
  - Pattern: `src/genro_asgi/tasks/scheduler.py:100` (`start` / `stop` /
    `_run_loop` — the periodic loop owned by the lifespan, the tick isolated
    so a failing round never kills the loop, and a `tick()` a test can call
    without the loop); `src/genro_asgi/lifespan.py` for the ordered
    startup/shutdown.
  - Files: src/genro_asgi/spa/orchestration/spa_commander.py,
    src/genro_asgi/spa/orchestration/group_handler.py,
    src/genro_asgi/spa/orchestration/freeze_handler.py,
    src/genro_asgi/applications/spa_app.py,
    tests/orchestration/test_orchestration_heartbeat.py (new)
  - Decisions:
    (1) **`heartbeat_loop()`** — the ONE interval of the whole system,
    started and stopped by the lifespan. It waits on `timer OR any
    `ping_now_event``: the timer gives a full round, a wake gives an
    anticipated round on THAT group only. `HEARTBEAT_SECONDS = 5.0`
    (constant, twin of `PROCESS_PING_INTERVAL`).
    (2) **`ping_groups()`** is the cascade and NOTHING else — a separate
    method so a test can run one round without the loop. It walks the
    groups, skipping any whose previous round is still open (the per-group
    lock), and awaits them with
    `asyncio.gather(..., return_exceptions=True)`: everybody is awaited, an
    exception is a value, nobody cancels a sibling. A mute process spends
    its two `PROCESS_PING_TIMEOUT` inside its own group and delays nobody
    else.
    (3) **`GroupHandler.ping()`** is the group's turn: it increments its
    counter, calls `ping_workers()` (only the SILENT ones — a photo fresh
    from traffic is skipped), and when the counter is due (or the group was
    woken) runs `check_occupancy()`. `ping_workers()` gathers
    `handler.ping_process()` the same way.
    (4) **The vertex's own tasks, each on its counter** inside
    `heartbeat_loop`: `drop_expired_users()` (the frozen whose
    `user_expiry_hours` / `guest_expiry_hours` ran out — nobody below them
    can notice, so the vertex prunes the row and the disk with verification,
    the declared F24 exception), `disk_cleanup` (the tasks that open the
    disk; the folder set-difference is a step of it), `check_resources()`
    (machine RAM against `machine_memory_alarm_percent`, deposit disk
    against `frozen_users_disk_alarm_percent` → writes
    `SpaCommander.state` and calls `need_resources()`, base `pass`, a
    Kubernetes commander overrides it by subclass).
    (5) **The wake is the only PUSH in the system**: an event per group,
    idempotent, without content — the information is WHICH event rang. It is
    rung by the EOF of one of its handlers, by the "nobody admits" of its
    placement, and by the crisis threshold on one of its photos. Machine
    urgencies (RAM, disk) stay on the timer: they are trends, not
    emergencies.
    (6) The active users' expiry belongs to the WORKER (X at the shot: it
    does everything and announces, and the ladder is pruned layer by layer);
    only the frozen are the vertex's.
  - Details: no caretaker object exists — the probe IS the beat. The
    monitor gets a fresh photo for free by ringing the wake.
    LINE CAP: the loop + cascade + vertex tasks are ~120 executable
    lines added across the two files; triplet docstrings, volume judged
    as a defect at review.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; tests
    covering: one round with a real child; a mute process delaying its own
    group and not the others; a wake giving an anticipated round on one
    group only; the counters firing `check_occupancy` / `drop_expired_users`
    / `disk_cleanup` / `check_resources` at their own cadences; the loop
    surviving a round that raises.
  - Verify: now — the `_TBD` round of this phase.

- [x] **Phase 5**: The grammar and the whole machine end to end
  > Done: the pool is WRITABLE. One new section of the site grammar — `commander`,
  > with its `groups` collection keyed by `name` — carries the two paths of the
  > installation (`frozen_users_path`, `instance_dir`, declared once and shared by
  > every group), the vertex's policies (`memory_max_percent`,
  > `machine_memory_alarm_percent`, the three `orchestration_log_*`,
  > `user_expiry_hours` / `guest_expiry_hours`) and, one rung down, the group's own
  > (the five occupancy percentages, `memory_max_percent` /
  > `worker_memory_max_percent`, `user_idle_freeze_minutes`) plus the identity of
  > its child (`entry_module`,
  > `executable`, `worker_class`, the two pool sizes, `worker_kwargs`). NO key says
  > how many workers there are, and no key names the freezer's disk. Every grammar
  > key is spelled exactly like the constructor parameter it feeds, so the read door
  > translates nothing: `ConfigurationHandler.commander_kwargs()` is the vertex's
  > signature and `group_kwargs()` is `{name: kwargs}`, one `GroupHandler` each,
  > with the two paths folded in and the keys the CHILD reads gathered into its own
  > `worker_kwargs` (its group's name, and the silence it measures itself). The
  > cascade got its missing top: `SpaCommander.memory_max_percent` +
  > `memory_concession_bytes` (the machine's `MemTotal` times that share, None where
  > the platform does not say), which is the ONE total a group's quota and a
  > worker's ceiling are percentages of. RECONCILIATION of amendment (d), decided
  > at the closing round of this phase: the ages live on the VERTEX only, where
  > `drop_expired_users` reads them to judge the FROZEN. The group's rung — the
  > ages of its ACTIVE users — is deferred to Macro 4 together with its reader,
  > the worker's own shot: born here it would have been two kwargs, two
  > assignments, a grammar key and a `group_kwargs()` entry that nobody in `src/`
  > reads, and what has no reader does not get born.
  > TWO GAPS OF THE UPPER PHASES CLOSED, both ratified design that no phase had
  > implemented and both without which "the whole machine end to end" cannot run
  > unattended: (a) `GroupHandler.ping()` now settles every process whose end has
  > not been read yet — `report_death()` on a handler in a `DEAD_STATES` state (3
  > lines), which is Phase 1 decision (3)'s "the group learns at its round, reading
  > the state" and Phase 3 decision (5)'s step 5; before it, nothing in `src/`
  > consumed a death and every test drove `report_death` by hand. (b) The bottom
  > layer of the chain keeps `hosted_users`, which `worker_handler.py` already
  > declared "the fold is its single writer": `on_new_user` / `on_user_adopted` add,
  > `on_user_frozen` / `on_drop_user` discard (4 readers, 2 of them aliases) —
  > without it a wild death is settled on an empty list and purges nobody.
  > Verified: `pytest tests/ -q` 1928 passed / 2 skipped (was 1918/2, +10 tests);
  > `ruff check src/ tests/` clean; `mypy src/` 94, the baseline, with ZERO findings
  > in the five touched modules (the one in `envelope_handler.py` is pre-existing,
  > measured with the change reverted); coverage `elements.py` 100%, `handler.py`
  > 100%, `envelope_handler` 100%, `group_handler` 100%, `spa_commander` 97% (the
  > five lines are the `/proc/meminfo` parse, which no macOS runs and the ubuntu CI
  > does). EXECUTABLE STATEMENTS ADDED in `src/`: 36 (elements 3, handler 17,
  > envelope_handler 6, group_handler 3, spa_commander 7) — the itemisation is in
  > notes.md. FOUR NEUTRALIZATION PROBES, each breaking its own tests: the silence
  > policy no longer folded into the child's kwargs (the e2e's freeze never happens,
  > plus two config tests), the round no longer burying the dead (the e2e alone),
  > the fold no longer keeping who is on board (the e2e alone), the concession
  > pinned to None (the vertex's own test).
  > Verified: the M3 END TO END is one story on the real things — the policies read
  > from a config FILE on disk through the server's own read door, the vertex and
  > the group built from nothing but what it says, three REAL child processes, a
  > real freezer on disk, and the real clock. In order: the reception born at boot;
  > two people placed on it and served through the WSGI seam; one of them frozen by
  > the idleness the CONFIG FILE declared (parked at the vertex, on disk past the
  > gate, placement to be assigned); her LAZY WAKE on her next request; the growth
  > on demand (the concession measured, the reception refusing a newcomer with the
  > reserve it keeps, the wake, the round, the second process, and the retry landing
  > on it); the closure for wasted capacity through its six steps over the real
  > child, the round that reads the ended state taking it out; and a WILD DEATH with
  > two people on board under the running `heartbeat_loop` — nobody drove it: the
  > end of the wire rang the wake, the round read `aborted`, the two on board were
  > purged whole, the frozen woman on nobody's board was untouched, and the group,
  > left with no worker at all, brought a fresh reception into being. The
  > orchestration log the config file named is read at the end and asserted row by
  > row: 3 `start_worker`, 1 `close_worker`, 2 `drop_worker` (`quitted` then
  > `aborted`), 2 `drop_user` (`process_aborted`), each with its decider, its
  > subject, the numbers in front of it and its outcome.
  > Verified: DECLARED DEVIATIONS. (1) `config/default_config.py` is NOT touched:
  > it resolves WHICH defaults recipe layers under a site and knows no key, so the
  > new section needed nothing there; `config/handler.py` is touched instead, which
  > the plan's Files list did not name — that is where a section becomes kwargs.
  > (2) `USER_PENDING_MAX_ITEMS` (decision 4) is NOT born: nothing writes
  > `pending_dbevents` / `pending_datachanges` yet (the notifications are Macro 4 by
  > the plan's own Notes), so a cap on them would be a constant with no writer. The
  > other constants of that decision were verified present: `HEARTBEAT_SECONDS`,
  > `QUIT_TIMEOUT_SECONDS`, `STORAGE_RESERVE_PERCENT`, the four cadences,
  > `PROCESS_PING_INTERVAL`, `PROCESS_PING_TIMEOUT`, `TRANSFER_START_DELAY`,
  > `DEPOSIT_LOCK_WAIT_LIMIT`. (3) No `AsgiServer` builds a pool: the server's read
  > door reads the section, and whoever OWNS a vertex — the new SPA front of Macro 4
  > — is the caller of these two readers. The e2e builds the pair exactly as that
  > front will, which is also what `tests/test_config.py` asserts through a real
  > `AsgiServer`.
  > Files: src/genro_asgi/config/elements.py,
  > src/genro_asgi/config/handler.py,
  > src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/group_handler.py,
  > src/genro_asgi/spa/orchestration/envelope_handler.py,
  > tests/orchestration/test_orchestration_m3_e2e.py (new),
  > tests/orchestration/test_orchestration_spa_commander.py,
  > tests/test_config.py,
  > docs/guides/configuration.md,
  > .phased/active/orchestration-m3-commander-groups/notes.md
  > Verify: now — the guide's new section (`docs/guides/configuration.md`, "The pool
  > section") was exercised through `tests/test_config.py`'s `SpaPoolConfig`: the
  > SAME recipe shape (a `commander_section(self, cfg)` method, a full group and a
  > child-only group), with different values — the published snippet itself was
  > not the one executed. The guide's log sample is the e2e's rows shortened of
  > the leading timestamp the formatter prepends, one decimal rounded.
  > Verified: the Verify Phase 3 DEFERRED to this phase is answered — "with a real
  > installation, the group grows and shrinks under load in a way that looks sane in
  > the orchestration log": the M3 e2e grows it on a refused newcomer, shrinks it on
  > wasted capacity and regrows it after a wild death, and the eight rows of the log
  > read in that order with the numbers each decision was taken on.
  > Verify: now — the `_TBD` round of this phase: NO `_TBD` name was created
  > (`grep -rn "_TBD" src/ tests/` returns nothing), because every grammar key is
  > the constructor parameter it feeds. What the owner is owed is a CONFIRMATION of
  > four names taken from the existing vocabulary rather than coined: the section tag
  > `commander` (the class is `SpaCommander`), the collection `groups` / `group` (the
  > class is `GroupHandler`, the index `group_map`), the collection key `name` (the
  > parameter is `GroupHandler.name`, where every other collection of this dialect
  > keys on `code`), and the two readers `commander_kwargs()` / `group_kwargs()`
  > (the twin of `server_kwargs()`). Each is one search-and-replace if he wants
  > another.
  > Verified: THE OWNER'S ROUND, 2026-08-18. The four names above are CONFIRMED as
  > they stand (`commander`, `groups` / `group`, the collection key `name`,
  > `commander_kwargs()` / `group_kwargs()`), and so is `worker_kwargs` where the
  > phase list said `kwargs` — the grammar key is spelled like the constructor
  > parameter it feeds. The two gaps closed out of mandate are RATIFIED as written.
  > Deviation (2) is ratified as an absence: `USER_PENDING_MAX_ITEMS` is born in
  > Macro 4 with the code that fills the queues. The group's expiry ages are NOT
  > born (see the reconciliation above): a column with no reader waits for its
  > reader. After that removal: `pytest tests/ -q` 1928 passed / 2 skipped (no test
  > lost — the group's two keys were assertions inside tests that still stand),
  > `ruff check src/ tests/` clean, `mypy src/` 94.
  - Run: opus / medium
  - Pattern: `src/genro_asgi/config/elements.py:78` (`AsgiServerGrammar`,
    the `@element(parent_tags=..., sub_tags=...)` declarations and the
    `subbuilder` seam at line 266); `tests/orchestration/test_orchestration_m2_e2e.py`
    (the end-to-end style with real child processes);
    `docs/configuration.md` for the guide section.
  - Files: src/genro_asgi/config/elements.py,
    src/genro_asgi/config/default_config.py,
    src/genro_asgi/spa/orchestration/spa_commander.py,
    src/genro_asgi/spa/orchestration/group_handler.py,
    tests/orchestration/test_orchestration_m3_e2e.py (new),
    tests/test_config.py, docs/configuration.md
  - Decisions:
    (1) **The rule**: grammar carries the POLICIES of an installation
    (percentages, ages, paths); module constants carry the TECHNICAL times.
    Units in the name, always.
    (2) **Vertex grammar**: `memory_max_percent` (the server's concession on
    the machine; None = all of it, or the container limit) ·
    `machine_memory_alarm_percent` · `orchestration_log_path` (+ `_max_bytes` /
    `_backup_count`) · `user_expiry_hours` / `guest_expiry_hours`, which Phase 4
    put HERE and not on the group (a frozen row does not say which group he came
    from) — to be reconciled with F44.5, where the group judges the ACTIVE users by
    the same two keys, through the cascade the percentages already use.
    NO `frozen_users_disk_alarm_percent`: the storage left the quotas (see the
    Phase 4 record) and answers to `STORAGE_RESERVE_PERCENT`, a constant.
    (3) **Group grammar**: `memory_max_percent` (the group's quota, a
    percentage of the concession — homonymy cascading on purpose) ·
    `occupancy_max_percent` · `restart_occupancy_max_percent` ·
    `reception_reserved_percent` · `new_user_occupancy_percent` ·
    `user_idle_freeze_minutes` · `user_expiry_hours` · `guest_expiry_hours` ·
    plus the inherited identity of the child (`entry_module`, `executable`,
    `worker_class`, `kwargs`, `main_threadpool_size`, `aux_threadpool_size`).
    NO `target_workers`, NO `max_workers`.
    (4) **Constants**: `HEARTBEAT_SECONDS` · `QUIT_TIMEOUT_SECONDS` ·
    `USER_PENDING_MAX_ITEMS` · `STORAGE_RESERVE_PERCENT` · the four cadences in
    beats (`CHECK_OCCUPANCY_BEATS` in the group, the other three at the vertex) ·
    (existing: `PROCESS_PING_INTERVAL`, `PROCESS_PING_TIMEOUT`,
    `TRANSFER_START_DELAY`, `DEPOSIT_LOCK_WAIT_LIMIT`).
  - Details: the keys are wired into the existing config grammar (M1's
    builder), with the defaults chosen here and written down; the guide
    section follows the keys.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; a config
    file carrying every key above builds a server whose commander and groups
    read them; the M3 end-to-end with REAL child processes covers: the
    reception born at boot, growth on demand, a user frozen by idleness, his
    lazy wake on the next request, a wild death with its bonifica, a closure
    for wasted capacity, and one orchestration log line per order.
  - Verify: now — read `docs/configuration.md`'s new section and the
    orchestration log of the e2e run: do the rows say who decided what, on
    whom, with which numbers, and how it ended?
  - Verify: now — the `_TBD` round of this phase, and the grep that no
    `_TBD` survives.

## Notes

- **Volume is a defect** (owner's rule, 2026-08-17, standing): "150
  lines where 70 suffice" is an error of the same class as wrong code.
  Every phase carries a line cap; wrapper layers delegating 1:1,
  methods wrapping one dict-write, dead parameters and defensive code
  without a requester are findings at review. Method docstrings follow
  the ratified triplet (params, returns, acts-on-state — nothing else);
  narrative belongs to module docstrings.
- **The chain of identity** stays as M2 left it: cookie → cid →
  `connection_user_map` → `user_worker_map` → the worker. The front
  (`SpaApplication`) keeps ZERO state, and wiring it to the new commander is
  Macro 4 — this workflow drives the two upper levels with tests and
  drivers, never through a real HTTP request.
- **The freezer is outside the ladder**: 6 ↔ disk ↔ 2, never through the
  wire. Filesystem access goes ONLY through storage nodes, and storage is
  pinned synchronous (`StorageMixin` calls `set_sync()`; the tests pin the
  same) — never `await` a storage node call.
- **The notifications are out of Macro 3** (`pending_notifications`, the
  broadcast dictionary, `notify_user`): they are designed with the page
  protocol in Macro 4. One requirement noted for then: the reply to a ping
  may carry the broadcasts about to expire.
- **Still [TRAVASO] from v3 §16, and NOT in this workflow**: the mechanics of
  a group hijack (F20), the fate of `workers_occupancy_metric` and the
  evaluator as objects (the formula itself is transplanted in Phase 3), the
  three clocks in full, the auth of the Prometheus scrape.
- **The legacy machine is untouched.** No module under
  `spa/orchestration/` imports `spa/commander.py` or `spa/worker.py`, in
  either direction; shared values (`GUEST_PREFIX`, `PING_OP_PATH`) are
  redefined with their ratified value, as M1/M2 already do.
- **A failing contract test is a STOP**, never something to adapt: the
  tests under `tests/orchestration/` that assert M1/M2 behaviour are the
  continuity of two macros of work.
