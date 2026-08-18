# Context: wf/orchestration-m4-request-login
Parent: main
Mode: interactive

## Objective
Build the REQUEST CHAIN and the LOGIN on the new orchestration stack: the step
that walks cookie → cid → user → group → `WorkerHandler` and hands the `http`
CALL to the child, the wait of a user on hold, the polite refusals, the login
verb on `SpaWorker` with the connection freeze at the end of the request, the
uniform fold at the vertex, and a NEW mountable front that owns
`SpaCommander` and its groups.

The legacy machine — `spa/commander.py`, `spa/worker.py` AND the legacy front
`applications/spa_app.py` with its four contract files — stays UNTOUCHED: the
new front is born ALONGSIDE it and the two live side by side until the cutover
in Macro 6. The data plane (addressed datachanges/dbevents, subscriptions,
notifications, the pending mailboxes) is Macro 5.

Authority order on any doubt: `temp/design_m4_2026-08-18.md` (the decision
record of this macro, 🟢 APPROVATO — R1..R14) >
`temp/interview_handler_2026-08-15.md` (register F1–F47) >
`temp/design_orchestrazione_v4_2026-08-17.md` >
`temp/design_orchestrazione_v3_2026-08-16.md` (§8 freezer, §11 login, §12 boot,
§14–15) > this plan.

**This plan amends the roadmap on one point** (`.phased/roadmap.md`, Macro 4
line): the wiring of `SpaApplication` and the cutover from the legacy commander
are NOT in this macro. R1 ratified a new front alongside; the cutover is Macro 6.

**Naming rule** (unchanged from M3): a new public name whose baptism is not
settled is born with the `_TBD` suffix. At the END of each phase the executing
chat brings the owner ONLY the surviving `_TBD` names — one at a time, semantics
plus 2–3 candidates — and the rename is a search-and-replace in its own commit.
A name whose code turned out unnecessary dies with it and is never brought up.
No `_TBD` survives the end of the workflow.

**Names already baptised** (the executor invents none of them): everything M1–M3
baptised, plus, from the record of 2026-08-18: `default` (the attribute of the
`groups` collection that ELECTS the base group — R2).

**Expected `_TBD` at birth**, with their semantics:
1. the new front class — a mountable application owning the new vertex;
2. the login verb on `SpaWorker` — relabels the connection onto the logged
   identity and flags the end-of-request freeze;
3. the login worker event — what climbs on the REPLY so the vertex folds it;
4. the vertex mutator that records a user's group, decided at placement (R14);
5. the per-user barrier map and its wait (R9);
6. the vertex's lifecycle pair (start / stop) and its request surface (R13, and
   the open point 2 below).

**Excluded words** (from names AND prose): parcel, deposit, judgment, budget,
valvola, relaunch, seat/posto, and the names of the dead. Say instead: register
item, freezer, check, timeout, restart, congelamento per inattività.

**Two open points, decided at the walkthrough of their phase, not before**:
1. *The wait deadline and the shape of the refusal* (Phase 2). The owner's
   directive: the hold's wait is a CLOCK → a module constant, never grammar.
   Material verified for the proposal: the legacy sends
   `Retry-After = int(decision_interval)` (commander.py:2367-2368); the new
   stack's homologous clock is `HEARTBEAT_SECONDS = 5.0` (spa_commander.py:136)
   × `CHECK_OCCUPANCY_BEATS = 6` (group_handler.py:119) — the 30 seconds within
   which a group looks at its own shape again. The behaviour is already declared
   in the group's docstring (group_handler.py:88-92): residents served as ever,
   503 with `Retry-After` to newcomers and to the woken.
2. *The vertex's surface toward the front* (Phase 2): ONE method that walks the
   whole chain and returns the envelope, or TWO (resolution and delivery apart).
   The phase presents both with their semantics; the owner rules, the baptism
   follows at the end of the phase.

## Work Plan

- [x] **Phase 1**: The vertex takes its groups, the barrier and the lifecycle
  > Done: the vertex builds its own groups — `SpaCommander(..., groups={name:
  > kwargs})` instantiates one `GroupHandler` per entry and hands each
  > `memory_concession_bytes` from its own property, so the hand-off the M3 review
  > caught wrong cannot be forgotten; building a group by hand stays public and the
  > M3 tests keep using it. `default_group` answers which group receives whoever
  > arrives with no past — the elected name or the first declared, and a KeyError
  > when there is no group to receive anybody. The grammar grew ONE attribute,
  > `groups(default=...)`, folded into `commander_kwargs()` because the vertex is
  > what reads it. The waiting room got its door: `user_hold_event_map`, one Event
  > per user on hold, raised by `hold_user` and released by `mark_user_frozen`,
  > `mark_user_adopted` and `drop_user` — the same mutators, no other writer — and
  > `await_user_release(user, timeout)` is what a request parks on. `record_user_group`
  > is called by `GroupHandler.assign_user` in the same breath in which it writes
  > `user_worker_map`, so a refused placement writes no group anywhere. `start`
  > brings the base group's reception up and only then starts the clock (READY is
  > the reception having presented itself); `stop` stops the clock and takes every
  > group down dry, and each kill is DECLARED first through `expect_death` — a
  > shutdown is an order, and N "WILD death" alarms per clean stop would be a false
  > account in the one log that says what the machine chose to do.
  > Verified: `pytest tests/ -q` 1949 passed / 2 skipped (was 1934/2 — the 16 tests
  > this phase adds); `ruff check src/ tests/` clean; 49 executable lines added to
  > `src/` against the phase cap of 108; coverage spa_commander 98%, group_handler
  > 99%, elements 100%, and not one line of this phase uncovered (what is missing in
  > those modules is the pre-existing `/proc/meminfo` read and two branches of
  > `_grow`/`_order_quit`); no `_TBD` name survives the phase; the four contract
  > files of the legacy front pass untouched.
  > Behaviours covered by the new tests: a vertex built from a recipe owns its
  > groups with the concession already inside them; the elected base group, the
  > first-declared fallback and the vertex that can receive nobody; a group built
  > without the concession is a `TypeError`; a hold raised and released wakes its
  > waiter at once, from all three mutators, and a wait that outlives its deadline
  > raises while the hold stays up; a second hold keeps the first cause and the same
  > door; nobody waits on a user who is not held; the group written where the
  > placement decided it, and nothing written when nobody took him; start brings the
  > reception up and stop leaves no child alive AND no wild death.
  > Declared: `test_each_task_of_the_vertex_runs_on_its_own_count_of_beats`
  > (implementation test, rule 10) was rewritten on the round boundary — it used to
  > cancel the clock mid-round and assert a whole-round relation, and the code was
  > absolved (`every` counts `runs` before awaiting the body). Rationale and the
  > owner's ruling in notes.md.
  > Files: src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/group_handler.py,
  > src/genro_asgi/spa/orchestration/worker_handler.py,
  > src/genro_asgi/config/elements.py, src/genro_asgi/config/handler.py,
  > tests/orchestration/test_orchestration_spa_commander.py,
  > tests/orchestration/test_orchestration_group_handler.py,
  > tests/orchestration/test_orchestration_heartbeat.py, tests/test_config.py,
  > .phased/active/orchestration-m4-request-login/notes.md
  - Run: opus / medium
  - Pattern: `.phased/done/orchestration-m3-commander-groups/plan.md` Phase 2
    (the vertex as it stands) and Phase 4 (the heartbeat it already owns);
    `GroupHandler.__init__` (group_handler.py:153) for the constructor it
    receives; `handler.py:255-277` (`applications`) for a collection attribute
    read as `self("<collection>.default", default=None)`.
  - Files: src/genro_asgi/spa/orchestration/spa_commander.py,
    src/genro_asgi/spa/orchestration/group_handler.py,
    src/genro_asgi/config/elements.py,
    src/genro_asgi/config/handler.py,
    tests/orchestration/test_orchestration_spa_commander.py,
    tests/orchestration/test_orchestration_group_handler.py,
    tests/test_config.py
  - Decisions:
    (1) **The vertex instantiates its groups** (R10). `SpaCommander(...,
    groups={name: kwargs})` builds one `GroupHandler` per entry inside its own
    `__init__`, handing each `memory_concession_bytes` from its own property —
    the manual hand-off that the M3 review already caught wrong disappears by
    construction. The explicit path (building a group by hand, passing the
    concession) STAYS PUBLIC: the M3 tests keep using it and must keep passing.
    (2) **The base group** (R2). The grammar grows ONE attribute on the
    collection: `groups(default=None)`, elects the group that receives whoever
    arrives with no past. Absent, the base group is the FIRST declared —
    `group_kwargs()` already returns them in recipe order. The reader is one
    line on `ConfigurationHandler`; the vertex holds the elected name and
    resolves the fallback itself, so a vertex built by hand behaves like one
    built from a recipe.
    (3) **The per-user barrier** (R9). A map `user → asyncio.Event` on the
    vertex: `hold_user` raises it, `mark_user_frozen` / `mark_user_adopted`
    release it, and an entry is born with the hold and dies with the release —
    outside the window the structure is EMPTY. One owner per Event, never a
    shared hold. The wait itself (a coroutine with the caller's own deadline) is
    born here and used in Phase 2. No other writer: the alignment row↔barrier is
    held by the single mutators, not by a guard.
    (4) **The group of a user is written by the group** (R14). `assign_user`,
    in the same synchronous breath in which it writes `user_worker_map[user]`,
    calls a MUTATOR of the vertex that records the group. The group never
    touches the vertex's dict. Writing it before the decision is REJECTED: the
    refusal window would need a `finally`.
    (5) **Lifecycle** (R13). Start: the beat on, the base group's reception born
    (`GroupHandler.start_worker`), and "ready" is the reception having presented
    itself (v3 §12.3). Stop: DRY — `terminate_process` to every child, no mass
    freeze; the ordered quit stays for the live manoeuvres. The names are `_TBD`.
    (6) The M3 deferral that lands here: the test of the `TypeError` on
    `GroupHandler`'s constructor without the concession, IN ITS NEW SHAPE — the
    vertex is what passes it now, so the test pins the explicit path.
  - Details: no request is served in this phase; the vertex is driven by tests
    and by the M3 drivers. Nothing in `spa/orchestration/` imports the legacy,
    in either direction.
    LINE CAP: +90 executable lines on `spa_commander.py` (which stands at ~615
    total), +10 on `group_handler.py`, +8 on the config pair. The barrier is a
    dict, an Event and a wait — a class for it would be a finding.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; tests
    covering: a vertex built from a recipe owns its groups with the concession
    already inside them; the elected base group and the first-declared fallback;
    a hold raised and released wakes the waiter at once, and a wait that expires
    raises; the group recorded at placement and not before (a refused
    `assign_user` leaves no group written); start brings the reception up and
    stop leaves no child alive.
  - Verify: now — the `_TBD` round of this phase.

- [x] **Phase 2**: The request chain at the vertex
  > Done: `SpaCommander.serve_request(cid, http, *, hold_timeout)` is the ONE
  > surface the front speaks to. It walks the whole chain — the cid becomes an
  > identity, the identity names his group (his own row, or `default_group`), the
  > group names the worker or places him NOW, and the request goes down as
  > `{"http": {..., "cid"}, "identity", "user_frozen"}` under the `/site` prefix.
  > The waiting is here and travels nowhere: `UserOnHold` is caught, waited out on
  > the barrier of Phase 1 against a budget computed ONCE (each round gets what is
  > left of it), and the walk starts over at the top, the map being the authority
  > at every step. The refusals leave as classes: `AssignmentRefused` carrying
  > `retry_after` — composed here and derived, `SHAPE_REVIEW_SECONDS` =
  > `HEARTBEAT_SECONDS` x `CHECK_OCCUPANCY_BEATS`, so the promise made to a browser
  > stays true the day the beat changes — `SiteFailedRequest` when the child
  > answered with a failure (the placement is sound and the wire is up: what broke
  > is the hosted site), and `ConnectionError` untouched when the wire is gone.
  > Every refusal counts itself in `counters["requests_refused"]`.
  > Ratified at the walkthrough (9 answers, temp/domande_fase2_m4_2026-08-18.md):
  > the single surface (the front never names a `WorkerHandler` or a wire); the
  > failure raises instead of being returned; NO deadline on the CALL in this macro
  > — declared absence, a child running a long query is not mute and the patience
  > belongs to the browser and its proxies; the hold budget is TOTAL; the
  > `Retry-After` derived and composed by the vertex inside the refusal; a counter
  > and not a log row per refusal; a woken user keeps the group he was frozen on
  > (his parcel was written by THAT group's code); the `/site` prefix so a site page
  > called `/op/something` cannot look like a contract op; a worker already dead but
  > still in the map falls through to a 502 rather than being re-placed, the round
  > that buries it being already rung by `on_child_lost`.
  > Verified: `pytest tests/ -q` 1960 passed / 2 skipped (was 1949/2 — the 11 tests
  > of the new file); `ruff check src/ tests/` clean; 74 executable lines added to
  > `src/` against the phase cap of 70 — the four over are the `SiteFailedRequest`
  > class, which the walkthrough created and the cap predates; coverage
  > spa_commander 99%, exceptions 100%, with no line of this phase uncovered.
  > NEUTRALIZATION PROBE run on the finest point: replacing the remaining budget
  > with a fixed per-wait timeout makes
  > `test_the_budget_is_the_whole_wait_and_not_one_of_them` FAIL — the total budget
  > is proved and not merely asserted. (Its first draft was vacuous: the keeper let
  > go three times and then left the hold up, so both readings refused. It now lets
  > go for a whole second and the clock is what tells them apart.)
  > Behaviours covered: a newcomer minted, placed on the base group and served,
  > with the exact payload on the wire; a resident routed to his own worker while
  > the fullest-first walk would have chosen another; the freezer verdict travelling
  > with the request; a woken user landing in his own group and not in the elected
  > one; the pool that takes nobody refusing with `retry_after` and counting it; a
  > held user's request leaving the instant the hold falls; a hold that outlives the
  > budget becoming a refusal; the site's own failure raising a class of its own and
  > counting as no refusal; a dead wire falling through; two simultaneous requests
  > of the same unknown landing on ONE worker.
  > Files: src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/exceptions.py,
  > src/genro_asgi/spa/orchestration/__init__.py,
  > tests/orchestration/test_orchestration_request_chain.py
  - Run: opus / medium
  - Pattern: the legacy front face — `UserStickyCommander.forward_envelope`
    (commander.py:2245) for WHAT a forward does, never for how it is built;
    `SpaWorker._serve_request` (spa_worker.py:1240) for the payload shape the
    child already reads: `{"http", "identity", "user_frozen"}`.
  - Files: src/genro_asgi/spa/orchestration/spa_commander.py,
    src/genro_asgi/spa/orchestration/group_handler.py,
    tests/orchestration/test_orchestration_placement.py,
    tests/orchestration/test_orchestration_spa_commander.py
  - Decisions:
    (1) **The canonical chain** (D3/D5, unchanged): cid → `resolve_user` → the
    user's group (his row, or the base group when he has none) → the group's
    `user_worker_map`, or `assign_user` deciding NOW → the `WorkerHandler` →
    `WorkerConnector.call`. The front walks none of it: the vertex is asked once.
    (2) **The payload** is built here: the `http` form the front packed, the
    `identity` the chain routed on, and the `user_frozen` verdict read off
    `user_is_frozen`. The child needs nothing else — `adopt_user` /
    `adopt_connection` do the rest by themselves (D4).
    (3) **The three refusals travel as types**, and each has ONE translation:
    `UserOnHold` → wait on the barrier of Phase 1 with the module deadline, then
    re-enter the chain from `resolve_user` (the map is the authority at every
    step); `AssignmentRefused` (with `NoRoomError` / `WorkerQuittingError`) and
    an expired wait → the polite 503; `ConnectionError` from the wire → the
    gateway's 502. The vertex RAISES; the numbers are the front's (Phase 4).
    (4) **OPEN POINT — the surface**: one method walking the whole chain and
    returning the envelope, or two (resolve, then deliver). The executor brings
    both forms with their semantics; the owner rules at the walkthrough.
    (5) The REPLY needs no folding here: `WorkerConnector._dispatch`
    (worker_connector.py:276) already hands the envelope to the chain BEFORE
    resolving the caller's future — the announcements of a request are folded
    with that request still in flight.
  - Details: EAFP throughout — the walk is a `try`, the reason a worker said no
    is its class. No new state at the vertex.
    LINE CAP: +70 executable lines. A wrapper delegating 1:1 to the group is a
    finding; so is a method that only re-reads a dict.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; tests
    covering: a newcomer minted, placed on the base group and served; a resident
    routed to his own worker with no new placement; a frozen user routed with
    `user_frozen=True` in the payload; each of the three refusals raised and
    typed; a held user's request released the instant the hold falls, and
    refused when the deadline expires first; two simultaneous requests of the
    same unknown user land on ONE worker (the single mutator).
  - Verify: now — the `_TBD` round of this phase.

- [x] **Phase 3**: The login — the worker's verb and the vertex's fold
  > Done: `SpaWorker.relabel_connection(cid, user, **fields)` is what the hosted
  > site calls in-process. It relabels the connection AT ONCE — the caller reads
  > the row back in the same breath and must see the new identity — brings the
  > user into being here if he was unknown, raises the flag the tail of the call
  > reads (`_login_previous_user_map`, cid → who it belonged to), drops any
  > departure the guest had been promised (a guest ceasing to exist is not carried
  > to the deposit) and announces `connection_relabeled`. The pages are not
  > touched: their owner is derived through the connection. A target carrying
  > `GUEST_PREFIX` raises, because the value crosses a border of trust to get here.
  > `SpaWorker.freeze_connection(cid)` is the tail, in the very place where
  > `close_request` and the deferred departure already live: it claims the
  > departure of the previous identity through the ONE claim the other three roads
  > use, writes ONE parcel under the new identity — the connection, its pages, and
  > the guest's store when the previous identity was a guest — and takes the rows
  > out: the connection, its pages, the guest, and the new identity too when this
  > connection was all he had here, so his own next request finds a row just born
  > and installs the carried store instead of discarding it. A refused write
  > leaves EVERYTHING alive and announces nothing: he stays resident here with his
  > connection attached, which is the legitimate degraded shape, and the failure is
  > counted in `freeze_failures`.
  > At the destination `adopt_connection` installs the carried store only onto a
  > row born a moment ago (`_install_carried_store`): a resident's own state wins
  > and what the guest accumulated dies OUT LOUD. The chain folds the announcement
  > at all three rungs: the handler swaps who it holds, the group forgets the
  > guest's placement, and `SpaCommander.relabel_connection` writes the three
  > ratified things — the cid points at its new owner, his row is born if missing,
  > the guest goes. Nothing is placed and the freezer is never opened.
  > Verified: `pytest tests/ -q` 1977 passed / 2 skipped (was 1960/2 — the 17 tests
  > of the new file); `ruff check src/ tests/` clean; 113 executable lines added
  > against the phase cap of 135.
  > TWO DEFECTS FOUND WHILE WRITING, both fixed with their test: the first draft of
  > `_release_login_rows` unmounted the previous identity ALWAYS, which deleted a
  > real resident on an avatar switch (caught by its own test, `KeyError: 'mario'`)
  > — R8 to the letter: only a guest is unmounted, a person keeps his row and the
  > idleness sweep parks it; and the announcement bypassed `hosted_users`, so a
  > process dying between a login and the tail of its call would have reported the
  > loss of a guest the surface had already forgotten and not of the person who
  > exists — the bottom rung of the chain now swaps them.
  > Ratified during the phase: `connection_relabeled` belongs in
  > `POPULATION_WORKER_EVENTS`. The population is a list of NAMES, not a count:
  > the login changes which names are on board even though the count does not move,
  > and every reader of the photo hangs on the names.
  > NEUTRALIZATION PROBE on that rule: taking the op out of the set must make
  > `test_a_login_makes_the_photo_due` fail. The FIRST draft of that test passed
  > under neutralization — `_snapshot_due` is an OR with the staleness leg, and a
  > fresh worker carries `_snapshot_sent_ts = 0.0`, so it was true anyway. Rewritten
  > from a photo just sent, asserting first that none is due; it now falls when
  > neutralized.
  > Behaviours covered: the relabel readable in the same breath, with the pages
  > following and the new row born empty; a guest target refused; an unknown
  > connection loud; the guest's promised departure dropped; the announcement's
  > exact shape; nothing leaving before the call is over; the tail carrying the
  > connection, its pages and the guest's store, and leaving nothing behind; an
  > avatar switch carrying no store and leaving the person his own; a refused
  > deposit leaving everything alive and announcing nothing; the carried store
  > becoming his own on a row just born and dying against a resident; THE RATIFIED
  > INVARIANT (the user parcel installed before the connection one, which is what
  > makes a wake win over a login's leftovers); the fold repointing the cookie and
  > forgetting the guest while keeping a real previous identity; the handler
  > swapping who it holds.
  > Files: src/genro_asgi/spa/orchestration/spa_worker.py,
  > src/genro_asgi/spa/orchestration/spa_commander.py,
  > src/genro_asgi/spa/orchestration/envelope_handler.py,
  > tests/orchestration/test_orchestration_login.py
  - Run: opus / medium
  - Pattern: `spa/worker.py:1936` + `register_registry.py:340-413` for WHAT the
    legacy relabel does (read it, do not transcribe it: the new registers are
    plain rows); `SpaWorker.freeze_user` (spa_worker.py:955) for the freeze
    discipline; `_connection_parcel` (:1471) for the shape that already exists;
    `temp/design_m4_2026-08-18.md` §3 for the whole travaso.
  - Files: src/genro_asgi/spa/orchestration/spa_worker.py,
    src/genro_asgi/spa/orchestration/envelope_handler.py,
    src/genro_asgi/spa/orchestration/spa_commander.py,
    tests/orchestration/test_orchestration_spa_worker.py,
    tests/orchestration/test_orchestration_envelope_chain.py
  - Decisions:
    (1) **The verb relabels AT ONCE** (R6). The connection row moves onto the
    logged identity, whose user row is born empty; the guest's row is left with
    no connections. The caller of record reads the row back in the same breath
    (genropy-asgi `siteregister_client.py:373-374`) and must see the new
    identity; pages born after the login belong to it, since `_stamp_request`
    reads `connection["user"]` every time.
    (2) **The freeze happens at the END of the request** (R4), in the tail of
    `_serve_request` where `close_request` and the deferred departure already
    live. Freezing at the instant of the call would contradict the freeze's own
    precondition: the in-flight WSGI call IS a pending.
    (3) **What the flag carries**: the previous identity, and the ONE local fact
    that decides the rest — whether it was a guest.
    (4) **The store travels inside the connection parcel** (R5), and ONLY if the
    previous identity was a guest (R8). With a real previous identity the parcel
    is connection+pages alone and his store stays his. At the destination
    `adopt_connection` installs the carried store only onto a row just born and
    empty — the resident wins where the resident IS.
    (5) **A connection freeze is born**: today `freeze_user` writes the store
    plus every connection parcel and unmounts the user whole. The new one writes
    ONE connection under the new identity and releases the rows the login left
    behind. It reuses `write_connection_register_item` (cause=`login`) — the
    freezer's shape does not change.
    (6) **The fold is UNIFORM** (R7): `connection_user_map[cid] = user`, the row
    in `user_map` if missing, and the unmounting of the guest — the last one
    ONLY when the previous identity was a guest (R8). No branch on the three
    shapes: they resolve at the destination, by the rule of (4).
    (7) The pages are not touched by the fold: the cid does not change at login,
    so `page_connection_map` keeps saying what it said.
  - Details: the login never crosses the wire — the hosted site calls the worker
    in-process through `site.spa_worker`. The op set of `answer_call` does NOT
    grow.
    LINE CAP: +110 executable lines on `spa_worker.py`, +25 on the fold.
    CONTRACT TEST (the owner's invariant, binding): at installation the USER
    parcel comes before the connection parcel — that order is what makes the
    resident win in the FROZEN case. The code already does it
    (`_resolve_row`, spa_worker.py:1264); the test nails it so a reordering is
    a STOP and not a surprise.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; tests
    covering: the relabel readable in the same breath; the freeze deferred to
    the end of the request (a login mid-request finds its rows to the end); the
    guest's store carried and installed on a fresh row; the same store DISCARDED
    when the row is already there (both because it was adopted first and because
    the user was resident); the avatar switch carrying connection+pages and NO
    store; the guest unmounted at the fold, the real previous identity kept.
  - Verify: now — the `_TBD` round of this phase.

- [ ] **Phase 4**: The new front
  - Run: opus / medium
  - Pattern: `applications/spa_app.py` — the demux (`internal_roots`,
    `resolves_natively`), the cookie read ONCE, `pack_http`, the response
    translation. It is READ and transcribed, never imported and never touched:
    the two fronts share no code until Macro 6 (the M1–M3 isolation rule).
  - Files: src/genro_asgi/applications/<new front>_TBD.py,
    src/genro_asgi/applications/__init__.py,
    tests/test_<new front>_TBD.py (contract tests of the new front),
    tests/test_config.py
  - Decisions:
    (1) **A class of its own, alongside** (R1). `SpaApplication` and its four
    contract files are NOT touched: they are the continuity sentinel of the
    machine that serves real traffic until the cutover.
    (2) **It reads its own configuration back from the handler** (R11):
    `commander_kwargs()` and `group_kwargs()` plus the elected base group, as
    every application re-reads its own section.
    (3) **ONE SPA front per server** (R12, the new rule): a second front reading
    the same `commander` section is a CONFIG ERROR, refused loudly at boot. The
    vertex is one per server, `frozen_users_path` is one root for the whole
    machine, and the memory cascade is anchored to ONE `MemTotal`. Several sites
    on one server are several GROUPS under the one vertex.
    (4) **The lifecycle is the application's**: `on_startup` starts the vertex,
    `on_shutdown` stops it; the front serves only from "ready" (R13).
    (5) **The translations** (the numbers of Phase 2's point 3): the polite 503
    with `Retry-After` for a refused placement and for an expired wait, the 502
    for a wire that failed, the `sticky_cid` cookie minted here and stamped on
    whatever exit built the response.
  - Details: the front keeps ZERO state — the identity it routes on is read off
    the vertex's own surface, and the fold is the single writer.
    LINE CAP: ~300 executable lines, the legacy front being 318 total. A line
    beyond what the legacy front does needs a reason in the phase record.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; the four
    legacy contract files pass UNCHANGED (a failure there is a STOP); new
    contract tests covering: the two-stage demux, the cookie minted and
    re-issued, a site path forwarded and its response translated, the 503 with
    `Retry-After`, the 502, and the second mounted front refused at boot.
  - Verify: now — the `_TBD` round of this phase, the new front's class name
    among them.

- [ ] **Phase 5**: The whole day, end to end
  - Run: opus / medium
  - Pattern: `tests/orchestration/test_orchestration_m3_e2e.py` (the day of the
    pool, built from nothing but a config FILE) — the same shape, one rung up:
    this one goes in through the front, over HTTP.
  - Files: tests/orchestration/test_orchestration_m4_e2e.py,
    tests/orchestration/fixtures (the recipe with two groups and `default`),
    .phased/active/orchestration-m4-request-login/notes.md
  - Decisions:
    (1) The story, in one test, with a REAL child and a REAL WSGI site: an
    anonymous visitor arrives with no cookie and is served (his store grows);
    he logs in; his next click finds his store where the login left it; a second
    browser of the same user joins him on the same worker; a user whose state is
    in the freezer wakes on his own next request; an avatar switch keeps the two
    stores apart.
    (2) The recipe declares TWO groups and elects the base one, so the grammar
    of R2 is proved by a file and not by a kwarg.
    (3) The refusals are proved through the front: a pool with no room answers
    503 with `Retry-After` to a newcomer while a resident keeps being served.
  - Details: no stub of the vertex, no stub of the group — the e2e is the one
    place where every rung is the real one.
    The scaffolding rule of the Notes applies here like everywhere else.
    LINE CAP: none on tests, but a scenario that duplicates a phase test without
    adding a seam is a finding.
  - Done: `pytest tests/ -q` green; `ruff check src/ tests/` clean; the e2e
    passes with real processes; no `_TBD` survives anywhere in `src/` or
    `tests/`.
  - Verify: now — the last `_TBD` round.
  - Verify: manual, with the owner — a real installation started through
    `genroasgi serve` on the new front, a browser served, the login of a real
    site, and the orchestration log read out loud.

## Notes

- **The volume is a defect of the same class as wrong code** (the owner's rule):
  "150 lines where 70 suffice" is judged at review like correctness. Every phase
  carries a line cap; wrapper layers delegating 1:1, methods wrapping one
  dict-write, dead parameters and defensive code without a requester are
  findings. Method docstrings follow the ratified triplet (params, returns,
  acts-on-state — nothing else); narrative belongs to module docstrings.
- **The scaffolding is already there**: every test written in this macro takes
  `short_root`, `repo_on_pythonpath` and `wait_for` from
  `tests/orchestration/conftest.py` (60 lines) and rolls NONE of its own. The M3
  volume review found 114 lines of duplicated scaffolding across the test files,
  and that conftest exists exactly to end it: a re-rolled temporary root, a
  re-rolled PYTHONPATH monkeypatch or a hand-written polling loop is a finding at
  review — in Phase 1 as much as in Phase 5.
- **Two kinds of tests** (rule 10): contract tests under `tests/`,
  implementation tests under `tests/orchestration/`. Every new test is
  classified at birth. A failing contract test is a STOP, never something to
  adapt — the four legacy front files above all.
- **The legacy is untouched**: `spa/commander.py`, `spa/worker.py` AND
  `applications/spa_app.py`. No module under `spa/orchestration/` or the new
  front imports them, in either direction; shared values are redefined with
  their ratified value, as M1–M3 already do.
- **The freezer stays outside the ladder**: 6 ↔ disk ↔ 2, never through the
  wire. Filesystem access goes ONLY through storage nodes, and storage is pinned
  synchronous (`StorageMixin` calls `set_sync()`; the tests pin the same) —
  never `await` a storage node call.
- **Out of this macro, declared**: the data plane (addressed delivery,
  subscriptions, the pending mailboxes, `USER_PENDING_MAX_ITEMS`), the
  notifications, the live move and the plan's ladder, `recycle_worker`,
  `hard_restart`, `dump`/`restore` with the soft boot liturgy, the pool monitor,
  the in-process worker, `broken` on `SpaCommander.state`, the per-user
  differentiation of the estimate, `relaunch()`, and the group-level
  `user_expiry_hours` / `guest_expiry_hours` for ACTIVE users.
- **Cross-repo, blocking for real traffic but not for this macro**: the
  `sticky_cid` seam through genropy-asgi (memory `bridge-identity-seam`).
- **Operational rules of this workflow**: a worktree needs
  `PYTHONPATH=<worktree>/src` for pytest (the editable install points at the
  main checkout); every long-running agent keeps a progress journal on file;
  `git restore` never runs over uncommitted fixes.
- **End of macro**: whole-diff review with four agents (correctness, volume,
  vacuous tests, fidelity to the record), neutralization probes for the seams
  each finding claims, and the ratified fixes interviewed one at a time before
  the squash.
