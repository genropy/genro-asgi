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

## Phase 4

**The ebook's per-module numbers are STATEMENTS, not lines — and the plan's own
prediction was wrong about it.** 00_authorities:360-363 warned phase 4 to expect
a count drift, offering "commander.py è oggi 3183 righe" as evidence. The book's
table header reads `Modulo · Ruolo · Stmt · Cov`
(docs/html/architettura_blocchi.html:610), so the figures are coverage.py
statement counts: measured today, nine of ten modules match to the digit
(worker.py 782, register_registry 146, evaluator 124, global_store 75,
worker_entry 69 at 72%, register 66, environ 60, subscription_index 44) and only
commander.py moved, 1209 → 1212, taking the block total 2.580 → 2.583. The card
records the +3 and the method correction together, because a reader who inherits
the wrong reading will "fix" numbers that are already right.

**A claim can be true of what travels and false of what is stored.** E22 ("i
registri contengono dati serializzabili per costruzione, mai oggetti vivi come
verità") is upheld by the move machinery — MOVE_REBUILT_FIELDS
(worker.py:341-343) and LIVE_ROW_FIELDS (worker.py:333-337) keep every live
object out of the parcel and out of every op result — and contradicted by the
rows themselves: a page row carries `collector`/`user_view`
(register_registry.py:308-324) and a roster row carries `process`/`caretaker`
(commander.py:29-31, 976). Recorded as a disagreement whose option (a) is
explicitly "no code": the alternative would be the opposite of the ratified
design, and the register whose rows hold OS handles is never serialized at all.

**Two ebook claims describe the same window and disagree with each other.** E4
says a request arriving mid-move "deve attendere, non fallire"; E14 says the
person "continua a essere servita dove si trova". The code parks the call on the
per-user barrier (commander.py:2087, 2617-2624) and releases it at
commander.py:2612-2615: waiting is right, "being served" is not. The card is
filed against the book, not the code — there is nothing to implement — so that
phase 5 does not open a work entry for it.

**Where the audit found real holes, it named the delivered guarantee instead of
the missing one.** E4's second clause and E21's lifecycle clauses are the two
genuine absences. For E4 the point is not that a rollback is missing but that
the evict is the point of no return (worker.py:2251), so what the system
actually promises is "the slice lands somewhere or dies loudly"
(commander.py:2481-2498, 2603-2610). Stating the delivered guarantee is what
lets the owner choose option (b) — amend the book — with the same confidence as
option (a).

**Lens 2 on this zone produced proposals, and two deliberate non-proposals.**
SD1..SD5 are five species-1 candidates, each with its coverage evidence (37 of
worker.py's 782 statements are unexecuted, and the never-run branches are named
line by line). SI1 (`Outbox.ping_now`, worker.py:440-443) is the zone's one pure
dead surface: no caller in src/, one test asserting it. SI2 refuses to propose
removing the three `RegisterRegistry` one-line forwarders — the module docstring
declares them an extension seam (register_registry.py:48-61) for a consumer that
lives in another repo — and SI4 records `holds_target` as an examined keep. A
zone audit that only proposes deletions teaches the next reader that everything
thin is waste.

## Phase 5 — consolidation: what an ordering pass can and cannot add

**The registers add ordering, not findings — and the ordering is the deliverable.**
Sixty-one cards spread over three zone files are unreadable as an agenda: the same
guard appeared once from the code side (D-series) and once from the test side
(T-D-series), and the dependency between C1's evacuation castle and five other
cards was invisible while they sat in different files. The two registers say what
the zone files could not: L1 must be decided first because its outcome moves L3,
L7, L18, L4 and the two baptism entries R13/R16 — the report-of-stall decision
either keeps a name and a roster field alive or kills both. Ordering by leverage
also put the twenty-one entries in an order where the first four are worth ~200
lines and the last seven are worth a condition each; a flat list of cards hides
that ratio.

**One entry differs in kind from all the others, and the register says so.** R4
(the ledger-gated spawn) is the only entry whose verdict also decides *which
authority prevails*: BRIEF Q4 admits "if the room is there, no new process at
all", NOTES notes:11-13 requires the successor registered before the flag, and the
code implements the NOTES. Every other fidelity entry asks "code or book?"; this
one asks "brief or notes?" first. Marking that in the entry itself, rather than
leaving the owner to notice mid-walkthrough, is the difference between an agenda
and a list.

**The "Scartate" section is where an audit earns trust.** Eight cards do not become
entries — D8's six necessary guards, the tests-side record of the same, I4, SI2,
SI4, TS1, TS2, and the `LocalPool.settled` item with no referent — and each carries
its motivation in one row. Without that section a reader cannot distinguish a card
that was examined and archived from a card that was forgotten, and the next run
would re-discover all eight. The count line closes the loop: 29 cards in the
ledger's entries + 8 discarded + 24 in the reconciliation record = every card
accounted for, verified programmatically rather than by eye.

**A consolidation phase can find a gap the zone phases could not: eleven ebook
claims were never brought to a card.** Phase 1 inventoried 36 claims and tagged
them by zone; phase 4 verified all 25 tagged `spa-world`; the 11 tagged
`recycling-code`/`tests` were assigned to phases 2 and 3, which worked by fidelity
points and strip experiments and never cite an `E`/`B` identifier. Only a phase
reading all four files together sees it. The temptation was to verify them here —
that would have been new audit work in a phase whose mandate is to order existing
findings, and it would have produced eleven claims with no zone evidence behind
them. Recorded as §5 of the reconciliation record: a coverage gap with two
options, one perimeter decision for the owner. Two of the eleven (E24 "operativo",
B6 "Consolidato") cannot be answered by measurement at all — they ask the owner to
weigh a word against the four fidelity deltas R1..R4, which is walkthrough
material by construction.

## Run inspection

- 6/6 phases done in one pass, no repair, no block, ~65 minutes total
  (13:10-14:15), all commits `wf(phase N): ...` on the branch.
- Phase 1's own commit was denied by the ask-mode pre-commit hook (the
  known unattended-session quirk in the plan Notes); the staged work
  landed inside phase 2's commit `86bdc0a`. One commit carries two
  phases; nothing lost. Later phases committed without incident — the
  quirk fired once, not systematically.
- Phase 3's seven strip experiments all restored byte-for-byte; the
  suite stayed green at every phase boundary (1569 passed / 2 skipped)
  and no committed state touches `src/` or `tests/`.
- Phase 5 surfaced a plan-level coverage gap the zone phases could not
  see: 11 of 36 ebook claims (zones `recycling-code`/`tests`) never
  reached a card, because phases 2-3 worked by fidelity points and
  strip experiments, not by the claims inventory. Recorded as §5 of
  the reconciliation record — a perimeter decision for the owner, not
  invented findings.
- Phase 6 ran its three checks programmatically (641 file:line refs
  resolve, 59/59 cards accounted, 46 verdict slots all empty), made 9
  numeral-only auto-fixes and flagged 4 items for the owner in
  `review.md` — including the stale "14 cards" in phase 3's plan note,
  out of its write perimeter, to align at finalize if desired.
