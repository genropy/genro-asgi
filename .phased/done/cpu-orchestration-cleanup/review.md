# Coherence review — cpu-orchestration-cleanup (Phase 5)

Scope: the files written by Phases 1..4, collected from their `Files:` fields.
No file outside that set was read for findings or modified.

## Auto-fixed

| File | What | Tool |
|---|---|---|
| `CLAUDE.md:175` | "holds the 16 setpoints" → "holds the 14 setpoints". Phase 3 deleted `newcomer_reserve_count`, Phase 4 deleted `reception_reserved_percent`; `GroupPolicy.SETPOINTS` now has 14 keys. | by hand, count verified against `group_policy.py:74-89` |
| `internals/10_server/020_applications/configuration_profiles/README.md:86` | "carries the 16 setpoints" → "carries the 14 setpoints", same fact. | by hand, same verification |

`ruff check` reported nothing on the file set before or after, so no lint,
import or formatting fix was applied. The full suite was re-run after the two
edits: 1781 passed.

## Flagged for human

Every entry is prose that still describes a mechanism Phases 1..4 deleted. None
was rewritten: the plan routes this category to this file, and the sentences
belong to the areas the next (interactive) plan reworks.

| File | Description | Suggested action |
|---|---|---|
| `src/genro_asgi/spa/orchestration/group_handler.py:36-37` | Module docstring: "the wake rings on the way out, so the group grows before he tries again". Phase 3 removed the periodic growth. The wake still rings (`assign_user` calls `ping_now()` on the refusal), but `check_occupancy` births nobody except the reception of a group with no living worker; it only lifts `saturated` once `_may_grow` is true again. | Say the wake lifts the saturation, so the NEXT arrival can father the worker inside its own placement. |
| `src/genro_asgi/spa/orchestration/group_handler.py:1557` | `record_cpu_pressure` docstring cites "(churn of 2026-08-28, rearm30)". `rearm` is the name Phase 2 replaced with `reopen`. | `reopen30`, or spell out `cpu_admission_reopen_percent` at 30. |
| `src/genro_asgi/spa/orchestration/spa_commander.py:148` | Module docstring: "`cpu_meter_loop` reads two scalar counters from each governed Linux process". Phase 1 moved the reading to psutil, which answers on every platform. | Drop "Linux", name psutil as the source. |
| `src/genro_asgi/spa/orchestration/spa_commander.py:214` | "Default cadence of the observation-only Linux worker CPU thermometer" — same leftover on `CPU_TEMPERATURE_SAMPLE_SECONDS`. | Drop "Linux". |
| `src/genro_asgi/spa/orchestration/worker_handler.py:273-275` | "the full photo remains the portable fallback on platforms without Linux's process table". After Phase 1 there is no platform without the reading; what is left is the fallback while fewer than two readings of the same process exist. | Say the photo covers the first interval, not a missing platform. |
| `src/genro_asgi/spa/orchestration/worker_handler.py:268-272` | The `#:` block "The last lightweight kernel reading as `(process birth, cpu seconds, sample instant)`" documents `_cpu_meter_reading`, but Phase 1 inserted `_process_probe` between the comment and its attribute, so the comment now attaches to the probe and the probe itself is undocumented. | Move the block back onto `_cpu_meter_reading` and give `_process_probe` its own line (what it caches, and that it is rebuilt on a pid change). |
| `tests/orchestration/test_orchestration_cpu_growth.py:57` | `grown_group` docstring: "its reception unreserved as the experiment runs it". Phase 4 deleted `reception_reserved_percent`; the helper no longer sets anything of the kind. | Drop the clause. |
| `tests/orchestration/test_orchestration_cpu_growth.py:581` | Comment: "the ordinary availability/reserve judge restores a reception". There is no reserve judge; the reception comes back from the empty-group branch of `check_occupancy`. | Name that branch instead. |
| `tests/orchestration/test_orchestration_m3_e2e.py:42-44` | Story header, step 5: "a newcomer nobody admits rings the wake, the round brings a second process into being, and his retry lands on it — the reception refuses him with the reserve it keeps for the trade only it has". Both the round's growth (Phase 3) and the reception's reserve (Phase 4) are gone. The body of step 5 (`:353-369`) is already correct: the birth lives inside the placement and there is no retry. | Rewrite the header to match its own body. |
| `tests/orchestration/test_orchestration_cpu_meter_psutil.py:68` | The in-tree contract test carries `group.cpu_admission_close_percent = None  # the name before Phase 2`; Phase 2's rename made the trailing comment false, and the file no longer matches its plan copy (`.phased/active/cpu-orchestration-cleanup/tests/phase-1/`). The divergence is already recorded in Phase 2's `> Review:`. | Owner's call: drop the comment in both copies, or update the plan copy to the post-rename text. Not touched here — a contract test is read-only to an executing phase. |

## Final state

- **Linter**: `ruff check` over the file set — `All checks passed!`. `ruff format`
  is NOT a gate of this project: `ruff format --check src/ tests/` says 102 files
  repo-wide would be reformatted, so no formatting was applied.
- **Suite**: `pytest tests/ -q` → **1781 passed**, 3 warnings, 111s. The one
  failure the plan's Notes expected on the parent commit
  (`test_orchestration_apply.py::test_no_admission_window_on_apply`) does not
  reproduce here: the suite is fully green before and after this phase.
- **Convergence loop**: one cycle. `ruff check` was already clean, the two
  documentation counts were corrected, the suite re-ran green; a second cycle had
  nothing to act on.
- **Files reviewed** (union of the `Files:` of Phases 1..4):
  - `pyproject.toml`, `CLAUDE.md`, `docs/guides/configuration.md`,
    `internals/10_server/020_applications/configuration_profiles/README.md`
  - `src/genro_asgi/spa/orchestration/group_handler.py`,
    `src/genro_asgi/spa/orchestration/group_policy.py`,
    `src/genro_asgi/spa/orchestration/spa_commander.py`,
    `src/genro_asgi/spa/orchestration/worker_handler.py`,
    `src/genro_asgi/applications/spa_app.py`, `src/genro_asgi/config/handler.py`
  - `tests/test_apply_group_settings.py`, `tests/test_config.py`,
    `tests/test_configuration_profiles_application.py`,
    `tests/test_group_policy.py`, `tests/test_group_policy_admission_names.py`,
    `tests/test_spa_app_profiles.py`
  - `tests/orchestration/group_stub.py`,
    `tests/orchestration/test_orchestration_apply.py`,
    `tests/orchestration/test_orchestration_cpu_growth.py`,
    `tests/orchestration/test_orchestration_cpu_meter_psutil.py`,
    `tests/orchestration/test_orchestration_cpu_offload.py`,
    `tests/orchestration/test_orchestration_cpu_temperature_meter.py`,
    `tests/orchestration/test_orchestration_group_handler.py`,
    `tests/orchestration/test_orchestration_m3_e2e.py`,
    `tests/orchestration/test_orchestration_m4_e2e.py`,
    `tests/orchestration/test_orchestration_memory_headroom.py`,
    `tests/orchestration/test_orchestration_no_reception_reserve.py`,
    `tests/orchestration/test_orchestration_no_speculative_birth.py`,
    `tests/orchestration/test_orchestration_placement.py`,
    `tests/orchestration/test_orchestration_policy_delegation.py`

### Checks that found nothing

Run over the same file set, each reported clean:

- `git grep -nE 'cpu_grow_|growth threshold' -- src tests docs internals CLAUDE.md`
  — no occurrence outside the phase-2 contract test, which asserts the old names
  are refused.
- `git grep -nE 'newcomer_reserve_count|_has_room|_placeable_newcomers|def _grow|reception_reserved_percent|get_worker_cap' -- src tests docs internals CLAUDE.md`
  — no occurrence outside the phase-3 and phase-4 contract tests, which assert
  their absence.
- `git grep -nE 'PROCESS_STAT_ROOT|PROCESS_CLOCK_TICKS' -- src` — nothing. The
  surviving `/proc` mentions in `src` are all `/proc/meminfo`,
  `/proc/self/status` and `/proc/self/smaps_rollup`: the MEMORY channel, which
  this workflow did not touch, in files outside the set.
- The phase-2, phase-3 and phase-4 in-tree contract tests are byte-identical to
  their plan copies; only phase-1 diverges, for the reason above.
- `GroupPolicy.SETPOINTS`, the dataclass fields, the `spa_app.py` grammar kwargs
  and the key list in `config/handler.py` name the same 14 setpoints.
