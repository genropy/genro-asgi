
## Phase 1

Three choices the plan did not settle, all forced by the push existing at all:

- `tests/orchestration/child_stub.py` learned `/op/subscribed_tables`. The push
  fires unconditionally at the first presentation, so every stub-based test now
  receives an op the stub answered with a `KeyError` and died on (16 failures,
  heartbeat and envelope-chain included). The stub records the set in
  `subscribed_tables`, exactly as a real worker does. This is a file outside the
  phase's declared `Files:`; it is declared here and in `> Files:`.
- Two contract tests of `test_contract_phase8_delivery_desk.py` beyond the one
  the plan named: `test_every_exchange_reply_carries_the_subscribed_table_names`
  asserted the behaviour this phase removes and was deleted (the new
  `test_contract_subscribed_tables_broadcast.py` carries the replacement
  behaviour); the `exchange()` helper and the retirement assertion of
  `test_the_exchange_returns_the_callers_own_events_in_the_same_round` dropped
  their `tables` key. The plan's rule "any other test asserting `reply["tables"]`
  or `result["tables"]` is adjusted the same way" covers both.
- Every test reading `worker.subscribed_tables` right after a `subscribeTable`
  now waits for it (`wait_for(... == set(lane.desk.subscribed_tables))`), because
  the refresh is an unawaited task instead of the call's own reply. Sites in
  phase4, phase9 and phase13. `test_the_new_page_announcement_carries_the_rows_subscriptions`
  was restructured for the same reason: any wire round-trip drains
  `worker_events`, and the push is one, so the births are read BEFORE the
  subscribe instead of after it. The assertions themselves are unchanged.

## Phase 2

- The `two_lanes` fixture waits for lane 1's `subscribed_tables` to carry the
  table before the test commits. The subscription is filed on lane 2, and the
  Phase 1 push that teaches lane 1 the set is a task: without the wait the
  source filter of lane 1 is a race, and a filtered-out commit would read as a
  defect of this phase.
- `_serve_on_thread` keeps `answer["connection_id"] = ...` OUTSIDE the `try`:
  the delivery must run on a failure, but nothing may be read off an `answer`
  that was never produced.

## Phase 4
The docstring findings were reported, not rewritten: the phase's own Decisions
designate that class of finding for `review.md`, and an edit to
`spa_worker.py` would have put a source file outside the review's own diff.
`ruff format` disagrees with 6 of the 12 code files; the project's gate is
`ruff check` only, and reformatting would rewrite lines Phases 1..3 never
touched, so it was left alone and flagged instead.

## Run inspection

- 4/4 phases done, no repair, no consult, no blocked phase; `EVENT: run-end ok 4/4`.
- Phase 1 touched `tests/orchestration/child_stub.py` outside its `Files:` (the test double had to answer `/op/subscribed_tables`) and deleted one contract test beyond the plan's two (`test_every_exchange_reply_carries_the_subscribed_table_names`, asserting the removed behaviour); both declared in `> Files:` / this file.
- Phase 3 edited `SpaWorker.subscribeTable`'s docstring in `spa_worker.py` outside its docs-only `Files:` to satisfy its own `Done:` grep (`closed by construction`); declared in `> Files:`. The plan should have listed the file.
- Phase 4's commit was denied inside the sub-session: the `pre-commit-rules.sh` PreToolUse hook answers `ask` on `git commit`, and its `PHASED_UNATTENDED=1` exemption is not present when the run is launched through `/goal`. The staged files were committed by the foreman session after `run-end` as `a2e2562`.
- Three items flagged for human in `review.md`: the `notifyDbEvents` docstring (two exits now), the `spa_console.py` help text, `ruff format` drift on 6 files (repo decision).
