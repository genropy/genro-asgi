# Notes — freeze-order

## Phase 1

- Baptism (owner, 2026-08-26): the op constant is `FREEZE_USER_OP_PATH`
  (`"/op/freeze_user"`, mirror of `DROP_USER_OP_PATH`); the worker verb is
  `freeze_designated_user` — the owner rejected "order" in the name.
- Design principle ratified at the gate: collisions are PREVENTED with
  serialization points, never handled with branches. The verb waits on the
  existing events (`_unfreeze_waits` for a pull in flight, a per-user drain
  event set by `close_request` for calls in flight) and takes
  `_claim_departure`; a claim already taken is an impossible state (the group
  serializes departures per user) and stays a loud RuntimeError, no policy.
- No handler-side wrapper: the vertex places orders via
  `worker_handler.connector.call(OP_PATH, ...)` directly, the existing pattern
  (spa_commander.py eval/census/observe).
- `freeze_user`'s triple check and `_drop_parcels` left untouched on purpose:
  Phase 2 removes them once the group's block exists. An outcome of `None`
  (call born mid-write) sends the order back to the drain wait — correct while
  nothing blocks new work.
- Known gap, Phase 4's to close: `_cut_stragglers` empties `_pendings` without
  ringing the per-user drain events, so an order waiting through a quit's cut
  would hang; Phase 4 (quit reuses the sequence) must wake those events when
  it cuts.
- Full-suite flakiness observed under machine load (NOT this phase's files):
  test_orchestration_envelope_chain, test_orchestration_foundations_e2e,
  test_orchestration_group_handler real-child tests failed once each on two
  loaded runs, all green in isolation and on the third full run (1532 passed).
  Pre-existing timing sensitivity, recorded, not absorbed.

## Phase 2

- Names used, brought to the owner at the close (he answered the gate with a
  plain "ok" and picked neither): `GroupHandler.freeze_hosted_user` and
  `SpaCommander.release_user_hold`, both carrying the `# wf:phase-2:new`
  marker for the naming review.
- The success road writes NOTHING at the group. Verified in
  `WorkerConnector._dispatch`: `_take_envelope` runs before `_resolve_reply`,
  so when the confirmation lands the fold has already applied
  `mark_user_frozen` (mark on, hold released), `GroupEnvelopeHandler`'s
  placement to None and the worker's `hosted_users.discard`. The docstring says
  so, because a reader would otherwise look for the missing mutations.
- Failure road, decided at the gate: the method releases the hold, writes one
  `log_order` row and returns False. No raise, so Phase 3's sweep and Phase 4's
  quit stay one line per user.
- Accepted risk, owner's ok at the gate: a request that passed `resolve_user`
  BEFORE the hold went up can still reach the source worker while the parcels
  are written. With the two checks gone it is no longer rolled back, so a page
  born in that request is lost silently. The window is `hold_user` → that
  call's own `open_request`. Closing it means the worker refusing a call for a
  user under departure — new surface, not this workflow's.
- Five tests were retired with the mechanism they photographed, all in
  `test_orchestration_spa_worker_departures.py`: the semaphore-window and
  write-window "keeps the user" pair (the second one replaced by the inverse
  contract), `test_a_write_window_deferral_keeps_the_flag_standing`,
  `test_a_call_closing_inside_the_give_back_drops_no_flag` with the
  `TwoPorterDeposit` class that existed only to stage the rollback, and
  `test_the_quit_survives_a_departure_deferred_at_its_edge`, rewritten as
  `test_the_quit_is_not_stopped_by_a_call_born_at_its_edge`.
- mypy (advisory) reports `group_handler.py:446` indexing
  `worker_handler_map` with `str | None`: that is the deliberate loud KeyError
  for a user this group has not placed. Not silenced.
- CLAUDE.md's "How it works" left alone on purpose: the single-user freeze
  still has no production trigger (Phase 3 gives it one), so writing that the
  group orders freezes today would overstate the machine.

## Phase 3

- Expiry horizon, decided at the gate (owner's ok on option a): ONE horizon per
  identity, owned by the vertex. `SpaCommander.get_user_expiry_seconds(user)` is
  new (3 lines) and `_expired_users` now uses it too, so the guest rule and
  `GUEST_PREFIX` stay in one module and the frozen road and the active road are
  judged by the same number. This is the one edit outside the phase's declared
  `Files:`, declared at the gate before approval.
- The drop needs NO new surface: `DROP_USER_OP_PATH` was already defined and
  already routed in the worker, with no sender anywhere — the same shape
  `/op/freeze_user` was in before Phase 1. The fold applies `drop_user` at both
  rungs (`GroupEnvelopeHandler.on_drop_user` unplaces, `CommanderEnvelopeHandler`
  prunes, and at the worker rung `on_drop_user = on_user_frozen` empties
  `hosted_users`), so the group writes nothing itself.
- The sweep judges only a user `user_worker_map` still places on THAT worker. One
  condition, not a mechanism: it is what keeps a photo that has not caught up
  with a departure from ordering a second one and raising the deliberate loud
  KeyError of `freeze_hosted_user`.
- Accepted at the gate, no mechanism added: the photo is as fresh as the last
  envelope out (seconds) against a silence declared in minutes. A user who spoke
  in that window is parked and woken lazily at his next click — one round trip,
  not a fault.
- No cap on how many users one round parks: `freeze_hosted_user` is awaited per
  user, and a group whose turn runs long already gets the vertex's
  "still in its turn" warning. A freeze is a photo plus a disk write.
- `expiry_delay` is GONE from the worker (`plan_transfers`, `quit`,
  `_flag_everybody_for_departure`, `_answer_then_quit`) with the `'X'` flag and
  its road in `_execute_transfer`. Verified before removing: `quit_process` never
  put it on the wire, so in production it was always `math.inf` and the whole
  branch was dead. `math` is no longer imported by spa_worker.py at all.
- `SECONDS_PER_MINUTE` MOVED from spa_worker.py to group_handler.py (it had no
  other reader, in src or tests), so the parent rung does not import a constant
  from the child module. `_last_real_activity` moved the same way: its only
  reader was the policy that left.
- Cadence: `CHECK_USER_ACTIVITY_BEATS = 12` (60s, twice the shape's 30s), because
  the silence it judges is declared in minutes.
- Nine tests retired with the worker policy they photographed (six in the flags
  and gate sections, the whole three-test valve section). What the valve section
  proved at the worker rung is proved elsewhere already: the parcel round trip by
  `test_what_the_freeze_writes_the_adoption_reads_back`, the call in flight by
  `test_a_call_in_flight_defers_the_departure_to_its_end`. The two judgments it
  proved are now group tests; `test_the_expiry_wins_over_the_valve_on_the_same_user`
  is re-asserted inside the group's expiry test.
- The scripted child of the group tests now carries a REAL photo row per user —
  state, `connection_count`, the three clocks — and answers `/op/drop_user` with
  the announcement a real worker makes. Its `transfer_flag` became declarable
  (default `"T"`, unchanged for every existing test): a flag is read at the vertex
  as a HOLD, so a story whose users are residents must declare none, or the
  REGISTER envelope raises `KeyError` on a user with no row yet.
- The driver's two orders were REMOVED from `x_spa_worker.py`: m3 and m4 were
  their only readers and both now ask the group for its round. m2 keeps its own
  copy — it has no group to judge — and its PLAN_ORDER now names whom it cedes;
  the full re-read of that scaffolding stays the task the plan books.
- Baptism (owner, 2026-08-26): the periodic is `check_user_activity` — chosen off
  three candidates for the symmetry with `check_occupancy`, the other periodic of
  the same object. `SpaCommander.get_user_expiry_seconds` stood as proposed; it
  follows rule 11 (`get_` = a pure reading that needs an argument).

## Phase 4

- Foreman decision (clarify, 2026-08-26): shape (a). The phase's addition is
  the BLOCK only: `quit_all` raises `hold_user` on every hosted user, then
  sends the ONE quit order per worker as today. No per-user freeze order
  travels the wire during quit: the worker's mass cycle
  (`plan_transfers`/`execute_transfers`) parks everybody exactly as wf/33
  built it, and each `user_frozen` releases its hold through the fold.
  Reasons: the plan pins the grace cut where wf/33 put it ("stay exactly as
  wf/33 built them"), and (b) would move it or need a second op/deadline;
  "order each one" in the phase text was written before the cut's position
  was checked — the title's "same sequence" means the user-visible order
  (block -> freeze -> confirm -> release), not the per-user op on the wire.
  The cut therefore does three things for a stuck user: parks him anyway,
  releases his hold, and wakes any per-user drain wait left pending
  (Phase 1 note on `_cut_stragglers`).
- Correction to the recorded reason, verified line by line before implementing:
  the cut does NOT wake a per-user drain wait. `_cut_stragglers` empties
  `_pendings` and sets `_transfers_changed`; the `_freeze_order_waits` events
  are set only by `close_request`, which returns at once for a user already
  out of the pendings. An ordered per-user freeze in flight during a cut would
  stay hung. In shape (a) that case does not exist — no per-user order travels
  the wire during a quit — so it is a wrong reason about an impossible case,
  not a defect. Nothing in Phase 4 rests on it.
- The block is the SAME barrier the photo's flags already raise: the fold's
  `CommanderEnvelopeHandler.on_worker_snapshot` holds every user whose row
  carries a `transfer_flag`, with cause `transfer_flag T`. What quit_all adds is
  its POSITION — the hold goes up before the order, where the photo can only
  ride the answer. A hold keeps its first cause, so nothing is written twice.
- Iterated over `user_worker_map`, not `hosted_users` (the Phase 3 condition):
  only a user this group PLACES on that worker is his, and a user merely passing
  through has his home elsewhere and loses nothing — `report_death` says the same
  with the same two lists. It also spares a `hold_user` on a user with no vertex
  row, which is a `KeyError` (the scripted child of the group tests reproduces it
  when its REGISTER photo names a user the vertex has not resolved yet).
- A worker in `DEAD_STATES` is skipped explicitly, though `_order_quit` would
  return on its own: the hold must not go up for a process whose death has
  already been folded — nobody would be left to release it. Verified besides that
  `frozen_commander_registers` normalises `on_hold` to None, so no leftover hold
  could reach the reboot register even so.
- Left alone on purpose: `restart_worker` and `close_worker` raise no hold in
  advance and meet their users on the photo, as before. Widening the block to
  them was offered at the gate and the foreman's plan edit names `quit_all` as
  the site, so it stays a question for its own task.
