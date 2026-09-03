# Coherence review — wf/datachange-addressing

File set (from the `Files:` fields of Phases 1..3):
`src/genro_asgi/spa/register_registry.py`, `src/genro_asgi/spa/orchestration/spa_worker.py`,
`src/genro_asgi/spa/orchestration/spa_commander.py`, `tests/test_register_registry.py`,
`tests/orchestration/test_contract_page_store_row.py`,
`tests/orchestration/test_contract_phase3_data_plane.py`,
`tests/orchestration/test_contract_phase8_delivery_desk.py`,
`tests/orchestration/test_contract_phase9_request_exchange.py`,
`CLAUDE.md`, `internals/20_spa/050_datachanges/design.md`,
`internals/20_spa/050_datachanges/README.md`.

## Auto-fixed
- `spa_worker.py:collect_page` docstring: one 118-column line reflowed to two
  (`row has ONE list and ONE index...` / `The exchange happens on EVERY request...`).
  Prose only, no wording change. Tests re-run green after it.
- `ruff check` reported nothing to fix on the file set at any cycle: one cycle, no
  second pass needed.

## Flagged for human
- Nothing. No docstring in the file set says an addressed write waits for the
  exchange or that the slot carries datachanges. Verified by reading each site:
  - `set_datachange`, `reset_datachanges`, `drop_datachanges` — each says the local
    branch appends on the row and every other address leaves as ONE CALL.
  - `collect_page` — "Empties the request slot" stands, and is accurate: the slot
    still carries `dbevents`, only `datachanges` left it.
  - `op_exchange` — says outright that the addressed writes arrive by their own op
    and do not ride the exchange; its signature carries no `datachanges`.
  - `op_on_datachange` — states the desk is the authority on existence and that
    `{"filed": False}` is what the verb raises on.
  - `PARCEL_PAGE_REBUILT_FIELDS` comment — says `datachanges` is a plain list that
    travels with the row, which the row-append leaves true.
- No design divergence from the pattern reference: the append is the one
  `RegisterRegistry.append_page_datachange` (registry definition, the
  `subscribe_page_store` subscriber, the local verb branch, and `collect_page` on
  what the desk returns — four callers, one index).
- The `Must not break:` lines hold: `collect_page` keeps
  `{"datachanges": [...], "dbevents": [...]}`; `deliver_slot_deposits` untouched;
  the phase14 refusals stand (`filters` → `NotImplementedError`, unknown target →
  `KeyError` naming it, judged at the desk); `user_view` / `new_collector` /
  `user_store_change_map` and the STATE kinds unchanged; `item_lock` still
  exclusive and re-entrant, `dispatch_lock` outside it.

## Final state
- `ruff check src/ tests/` — All checks passed.
- `pytest tests/ -q` — 1828 passed, 96% coverage.
- Commits: `cb126fc` (Phase 1), `37fe39a` (Phase 2), `d9c3ec5` (Phase 3).
