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

## Phase 5

- Stale prose about a deleted mechanism was REPORTED, not rewritten. The
  phase's Decisions list two categories to auto-fix (tool-fixable lint,
  formatting, trivially mechanical) and then say separately to report in
  `review.md` every docstring or `CLAUDE.md` sentence still describing the
  reserve, the periodic growth, the reception's reserve, `/proc` or the old
  threshold names. That third instruction says report, not fix, and the
  sentences sit in the areas the next (interactive) plan reworks — rewriting
  them here would be written twice and read once. Nine such sentences are in
  `review.md` under *Flagged for human*, each with the line and a suggestion.
- The two counts corrected in `CLAUDE.md` and the profiles README ("16
  setpoints" → 14) were treated as mechanical instead: the number is verified
  by counting `GroupPolicy.SETPOINTS`, it describes no mechanism, and Phases 3
  and 4 falsified it in files they owned.
- `ruff format` was NOT run. `ruff format --check src/ tests/` would reformat
  102 of 219 files repo-wide, so the project's gate is `ruff check` alone;
  formatting the phase's file set would have produced a diff belonging to
  nobody's decision.
- The plan's Notes expect `test_orchestration_apply.py::test_no_admission_window_on_apply`
  to fail on the parent commit. It does not fail here — the suite is fully
  green (1781) before and after this phase, as Phase 1's note already recorded.
