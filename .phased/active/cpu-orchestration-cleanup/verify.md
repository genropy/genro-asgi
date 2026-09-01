
## Phase 5

- **now** — read `review.md` → *Flagged for human*. Nine docstrings and comments
  in the files Phases 1..4 touched still describe the periodic growth, the
  reception's reserve, `/proc`/Linux as the CPU source, or the `rearm` name. Each
  entry carries the line and a suggested rewrite; the wording is the owner's, and
  the code around it is what the next plan reopens.
- **now** — decide the phase-1 contract test divergence: the in-tree copy of
  `tests/orchestration/test_orchestration_cpu_meter_psutil.py:68` carries
  `# the name before Phase 2` on a line the Phase 2 rename already changed. Either
  drop the comment in both copies, or update the plan copy under
  `.phased/active/cpu-orchestration-cleanup/tests/phase-1/`.
