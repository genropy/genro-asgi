
## Phase 1
- The plan asked for a `#:` comment on the field: `item_lock` is a row key, not a module
  constant, so it has no `#:` site. The contract lives in the module docstring paragraph
  ("The row's own lock") and in the two REBUILT-set comments in `spa_worker.py`.
- The parcel test lives in `tests/test_register_registry.py` and reaches
  `SpaWorker._connection_parcel` directly, as the plan's decision named it.

## Run inspection

- 5/5 phases done after one consult; `EVENT: run-end stopped 4/5` because the launcher read Phase 5 still `[>]`.
- Phase 2 pulled part of Phase 3 forward (`setStoreSubscription`, `_install_page_subscriptions`, `collect_page` already read the row's queue, without `item_lock`) and added `_detach_parcel_capture`: the deep copy of a page store copied its subscriber, which does not pickle and would have fed the live row's queue. Also edited `test_contract_phase4_dbevents.py` (autocreated parent no longer travels); declared in `> Files:`, no `## Phase 2` entry in this file.
- Phase 3 failed on a plan defect: its first `Done:` demanded no `collector` word in `spa_worker.py`, but `_install_carried_store` calls `new_collector` for the `user_view`, kept by a `Must not break:`. Consult answered `apply`: the foreman narrowed the criterion (`| grep -v new_collector`), re-ran the Done, closed the phase (`f0bf7e7`); the launcher recorded `e97e9ab` and went on.
- Phase 5 did its work (`review.md`, four items flagged for human) and committed it, but the marker stayed `[>]` and no `> Done:` landed: the launcher stopped for no progress. Same class as the previous run's Phase 4 (the sub-session's final commit step does not complete); closed by the foreman after `run-end`.
- Nothing tripped a budget cap; no session died.
