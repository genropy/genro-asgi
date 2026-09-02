
## Phase 2
- `temperatures` in `_spare_worker` is annotated `dict[str, float]` rather than
  left bare: the plan removed the None branch, and the annotation is where that
  guarantee is written down for the next reader. `get_cpu_temperature_percent`
  still declares `float | None` — the caller narrows it, no cast was added.
- The new check sits after the `saturated` lift and before the
  `cpu_admission_close_percent` gate, so a group with no living worker still
  gets its reception back before any temperature is demanded.

## Phase 3
- The five wording findings (two stale docstrings in `group_handler.py`, the
  local named `cpu_percent`, the duplicated clause in `CLAUDE.md`, the
  `check_occupancy` docstring gap) were REPORTED, not fixed: the phase's own
  decision routes "every docstring or `CLAUDE.md` sentence that still describes
  the photo's CPU smoothing" to `review.md`, and the wording of that prose is
  the owner's.
- `ruff format` was measured and rejected as a fix: 103 of the 220 files in
  `src/ tests/` would be reformatted and no pre-commit config asks for it, so a
  reformat of 8 files in the set would be this phase inventing a convention.
- The only edit is a whitespace reflow of the docstring sentence Phase 1 wrote
  in `spa_worker.worker_snapshot`; the words are untouched.

## Quality check

- Review agent, 2026-09-02: two tests that lost their observable with the photo's CPU were settled —
  `test_cpu_never_enters_memory_occupancy` deleted (its body had become a copy of the PSS test) and
  the dead middle step of `test_a_photo_past_the_restart_setpoint_brings_the_round_forward` removed;
  the ordering `cpu_temperature_missing` before the pressure gate gained a test; one 109-column
  docstring line rewrapped. Left to the owner: the local name `cpu_percent` in `_judge_cpu_admission`
  and five test helpers; the mypy advisory on `temperatures: dict[str, float]`.
