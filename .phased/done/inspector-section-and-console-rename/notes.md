## Run inspection

- Run stopped by the foreman after the first EVENT, with 4/6 phases committed.
- One session executed FOUR phases. The launcher opened it as
  "Phase 1 — opus, effort low, mode light" and it went on to close Phases 1, 2,
  3 and 4, one commit each (246ff94, 9d47b82, 78d80ca, 889523e), reporting a
  single wall time of 19m17s and emitting one `EVENT: phase-done 1 4/6`.
  Reading: `low` effort selects light mode, whose slim `/goal` contract runs
  WITHOUT the execute-phase-agent skill — nothing held the one-phase-per-session
  boundary, and the goal-seeking session walked the plan. The session log
  (`log/phase-1.txt`, 6 lines) carries only its final message, about Phase 4;
  it holds no trace of the phase transitions.
- Consequence on the execution config: Phases 2 (medium), 3 (high) and 4
  (medium) were all executed at `low` effort in the slim contract. Phase 3 was
  rated `high` deliberately — its Details leave one judgement inside the phase
  (use the worker connector's existing fire-and-forget mechanism, never invent
  a frame type). It did not run at that effort.
- Phase 4 modified a file no phase declared: `src/genro_asgi/routed_application.py`
  (+8 lines) now branches on `isinstance(result, StreamingResponse)` in the
  dispatch of EVERY RoutedApplication, because no route could stream before.
  The phase annotated it in its Done. It is a type test on the shared dispatch
  path, added at low effort, and it is outside the `Files:` list Phase 6 was
  told to review — Phase 6 must cover it.
- Phase 5 died mid-flight when the launcher was killed. It never marked itself
  `[>]` and wrote no source file: `log/phase-5.txt` is empty and the tree
  carried no `src/` change. Nothing to reset, nothing to salvage.
- Suite state at the stop: 2111 passed / 2 skipped, `ruff check src/` clean
  (as reported by the Phase 4 session; not re-run by this inspection).

## Phase 5
- `inspector_section.py` needed no change: the placeholder and the real page are
  served by the same `page` route reading `resources/inspector.html`, so the
  phase touched only the resource and the contract test. Its `Files:` reflects
  what landed, not the plan's estimate.
- The tree is rebuilt from the census by FILTERING (`connection.user == user`,
  `page.connection_id == cid`) rather than by following the items' own `pages` /
  `connections` container fields: the census reduces a container of objects to a
  count, so those fields are not reliably traversable, while the scalar back
  references always are.
- The page derives its endpoints as siblings by stripping a trailing `/page`
  from `location.pathname`, so it works both at `.../inspector/page` and at
  `.../inspector/page/`.

## Phase 6
- The double `_census_field` evaluation in `spa_worker._census_register` was
  flagged rather than fixed: the one-line fix is a walrus binding, and `:=`
  appears nowhere in `src/`, so the fix would have introduced an idiom the
  codebase does not use — outside what a coherence phase may decide alone.
- The only auto-fix of the phase is formatting: the `__all__` of
  `server_sections/__init__.py` had grown past the declared `line-length = 100`
  without ruff noticing (`E501` is not in its `select`).

### Second launch (Phases 5-6)

- Relaunched after the stop with 4/6 already committed. Both remaining phases
  ran one-per-session as intended (`phase-done 5 5/6`, `phase-done 6 6/6`,
  `run-end ok 6/6`) — neither is `low` effort, so neither entered light mode
  and the boundary held. Phase 6: 8m35s at opus/xhigh/full.
- Phase 6 reviewed `routed_application.py` too, the file Phase 4 touched
  without declaring it: its verdict is that nothing in the set is a logic
  error or a pattern divergence. One auto-fix only — the `__all__` of
  `server_sections/__init__.py` at 133 chars against the declared
  `line-length = 100`, invisible to ruff because `E501` is not in its
  `select = ["E4", "E7", "E9", "F"]`.
- Seven items flagged for the human in `review.md`. Two of them are the
  consequences of decisions taken during this run and worth the owner's eye:
  the double observation event per worker mutation (worker report + vertex
  relay, both asked for by Phase 3), and `_observation_switched` named as a
  state while it means "the spawn-time catch-up already fired".
- Final state: 2112 passed / 2 skipped, coverage 96%, `ruff check src/ tests/`
  clean, tree clean. One human check outstanding in `verify.md` — the browser
  pass on `/_server/inspector/page` with `GNR_ASGI_INSPECTOR=1`.

## Panel review (quality check)

16 agents: 4 dimensions in parallel (correctness, cross-phase coherence,
pattern conformance, test coverage), 18 raw findings, 14 after dedup, the top 4
by severity put under 3 refuting skeptics each. 2 confirmed, 2 dismissed, 10
left unverified by the cap.

**Confirmed and FIXED here** — `GNR_ASGI_INSPECTOR=1 pytest tests/` was 2 failed
/ 2110 passed: the two contract tests that photograph the whole `_server`
section list read the developer's environment, because `server_app.py:145`
consults the variable at construction. An autouse fixture in
`tests/test_server_application.py` now removes it for that module (the shape
`test_inspector_section.py::plain_server` already used). Commit `4ab02e2`;
green with the variable set and unset alike.

**Confirmed, NOT this workflow's, open** — no ASGI source in this repo reads
`http.disconnect`: `StreamingResponse.__call__` never touches `receive`, and
uvicorn's `send` returns early on a disconnected client without cancelling the
app task. Two of the three skeptics reproduced it on uvicorn 0.37: close the
tab and the SSE generator stays blocked on `queue.get()`, so the `finally`
never unsubscribes, `observation_watched` stays True and every worker keeps
reporting for a reader that is gone. Cost corrected from the original filing:
a detached task plus a lane frame per mutation, NOT a round trip inside the
traffic path (`report_observation` is fire-and-forget). Locus is
`streaming.py` / `sse.py`, untouched by this workflow, and
`applications/mcp.py:236` has carried the same gap all along — the fix is one
disconnect listener in the transport, serving both consumers.

**Dismissed 3/3, correctly** — two findings claiming the observation tests are
vacuous. The skeptics ran the neutralisations themselves: removing the
`observation_watched` half of the condition at `worker_handler.py:319` makes
`test_nobody_watching_leaves_the_worker_silent` fail. The tests kill the
mutation.

**Cap: 10 found and never adversarially verified.** Three checked by hand at
review time:
- the cookie alarm is FALSE: what the inspector's responses carry is the
  server's own session cookie, never `sticky_cid` — the non-negotiable holds.
  The test is weak (it asserts against a server with no SPA front), not wrong.
- `_get_worker_census` (spa_commander.py:1018) does catch everything into
  `{"error": ...}`, so a DEAD worker is covered as the Done required; but
  `connector.call` is called with no `timeout`, and a worker that is alive but
  MUTE holds the census route waiting indefinitely. Real, and adjacent to what
  the Done named rather than inside it.
- the subscriber queue has no `maxsize` (inspector_section.py:116), so the
  documented `except asyncio.QueueFull` drop in `publish_observation` is dead
  code. Not a memory risk (the server-side generator drains regardless of the
  browser) — a contract that says one thing while the code does another.
The remaining seven, unverified: `census()["dbevent_deposit"]` always empty in
the new core, the task exception never retrieved in
`_fire_observation_switch`, two overlapping census fetches racing in the page,
`answer_call`'s docstring still saying "four ops" where there are now six, and
a test awaiting a queue with no deadline that would hang instead of failing.
