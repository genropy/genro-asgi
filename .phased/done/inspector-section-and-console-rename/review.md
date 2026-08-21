# Coherence review — inspector section and console rename

Reviewed: the file set written by Phases 1..5, cross-checked against the
pattern references those phases named. No pre-existing file outside that set
was touched.

## Auto-fixed

| File | What | How |
|------|------|-----|
| `src/genro_asgi/applications/server_sections/__init__.py` | The `__all__` list grew to a single 133-character line when Phase 4 added `INSPECTOR_ENV_VAR` and `InspectorSection`, against the `line-length = 100` declared in `pyproject.toml`. Ruff did not catch it: its `select` is `["E4", "E7", "E9", "F"]`, and `E501` lives in `E5`. | Wrapped one name per line, by hand; the full suite re-run green afterwards. |

Nothing else was auto-fixable: ruff was already clean on the whole file set
before this phase started, and no unused import, no dead name and no
formatting divergence beyond the one above survived Phases 1..5.

## Flagged for human

1. **`spa_worker.py` — `_census_register` evaluates `_census_field` twice per
   field**, once in the `if` that decides whether to carry it and once as the
   value. The function is pure, so no reading is wrong; on a container field it
   pays the `all()` scan and the `sorted()` twice. Not auto-fixed on purpose:
   binding the result once inside a comprehension means the walrus operator,
   and `:=` appears nowhere in `src/` — introducing an idiom the codebase does
   not use is not a mechanical fix. *Suggested:* leave it (the census is a
   debug-only path, called on demand), or bind it and accept the new idiom.

2. **Every worker-side mutation reaches the stream twice.** The worker reports
   it from `add_worker_event` → `report_observation` (`source` = the worker
   name), and the same event is republished at the vertex from
   `CommanderEnvelopeHandler.__call__` over `ENVELOPE_SLOT_WORKER_EVENTS`
   (`source` = `"commander"`). Both readings were asked for by Phase 3 — the
   register changed / the vertex maps changed — and the page tolerates
   duplicates by construction (no merge logic, any event debounces one
   refetch). The visible effect is the event log showing each birth twice with
   two different sources. *Suggested:* decide whether that is the intended
   two-perspective record or whether the fold relay should skip the kinds the
   worker already reported.

3. **The `census` route is contract-tested only empty.**
   `tests/test_inspector_section.py::test_the_census_is_json` asserts the body
   is `{}` — the test server mounts no `SpaApplicationNew`, so nothing
   exercises the route's per-front shaping. The populated census is covered one
   layer down, at commander level, in
   `tests/orchestration/test_orchestration_census.py`. *Suggested:* if the
   route's shaping is ever to be trusted without reading it, one end-to-end
   test mounting a `local_worker` front behind `_server/inspector/census`.

4. **`worker_handler.py` — `_observation_switched` is set once and never
   cleared.** Behaviour is right today: a later watcher's
   `switch_observation(True)` reaches every living worker, so the flag only
   guards the spawn-time catch-up of a worker that registered while somebody
   was already looking. But it is named as a state ("switched") while it means
   "the catch-up has already been fired". *Suggested:* clear it in the off
   switch, or rename it to what it guards.

5. **`resources/inspector.html` — resume reads twice.** `toggleStream` reopens
   the EventSource (whose open already delivers a full `census` event) and then
   calls `readCensus()` as well: one redundant fetch per resume click.
   Harmless; noted because it is the only place the page pays for the same
   reading twice.

6. **`CLAUDE.md` is stale on both halves of this workflow.** Its "How it works"
   overview still names the eval door the `inspect` family and knows nothing of
   the `_server/inspector` section. By the plan's own decision no phase touched
   the file (it carries uncommitted local edits on this machine), so the
   overview update is a human follow-up — in the same commit that lands it, per
   the house rule.

7. **genropy-asgi still imports `SpaInspectorMcpApplication`** in
   `src/genropy_asgi/spa/config.py`, mounting it at `_inspect`. Phase 1 left no
   compatibility alias, as ratified, so that repo needs the one-line follow-up
   (`SpaConsoleMcpApplication`, `mount="_console"`, `code="console"`). Declared
   in the plan's Notes as outside this workflow.

Nothing in this list is a logic error, a divergence from a pattern reference or
a missing edge case in the code as specified: the eval-op chain, the
`SseStream` usage, the section shape and the child→parent lane all follow the
files the phases pointed at.

## Final state

- **Linter** — `ruff check` on the reviewed file set: `All checks passed!`;
  repo-wide `ruff check src/ tests/`: `All checks passed!`
- **Suite** — `python -m pytest tests/ -q`: **2112 passed, 2 skipped**,
  2 warnings, coverage 96%.
- **Convergence** — one cycle: lint (clean) → one formatting fix → lint
  (clean) → suite (green). The second cycle found nothing to do.
- **Files reviewed** (13 + 1 resource):
  - `src/genro_asgi/applications/spa_console.py`
  - `src/genro_asgi/applications/server_app.py`
  - `src/genro_asgi/applications/server_sections/__init__.py`
  - `src/genro_asgi/applications/server_sections/inspector_section.py`
  - `src/genro_asgi/applications/server_sections/resources/inspector.html`
  - `src/genro_asgi/routed_application.py`
  - `src/genro_asgi/spa/orchestration/spa_commander.py`
  - `src/genro_asgi/spa/orchestration/spa_worker.py`
  - `src/genro_asgi/spa/orchestration/worker_handler.py`
  - `src/genro_asgi/spa/orchestration/envelope_handler.py`
  - `tests/test_inspector_section.py`
  - `tests/orchestration/test_orchestration_console.py`
  - `tests/orchestration/test_orchestration_census.py`
  - `tests/orchestration/test_orchestration_observation.py`
- **Rename completeness** — `grep -rn
  "spa_inspector\|SpaInspector\|INSPECT_OP_PATH\|inspect_target\|inspect_expression"
  src/ tests/` returns nothing, and the word "inspect" appears nowhere in
  `spa_console.py` or its test.
