# Notes — cpu-orchestration-cleanup

Decision register of the rework: `temp/scheda_ragioni_cpu_orchestration_2026-09-01.md`
(untracked, same worktree). Decisions 1, 4, 8 and 8b of that register are this plan.

## Pre-made at planning (owner not yet consulted on these two)

- **Empty group.** Removing the reserve removes the road that rebuilt the reception
  when the only worker died (`test_a_dead_only_worker_is_replaced_by_the_availability_judge`).
  Phase 3 keeps ONE user-less birth: `check_occupancy` starts a worker when
  `living_workers` is empty. A group with no reception cannot serve anonymous
  requests at all, so this is the group's existence, not speculative capacity.
- **Who writes `saturated`.** `_grow` wrote it when the memory refused a birth.
  Phase 3 moves the write into `assign_user`, at the refusal that raises
  `AssignmentRefused` after the fallback also failed, and `check_occupancy` lifts it
  when `_may_grow` is true again. Same reader as today: `SpaCommander.serve_request`
  refuses the anonymous stranger while the group is saturated.

## Phase 1

- The baseline was red on arrival for an environment reason, not a code one:
  `genro-asgi` 0.37.0 was installed non-editable in the interpreter, so the
  suite imported `site-packages/genro_asgi` instead of this worktree's `src/`
  (63 failures). `pip install -e . --no-deps` — the install the phase
  prescribes anyway — restored the intended baseline: 1769 passed, including
  `test_no_admission_window_on_apply`, which the plan's Notes expected to fail
  on macOS. It does not.
- `tests/orchestration/test_orchestration_m4_e2e.py` was not in the phase's
  `Files:` and had to be touched. Reading the CPU clock through psutil makes
  the thermometer live on macOS too, and `get_occupancy_percent` takes the max
  of memory and CPU: a freshly forked worker under the e2e load then refuses
  placement and the front answers 503. The two stories are about identity,
  placement and deaths; their `server` fixture already neutralises the periodic
  judges, so it now also patches `WorkerHandler.get_process_cpu_reading` to
  return None. The tests were green on macOS only because the platform had no
  CPU source — they would have failed on Linux before this phase.
- The recipe route was tried first and rejected: `cpu_temperature_sample_seconds`
  is declared as a grammar kwarg on `commander` in `spa_app.py` but is absent
  from the key list in `config/handler.py:commander_kwargs`, so a recipe that
  declares it is silently ignored. Left as found — out of this phase's scope.
