# Phase 4 — Coherence review

Scope: only the files written by Phases 1..3.

- `src/genro_asgi/spa/subscription_index.py`
- `src/genro_asgi/spa/orchestration/spa_commander.py`
- `src/genro_asgi/spa/orchestration/worker_handler.py`
- `src/genro_asgi/spa/orchestration/spa_worker.py`
- `tests/orchestration/conftest.py`
- `tests/orchestration/child_stub.py`
- `tests/orchestration/test_contract_phase4_dbevents.py`
- `tests/orchestration/test_contract_phase8_delivery_desk.py`
- `tests/orchestration/test_contract_phase9_request_exchange.py`
- `tests/orchestration/test_contract_phase13_desk_projection.py`
- `tests/orchestration/test_contract_subscribed_tables_broadcast.py`
- `tests/orchestration/test_contract_slot_deposit.py`
- `CLAUDE.md`
- `internals/20_spa/060_dbevents/design.md`

## Auto-fixed

None. `ruff check` reported zero errors on the file set at the first cycle, so
the convergence loop closed after one pass with nothing to fix. No unused
import, no tool-fixable finding, no mechanical fix was applied.

## Flagged for human

1. **`src/genro_asgi/spa/orchestration/spa_worker.py:1341`** — the narrative of
   `notifyDbEvents` still says the deposits leave with the collect only:
   *"Lays the deposits on the request slot, whence the end-of-request exchange
   carries them to the desk."* After Phase 2 the slot has two exits: the
   exchange inside `collect_page`, and `deliver_slot_deposits` through
   `/desk/deposit` in the `finally` of `_serve_on_thread`. This is the docstring
   class the phase was told to report rather than rewrite.
   Suggested action: replace the clause with one naming both exits — the
   exchange when a `collect_page` comes, the end-of-request deposit otherwise.

2. **`src/genro_asgi/applications/spa_console.py:22`** — the console help text
   names `commander.delivery_desk.subscribed_tables` as a surface. The property
   still exists and the text is not wrong; flagged only because it is the one
   place outside the file set that documents the set, and it says nothing about
   how a worker now learns it. Out of the phase's file set, so untouched.
   Suggested action: none required; a one-line mention would help a reader who
   arrives from the console.

3. **`ruff format` disagrees with 6 of the 12 code files** (among them
   `test_contract_phase8_delivery_desk.py` and
   `test_contract_phase9_request_exchange.py`). The project's gate is
   `ruff check`, not `ruff format`, and reformatting would rewrite lines these
   phases never touched. Left alone deliberately.
   Suggested action: a formatting decision for the repo, not for this plan.

No logic error, no divergence from the pattern references, no missing edge case
was found. `DeliveryDesk.file_dbevent` remains the only writer of
`page_dbevent_map` (`op_deposit` calls it). `collect_page` still delivers AND
retires, and returns `{"datachanges": [...], "dbevents": [...]}` unchanged. The
six `wf:phase-1:new` / `wf:phase-2:new` markers are in place on the six new
callables and on no others.

## Final state

- `ruff check` on the file set: `All checks passed!` (zero errors).
- `pytest tests/ -q`: 1809 passed, 3 warnings; coverage 97%.
- Files reviewed: the 14 listed above; no file outside that set was modified.
