# Coherence review — accensione-genropy-piano-dati (Phase 11)

Scope: only the files written by Phases 7–10, the centralized-delivery redesign,
cross-checked against each other and against the shared modules they consume
(`spa/global_store.py`, `spa/subscription_index.py`, `spa/register_registry.py`),
which stay untouched. This file REPLACES the Phase 6 review: the section
*What the redesign dissolved* accounts for every finding of that review, so
nothing of it is lost by the replacement.

## Auto-fixed

| File | What | Tool |
|------|------|------|
| `src/genro_asgi/spa/orchestration/spa_commander.py:227`, `spa_worker.py:354` | `__all__` back in order in both files: Phase 8 inserted `DESK_PATH_PREFIX` and `DeliveryDesk` leaving `STATE_KINDS` out of place, and Phases 9–10 put the six `DESK_*` entries ahead of `DEPOSIT_LOCK_*`. Both lists keep the file's own convention — constants A–Z, then classes. | `ruff check --select RUF022 --fix`, the rule invoked explicitly (it is outside the project's frozen selection, so nothing reported it) |
| `spa_commander.py:475` (`op_store_lock`, 101), `:515` (the release's log line, 101), `spa_worker.py:1314` (the grant call, 102), `test_orchestration_group_handler.py:101` and `test_orchestration_worker_handler.py:114` (the `.format()` of the child-script template, 102 — pushed over by the Phase 7 rename to `ENVELOPE_SLOT_WORKER_SNAPSHOT`), `test_orchestration_group_handler.py:461` (101), `test_orchestration_spa_worker_process.py:496` (101) | Seven lines over the declared `line-length = 100`, all introduced by Phases 7–10. Wrapped the way each file already wraps: a `def` breaks after the open paren with the marker on that line, a call breaks its arguments, the assert its comparison. | hand edit — `E501` is not in the selected rule set, so nothing reported them |
| `spa_worker.py:1494` (`call`), `:1525` (`run_on_loop`) | Two `wf:phase-7:new` markers sat on the FIRST LINE OF THE DOCSTRING instead of the definition line, so they read as documentation text and the naming review would have looked for them in the wrong place. Moved onto the `def`; `call`'s signature wrapped, since the marker took it to 109 columns. | hand edit — no lint rule knows this contract |

None of the three touches behaviour: **2075 passed, 2 skipped** before and after,
`ruff check` clean on the file set both times.

## Flagged for human

1. **`STATE_KINDS` is declared twice, once on each side of the wire.**
   `spa_worker.py:316` and `spa_commander.py:220` hold the same literal
   `frozenset({"page_store", "user_store", "connection_store"})`, and both
   export it in `__all__`. It is the routing decision itself: the worker stamps
   `kind` on a datachange (`set_datachange`, `spa_worker.py:1013`) and the desk
   reads it to choose a queue (`file_datachange`, `spa_commander.py:394` — STATE
   goes to `user_store_change_map`, anything else to `page_datachange_map`). Two
   literals that must agree with no import between them: a kind added on one
   side alone routes STATE writes into a page queue, silently. *Suggested
   action*: one definition, imported by the other side — or a declared reason
   why the two vertices name the kinds independently.

2. **The exchange happens on every *collect*, not on every request.** The
   decision reads «the exchange happens at the end of EVERY request,
   empty-handed included», and `collect_page`'s own docstring
   (`spa_worker.py:974`) repeats it — but the exchange lives INSIDE
   `collect_page` (`:985`), which the hosted site calls, not the request path
   (`_serve_request`, `:2131`). A request that produces datachanges and never
   collects leaves them on its slot, and the next request on that same
   traffic-pool thread discards them with `open_request_slot()` (`:867`).
   Nothing is misdelivered — every datachange carries its own target — they
   simply never leave. This is the provisional tiraggio the owner already
   accepted for the first pass; what is worth deciding is only whether the
   docstrings should say *collect* while it lasts. *Suggested action*: none
   inside this workflow.

3. **The source filter can be one request stale.** `subscribed_tables`
   (`spa_worker.py:466`) is refreshed only by the reply of an exchange (`:996`)
   or of a `subscribeTable` (`:1177`), and `notifyDbEvents` drops at the source
   every deposit whose table is not in it (`:1217`). So a page on worker A
   subscribing table T is invisible to worker B until B's next collect: a commit
   on B in that window is not announced at all. Impossible with a single worker,
   and the second pass is where inter-worker delivery is built. *Suggested
   action*: decide it there, since the fix is a push toward the workers and not
   a wider cache.

4. **`op_store_unlock`'s `changes: Any = None` has no caller that omits it.**
   `release_global_lock` (`spa_worker.py:1319`) always sends
   `to_tytx([], "json")`, the empty drain included — so
   `from_tytx(None, "json")` at `spa_commander.py:521` is reachable only through
   a hand-made call. A default nothing exercises, in a codebase whose rule is
   no defensive code. *Suggested action*: make it required, or state why the op
   accepts a release with no `changes` key.

5. **Phase 6's finding 6 survived the redesign, one file further up.**
   `release_global_lock` (`spa_worker.py:1319`) calls `copy.drain()` and then
   `copy.detach()`; a raise from inside the drain skips the detach and leaves
   the observer attached to a working copy that is already garbage. The cost is
   the same as before — the copy is thrown away anyway — and turning the two
   lines into a `try/finally` is still a defensive addition, which is the
   owner's call.

6. **Phase 6's finding 3 (size alarm) stands, and grew.** `SpaWorker` is now
   **2575 lines and 100 methods** (2459 and 96 at Phase 6), and `RequestSlot`
   moved into the same module. The data-plane block is still the cohesive
   candidate, now with the slot and the exchange in it. `SpaCommander`'s own
   file went to 1237 lines, of which `DeliveryDesk` is ~355: that one IS an
   object the Phase 6 review said was missing, so the commander side answered
   the alarm and the worker side did not. *Suggested action*: none inside this
   workflow; the second pass decides.

7. **Phase 6's finding 7 stands untouched**: `SpaWorker.drop_connection` takes
   `(identity, session_id)` and `SpaCommander.drop_connection` takes `(cid)`.
   The cascade homonymy is admitted by convention; the two are still not
   interchangeable at a call site.

8. **The two pre-existing over-100 lines are still there**, both older than this
   workflow and left alone on purpose: `worker_connector.py:271` (commit
   `ca75bfb`) and `test_orchestration_spa_worker_departures.py:603` (commit
   `51de991`).

9. **A wider ruff selection reports 25 findings on this file set**
   (`--select E,W,F,I,RUF,B,SIM,C4`; 12 tool-fixable), down from 34 before this
   phase's fixes and none of them under the project's frozen `E4,E7,E9,F`:
   8 `I001`, 7 `SIM105`, 4 `RUF100` (`# noqa: N802`/`N803` directives at
   `spa_worker.py:904`, `:1130`, `:1136`, `:1180`, dead because the naming
   family is not enabled — all four older than Phase 7), 2 `E501` (finding 8),
   2 `SIM118`, 1 `RUF006`, 1 `RUF043`. `pyproject.toml` states that adopting a
   rule is a per-rule decision and never a side effect, so none was touched.
   *Suggested action*: the `RUF100` four are the cheapest of them — dead
   directives, nothing to weigh — if a sweep is wanted, it is its own change.

Verified as sound, no action needed: the CALL lane answers exactly once on
every path — a served call, a handler that raises and an unknown path all
produce a REPLY (`worker_connector.py:337`), and a wire that dies fails every
parked caller (`_fail_pending`) and cancels every service task
(`_cancel_child_calls`) before `on_child_lost` hands the store grant back
(`worker_handler.py:426`), so no waiter is left holding what it never got; the
grant's FIFO is `asyncio.Lock`'s own, which retires a cancelled waiter and wakes
the next by itself; `op_store_unlock` writes the master BEFORE releasing, so the
next grant carries the changes, and a release for a grant no longer in force
applies nothing (`holds`, `global_store.py:187`); the desk files arrivals before
draining in both `op_exchange` and `op_subscribe_table`, which is what closes
the subscribe-and-commit window; the three species never share a queue, and each
ages on its own clock (`_fresh_changes` on `change_ts` datetimes,
`drain_page_dbevents` on the deposits' epoch `ts`); `drop_page` clears both page
queues and the subscriptions in one breath. The `threading.local()` behind
`request_slot` is NOT a divergence from the plan's «explicit per-request
object»: the reason is recorded in `notes.md` under `## Phase 9` (the site's
verbs take no slot argument, and one request is one traffic-pool thread end to
end).

## What the redesign dissolved

Every finding of the Phase 6 review, accounted for:

- **1 (the ascent drops the Bag attributes of a write)** — dissolved. There is
  no ascent of writes any more: the release applies the drained changes in full
  shape through `GlobalStore(...).apply_changes(...)`
  (`spa_commander.py:521`), attributes, reason and fired included.
- **2 (a refused derived write leaves the replica divergent)** — dissolved with
  the replica itself. `global_replica`, `record_global_write`, `_global_writes`,
  `_take_global_store`, `apply_global_writes`, `old_value`,
  `ENVELOPE_SLOT_GLOBAL_STORE` and `GLOBAL_WRITES_KEY` have no occurrence left
  in `src/genro_asgi/spa/orchestration/`; the only hits in `src/` are in
  `spa/worker.py`, the pre_refactoring stack, which is read-only by plan.
  `test_contract_phase10_global_store_desk.py:188` pins their absence.
- **3 (size alarm)** — stands, see finding 6 above.
- **4 (`dbevent_deposit` vs `deposit_dbevent`)** — dissolved: Phase 9 removed
  `deposit_dbevent`, and `test_contract_phase9_request_exchange.py:274` pins its
  absence. Only the noun-first shaper survives, so the pair that was hard to
  read side by side no longer exists.
- **5 (`global_register_item_tytx` has no reader left)** — dissolved: removed
  with the descent of the store, absence pinned by the same phase-10 contract.
- **6 (the lock leaves the working copy attached on a raise)** — survived,
  moved; see finding 5 above.
- **7 (`drop_connection` argument divergence)** — survived untouched; finding 7.
- **8 (two pre-existing long lines)** — survived; finding 8.
- **9 (the wider ruff selection)** — survived, smaller; finding 9.

## Final state

- **Linter**: `ruff check` on the 21 files of the set — *All checks passed*.
  Also clean over the whole tree (`ruff check .`).
- **Suite**: `python -m pytest tests/ -q` → **2075 passed, 2 skipped**,
  coverage 97%.
- **Files reviewed** (the union of the `Files:` fields of Phases 7–10, taken
  from the diff of their four commits, `6ba6999..acb0bcc`):
  - `src/genro_asgi/spa/orchestration/spa_worker.py`
  - `src/genro_asgi/spa/orchestration/spa_commander.py`
  - `src/genro_asgi/spa/orchestration/worker_connector.py`
  - `src/genro_asgi/spa/orchestration/worker_handler.py`
  - `src/genro_asgi/spa/orchestration/envelope_handler.py`
  - `tests/orchestration/conftest.py`
  - `tests/orchestration/child_stub.py`
  - `tests/orchestration/test_contract_phase3_data_plane.py`
  - `tests/orchestration/test_contract_phase4_dbevents.py`
  - `tests/orchestration/test_contract_phase7_worker_call_lane.py`
  - `tests/orchestration/test_contract_phase8_delivery_desk.py`
  - `tests/orchestration/test_contract_phase9_request_exchange.py`
  - `tests/orchestration/test_contract_phase10_global_store_desk.py`
  - `tests/orchestration/test_orchestration_envelope_chain.py`
  - `tests/orchestration/test_orchestration_foundations_e2e.py`
  - `tests/orchestration/test_orchestration_group_handler.py`
  - `tests/orchestration/test_orchestration_m2_e2e.py`
  - `tests/orchestration/test_orchestration_spa_worker_departures.py`
  - `tests/orchestration/test_orchestration_spa_worker_process.py`
  - `tests/orchestration/test_orchestration_worker_connector.py`
  - `tests/orchestration/test_orchestration_worker_handler.py`
  - (`tests/orchestration/test_contract_phase5_global_store.py` was DELETED by
    Phase 10, under the foreman decision recorded in `notes.md`)
- **Contract-test density**: 31 tests, 105 assertions, 2 `pytest.raises` across
  the four new phase files — nothing vacuous.
- **Markers standing for the finalize naming review**: 39 `wf:phase-N:new` in
  `src/` (2 phase-2, 5 phase-3, 3 phase-4, 6 phase-7, 12 phase-8, 5 phase-9,
  6 phase-10), every one of them now on its own definition line.
