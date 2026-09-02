## Phase 1

- The `Done:` grep lists "commander census" among the files naming `cpu_heating_seconds`.
  The census carries the VALUES (`cpu_temperature_percent`, `cpu_temperature_sample_percent`),
  never the setpoint's name, so `spa_commander.py` cannot appear in that grep. Read as:
  policy, grammar, `config/handler.py`, `group_handler.py`, `worker_handler.py`, the three
  docs — all found; the census is asserted by the meter test instead.
- `test_fresh_temperature_closes_and_reopens_cpu_admission` changed meaning on purpose:
  one idle 100 ms sample no longer reopens a worker at 80% (it cools it to ~78.4%); five
  seconds of silence do. That is the defect measured on `temp4`.
- The indentation of `cpu_temperature_sample_seconds` in the commander grammar signature
  (`spa_app.py`) was wrong by four spaces; fixed in passing, same file.
- The census test double in `test_orchestration_census.py` gained the new attribute.

## Phase 2

- Decisions said `WorkerHandler.assign_user` refuses a CPU-closed worker. Implemented, it broke
  the fallback the same Decisions keep (`_fallback_candidate` walks the CPU-closed workers
  through the same gate): four cpu_growth tests failed. Resolved at the gate (owner, 2026-09-02):
  the gate judges state, heads and the memory veto; the CPU admission stays where it was, the
  placement's candidate filter, so the fallback keeps working as designed.
- `_expected_occupancy` lost its last callers in batch 1 (the gate takes no cost) and was
  removed here rather than in batch 3; the rest of the estimate chain follows in batch 3.
- The invalid profile of `test_invalid_apply_all_or_nothing` relied on the deleted
  `close < occupancy` cross rule; it now uses `worker_memory_admission_percent: 99` (>= restart).
- `test_the_reactive_growth_and_a_placement_cannot_fork_twice` sat at 79% to be refused by the
  old cap plus the 5% estimate; it sits at 85% now, past the veto.
