# Notes — wf/17-design-audit

## Phase 2

Choices this phase made that the plan did not settle.

**H2 recorded as superseded-candidate, not as a finding.** The plan told phase 2
to write "the exchange docstring hygiene item (commander.py ~1279: says the
commander discards an in-flight user's datachanges)" as one card. That sentence
does not exist in the tree: `exchange_destinations`' docstring
(commander.py:1266-1273) is about addresses the surface cannot resolve and
matches its own code (commander.py:1288-1292), and the two texts that do speak
of an in-flight user (commander.py:1783-1786, 180-181) say the move machinery
parks and salvages — never that the commander discards. Writing the card as if
the defect were there would have put a fabricated quote in walkthrough material.
The card therefore states what each candidate text actually says, and hands
phase 4 the only place left to look (worker.py, the zone this phase does not
read, where "the worker discards" would be documented). Rejected alternative:
silently dropping the item — the plan requires it to land somewhere, and a
silent drop is what the phase-5 "Scartate" rule forbids.

**D8: the guards verified NECESSARY are a card, not an omission.** Species 1
hunts guards no caller can reach. Six guards in the same code look like
siblings of the ones proposed for removal but are load-bearing — most
sharply commander.py:3138, where dropping the `!= "dead"` check would let
`retire_worker` flip a tombstone back to `draining` and SIGTERM it
(commander.py:1083-1084). Phase 3 strips guards experimentally; without this
card it would strip them for symmetry and read the falling tests as cementing.
So the card records the reachability proof for each, as a do-not-touch list.

**Named authorities-of-origin instead of verdicts on two accretions.** The three
`trigger_*` twins (commander.py:2687-2718) and the accelerated half-series fit
in `worker_floor_velocity` (evaluator.py:294-298) are both unrequested by any of
the three authorities — the second one is justified only in its own docstring,
which the ratified rule ("design and review start from ratified decisions")
excludes as a decision record. Both are written as proposals naming that
absence, with the line-count answer to "written today from the ratified story",
never as defects. Nothing dies by default in this run.

**Two anchors of the issue corrected in passing, inside the cards.**
`RECYCLE_RETRY_SECONDS` is a public-by-use constant that `__all__` does not
list (commander.py:304-321) while the tests import it
(tests/test_spa_move.py:58) — recorded under F6, since the baptism list is
where an undeclared public name belongs. And the same constant times three
unrelated things (503 window, recycle re-pick gate, stall-report throttle),
which is C3's whole subject.
