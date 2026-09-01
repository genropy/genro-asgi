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
