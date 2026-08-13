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

---

## Phase 3 — Zone reading: the tests that cement

**Five of seven species-1 defenses are uncemented.** The strip experiments
answered the phase's own question with numbers: removing D2, D3, D4, D5 or D6
breaks no test at all (249 passed each time). Only D1 and D7 have a test
apiece, and both of those tests construct by hand a scenario production cannot
produce — a faked in-process worker called directly (tests/test_spa_move.py:2462-2467)
and eight floor samples sharing one `time.time()` reading
(tests/test_spa_evaluator.py:518-521). That is the shape of the finding: the
guards were not added because a test demanded them.

**D4 and D7 were stripped INTO a loud error, not out.** Removing a `return`
that silences a branch proves nothing — the test suite would pass either way.
Replacing it with an `AssertionError` makes any test that reaches the branch
explode, so silence is evidence of unreachability rather than absence of
assertion. D4 stayed silent (uncemented); D7 exploded, naming its one test.

**D7 has no "remove" option, and the card says so.** Without the `return None`
at evaluator.py:292-293, `max(velocity, accelerated)` at evaluator.py:298 would
compare None with a float — a loud error, but three lines away from its cause.
The card offers only "keep" or "make it loud here", so phase 5 does not write a
removal proposal that cannot be executed.

**The `LocalPool.settled` hygiene item has no referent (second confirmation).**
Phase 1 recorded it as a claim to verify; phase 3 was to locate it. It is not
there: `LocalPool` (tests/test_spa_move.py:149-189) has no `settled`; the live
helper `settled_at` (tests/test_spa_move.py:78) has 17 callers; and the only
`None` convention the class uses — `process=None` — is still admitted by
`new_roster_row`'s signature (commander.py:976) and read in three live places
(commander.py:863, 1089, 1136). Recorded as a no-removal card that hands
phase 5 the "Scartate" motivation, since a hygiene item that cannot be located
must land somewhere rather than evaporate.

**A defensive-looking test is not automatically a ledger entry.** The reading
sweep found three families that look like species 2 and are not: the loud-error
contract tests (tests/test_spa_commander.py:393-410) are the house rule's own
test face, and the "unknown worker" tests of the observers guard a window that
tests/test_spa_monitor.py:130 documents as real. They are recorded as non-entries
so phase 5 does not mistake them for cementing tests.
