# Phase 9 — coherence review and auto-fix

Scope: the files written by Phases 1..8, collected from their `Files:` fields
(8 source modules, 11 test modules, `pyproject.toml`, the internals README and
`CLAUDE.md`). No pre-existing file outside that set was touched.

## Auto-fixed

None. The configured linter (`ruff check`, rule set `E4,E7,E9,F` per
`pyproject.toml:98-105`) reported zero errors on the file set at the first
cycle, so the convergence loop stopped after cycle 1 with nothing to fix: no
unused import, no undefined name, no shadowing. Nothing mechanical was left to
correct, and no rollback was needed.

`ruff format` was deliberately NOT run. It would reformat 10 of the 19 files —
but also 97 of the repository's 210 Python files, so it is not this project's
formatter and applying it here would have produced noise the rest of the tree
does not carry.

## Flagged for human

1. **`spa_commander.py:1395` — `apply_group_settings` documents a precondition
   it does not enforce.** The docstring says "Never both" of `profile` and
   `profile_name`, but a caller passing both is not refused: `profile_name`
   silently overwrites `profile`, since the stored read assigns over the
   argument. Suggested action: either raise an explicit error on both (the
   project's "impossible cases get explicit errors" rule), or drop the sentence
   and document that `profile_name` wins. Not auto-fixed: it is a behaviour
   decision, and the route layer in `spa_app.py` never sends both.

2. **`configuration_profiles.py:104-105` — the precedence of the two 400s
   changed.** Before Phase 2 the body was checked first: a request with a bad
   name AND no body answered "the profile body must be a JSON object". Now
   `store.get_profile_name(name)` runs first, so the same request answers the
   name violation. Both are still 400 and the archive's contract test passes
   unmodified; only the message a doubly-invalid request receives differs.
   Suggested action: accept it, or restore the body-first order if any consumer
   matches on that message.

3. **`group_policy.py:151,159` — `from_settings` and `_check_value` are
   classmethods**, against the parent CLAUDE.md rule "instance methods only".
   Phase 3 recorded the reason (the call site `GroupPolicy.from_settings(...)`
   is cited verbatim by the design and by Phases 4, 5 and 6). `_check_value`
   follows from that choice rather than from its own. Suggested action: ratify
   the exception in the project rules, or move the validation to a builder
   object.

4. **mypy (advisory, never gating): 52 findings on the 8 source modules**, all
   but one in the two families the project already documents as deliberate —
   implicit-Optional grammar signatures on `spa_app.py` element kwargs, and
   attribute access on `BaseServer | None`. The one finding from this plan's own
   code is `configuration_profiles.py:105`: `store.write(name, body_data)` is
   handed `dict[str, Any] | None`. The runtime behaviour is correct — `None`
   fails the `isinstance` check inside `ProfileStore.write` and comes back as the
   same 400 the old code raised — but the annotation says it cannot happen.
   Suggested action: widen `ProfileStore.write`'s parameter to `Any`, or keep the
   `None` check in the route.

5. **Carried over from the phases' own `> Review:` notes** (already in the plan,
   restated here so the quality check sees them in one place):
   - Phase 3: `GroupPolicy.SETPOINTS` is a dict of bare 5-tuples decoded by one
     comment; and a settings dict carrying both a per-key and a cross-rule
     violation reports the per-key ones only.
   - Phase 4: the cross rule on the CPU band is checked twice — in the
     constructor and in `GroupPolicy`.
   - Phase 5: `SingleGroupRequired` lives in `spa_commander.py`, not with the
     rest of the orchestration exceptions.
   - Phase 6: the 400 payload of the apply route deviates from the ratified
     shape.

Cross-checked and found correct, so NOT flagged: the 14 rows of
`GroupPolicy.SETPOINTS` match the design's setpoint matrix
(`temp/design_profili_fase2_2026-08-28.md:523-537`) key by key — type, default,
bound and bound strictness, including the two exclusive lower bounds
(`memory_max_percent`, `new_user_occupancy_percent`) and the deliberate absence
of an upper bound on `worker_memory_max_percent` (design line 326: it may exceed
100). The four cross rules match the matrix's dependency column.

## Final state

- **Linter**: `ruff check` over the 19 files of the set — `All checks passed!`,
  exit 0.
- **Suite**: `python -m pytest tests/ -q` — **1629 passed**, 3 warnings, 97%
  coverage. Same count as the baseline taken before this phase started.
- **Cycles**: 1 of the 3 allowed. Cycle 1 found nothing to fix, so the loop
  stopped early with no change to any reviewed file.
- **Files reviewed** (20):
  - `src/genro_asgi/profile_store.py`
  - `src/genro_asgi/applications/configuration_profiles.py`
  - `src/genro_asgi/spa/orchestration/group_policy.py`
  - `src/genro_asgi/spa/orchestration/group_handler.py`
  - `src/genro_asgi/spa/orchestration/worker_handler.py`
  - `src/genro_asgi/spa/orchestration/spa_commander.py`
  - `src/genro_asgi/applications/spa_app.py`
  - `src/genro_asgi/lifespan.py`
  - `tests/test_profile_store.py`
  - `tests/test_group_policy.py`
  - `tests/test_apply_group_settings.py`
  - `tests/test_spa_app_profiles.py`
  - `tests/test_spa_profile_grammar.py`
  - `tests/test_lifespan.py`
  - `tests/orchestration/test_orchestration_policy_delegation.py`
  - `tests/orchestration/test_orchestration_group_handler.py`
  - `tests/orchestration/test_orchestration_cpu_growth.py`
  - `tests/orchestration/test_orchestration_apply.py`
  - `tests/orchestration/test_orchestration_audit_destinations.py`
  - `pyproject.toml`
  - (documentation, reviewed but not linted:
    `internals/10_server/020_applications/configuration_profiles/README.md`,
    `CLAUDE.md`)
- **Note on one file outside the set**:
  `tests/orchestration/test_orchestration_foundations_e2e.py` differs from the
  branch base, but it was changed by `ec108ed` — the out-of-workflow fix that
  unblocked Phase 2's red baseline, recorded in that phase's `> Blocked once`
  note. No phase of this plan owns it, and it was not reviewed here.
- **New-callable markers**: 36 `wf:phase-N:new` markers stand in `src/`, left in
  place for the whole-workflow naming review at `/finalize-workflow`.
