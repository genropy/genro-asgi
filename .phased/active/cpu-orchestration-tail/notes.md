
## Phase 2
- `temperatures` in `_spare_worker` is annotated `dict[str, float]` rather than
  left bare: the plan removed the None branch, and the annotation is where that
  guarantee is written down for the next reader. `get_cpu_temperature_percent`
  still declares `float | None` — the caller narrows it, no cast was added.
- The new check sits after the `saturated` lift and before the
  `cpu_admission_close_percent` gate, so a group with no living worker still
  gets its reception back before any temperature is demanded.
