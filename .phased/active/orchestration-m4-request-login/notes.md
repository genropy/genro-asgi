# Notes — orchestration-m4-request-login

## Phase 1

**Test rewritten, declared (rule 10).**
`tests/orchestration/test_orchestration_heartbeat.py::test_each_task_of_the_vertex_runs_on_its_own_count_of_beats`
is an IMPLEMENTATION test and was rewritten in this phase. It failed once in
three full-suite runs, and the code was ABSOLVED: `every` counts `runs` BEFORE
awaiting the body (beats.py), and the test cancelled the clock mid-round, then
asserted a whole-round relation (`turns(cleanup_frozen) == runs(drop_expired_users)`).
A round truncated inside `drop_expired_users`' own `asyncio.to_thread` left
`cleanup_frozen` one turn behind. The 15 tests this phase adds — two of them
spawning real children — widened the window enough for it to fire.

The rewrite stops the clock ON A ROUND BOUNDARY (the last task of the round has
caught up with the first) instead of widening the assertion, and the relations
became EXACT where they used to be a tolerance:
`runs(drop_expired_users) == beats`, `runs(check_resources) == beats // 2`,
`runs(cleanup_frozen) == 0`, `turns(cleanup_frozen) == beats`.
The owner ruled on 2026-08-18: widening the assertion for good (the other road)
would blunt a bite the M3 hunt taught to keep sharp.

**A verb born after the `_TBD` round: `expect_death`.**
The dry shutdown killed every child with `terminate_process`, and `on_child_lost`
denounced each as a WILD death — a false classification (a shutdown IS an order)
that would have written N alarms into the orchestration log at every clean stop
and taught the sysop to ignore them. `GroupHandler.stop` now declares the death
before dealing it, one line per kill, through a public verb on `WorkerHandler`
that wraps the primitive already in the house (`_park_death_wait`). The name is
the reader's own word: `on_child_lost` says "the parked wait says whether anybody
was EXPECTING it". `order_death` was rejected — it collides with `_order_quit`,
which really does send an order to the child.

**The six `_TBD` of the phase, baptised 2026-08-18**: `default_group` (the
property, the constructor kwarg and the key `commander_kwargs()` folds in) ·
`user_hold_event_map` · `await_user_release` · `record_user_group` ·
`start` / `stop` on the vertex · `stop` on the group.

## Phase 2

**The nine answers of the walkthrough** are in `temp/domande_fase2_m4_2026-08-18.md`
and summarised in the phase's `Done:` block. Two of them are worth finding again
from here:

- **No deadline on the CALL** (question 3) is a DECLARED ABSENCE, not an
  oversight. A child running an endless query is not mute — it answers its pings
  and the machine reads it as healthy — so cutting the wait would create a worse
  problem: a REPLY arriving for nobody while the query keeps running. The real
  patience belongs to the browser and its proxies. The day it is needed it will be
  the FRONT's (a `wait_for` around the surface), never machinery of the connector.
- **A dead worker still in the map** (question 9) falls through to a 502 instead
  of being re-placed. Re-placing before the burial would race with
  `report_death`, which has to settle the dead worker's account before its users
  start again. The window is short by construction (`on_child_lost` rings the
  wake, so the round that buries is anticipated), the outcome is loud and
  self-healing, and an unlucky user reloads.

**The four `_TBD` of the phase, baptised 2026-08-18**: `serve_request` ·
`SiteFailedRequest` (the worker is healthy — it ANSWERED; what failed is the
hosted site, and an exception naming the worker would send the sysop to suspect
the wrong thing) · `SHAPE_REVIEW_SECONDS` (the name says the ORIGIN, because the
origin is what defends the derivation: whoever reads `RETRY_AFTER_SECONDS =
HEARTBEAT x BEATS` would one day "simplify" it to 30.0 and the promise to the
browser would start lying; the HTTP word stays on the exception's `retry_after`
field, which is where HTTP begins) · `SITE_PATH_PREFIX` (the exact twin of the
legacy `OP_PATH_PREFIX`: two prefixes, two families of paths on one wire).
