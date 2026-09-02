
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
