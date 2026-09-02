# Phase 5 — Coherence review and auto-fix

Scope: only the files written by Phases 1–4.

- `src/genro_asgi/spa/register_registry.py`
- `src/genro_asgi/spa/orchestration/spa_worker.py`
- `tests/orchestration/conftest.py`
- `tests/orchestration/test_contract_page_store_row.py`
- `tests/orchestration/test_contract_phase1_registry.py`
- `tests/orchestration/test_contract_phase3_data_plane.py`
- `tests/orchestration/test_contract_phase4_dbevents.py`
- `tests/orchestration/test_contract_phase9_request_exchange.py`
- `tests/test_register_registry.py`
- `CLAUDE.md`
- `internals/20_spa/050_datachanges/README.md`
- `internals/20_spa/050_datachanges/design.md`

## Auto-fixed

None. `ruff check` reported zero errors on the file set at the first cycle, so
the convergence loop ended after one pass with nothing to fix. No unused
import, no tool-fixable finding, no mechanical divergence was found.

## Flagged for human

1. **`tests/orchestration/test_contract_phase3_data_plane.py`, module docstring
   (lines 17 and 27–31).** It still says a page has "its own collector": line 17
   lists "the two collectors" among what the file derives from, and the Phase 9
   amendment paragraph closes with "What stays purely local is the page's own
   capture: its collector and its ``user_view``". After Phase 2 the page's own
   capture is the row's queue filled by `subscribe_page_store`; only the
   `user_view` is still a collector. Suggested action: reword the two spots to
   "the page's queue and its ``user_view``" and "the row's queue, the page
   listening to itself". Not auto-fixed: a contract file's text is read-only to
   an executing phase (`contracts.md`), and the change is editorial, not
   mechanical.

2. **`tests/orchestration/test_contract_phase3_data_plane.py:124` — test name
   `test_collect_page_merges_both_collectors_by_ts`.** "Both collectors" now
   names the row's queue plus the `user_view`. The assertions are correct; only
   the name is stale. Suggested action: rename to
   `test_collect_page_merges_both_captures_by_ts`. Not auto-fixed: renaming a
   contract test is the owner's call.

3. **`tests/orchestration/test_contract_phase9_request_exchange.py:181` — test
   name `test_collect_merges_own_collectors_with_the_retired_pendings`, and its
   `wf:contract:` comment at line 183 ("its collector and its ``user_view``,
   still local").** Same staleness as (2), in a contract comment this time.
   Suggested action: "its queue and its ``user_view``", and the name to
   `test_collect_merges_own_captures_with_the_retired_pendings`. Not
   auto-fixed: same reason.

4. **`src/genro_asgi/spa/register_registry.py:68` — "keys, live stores and
   collectors survive the login".** Read against the login path this is still
   true: what survives there is the `user_view`, which is a collector. It is
   ambiguous only because the page no longer has a collector of its own.
   Suggested action, optional: "keys, live stores and captures survive the
   login". Flagged, not fixed — it is a wording judgment on a paragraph the
   plan's `Must not break:` on the user store leaves in place.

No docstring in the file set says the page queue is drained from anything but
the row. `register_registry.py` lines 92–96, 327, 466 and 518 all describe the
`user_view` or the connection store, which the plan keeps as they are.
`CLAUDE.md:334–349` and `internals/20_spa/050_datachanges/design.md:12–20`
describe the row's queue, `subscribe_page_store` and `item_lock` coherently
with the code.

## Final state

- Linter: `ruff check <file set>` → `All checks passed!` (also `ruff check
  src/ tests/` → `All checks passed!`).
- Suite: `python -m pytest tests/ -q` → `1817 passed, 2 warnings`.
- Files reviewed: the 12 listed above. No file outside the set was touched.
