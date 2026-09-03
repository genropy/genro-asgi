# Notes — wf/datachange-addressing

## Run inspection
- Run 2026-09-03, 4/4 phases, `run-end ok`. A first launch died at once: the sub-session's OAuth session had expired (`claude /login` fixed it, nothing touched).
- Phase 1 rewrote a contract test the plan had not declared: `test_contract_phase9_request_exchange.py::test_set_datachange_to_any_target_travels_through_the_commander` asserted the "no local shortcut" behaviour D-DC4 replaces; now `test_set_datachange_to_a_page_of_the_caller_lands_on_its_row`. Coherent with the ratified decision, undeclared in the plan.
- Phase 2 left its seven files STAGED, not committed: the `pre-commit-rules.sh` hook asks an interactive confirmation the sub-session cannot give (known quirk). The Phase 3 session committed them as `37fe39a` before starting its own work, so no mixed commit.
- Phase 2 recorded that the desk judges a target's existence against `page_connection_map` / `user_map`, fed by the worker events that ride every REPLY (`send_reply`), so a page is known at the vertex from the end of the request that created it. The phase's note claimed a `KeyError` for a page born in the caller's own request: wrong, such a page belongs to the caller and takes the local branch. A page of ANOTHER user is addressable only once its id left with that REPLY, so the window is unreachable; `KeyError` remains the case of a page already dropped at the vertex. No decision open.
- Phase 2 found five exchange sites carrying `datachanges` in `test_contract_phase8_delivery_desk.py`, not the three the plan's line numbers named; `_refuse_unservable_address` also lost its `target` parameter (no reader left).
- Phase 3 and Phase 4 ran in the same session (`phase-done 3 4/4`); Phase 4 auto-fixed one docstring line width only, flagged nothing.
