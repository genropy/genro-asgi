# Context: wf/41-freeze-order
Parent: develop
Mode: interactive

## Objective

Make putting a user to sleep **one atomic operation in a deterministic order**
(owner, 2026-08-26): the group blocks him, the group orders the freeze, the
worker waits for HIS calls to end, freezes, and confirms. The worker keeps no
policy and takes no departure decision of its own.

Closes #41; #40 is its symptom (a page born between the photograph and the
release is lost, and every RPC on it answers 400 until reload).

Authority: `temp/interview_handler_2026-08-15.md` (D4 the freezer is the only
transfer channel, D9, F7, C3 governed vs wild death, the `on_hold` gate as an
`except`) > `temp/design_orchestrazione_v4_2026-08-17.md` > this plan.

## What the code does today, verified on develop (66a4cd1)

**Nobody blocks.** `freeze_user` photographs and then asks THREE times whether
anything changed — before the folder semaphore, under it, and once the write is
over — and when something did, it takes the parcels back off the deposit
(`_drop_parcels`) and gives up. Optimistic concurrency with a repair, where the
agreed flow is a block.

**The guard is the wrong one.** `_claim_departure`/`_departing_users` stops a
SECOND departure of the same user; nothing stops new work for him. `_pendings`
counts calls, and a call enters it only when it carries an identity
(`_serve_request`: `if user is not None: self.open_request(user)`). A page born
through `new_page` is not covered — reproduced: `D after thaw: ['p-old']`, the
page born during the freeze is gone.

**There is no departure channel in either direction.** parent→child carries
`ping`, `eval`, `census`, `observe`, `quit`, `drop_user`, `drop_connection`;
child→parent carries only the delivery desk's ops.

**The single-user freeze has NO production trigger at all.** `plan_transfers`
and `execute_transfers` are called from exactly one place — `quit`. The idle
valve is therefore inert: `user_idle_freeze_minutes` is read and the T/X flags
are computed, but nothing fires them outside a quit. Compaction does not cede
users either: it closes the whole worker (`restart_worker` → `quit_process`).
The m2 e2e drives the two verbs with test-only orders, and says so.

So this workflow does not MOVE a policy from the worker to the group: it builds
the ordered operation, and gives the group the trigger it never had.

**And the wire that falls writes what nobody will read.** `on_wire_lost` →
`freeze_all_users` saves the parcels of a process nobody can vouch for; on a
wild death the vertex then drops those very parcels through `drop_user` →
`drop_user_folder`, counted in `frozen_users_discarded`. The commander's own
docstring says what a dead process left is not to be trusted. Owner, 2026-08-26:
a process that lost its wire is unhealthy — it saves nothing.

## The decisions this plan stands on

**D-a. One sequence, one direction** (owner, 2026-08-26): the group blocks the
user → the group orders the worker to freeze him → the worker waits for THAT
user's calls, photographs, confirms → the block falls. Requests that arrived
meanwhile parked on the vertex's existing `on_hold` barrier, walk again, find
him frozen and take the lazy wake at the destination.

**D-b. The worker keeps no policy.** Idleness and expiry are judged by the
group, from the three clocks the photo already carries per user. No new gauge.

**D-c. No child→parent permission.** The judgment is always the group's, so
there is nothing to ask: one op parent→child is the whole surface.

**D-d. A wild death saves nothing** (owner, 2026-08-26).

**D-e. The block makes the repairs unnecessary.** With nothing able to change
under the photograph, the three checks and `_drop_parcels` go.

## Naming rule

A new public name whose baptism is not settled is born with the `_TBD` suffix
and is brought to the owner at the END of its phase — semantics plus 2-3
candidates. No `_TBD` survives the workflow. Expected at birth: the freeze op's
path constant and the worker verb it routes to; the group's method that runs the
whole sequence for one user; the group's periodic judgment.

## Work Plan

- [x] **Phase 1**: The freeze order, and a worker that only executes
  > Done: `FREEZE_USER_OP_PATH` (`"/op/freeze_user"`) beside `/op/drop_user`;
    `SpaWorker.freeze_designated_user` executes the order — waits on the pull
    (`_unfreeze_waits`) and on a per-user drain event set by `close_request`,
    claims the departure, parks through `freeze_user` and answers only then,
    `user_frozen` riding the same REPLY; a user not hosted is a loud KeyError
    in the REPLY. Names baptised by the owner (no `_TBD` left).
  > Files: src/genro_asgi/spa/orchestration/worker_handler.py, src/genro_asgi/spa/orchestration/spa_worker.py, tests/orchestration/test_orchestration_spa_worker_departures.py, tests/orchestration/test_orchestration_spa_worker_process.py
  > Review: full-suite runs under machine load twice showed flakiness in
    real-child tests outside this phase's files (envelope_chain,
    foundations_e2e, group_handler) — green in isolation and on the unloaded
    third run (1532 passed); pre-existing timing sensitivity, recorded in
    notes.md, not absorbed.
  - Run: opus / medium
  - Cap: 90 executable lines in `src/`.
  - Files: spa_worker.py, worker_handler.py, tests/orchestration/
  - One op parent→child, beside `/op/drop_user`: freeze THIS user. The worker
    waits for that user's pendings to drain, photographs, writes, answers the
    REPLY with the outcome, and announces `user_frozen` as it does today — the
    fold at the vertex is unchanged.
  - `_TBD`: the op path constant and the verb it routes to.
  - Done: ordered, a user with no call in flight is parked and the REPLY says
    so; a user with a call in flight is parked when that call ends, and the
    order does not return before; a user this worker does not host is a loud,
    explicit refusal in the REPLY.

- [x] **Phase 2**: The block before the order, and the repairs removed
  > Done: `GroupHandler.freeze_hosted_user` runs the whole sequence for one
    user — his worker read off `user_worker_map`, `hold_user` at the vertex
    (cause `freeze on <worker>`), the Phase 1 order, and on the confirmation
    nothing left to write: the `user_frozen` worker event rides that same REPLY
    and the fold reads an envelope before the caller is answered, so the mark,
    the barrier, the placement and `hosted_users` already say what they must.
    A refusal — wire gone or `error` in the REPLY — releases the hold through
    the new `SpaCommander.release_user_hold` (the mutator that says "he stayed
    where he was"), writes one `log_order` row and returns False.
    `SpaWorker.freeze_user` now judges the row ONCE, at the door: the check
    under the folder semaphore, the check after the write, `_drop_parcels` and
    `_get_freezable_item` are gone with their narrative in both docstrings.
    Names baptised by the owner (no `_TBD` left).
  > Files: src/genro_asgi/spa/orchestration/group_handler.py, src/genro_asgi/spa/orchestration/spa_commander.py, src/genro_asgi/spa/orchestration/spa_worker.py, tests/orchestration/test_orchestration_group_handler.py, tests/orchestration/test_orchestration_spa_worker_departures.py
  > Verified: 1532 passed on the full suite, ruff clean; the #40 probe asserts
    that nothing of the user's goes down the wire between the order and the
    confirmation, and five tests photographing the removed repairs were retired
    or rewritten (listed in notes.md).
  > Verify: deferred: needs Phase 3 — with a real site behind the front, leave
    a user silent past `user_idle_freeze_minutes` and click again: he is parked
    while silent and wakes at the destination with no 400 and no re-login.
  - Run: opus / medium
  - Cap: 80 executable lines in `src/` (expect a NEGATIVE net: the three checks
    and `_drop_parcels` go).
  - Files: group_handler.py, spa_commander.py, spa_worker.py, tests/
  - The group's method for one user: raise the hold (`hold_user`, cause named),
    send the order of Phase 1, await the confirmation, mark him frozen, release.
    A failure releases the hold too — a user must never stay blocked on a
    departure that did not happen.
  - With the block in place, `freeze_user` stops re-checking and stops rolling
    parcels back. `_departing_users` stays: it still answers "one departure at a
    time".
  - `_TBD`: the group's method name.
  - Done: a request for a user under the order parks on the barrier and is
    served at the destination after the confirmation — never a 400; a page
    cannot be born on the source worker between the photograph and the release
    (the #40 probe, as a test); a freeze that fails leaves the user unblocked
    and where he was; `_drop_parcels` and the two extra checks are gone.

- [x] **Phase 3**: The judgment moves to the group, with the trigger it lacked
  > Done: `GroupHandler.check_user_activity` is the group's second periodic
    (`@every(CHECK_USER_ACTIVITY_BEATS)`, 12 beats, called by `ping` after
    `check_occupancy`): it reads the two REAL clocks of every active user off his
    worker's last photo and takes ONE of two decisions per user — silence past
    `user_idle_freeze_minutes` goes to `freeze_hosted_user`, silence past
    `SpaCommander.get_user_expiry_seconds` (new, and `_expired_users` now uses it
    too, so one horizon per identity serves both the frozen and the active) goes
    to `DROP_USER_OP_PATH`, an op already routed in the worker that until now had
    no sender. Only a user `user_worker_map` still places on that worker is
    judged. `user_idle_freeze_minutes` is a GROUP setting now — the recipe surface
    did not move, the grammar already declared it on `group` — and the worker
    keeps no gauge: `plan_transfers` lost its T/X policy, `expiry_delay` and the
    dead `'X'` road are gone from `plan_transfers`, `quit`,
    `_flag_everybody_for_departure`, `_answer_then_quit` and `_execute_transfer`,
    with `SECONDS_PER_MINUTE`, `_last_real_activity` and `import math`. Net
    NEGATIVE in `src/`. Name baptised by the owner (no `_TBD` left).
  > Files: src/genro_asgi/spa/orchestration/group_handler.py, src/genro_asgi/spa/orchestration/spa_commander.py, src/genro_asgi/spa/orchestration/spa_worker.py, src/genro_asgi/config/handler.py, src/genro_asgi/applications/spa_app.py, CLAUDE.md, tests/orchestration/test_orchestration_group_handler.py, tests/orchestration/test_orchestration_spa_worker_departures.py, tests/orchestration/test_orchestration_m2_e2e.py, tests/orchestration/test_orchestration_m3_e2e.py, tests/orchestration/test_orchestration_m4_e2e.py, tests/orchestration/x_spa_worker.py, tests/test_config.py
  > Verified: 1526 passed on the full suite, ruff clean, mypy (advisory) with no
    new finding on the touched files. m3 and m4 now drive the freeze through the
    group's own round instead of the test-only orders, which were removed from
    `x_spa_worker.py` for want of readers; nine tests photographing the worker's
    departed policy were retired and their two judgments re-asserted at the group.
  - Run: opus / medium
  - Cap: 90 executable lines in `src/`.
  - Files: group_handler.py, spa_worker.py, config (the setting's home), tests/
  - The group reads the photo's clocks and decides who sleeps for idleness and
    who is expired, on its own beat (`@every`, cadence declared with the others).
    `user_idle_freeze_minutes` stops being a worker setting; `plan_transfers`
    loses its T/X policy.
  - `_TBD`: the periodic method's name.
  - Done: a user silent past the setting is ordered to sleep by the group and
    the worker never decides it; an expired one is dropped, not parked; a worker
    built alone (no group) freezes nobody by itself.

- [x] **Phase 4**: The quit reuses the same sequence
  > Done: `GroupHandler.quit_all` raises `hold_user` on every user the group
    places on a worker (cause `quit of <worker>`) BEFORE ordering that worker
    away, and skips a worker already in `DEAD_STATES` — its death is folded, so
    nobody would be left to release a hold raised on it. It is the SAME barrier
    the photo's `transfer_flag` rows raise at the vertex, moved ahead of the
    order, which is the window the photo cannot close: the photo rides the
    answer. The order stays ONE per worker — no per-user order travels the wire
    here — and the holds fall as the freezes confirm, through the fold that
    reads `user_frozen` and, for whoever's announcement did not survive the
    closing wire, through the death of the process. `plan_transfers`,
    `execute_transfers`, `PENDING_CALL_GRACE_SECONDS`, `_cut_stragglers` and
    `SpaWorker.quit` are untouched. Shape (a), decided by the foreman on a
    `clarify?` and applied to this plan verbatim (4579913). +5 executable lines
    in `src/` against a cap of 60; no new public name, so no `_TBD` was born.
  > Files: src/genro_asgi/spa/orchestration/group_handler.py, tests/orchestration/test_orchestration_group_handler.py, CLAUDE.md, .phased/active/freeze-order/notes.md, .phased/active/freeze-order/verify.md
  > Verified: 1529 passed on the full suite (1526 before, plus the three new
    tests), ruff clean, mypy advisory with no new finding. The wf/33 contract
    tests pass untouched: `test_the_group_orders_every_worker_into_the_reboot_directory`,
    the reboot round trip in `test_orchestration_spa_commander.py`,
    `test_a_straggler_is_cut_past_the_grace_and_parked_without_his_call`,
    `test_the_quit_writes_its_parcels_where_it_is_told`.
  > Review: the third `Done:` clause is met by composition, not by a test of its
    own: that a user CUT past the grace is parked is asserted at the worker rung
    (no vertex there), and that his hold then falls is the one road asserted at
    the group rung — the cut ends in `freeze_user`, whose `user_frozen` the fold
    turns into the release. No dedicated test spans both rungs for the cut user.
  > Verify: deferred: needs a real site behind the front — restart under
    `serve --reload` while a user is clicking and watch the click that lands
    during the quit wait and be served after the reboot, with no 400 and no
    re-login (also in verify.md).
  - Run: opus / medium
  - Cap: 60 executable lines in `src/`.
  - Files: group_handler.py, spa_worker.py, tests/
  - `quit_all` becomes: raise `hold_user` on every hosted user (through the
    vertex, as `freeze_hosted_user` does), send the ONE quit order, then let
    the process go. No per-user order travels the wire: the worker's mass
    cycle parks everybody as wf/33 built it, and each `user_frozen` releases
    its hold through the fold. `PENDING_CALL_GRACE_SECONDS` and the cut stay
    exactly as wf/33 built them — the cut is what unblocks a stuck user: it
    parks him anyway, releases his hold, and wakes any per-user drain wait
    left pending (Phase 1 note on `_cut_stragglers`).
  - Done: a soft quit raises a hold on every hosted user and every hold is
    released as the freezes confirm; the reboot round trip still holds (the
    wf/33 contract tests pass untouched); a user cut past the grace is parked
    AND unblocked.

- [x] **Phase 5**: A wild death saves nothing
  > Done: `SpaWorker.on_wire_lost` no longer parks anybody: it logs that the
    wire is gone and calls `exit_process`. `freeze_all_users` went with it —
    that call was its only reader in `src/` (the quit parks through
    `plan_transfers`/`execute_transfers`, never through it), so the method was
    removed entirely rather than left without readers (owner, option a). The
    vertex's wild-death path is untouched: `WorkerHandler.on_child_lost` still
    reads the parked wait, and the commander still drops what such a worker
    leaves, counted in `frozen_users_discarded` — the four tests photographing
    that counter pass unchanged. Docstrings realigned in `worker_entry.serve`
    and in the module docstring of the process test file. Net NEGATIVE in
    `src/` (-26 executable lines against a cap of 30). No new public name, so
    no `_TBD` was born.
  > Files: src/genro_asgi/spa/orchestration/spa_worker.py, src/genro_asgi/spa/orchestration/worker_entry.py, tests/orchestration/test_orchestration_spa_worker_departures.py, tests/orchestration/test_orchestration_spa_worker_process.py
  > Verified: 1528 passed on the full suite, ruff clean, mypy advisory with no
    new finding on the two touched src files. Three tests photographing the
    removed self-defense were retired or rewritten
    (`test_the_mass_cycle_leaves_a_departure_already_under_way_to_whoever_has_it`
    and `test_the_mass_cycle_gives_the_loop_back_between_two_users` removed,
    `test_a_dead_wire_parks_everybody_in_the_deposit_and_ends_the_worker`
    rewritten as `test_a_dead_wire_ends_the_worker_and_writes_nothing_to_the_deposit`),
    the real-child e2e now asserts an empty deposit
    (`test_a_real_child_serves_its_site_and_ends_alone_when_the_wire_goes`), and
    one new test says it at the worker rung
    (`test_a_worker_that_loses_its_wire_saves_nothing_and_leaves`).
  - Run: opus / medium
  - Cap: 30 executable lines in `src/` (a removal).
  - Files: spa_worker.py, tests/
  - `on_wire_lost` stops calling `freeze_all_users`: the process closes and
    ends. The vertex's wild-death path is unchanged — it already drops what
    such a worker leaves.
  - Done: a worker that loses its wire writes nothing to the deposit and its
    users are lost at the vertex exactly as before, counted the same way.

## Friction to record, not to fix here

- The m2 e2e drives `plan_transfers`/`execute_transfers` through orders that
  exist only in the test. After Phase 3 the production trigger exists, and that
  scaffolding should be re-read — its own task.
- #36 (the pool oscillating: growth by heads, closure by occupancy) is
  adjacent and NOT touched here.

- `check_user_activity` caps each ordered departure with
  `DEPARTURE_ORDER_WAIT_LIMIT` but nothing caps the ROUND: k users judged idle
  while a call of theirs is in flight cost k x the ceiling, and the vertex
  gathers the group turns, so its clock is blocked for all of it. Raised at the
  quality check of 2026-08-26 and left out on the owner's decision: a ceiling on
  the round is a design choice and needs a name of its own. Its own task.

## Quality check

> Quality check: 2026-08-26T21:58:36Z — commit dae5b29 — review extended, QA declined, findings 3 confirmed, 0 dismissed
