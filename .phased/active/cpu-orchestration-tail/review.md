# Phase 3 — Coherence review of Phases 1..2

Scope: the files written by Phase 1 and Phase 2, and only those. Base of the
comparison: `2d2a50c` (the plan's declared base) → `HEAD`.

## Auto-fixed

| File | What | Tool |
|---|---|---|
| `src/genro_asgi/spa/orchestration/spa_worker.py` (`worker_snapshot` docstring, lines 640-642) | The sentence Phase 1 wrote left one line at 86 columns inside a paragraph wrapped at 70-79; the words are unchanged, the wrap is even again. | manual reflow (whitespace only) |

Nothing else was auto-fixable: `ruff check` was already clean on the whole file
set at the start of the phase, and no unused import, name or helper survived the
deletions (the four CPU tests of `test_orchestration_envelope_chain.py` left no
orphan helper — `envelope`, `photo_of` and the `handler` fixture all still have
readers).

## Flagged for human

1. **`src/genro_asgi/spa/orchestration/group_handler.py:105`** — the module
   docstring still says "A photo's historical ``cpu_percent`` is not an
   orchestration input". Since Phase 1 the photo carries no CPU field at all, so
   the sentence draws a distinction against something that no longer exists.
   *Suggested*: delete the sentence, or replace it with "The photo carries no
   CPU."

2. **`src/genro_asgi/spa/orchestration/group_handler.py:1528`** —
   `_judge_cpu_admission`'s docstring says "The smoothed CPU photo controls
   admission only". The smoothing left the photo in Phase 1; what the method
   actually reads is `WorkerHandler.get_cpu_temperature_percent()`, the
   commander-side filtered temperature. *Suggested*: "The filtered temperature
   controls admission only".

3. **`src/genro_asgi/spa/orchestration/group_handler.py:1548-1551`** —
   `_judge_cpu_admission` names its local `cpu_percent`, which is the spelling of
   the photo key Phase 1 removed, for a value that comes from the thermometer.
   *Suggested*: rename it `cpu_temperature_percent`, the name the journal rows of
   the same method already use. Left alone here: a name is the owner's call, and
   the same local name lives in test helpers this plan never touched
   (`test_orchestration_apply.py:59`, `test_orchestration_placement.py:92`,
   `test_orchestration_group_handler.py:62`, `test_orchestration_cpu_offload.py:44`),
   so the rename is one decision over several files, not a local edit.

4. **`CLAUDE.md:282-286`** — Phase 1's replacement left the sentence saying the
   same thing twice: "two derived by ``WorkerEnvelopeHandler`` between two
   photos, ``recent_call_count`` / ``recent_service_seconds``, derived between
   two photos by the fold." *Suggested*: end the sentence at
   "``recent_service_seconds``" — the deriver and the interval are already named
   in its first half. (The retirement paragraph at line 217 also carries a
   two-word line after Phase 2's insertion; a reflow of that paragraph would
   close it.)

5. **`src/genro_asgi/spa/orchestration/group_handler.py:check_occupancy`
   docstring** — Phase 2 gave the method an early return that ends the round with
   no step at all when a living worker has no temperature yet; the docstring
   still lists only the steps it may take. The module docstring covers the rule
   ("a worker with no temperature yet suspends the judgment", line 96), so this
   is a gap, not a contradiction. *Suggested*: one clause on the gate.

6. **`ruff format` is not this repo's convention** — it would reformat 8 of the
   10 Python files in the set, and 103 of the 220 files repo-wide; there is no
   pre-commit config and `[tool.ruff.lint]` deliberately freezes a narrow rule
   set. Not applied, and not a finding against these phases.

7. **`src/genro_asgi/spa/orchestration/group_handler.py:1478`** — the
   `temperatures: dict[str, float]` annotation Phase 2 added is a NEW mypy
   advisory error (`Value expression in dictionary comprehension has
   incompatible type "float | None"`); at `2d2a50c` the dict was unannotated and
   mypy said nothing. The annotation is deliberate (`notes.md`, Phase 2: it is
   where the caller's guarantee is written down) and mypy is declared
   non-blocking in `pyproject.toml`, which also forbids silencing it with a cast
   or a `type: ignore`. *Suggested*: leave it, or make the guarantee real by
   narrowing what `WorkerHandler.get_cpu_temperature_percent` returns — a
   signature change on a method with other callers, so not this phase's edit.

Nothing in the file set contradicts a `Must not break:` header: the only writer
of `cpu_temperature_percent` is still `WorkerHandler.record_cpu_reading`, every
journal reason code keeps its spelling, and the photo keeps `rss_bytes`,
`pss_bytes` and the user rows with their service counters.

## Final state

- `ruff check` on the file set: **All checks passed!** (also repo-wide on
  `src/ tests/`).
- `pytest tests/ -q`: **1784 passed**, 3 warnings, in 116.92s.
- `mypy`: advisory and non-blocking here; 138 pre-existing errors repo-wide, ONE
  of them new from these phases (item 7 above).
- Convergence: one cycle. The second `ruff check`/`pytest` pair after the single
  fix was green, so no further cycle ran.
- Files reviewed (11): `src/genro_asgi/spa/orchestration/envelope_handler.py`,
  `src/genro_asgi/spa/orchestration/spa_worker.py`,
  `src/genro_asgi/spa/orchestration/group_handler.py`, `CLAUDE.md`,
  `tests/orchestration/test_orchestration_envelope_chain.py`,
  `tests/orchestration/test_orchestration_cpu_temperature_meter.py`,
  `tests/orchestration/test_orchestration_group_handler.py`,
  `tests/orchestration/test_orchestration_pss_accounting.py`,
  `tests/orchestration/test_orchestration_spa_worker_process.py`,
  `tests/orchestration/test_orchestration_user_service_counters.py`,
  `tests/orchestration/test_orchestration_cpu_growth.py`.
