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

## Phase 3

**The eight clarifications** are in `temp/domande_fase3_m4_2026-08-18.md`. Three of
them settle things a future reader will look for:

- **The verb drops the guest's transfer flag in its own synchronous breath**
  (question 4), so the race never happens: at the tail of the call there is ONE
  departure, not two. Freezing a guest who is ceasing to exist would write a
  parcel only the reaper will ever read.
- **A refused write is a legitimate degraded shape** (question 5), not a failure
  to repair: the person stays resident on the worker he logged in on, with his
  connection attached — the legacy's own "prior == worker: nothing to do". The
  flag is dropped either way, so there is no retry on the next request. Declared
  residue: if his next request places him on ANOTHER worker, the rows left here
  are orphans and the guest's store is lost; the disk failure that caused it is
  already an alarm, and the machine stays correct.
- **The empty round when the target is already here** (question 6) is ACCEPTED:
  the connection goes to the deposit and comes back on the next click, on the same
  process. "For everybody, no branch" is ratified to the letter, and a login onto
  a worker where the person is already living is a coincidence, not the common
  case.

**The five `_TBD`, baptised 2026-08-18**: `relabel_connection` — the SAME word at
two rungs (the worker relabels in its registers, the vertex in its indexes), which
is the cascade homonymy `add_user` already has · `connection_relabeled`, the
participle of that verb, in the family `<subject>_<participle>` · `freeze_connection`,
the exact brother of `freeze_user` (`settle_login` was rejected: in the legacy it
is the vertex's DECISION, and reusing it would be homonymy by drift) ·
`_login_previous_user_map`, whose value is an identity and says so ·
`_release_login_rows` and `_install_carried_store` aligned to the two above without
a round of their own.

## Phase 4

**The six clarifications** are in `temp/domande_fase4_m4_2026-08-18.md`. The one
that outlived them all is not among them: mid-phase the owner corrected the
OWNERSHIP of the pool, and R11/R12 were rewritten (record v1.1). What the
correction turned on is a fact that was in front of us the whole time —
`SpaApplication` owns its commander and is configured through the open-signature
`application(...)` element — and what I had presented as a constraint (an
application cannot hold its own pool configuration) was never true.

Consequences worth finding again from here:

- **The site dialect no longer has words for a pool.** A recipe that writes
  `configuration().commander(...)` now fails, and a test pins it.
- **`node_label="commander"`** on the front's grammar element: without it the
  builder files the node as `commander_0`, because the singleton cardinality that
  used to come from the parent's `sub_tags` is gone with the move.
- **The 503 says nothing about WHY.** Three reasons reach the front as
  `AssignmentRefused` — a saturated group, a broken group, an expired hold — and
  the reason travels in the exception's `cause`, to the log. Telling the browser
  which one would leak how full the pool is and give a client nothing it can act
  on. What COULD depend on the reason is the `Retry-After` (an expired hold is a
  different scale from a group that has to wait for its own round); it does not
  today, and that is a declared uniformity, not an oversight.
- **Resource exhaustion is not the 503's business.** Machine memory and freezer
  storage are read by `check_resources`, which writes its order row and calls
  `need_resources()` — the seam a k8s commander overrides. The real escalation
  verb, `notify_sysop` (v3 §9), arrives with the notifications in Macro 5, and
  these three points are its callers.

**Pending, at the owner's request**: an audit of the naming convention he stated
during this phase — a module constant and its grammar key are the SAME words and
differ only in case (`FOO_BAR_SPAM` / `foo_bar_spam`), while a PARAMETER is free
to take the short contextual form (`spam`, `current_spam`). To be checked over the
whole codebase, as work of its own.

## Phase 5

**Six clarifications, all ratified before a line was written**: the story enters
at the ASGI level through `AsgiServer.__call__` and not through a socket (the
manual Verify is the transport proof; a uvicorn of our own would duplicate it and
would blind the assertions, which read `user_worker_map`, `hosted_users` and the
freezer riga by riga); the ASGI scaffolding lives in the ROOT conftest, the only
place a contract test and an implementation test both reach by construction —
the reverse would make the stable depend on the volatile; the observation window
is the RESPONSE BODY, because an op whose only caller is a test does not get to
live in `src/` and because the body proves the road the store travelled, not that
a dictionary has a key; the pool grows to TWO workers before the stickiness
chapter, since an `X-Worker` asserted on a pool of one is the vacuous shape the
M3 hunt already caught once; the cadence of the shape is moved with
`check_occupancy.every_beats`, the knob `beats.every` documents; and the child's
instrumentation moves to a module of its own, story-free, because Macro 5 will
want it for a third end-to-end.

**The sequence of the pool's states is part of the design, not an accident.**
Stickiness needs the reception to refuse while the second worker admits (100 MB:
70% against a cap of 30, and 70% against 80); the refusal needs NOBODY to admit
AND the growth to be gated (85 MB: two processes holding 164% of the concession).
Raising `every_beats` does not cover the second one on its own — `GroupHandler.ping`
reads `ping_now_event` and passes `now=woken`, and a totally refused placement is
exactly what rings it — so the last chapter rests on the memory gate: a pool that
CANNOT grow, which is also the truer story.

**The defect the story found**, and the reason an end-to-end exists. R8 admits a
real previous identity at a login (the avatar switch), and phase 3 had taught that
to `SpaCommander.relabel_connection` alone, where the mistake had been loud (a
`KeyError`). Under it, `WorkerEnvelopeHandler` and `GroupEnvelopeHandler` went on
reading every previous identity as a guest ceasing to exist — and there the
mistake was mute: a person with a second browser open lost his place in the
process and his placement in the group, and the click after landed on a row just
born, throwing away the store still sitting in the process he had left. Nothing
raised. Both folds now ask `GUEST_PREFIX`, which is what the register one rung
down had always said (`_release_login_rows`). Neutralization verified by
reverting the fix: the e2e fails on the trail of the second browser.

**Declared, and to be closed within this macro**: the tail of a login deletes the
receiving identity's row when that connection was all he had on the worker, and
announces nothing — so `WorkerHandler.hosted_users` keeps a name whose rows are
gone. After chapter 6 `std_0002` still lists `mario`, who lives on `std_0001`; a
wild death of `std_0002` would report the loss of a user who is fine. It is the
same ledger as the M3 review finding on `hosted_users` (readers and no writer),
with the opposite sign, and it is a change to the protocol of the login — the
worker announcing a consequence instead of a fact — so it gets its own interview
and its own commit, before the end-of-macro review.
