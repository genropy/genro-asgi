# Context: wf/17-design-audit
Parent: main | Issue: #17
Mode: autonomous

## Objective
Design-vs-code audit of the spa world against three authorities: the ratified
wf#8 recycling brief (`temp/wf8_recycling_design_brief.md`), the wf#8 decision
record (`.phased/done/8-process-recycling/notes.md` on branch
`wf/8-process-recycling`), and the presentation ebook (`docs/html/`). Two
lenses — fidelity to the brief, essentiality/slimming — producing zone cards
with file:line evidence, consolidated into two registers. The run stops at the
cards: every verdict column stays EMPTY for the owner's walkthrough; the fix
phase is a later run. No source code is modified anywhere in this workflow —
not even the two known hygiene items (they are recorded as cards, not fixed).

All audit deliverables live in `.phased/active/17-design-audit/audit/` and are
committed with their phase. Deliverable prose is in Italian (walkthrough
material, matching the 2a audit precedents); plan, commits and notes stay in
English.

## Work Plan
- [x] **Phase 1**: Authority extraction — the faithful checklist
  - Pattern reference: `temp/audit_fedelta_2a_2026-08-02.md` (verdict-table shape), issue #17 body (the enumerated points)
  - Files: `.phased/active/17-design-audit/audit/00_authorities.md` (new)
  - Decisions:
    - Sources read verbatim, never paraphrased: every claim carries a quote and its source anchor (file + line for the brief, section heading for notes.md and the ebook).
    - notes.md is read from the branch: `git show wf/8-process-recycling:.phased/done/8-process-recycling/notes.md`.
    - The ebook is read from the HTML twins (`docs/html/presentazione_2_stato_orchestrazione.html`, `docs/html/architettura_blocchi.html`), never the epub.
    - Each extracted claim is tagged with the zone it applies to: `recycling-code` (commander.py/evaluator.py), `tests`, `spa-world` (worker + satellites).
  - Details: Read issue #17 (`gh issue view 17`), `temp/wf8_recycling_design_brief.md` (277 lines), the wf#8 notes.md (171 lines, via git show), and the two ebook HTML files (strip markup, read the prose — part 2 covers the spa world). Write `audit/00_authorities.md` with four sections: (1) **Fidelity points** — the six lens-1 points from the issue (planner task with decision_interval 300s vs the beat XOR third force; the PLAN model one-reading→redistribution→replacements-from-the-worst→compaction; designated_reception; ledger-gated spawn from capacity_headroom; floor_series_depth 48-vs-72 and minimum fit points 3-vs-6; the baptism list), each with the authority's verbatim words and anchor. Known fact from planning: `planner`, `decision_interval`, `designated_reception` have zero hits in `src/genro_asgi/` — record this. (2) **Baptism list** — the 10 names from the issue (`floor_slope` in evaluator.py; `wait_worker_ready`, `drain_order`, `advance_evacuations`, `evacuation_pass`, `evacuate_user`, `warn_stalled_evacuation`, `regeneration_failed_at`, roster fields `evacuating_since`/`evacuation_warned_at` in commander.py) with what each authority says, if anything. (3) **Method** — the burden-of-proof questions from the 2a essentiality audit (who postulated this? what breaks without it? is there a shorter road?) and the four species from issue lens 2. (4) **Ebook claims inventory** — every checkable claim the ebook makes about the spa world, tagged per zone. Also record the two known hygiene items (LocalPool.settled in tests/test_spa_move.py reading the abolished None convention; the exchange docstring at commander.py ~1279 claiming the commander discards in-flight datachanges).
  - Done: `audit/00_authorities.md` exists with the four sections; contains all six fidelity points and all 10 baptism names; `grep -c 'planner\|decision_interval\|designated_reception' .phased/active/17-design-audit/audit/00_authorities.md` returns ≥ 3.
  > Done: `audit/00_authorities.md` written (six sections: fidelity points, baptism list,
  > method, ebook claims inventory, known hygiene, scope disclaimer). Six fidelity points
  > F1..F6, all 10 baptism names with a verified 2026-08-13 anchor each, 36 ebook claims
  > (E1..E26 from presentation 2, B1..B10 from the block architecture) zone-tagged.
  > The grep gate returns 10 (≥ 3). Absences confirmed by grep over `src/genro_asgi/`:
  > `planner` 0, `decision_interval` 0, `designated_reception` 0, `condemned_workers` 0;
  > `capacity_headroom` 2, `floor_series_depth` 5, `_FLOOR_FIT_MINIMUM = 6` at evaluator.py:91.
  > Suite 1569 passed / 2 skipped, `ruff check .` clean, `git status --porcelain` only under
  > `.phased/`. No source or test file touched.
  > Decided without asking (unattended): both known hygiene items are recorded as
  > claims-to-verify rather than as facts, because neither anchor resolved as the issue
  > states them — no `LocalPool.settled` symbol exists (the live helper is `settled_at` at
  > tests/test_spa_move.py:78) and the docstring at commander.py:1265-1273 speaks of
  > unroutable addresses, not of an in-flight user's datachanges (that text is at
  > commander.py:1783 and 180-190). Phases 2 and 3 resolve which text the issue meant.
  > Files: .phased/active/17-design-audit/audit/00_authorities.md

- [x] **Phase 2**: Zone reading — recycling code vs authorities
  - Pattern reference: `temp/audit_fedelta_2a_2026-08-02.md` (per-point verdict table with file:line), `temp/audit_essenzialita_2a_2026-08-01.md` (per-file essentiality verdicts)
  - Files: `.phased/active/17-design-audit/audit/zone_recycling_code.md` (new); read-only: `src/genro_asgi/spa/commander.py`, `src/genro_asgi/spa/evaluator.py`, `audit/00_authorities.md`
  - Decisions:
    - Both lenses on the source, in one read-through: lens 1 (all six fidelity points + the baptism names with their semantics as implemented) and lens 2 species 1, 3, 4 (impossible-scenario defenses; meaningless indirection — one-line forwarders, single-caller helpers, name-without-concept layers; patch castles — for each accretion zone answer "written today from the ratified story, how many lines?"). Species 2 (cementing tests) belongs to Phase 3, not here — but each species-1 defense card must name the guard precisely enough for Phase 3 to strip it.
    - Prime suspects for species 4, per the issue: the five panel/fix spirals of wf#8 — evacuations, floor series, replacements.
    - Cards are proposals with EMPTY verdict slots. House rule for species-1 proposals: remove, or replace with a loud error — never silent handling.
    - The exchange docstring hygiene item (commander.py ~1279: says the commander discards an in-flight user's datachanges; it now ships them and the worker discards) is one card in this file.
  - Details: Read `audit/00_authorities.md` first, then commander.py (3183 lines) and evaluator.py (360 lines) in full. For every fidelity point: quote what the authority says (from 00_authorities.md), state what the code does with file:line, classify the delta (conforms / drifted / absent / superseded-candidate). For every baptism name: file:line of definition, its actual semantics in one sentence, 2–3 rename candidates or "keep" with reason (the owner baptises at walkthrough). For lens 2: one card per finding — the guard/indirection/castle, file:line, who can reach it (caller analysis), the concrete proposal (remove X / merge Y / rewrite Z in ~N lines). Write `audit/zone_recycling_code.md`: section per lens, one card per finding, every card with file:line.
  - Done: `audit/zone_recycling_code.md` exists; contains one card per fidelity point (≥ 6), one card per baptism name (10), the exchange-docstring hygiene card; every card carries at least one `file:line` reference; `git status --porcelain` shows changes only under `.phased/`.
  > Done: `audit/zone_recycling_code.md` written — 33 cards, every verdict slot EMPTY:
  > 6 fidelity (F1..F6), 10 baptism (N1..N10 with semantics + 2-3 candidates each),
  > 8 species-1 (D1..D7 removal proposals + D8 recording 6 guards VERIFIED NECESSARY so
  > phase 3 does not strip them), 5 species-3 (I1..I5), 3 species-4 castles (C1..C3),
  > 1 hygiene (H2). 128 `file:line` references, all verified to resolve against the
  > current tree by an inline python check.
  > Lens-1 outcome: F1 absent (the planner task does not exist — pool_beat still rides
  > the probe return at commander.py:969-970, which is the wf#5 f8 decision the brief
  > superseded), F2 drifted (XOR per beat, no PLAN object, three flags not collapsed),
  > F3 absent as a symbol and divergent as behaviour (the reception role does move, but
  > onto the second-oldest active worker, not onto the fresh replacement), F4 divergent
  > (the brief's ledger gate is unimplemented — capacity_headroom has one reader, the
  > compaction; the code follows the NOTES counter-decision instead), F5 divergent on
  > both values (72 vs 48, 6 vs 3) and conforming on shape, F6 conforming on the ten
  > names but divergent on the finalize panel's three (RECYCLE_RETRY_SECONDS exists yet
  > is absent from `__all__`; `abandon_recycle` and roster `recycle_failed_at` were never
  > born under those names).
  > Decided without asking (unattended): H2 is recorded as SUPERSEDED-candidate rather
  > than as a finding, because the sentence the issue wants corrected does not exist in
  > the tree — the docstring at commander.py:1266-1273 speaks of unresolvable addresses
  > and matches its code, and the two texts about an in-flight user (commander.py:1783,
  > 180-181) never claim the commander discards. The card hands phase 4 the one place
  > left to look (worker.py, where "the worker discards" would be documented).
  > Also decided: the three `trigger_*` twins and the accelerated floor fit are recorded
  > as proposals with named authorities-of-origin (none, in both cases) rather than as
  > defects — nothing dies by default in this run.
  > Suite 1569 passed / 2 skipped, `ruff check .` clean, `git status --porcelain` only
  > under `.phased/`. No source or test file touched.
  > Verify: now — the plan's phase commits cannot land from this unattended session (the
  > pre-commit hook denies them, the quirk the plan's Notes record): phase 1's and phase
  > 2's commits must be landed from the mother session.
  > Files: .phased/active/17-design-audit/audit/zone_recycling_code.md,
  > .phased/active/17-design-audit/plan.md, .phased/active/17-design-audit/notes.md

- [x] **Phase 3**: Zone reading — the tests that cement
  - Pattern reference: `temp/audit_essenzialita_2a_2026-08-01.md` (verdict style); method is the issue's own: strip the code, see which tests fall
  - Files: `.phased/active/17-design-audit/audit/zone_tests.md` (new); read-only: `tests/test_spa_move.py`, `tests/test_spa_commander.py`, `tests/test_spa_evaluator.py`, `tests/test_spa_monitor.py`, `audit/zone_recycling_code.md`; transiently modified and restored: `src/genro_asgi/spa/commander.py`, `src/genro_asgi/spa/evaluator.py`
  - Decisions:
    - The unit of removal is the PAIR (code branch + cementing test). For each species-1 defense card from Phase 2: strip the guard experimentally, run the spa test files (`pytest tests/test_spa_move.py tests/test_spa_commander.py tests/test_spa_evaluator.py tests/test_spa_monitor.py -x -q` is NOT enough — run without `-x` to collect ALL falling tests), record which tests fall, then `git restore src/` immediately. Every experiment ends with a restore; no experiment survives into the commit.
    - For each falling test ask the issue's question: "does this scenario exist in the real product?" — answer with caller analysis, not opinion.
    - The `LocalPool.settled` hygiene item (tests/test_spa_move.py, dead helper reading the abolished None convention) is one card in this file: locate it, list which tests still call it (possibly none — then it is dead code), propose removal.
    - A test asserting behaviour for an unreachable state is itself a slimming-ledger candidate: the card proposes the pair removal, not the test alone.
  - Details: Read `audit/zone_recycling_code.md` for the species-1 defense cards. For each: perform the strip experiment as decided above, write one card — guard (file:line), tests that fell (test file::test name), reachability verdict proposal, pair-removal proposal. Also sweep the four test files for tests that only exercise defensive branches (no experiment needed when reading suffices — say so on the card). Write `audit/zone_tests.md`. Before finishing: `git status --porcelain` must show changes only under `.phased/`, and the full suite must be green.
  - Done: `audit/zone_tests.md` exists with one card per species-1 defense from Phase 2 (each naming the falling tests or stating "no test falls — the defense is uncemented") plus the LocalPool.settled card; `git status --porcelain` shows changes only under `.phased/`; `pytest tests/ -q` passes.
  > Done: `audit/zone_tests.md` written — 14 cards, every verdict slot EMPTY: 7 strip
  > experiments (T-D1..T-D7, one per species-1 defense D1..D7), 1 section B recording D8's
  > six necessary guards as deliberately not stripped, 1 hygiene card (`LocalPool.settled`),
  > 3 reading-sweep cards (TS1..TS3). 63 `file:line` references, all verified to resolve
  > against the current tree by an inline python check.
  > Experiment outcome: **five of seven defenses are completely uncemented** — stripping
  > D2 (commander.py:3132-3133), D3 (3127-3129), D4 (3084 `since is None`), D5
  > (evaluator.py:318 `or []`) or D6 (commander.py:2591 isinstance) leaves 249/249 spa
  > tests passing. D1 fells exactly one test
  > (test_spa_move.py::test_the_in_process_worker_is_never_recycled, and only its second
  > half — the two options of D1 cost half of it each, never both); D7 fells exactly one
  > (test_spa_evaluator.py::test_floor_velocity_is_none_when_no_pair_is_separated_in_time,
  > which writes eight samples sharing one `time.time()` reading).
  > Decided without asking (unattended): D4 and D7 were stripped INTO a loud
  > `AssertionError` rather than out — a removed silent `return` proves nothing, since the
  > suite passes either way; the raise makes any test reaching the branch explode, so
  > silence becomes evidence of unreachability. D4 stayed silent, D7 exploded.
  > Also decided: T-D7 offers only "keep" or "make it loud here", not "remove" — without
  > the `return None` at evaluator.py:292-293, `max(velocity, accelerated)` at
  > evaluator.py:298 would compare None with a float, a loud error three lines from its
  > cause. Phase 5 must not write a removal proposal that cannot be executed.
  > Also decided: the `LocalPool.settled` item is recorded as a no-removal card (second
  > confirmation after phase 1) — `LocalPool` (tests/test_spa_move.py:149-189) has no
  > `settled`, the live `settled_at` (tests/test_spa_move.py:78) has 17 callers, and the
  > `process=None` convention is still admitted by `new_roster_row` (commander.py:976) and
  > read at commander.py:863, 1089, 1136. The card hands phase 5 its "Scartate" motivation.
  > Every experiment restored the original file text byte for byte. Suite 1569 passed /
  > 2 skipped, `ruff check .` clean, `git status --porcelain` only under `.phased/`.
  > No source or test file left modified.
  > Verify: at walkthrough — the 14 cards are proposals with empty verdicts; the owner's
  > call on each, one at a time. (The hook quirk phase 2 flagged did not recur: this
  > phase's commit landed from the unattended session, 27aaa62.)
  > Files: .phased/active/17-design-audit/audit/zone_tests.md,
  > .phased/active/17-design-audit/plan.md, .phased/active/17-design-audit/notes.md

- [ ] **Phase 4**: Zone reading — the spa world vs the ebook  `vast`
  - Pattern reference: `temp/audit_fedelta_2a_2026-08-02.md` (disagreement-as-finding table)
  - Files: `.phased/active/17-design-audit/audit/zone_spa_world.md` (new); read-only: `src/genro_asgi/spa/worker.py`, `src/genro_asgi/spa/worker_entry.py`, `src/genro_asgi/spa/register.py`, `src/genro_asgi/spa/register_registry.py`, `src/genro_asgi/spa/subscription_index.py`, `src/genro_asgi/spa/global_store.py`, `src/genro_asgi/spa/environ.py`, `src/genro_asgi/spa/__init__.py`, `audit/00_authorities.md`
  - Decisions:
    - Authority here is the ebook claims inventory from Phase 1 (zone tag `spa-world`): every disagreement between code and book is a card — the resolution options are always the same two, "the code adapts" or "the owner amends the book on record"; the card presents both, the owner picks at walkthrough.
    - Lens 2 species 1 and 3 sweep on these modules (species 4 castles are a commander phenomenon per the issue; flag one here only if it jumps out). No strip experiments in this phase — analytical only.
    - worker.py was NOT touched by wf#8 (verified at planning) — drift here is ebook-vs-code, not brief-vs-code; do not re-audit it against the brief.
  - Details: Read the ebook claims inventory, then the eight modules. For each ebook claim about these modules: confirm with file:line or write a disagreement card (book says X — section; code does Y — file:line; options: adapt code / amend book). For lens 2: one card per impossible-scenario defense or meaningless indirection found, same card format as Phase 2. Write `audit/zone_spa_world.md`.
  - Done: `audit/zone_spa_world.md` exists; every ebook claim tagged `spa-world` in 00_authorities.md is either confirmed (with file:line) or has a disagreement card; every card carries a `file:line`; `git status --porcelain` shows changes only under `.phased/`.

- [ ] **Phase 5**: Consolidation — the two registers
  - Pattern reference: `temp/audit_essenzialita_2a_2026-08-01.md` §G "Sintesi — TUTTI I VERDETTI" (the ratifiable-list shape, but with verdicts EMPTY)
  - Files: `.phased/active/17-design-audit/audit/reconciliation_record.md`, `.phased/active/17-design-audit/audit/slimming_ledger.md` (both new); read-only: the three zone card files and `audit/00_authorities.md`
  - Decisions:
    - Register 1, the reconciliation record: one entry per fidelity point (authority-says / code-does / file:line / options / verdetto: —), the baptism section (per name: semantics, 2–3 candidates or keep-with-reason, verdetto: —), the ebook-disagreement section (adapt-code vs amend-book, verdetto: —).
    - Register 2, the slimming ledger: one CONCRETE proposal per entry — "remove X and its test T", "merge Y into Z", "rewrite W in ~N lines from the ratified story" — each with file:line and the burden-of-proof answers, verdetto: —.
    - Nothing dies by default: every entry is the owner's call, one at a time, at walkthrough. The registers are the walkthrough agenda.
    - Every zone card must land in exactly one register entry or be explicitly discarded in a final "Scartate" section with its reason. No silent drops.
  - Details: Read the three zone files and 00_authorities.md. Merge duplicate findings (the same guard seen from code side in Phase 2 and test side in Phase 3 becomes ONE ledger entry carrying both file:line sets). Order the ledger by leverage (biggest simplification first). Write both registers in Italian. End each register with a one-line count (N voci, M in attesa di verdetto) and the "Scartate" section.
  - Done: both register files exist; every fidelity point from 00_authorities.md has a reconciliation entry; grep of each zone-card identifier in the registers plus the Scartate section accounts for all cards; both files end with the count line.

- [ ] **Phase 6**: Coherence review and auto-fix (final, mandatory)
  - Pattern reference: cross-check against Phases 1..5 (their `Files:` fields)
  - Files: only the files written by Phases 1..5 (`.phased/active/17-design-audit/audit/*.md`); plus `.phased/active/17-design-audit/review.md` (new). Never touch a pre-existing file they did not modify.
  - Decisions:
    - Auto-fix directly: broken `file:line` references (re-resolve against the current tree and correct the line number), typos in file paths, markdown formatting, internal cross-reference slips between the audit files.
    - Never auto-fix: the substance of a card or register entry, verdicts (they must stay empty), adding or removing findings. Those go to `review.md` only.
  - Details: Convergence loop (max 3 cycles): (1) parse every `path:line` reference in the five audit files and verify the path exists and the line number is within the file (a small inline python check); (2) verify coverage — every fidelity point and baptism name from 00_authorities.md appears in the reconciliation record, every zone card is accounted for in a register or in Scartate; (3) fix what is auto-fixable, re-check. Then run `pytest tests/ -q` (must be green — asserts no experiment residue from Phase 3) and confirm `git status --porcelain` shows only `.phased/` changes. Write `review.md` with three sections: **Auto-fixed** (file, what), **Flagged for human** (file, description, suggested action), **Final state** (reference-check output, suite result, files reviewed).
  - Done: `review.md` exists in the plan directory with the three sections; every `file:line` reference in the audit files resolves; `pytest tests/ -q` passes; `git status --porcelain` clean after the phase commit.

## Notes
- The run STOPS at the cards. Verdicts are the owner's, given at a walkthrough
  after the run; the fix phase is a separate later workflow. No verdict column
  is ever filled by this run.
- No source or test file is modified in any committed state. Phase 3's strip
  experiments are transient and end with `git restore src/`; Done criteria
  enforce the clean tree.
- Planning-time findings already known: `planner`, `decision_interval`,
  `designated_reception` have zero hits in `src/genro_asgi/` (verified
  2026-08-13) — absences to document, not to re-discover.
- wf#8's real surface (from `git diff --stat` against its plan-add commit):
  commander.py +663, evaluator.py +99, test_spa_move +733, test_spa_evaluator
  +143, test_spa_commander +64, test_spa_monitor +29.
- Owner's environment quirk: the pre-commit hook in ask mode can deny commits
  to unattended sub-sessions. If phase commits are blocked during the run,
  land them from the mother session (known workaround).
- Audit deliverables are in Italian (walkthrough material, per the 2a audit
  precedents in `temp/`); everything else in English per policy.

## Suggested execution config
| Phase | Effort | Model |
|-------|--------|-------|
| Phase 1 | medium | opus |
| Phase 2 | high | opus |
| Phase 3 | high | opus |
| Phase 4 | high | opus |
| Phase 5 | high | opus |
| Phase 6 | xhigh | opus |
