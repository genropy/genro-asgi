# Context: wf/accensione-genropy-piano-dati
Parent: main
Mode: autonomous
Must not break: what the four `tests/test_spa_application*.py` assert must keep a living equivalent on the new front, or at the Macro 6 cutover that behaviour disappears together with the files that guarded it
Must not break: `set_datachange` is born local, but its signature already carries `kind`, `target` and `filters` — the local branch is one outcome of an addressing decision, never its absence — otherwise the inter-worker delivery of the second pass reopens the signature and every caller
Must not break: the page rows — store, collector, `user_view`, `dbevents`, subscriptions — stay packageable, because the hot move and any restart liturgy package user rows and pass through them

## Objective

Give the new core (`spa/orchestration/`) the data plane the hosted GenroPy site
requires, so genropy-asgi can run on it: the shared registry inside
`SpaWorker`, the lifecycle verbs in the forms the site calls, the local
datachange plane, the table events, and the site-written global store climbing
the envelope. The governing rule (owner, 2026-08-19): toward the site the new
worker imitates the pre_refactoring worker in full — the only licensed
divergence is how the worker talks to the commander. The scope stops inside
genro-asgi: the bridge rebase and the browser test are instructions for
genropy-asgi, decided at the end, not phases here.

## Work Plan

- [x] **Phase 1**: The registry enters the worker  `vast`
  - Pattern reference: `src/genro_asgi/spa/worker.py:503` (`self.registry = self.build_registry()`, the delegating properties at :566) and `src/genro_asgi/spa/register_registry.py:128` (the registry's own lifecycle vocabulary)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`; discovery rule for the tests — every reference to `user_register` / `connection_register` / `page_register` under `tests/orchestration/` (measured: 74 reads by key, 25 comparisons against dict literals, 35 idiomatic reads that survive as they are)
  - Decisions:
    - `SpaWorker` gains `build_registry()` returning `RegisterRegistry()` — the pre_refactoring hook name, kept verbatim so the bridge overrides nothing — and holds it as `self.registry`.
    - The three flat dicts die; `user_register` / `connection_register` / `page_register` become properties returning `self.registry.user_items` / `.connection_items` / `.page_items` (decision §7a of 2026-08-20: the worker keeps the `*_register` names, the bridge translates to the `*_items` the site reads).
    - `src/genro_asgi/spa/register_registry.py` is NOT touched: the worker adopts the registry idioms (`get` / `create` / `update` / `drop` / `keys_by`), never the reverse. Writes stay confined to the existing single-writer mutators (`_add_*_item`, `_remove_*_item`), rewritten inside on `create`/`drop`.
    - The worker's own row fields (`state`, the transfer flag, the three clocks) survive as extra fields of the registry rows — `create` stores caller fields verbatim, exactly as it keeps the site's `start_ts`.
    - `page_register.keys_by("session_id", cid)` works without new indexes: `RegisterRegistry` is born with `page_items` indexed on `("session_id", "root_page_id")` (`register_registry.py:136`).
    - The registry move and the test rewrites travel in this same phase, so it closes green (owner decision 6, 2026-08-19). The 25 dict-literal comparisons are rewritten to assert the keys or fields they actually meant.
  - Details: rewrite the 12 register writes into `create`/`drop` calls inside the mutators; rewrite the 58 reads into registry idioms; keep every announcement (`add_worker_event`), the freeze/adopt cycle, the login fold and the departures working on the same rows — the whole existing `tests/orchestration/` suite is the harness proving nothing regressed. Copy `.phased/active/accensione-genropy-piano-dati/tests/phase-1/` into `tests/orchestration/` verbatim (implementation-test classification, per project rule 10).
  - Done: the plan's tests for this phase, copied into the test tree, pass; `python -m pytest -q` fully green; `ruff check src/ tests/` clean.
  > Done: `tests/orchestration/test_contract_phase1_registry.py` 11 passed; full suite 2007 passed, 2 skipped; `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `tests/orchestration/test_contract_phase1_registry.py` (new), `tests/orchestration/test_orchestration_login.py`, `tests/orchestration/test_orchestration_m4_e2e.py`, `tests/orchestration/test_orchestration_spa_worker.py`, `tests/orchestration/test_orchestration_spa_worker_departures.py`, `tests/orchestration/test_orchestration_spa_worker_process.py`
  > Decided here: the parcel shape now names what the rebirth builds itself —
  > `PARCEL_CONNECTION_REBUILT_FIELDS`, `PARCEL_PAGE_REBUILT_FIELDS`,
  > `PARCEL_PAGE_REPLAYED_FIELDS` — because a registry row carries
  > `register_item_id` (which `create` refuses as a keyword), the two collectors
  > (objects bound to this process's Bags) and the sets `new_page` seeds itself.
  > The three subscription sets travel as plain values and are subscribed again
  > on the woken page by `_install_page_subscriptions`, the pre_refactoring's
  > `install_pages` shape (`spa/worker.py:2323`). `_page_user` is gone: the
  > derivation is `registry.page_user`. `change_connection_user` keeps the
  > `KeyError` its docstring declares with an explicit raise, `Register.get`
  > returning None where the dict raised.
  > Verify (later): the advisory mypy count went 124 -> 146. Every new finding is
  > the same category that already dominates the baseline in `register_registry.py`
  > — `Register.get` is typed `dict | None` where the flat dict raised — so the
  > plan's "do not chase it" holds; a human may still want to decide whether the
  > worker's register reads earn a per-module override in pyproject.toml.

- [x] **Phase 2**: The lifecycle verbs in the site's forms
  - Pattern reference: `src/genro_asgi/spa/worker.py:1917` (`new_connection`), `:1999` (`new_page`), `:2078` (`drop_page`), `:2084` (`drop_connection`), `:2024` (`demolish_page`, the cascade announced in the order it climbs)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py` (the verbs and the single internal caller of `drop_connection` at the op handler, `spa_worker.py:757`)
  - Decisions:
    - Signatures are the pre_refactoring ones verbatim: `new_connection(identity, **fields)`, `new_page(identity, page_id, **fields)`, `drop_page(identity, page_id)`, `drop_connection(identity, session_id)`. Identity first positional; the `cascade` the site passes is absorbed by the bridge, never a worker parameter (owner decision 7, 2026-08-20).
    - There is NO baptism cascade: `drop_page` has no internal callers and `drop_connection` exactly one (the op handler), which adapts (owner decision 8, verified).
    - `add_user` / `add_connection` / `add_page` remain the announcing mutators; the new verbs are facades over them (or over the registry's own `new_*`), so `worker_events` keeps rising unchanged. `add_user(identity, encoded, parcel_wins=)` of the channel op world does not collide: the site never calls `add_user` (decision 9).
    - `change_connection_user(cid, user, **fields)` already exists (`spa_worker.py:958`) and is signature-compatible; this phase only aligns its row semantics with the registry (guest entry follows its first real identity, resident wins).
  - Details: add the four verbs; route their row work through the registry so the cascade announcements (`drop_page` → `drop_connection` → `drop_user` as departures empty rows) match the pre_refactoring order; adapt the one internal caller; copy the phase tests into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass; full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase2_site_verbs.py` 13 passed; full suite 2020 passed, 2 skipped; `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `tests/orchestration/test_contract_phase2_site_verbs.py` (new), `tests/orchestration/test_orchestration_login.py`, `tests/orchestration/test_orchestration_m4_e2e.py`, `tests/orchestration/test_orchestration_spa_worker.py`
  > Decided here: aligning `change_connection_user` with the registry (plan decision
  > 4 of this phase) delegates the whole row work to
  > `RegisterRegistry.change_connection_user`, and its declared divergence —
  > **the guest entry follows its first real identity**, key changed, live store
  > conserved — replaced the worker's own former semantics, where the guest row
  > stayed behind holding the store and the new identity was born empty. Three
  > behaviours moved with it: `freeze_connection` reads the store to parcel off
  > the CURRENT owner (the same Bag object, so the parcel is unchanged) instead
  > of the vanished guest row; a login-time write by the hosted site lands on the
  > connection's current owner (the m4 test site now derives the owner off the
  > connection, as a real site does); and a login from a real prior loses what
  > the site wrote after the re-label, its born identity's row being released
  > with the departure — asserted at `test_orchestration_m4_e2e.py` step 7.
  > `drop_page` keeps its tolerance of an absent page; `drop_connection` now
  > raises `KeyError` on an absent connection, as its contract states, and the
  > op handler — its one internal caller — reads the row first and stays silent
  > on absence, an op being no site.

- [x] **Phase 3**: The local data plane
  - Pattern reference: `src/genro_asgi/spa/worker.py:1142` (`collect_page`), `:1358` (`set_datachange`), `:1395` (`reset_datachanges`), `:1411` (`drop_datachanges`), `:1432` (`setStoreSubscription`)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`
  - Decisions:
    - `collect_page(page_id)` drains under `dispatch_lock` (already an RLock, `spa_worker.py:350`): the page's filtered collector plus its `user_view`, merged by `change_ts` with a stable sort; `dbevents` its own species in its own key; unknown page raises `KeyError`.
    - `set_datachange(identity, change, kind=, target=, filters=, replace=, **addressing)` — the full pre_refactoring signature, LOCAL branch only: the target page lives here by construction (one worker of fact). `replace=True` coalesces on the daemon's three fields (path, reason, fired). A target this worker does not hold is an explicit error, not a silent skip — the addressing decision exists, its remote branch does not yet.
    - `setStoreSubscription(identity, page_id, storename, prefix, active=True)`: `storename='page'` moves `subscribed_paths` and the collector's prefix set together; `storename='user'` opens/widens/narrows `user_view` through `registry.subscribe_store_path`; any other storename raises `ValueError`.
    - The reserved protocol names keep their spelling (`setStoreSubscription`, with the same `noqa: N802` convention as the pre_refactoring).
  - Details: transcribe the five verbs from the pre_refactoring worker, keeping the dispatch_lock discipline; nothing ascends — these are process-local by stickiness; copy the phase tests into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass; full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase3_data_plane.py` 14 passed; full suite 2034 passed, 2 skipped; `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `tests/orchestration/test_contract_phase3_data_plane.py` (new)
  > Decided here: the three exchange ops write on the row DIRECTLY — no
  > `exchange_message` / `route_datachange` / `apply_datachange` chain was
  > transcribed. That chain exists in the pre_refactoring to shape a message for
  > the ASCENT, and the ascent has no code in this pass; the local branch of the
  > switch is one lookup, so the machinery would have been a shape with no
  > reader. One private resolver holds it, `_addressed_row(op, kind, target,
  > filters)`, and it is where the second pass grows the two remote branches.
  > Both are explicit `NotImplementedError` today rather than silence: a
  > `filters` broadcast (only the commander sees every page) and a `STATE_KINDS`
  > address (a change born on another worker arriving as a real Bag write —
  > nothing local produces one, the site writing its own stores through the Bag
  > it holds). `SIGNAL_KIND` and `STATE_KINDS` are transcribed constants of the
  > pre_refactoring, so no baptism is due; `_addressed_row` is private.
  > Closing a `user` subscription now also narrows the collector
  > (`user_view.unsubscribe_path`), where the pre_refactoring discarded the row's
  > set alone and left the view capturing the prefix it no longer declared —
  > the `page` branch's own symmetry, and the sets are what a move packages.

- [x] **Phase 4**: The table events
  - Pattern reference: `src/genro_asgi/spa/worker.py:1483` (`subscribeTable`), `:1524` (`notifyDbEvents`), `:1569` (`dbevent_deposit`), `:1591` (`fan_out_local`); the index is `src/genro_asgi/spa/subscription_index.py:59`, reused as is
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`
  - Decisions:
    - The worker gains `subscriptions` (a `SubscriptionIndex`) beside the registry; `spa/subscription_index.py` is shared and NOT touched.
    - `subscribeTable(identity, table, page_id, subscribe=True, subscribeMode=None)`: the row's `table_subscriptions` set and the index move together; `subscribeMode` accepted and ignored, as the daemon does; unknown page raises `KeyError`.
    - `notifyDbEvents(identity, dbevents, reason=, page_id=, local_only=False, **addressing)`: deposits shaped once (`table`, `batch`, `from_page_id`, `reason`, `ts`), local fan-out under `dispatch_lock`, empty batches never announced, `local_only` deposits on the origin page alone. LOCAL form: with one worker of fact «announce locally» is the whole announcement — nothing ascends, but the signature is the full one so the second pass adds the ascent without reopening it.
    - Dropping a page clears its subscriptions from the index (the drop verbs of Phase 2 learn to call `subscriptions.drop_page`).
  - Details: transcribe the two ops and the two local helpers; wire the index into the drop cascade; the deposit is a page-row append, drained by `collect_page` on the `dbevents` key (Phase 3); copy the phase tests into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass; full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase4_dbevents.py` 11 passed; full suite 2045 passed, 2 skipped; `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `tests/orchestration/test_contract_phase4_dbevents.py` (new)
  > Decided here: the index is cleared in `_remove_page_item`, the single-writer
  > mutator every removal path funnels through, not in the drop verbs the plan
  > named — same outcome for them, and the freeze is covered too, its parcel
  > carrying `table_subscriptions`. Its other half is `_install_page_subscriptions`,
  > which now re-subscribes each replayed table into the index and not only into
  > the row's set. `notifyDbEvents` omits the ascent (no code in this pass, per the
  > plan) and `invalidate_table_cache` (the new worker holds no table cache, so
  > the call would have had no object); the cache lands in the non-`local_only`
  > branch when it is transcribed. `dbevent_deposit` keeps the pre_refactoring
  > spelling rather than rule 11's `get_` prefix, the governing rule of this
  > workflow being full imitation toward the site.

- [x] **Phase 5**: The site's global store climbs the envelope
  - Pattern reference: `src/genro_asgi/spa/worker.py:1750` (`store_set`), `:1761` (`store_del`), `:1766` (`global_store_lock`) for the verb forms; `src/genro_asgi/spa/global_store.py` (`GlobalStore`, `CapturingGlobalStore`, reused); the envelope seams are `spa/orchestration/spa_worker.py:1360` (`_outbound`), `:1369` (`_take_global_store`) and `spa/orchestration/worker_connector.py:286` (`_take_envelope`)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `src/genro_asgi/spa/orchestration/worker_connector.py`, `src/genro_asgi/spa/orchestration/envelope_handler.py`, `src/genro_asgi/spa/orchestration/spa_commander.py`
  - Decisions (the ratified mechanics of 2026-08-20, handoff §4.2 point 10 — the ONE licensed divergence from the pre_refactoring, already weighed, do not reopen):
    - The `WorkerConnector` asymmetry stays intact: down CALL, up presentation and REPLY, nothing else. The rejected alternatives (a child→parent CALL/EVENT lane; making the `with` wait for an ack; re-running the lock body) stay rejected.
    - The worker holds a live replica (`global_store`, a `GlobalStore` — the pre_refactoring's own name, derived, no baptism due) hydrated from the descending `GLOBAL_STORE_KEY`; `_take_global_store` keeps replacing it whole.
    - A write applies FIRST to the own replica, then queues for the slot of the first envelope out, beside `worker_snapshot` in `_outbound`. On the commander side `_take_envelope` hands the envelope to the fold BEFORE unblocking the caller; the fold applies the writes to the global master, which redescends as it already does.
    - `old_value` rides ONLY derived writes — those drained from a `global_store_lock` body, whose value is a function of the value read. A stale derived write (master no longer holds the old value) is refused whole with one log line on the commander: no error channel to the site, risk accepted by the owner («le scritture di global sono rarissime»; with one worker the writer is one and the refusal cannot fire).
    - Absolute writes (`store_set` / `store_del` outside the lock) travel without `old_value`: last-writer-wins, the commander a blind courier.
    - The envelope slot key and the fold hook are new names: they carry `wf:phase-5:new` markers for the single naming review at finalize.
  - Details: add the replica and the three verbs; extend `_outbound` with the writes slot and the commander-side fold with its application and refusal; the two-sided skeleton tests in the phase's contract file state exactly the behaviour to implement — replace their red bodies with real tests over the in-process handler harness (`tests/orchestration/test_orchestration_envelope_chain.py` fixtures are the pattern); copy the phase tests into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass (skeleton bodies implemented, every `wf:contract:` line satisfied); full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase5_global_store.py` 9 passed, the five skeletons implemented over the real vertex and a real wire; full suite 2054 passed, 2 skipped; `ruff check src/ tests/` clean; advisory mypy unchanged at 146.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `src/genro_asgi/spa/orchestration/worker_connector.py`, `src/genro_asgi/spa/orchestration/envelope_handler.py`, `src/genro_asgi/spa/orchestration/spa_commander.py`, `tests/orchestration/test_contract_phase5_global_store.py` (new), `tests/orchestration/test_orchestration_spa_worker_process.py`
  > Decided here: `global_store_lock` asks nobody and is SYNC only — a plain
  > `@contextlib.contextmanager` on the worker, not a lease. The
  > pre_refactoring's two forms exist because its lock is a round trip whose
  > vehicle follows the handler; the ratified asymmetry leaves nothing to await,
  > and the hosted site reaches the worker on the traffic pool, so a `with`
  > needing no await serves it as it stands. `spa/global_store.py` is untouched:
  > `GlobalStoreLease` still serves the production stack.
  > The intermediate node a body autocreated is NOT queued — only the leaf — so
  > the master autocreates it itself instead of having a whole subtree replaced
  > by this replica's copy of it. `old_value` is read at the lock's exit, the
  > replica being untouched while the body runs.
  > `_take_global_store` now hydrates `global_replica` beside filing
  > `global_register_item_tytx`, which gave the slot a meaning the two
  > placeholder strings of `test_orchestration_spa_worker_process.py` did not
  > have: they became real encoded stores through a `master_store` helper — an
  > implementation test rewritten with the implementation it photographs, per
  > project rule 10.
  > `record_global_write` on the worker, `GLOBAL_WRITES_KEY`,
  > `CommanderEnvelopeHandler.on_global_writes` and
  > `SpaCommander.apply_global_writes` carry their `wf:phase-5:new` markers;
  > `global_store`, `global_replica`, `store_set`, `store_del` and
  > `global_store_lock` are pre_refactoring names, derived, no baptism due.

- [x] **Phase 6**: Coherence review and auto-fix (final, mandatory)
  - Pattern reference: same as Phases 1..5 (cross-check against them)
  - Files: only the files written by Phases 1..5 (collect them from their `Files:` fields). Never touch a pre-existing file they did not modify.
  - Decisions:
    - Auto-fix directly: tool-fixable lint (ruff), unused imports, formatting, trivially mechanical fixes. Re-run the tests after each non-tooling fix; if one breaks a test, roll back that fix and flag it instead.
    - Never auto-fix: logic errors, design divergences from the pattern reference, missing edge cases, anything architectural. Those go to `review.md` only.
  - Details: convergence loop (max 3 cycles) of linter scoped to the file set → auto-fix → linter → test suite; stop early if a cycle makes no progress. Then write `.phased/active/accensione-genropy-piano-dati/review.md` with three sections: **Auto-fixed** (file, what, tool), **Flagged for human** (file, description, suggested action), **Final state** (linter output, suite result, files reviewed).
  - Done: `review.md` exists in the plan directory with the three sections, linter zero errors on the file set, full suite green.
  > Done: `review.md` written with its three sections (**Auto-fixed**, **Flagged
  > for human**, **Final state**); `ruff check` on the 14 files of the set — and
  > on `src/ tests/` whole — All checks passed; full suite 2054 passed, 2 skipped.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `.phased/active/accensione-genropy-piano-dati/review.md` (new)
  > Decided here: only two fixes were mechanical enough to apply — `__all__` back
  > to alphabetical order (Phase 1 put the three `PARCEL_*` entries ahead of
  > `DEPOSIT_LOCK_*` in an otherwise sorted list) and the two signatures over the
  > declared `line-length = 100`, wrapped the way every other multi-line def in
  > the file wraps. Neither is reported by any tool: the project's ruff selection
  > is frozen at `E4,E7,E9,F`, so `RUF022` and `E501` are both off. A wider probe
  > (`--select E,W,F,I,RUF,B,SIM,C4`) finds 22 findings on this file set and NONE
  > was fixed: `pyproject.toml` states that adopting a rule is a per-rule
  > decision and never a side effect, so applying those would have been an
  > architectural change smuggled into a lint pass. Nine items went to
  > `review.md` instead of the code, two of them load-bearing for the second
  > pass: the ascent's write shape drops the Bag `attributes`/`reason`/`fired`
  > the drained change carries, so a site's node attributes never reach the
  > master; and a derived write the master refuses stays applied on the worker's
  > replica, which re-synchronises only on a presentation — a phantom value
  > readable for the rest of that process's life. Both are consequences of the
  > ratified mechanics, not divergences from them, so neither was touched.
  > Verify (now): `review.md` §Flagged for human — 9 items, none of them a change
  > made here. Items 1, 2 and 3 (the write shape, the divergent replica, the
  > 96-method worker) are decisions for the second pass; item 4 is a name for the
  > finalize naming review.

- [x] **Phase 7**: The worker-to-commander CALL lane
  - Pattern reference: `src/genro_asgi/channel/hub.py` (the call/serve machinery of the hub: pending futures by frame id, CALLs served as tasks) and `src/genro_asgi/spa/orchestration/worker_connector.py:286` (`_take_envelope`, the branch that exists); the loop-hop from a pool thread follows `src/genro_asgi/spa/worker.py:1770` (`acquire_global_lock`, the pre_refactoring pattern)
  - Files: `src/genro_asgi/spa/orchestration/worker_connector.py`, `src/genro_asgi/spa/orchestration/spa_worker.py`
  - Decisions:
    - The connector gains the second dispatch branch: a CALL arriving from the child is served as a task through a handler the owner of the connector provides, and answered with a REPLY; an unhandled path answers an error REPLY, never a silent discard.
    - The worker gains a `call()` (marker, name at the naming review): writes a CALL with its own frame id, parks a future, and its read loop learns to route the parent's REPLYs to those futures; reachable from a traffic-pool thread by hopping onto the loop.
    - Full duplex is the transport's own: interleaving needs no new machinery, only the two branches.
    - Riding this phase (same file): the ratified renames — the three surviving envelope slot constants become `ENVELOPE_SLOT_WORKER_EVENTS`, `ENVELOPE_SLOT_WORKER_SNAPSHOT`, `ENVELOPE_SLOT_PRESENTATION`, all defined in `worker_connector.py`, wire values unchanged — and the two stray literals of M2/M3 (`spa_worker.py:1278`, `:1394`) start using them.
  - Details: implement the two branches and the worker call; adapt the envelope-chain tests that name the renamed constants; copy the phase tests into `tests/orchestration/` and implement their red bodies as real tests over an in-process connector pair.
  - Done: the plan's tests for this phase, copied into the test tree, pass (every `wf:contract:` line satisfied); full suite green; ruff clean.

  > Done: `tests/orchestration/test_contract_phase7_worker_call_lane.py` — 5/5,
  > every `wf:contract:` line satisfied over an in-process connector+worker pair
  > on a real UDS; full suite 2060 passed, 2 skipped; `ruff check .` clean.
  > Files: `src/genro_asgi/spa/orchestration/worker_connector.py`,
  > `src/genro_asgi/spa/orchestration/spa_worker.py`,
  > `src/genro_asgi/spa/orchestration/envelope_handler.py` (NOT in the phase's
  > `Files:` — the ratified renames put the three slot constants in
  > `worker_connector.py`, and two of them were defined there),
  > `tests/orchestration/test_contract_phase7_worker_call_lane.py` plus the 10
  > test files that named the renamed constants.
  > Decided here (no question could be asked): the connector asks its handler
  > through a `serve_child_call(path, data)` hook (marker `wf:phase-7:new`),
  > sync or async — the same "the wire asks its handler" road as
  > `read_envelope`, no callback handed in at construction. `WorkerHandler`
  > does NOT grow that hook in this phase (it is not in the phase's `Files:`
  > and Phase 8 wires it to the desk): until then every child CALL comes back
  > as an error REPLY carrying the `AttributeError`, which is the declared
  > "never a silent discard" behaviour and is asserted as such.
  > The failure the lane raises on is `CommanderCallFailed(path, cause)`, born
  > in `worker_connector.py` rather than `exceptions.py`, which the phase does
  > not own. The sync door for the pool threads is `run_on_loop`, the
  > pre_refactoring name for the pre_refactoring pattern (`spa/worker.py:1746`),
  > and the loop it hops onto is taken with the wire in `attach_stream`.
  > Two superseded assertions were rewritten with the mechanism they photograph:
  > `test_orchestration_worker_connector.py` (a child CALL was "unexpected" —
  > now it is served, so the denounced envelope is a third method, and a new
  > test pins the error REPLY of a hookless handler) and
  > `test_orchestration_spa_worker_process.py` (a REPLY on the worker was
  > "unexpected" — now it is the answer to a call placed upward).
  > Review: the parked calls of `spa_worker` are NOT failed when the wire dies,
  > unlike the connector's `_fail_pending`. A `run_on_loop` waiting on a pool
  > thread at that moment blocks until the process ends, which is what
  > `on_wire_lost` is already doing — no reader for a rescue, so none written.

- [x] **Phase 8**: The commander's delivery desk
  - Pattern reference: `src/genro_asgi/spa/subscription_index.py:59` (the index, reused as is, now commander-side) and `src/genro_asgi/spa/commander.py` page_subscriptions handling (the pre_refactoring's own desk half)
  - Files: `src/genro_asgi/spa/orchestration/spa_commander.py`, `src/genro_asgi/spa/orchestration/envelope_handler.py`, `src/genro_asgi/spa/orchestration/worker_handler.py` (wiring the lane's handler to the desk)
  - Decisions:
    - The commander alone holds: the table→pages `SubscriptionIndex`, the per-page queues (two species, datachanges and dbevents, never mixed), the per-user queues (STATE store writes). All OUTSIDE the pickled surface: events are ephemeral (owner: lost at freeze, gone with websockets).
    - The subscription call updates the index before answering: the subscribe-window is closed by construction.
    - The exchange sorts the arriving events into the queues FIRST and answers AFTER — the caller's own events come back in the same round.
    - Every exchange reply carries the current list of subscribed table names (the worker's source-filter cache).
    - `replace=True` coalesces inside the target queue on the daemon's three fields (path, reason, fired).
    - One hygiene rule for all three queue species: events older than a threshold are discarded (parameter with default; proposal 300 seconds — marker, value confirmed at the naming review). The `drop_page` fold clears the page's queue and its index entries.
    - An event whose table nobody subscribes dies at the desk.
  - Details: build the desk and its lane handlers (subscription, exchange, the phase-10 store ops arrive later); wire `drop_page`/`drop_user` folds to the cleanup; copy the phase tests into `tests/orchestration/` and implement their red bodies over an in-process commander+worker pair.
  - Done: the plan's tests for this phase, copied into the test tree, pass; full suite green; ruff clean.

  > Done: `tests/orchestration/test_contract_phase8_delivery_desk.py` — 9/9,
  > every `wf:contract:` line satisfied over a real lane (a `SpaWorker` on one
  > end, a real `WorkerHandler` under a real `SpaCommander` on the other, on a
  > real UDS); full suite 2069 passed, 2 skipped; `ruff check .` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_commander.py`,
  > `src/genro_asgi/spa/orchestration/worker_handler.py`,
  > `tests/orchestration/test_contract_phase8_delivery_desk.py`.
  > `envelope_handler.py` was NOT touched: its `on_drop_page`/`on_drop_user`
  > already call the commander's folds, and the desk hangs off those.
  > Decided here (no question could be asked, all recorded in `notes.md`): the
  > three queues are plain lists rather than `DataChangeCollector`s (the
  > collector is a Bag observer — one dead Bag per page — and its dedup is one
  > comprehension); `serve_child_call` cascades `WorkerConnector` →
  > `WorkerHandler` → `DeliveryDesk`, which dispatches to `op_<segment>` by name
  > the way the chain dispatches `on_<op>`; `STATE_KINDS` is redefined at the
  > vertex rather than imported from the child's module, the `GUEST_PREFIX`
  > pattern already in the tree; a filtered address raises `NotImplementedError`
  > at the desk — the branch MOVED one rung up, it did not dissolve, because
  > resolving a filter needs a page surface answering `field:value` that the new
  > vertex does not have.
  > `drop_connection` was routed through `delivery_desk.drop_page`: it deleted
  > its pages straight out of `page_connection_map`, so the desk would never
  > have heard of them and the `drop_user` cascade would have left their queues
  > behind.
  > Review: the desk holds its queues while the pre_refactoring-era
  > `pending_dbevents`/`pending_datachanges` fields still sit unused in
  > `SpaCommander._new_row` (inside the pickled surface, read only by
  > `drop_user`'s counter and `mark_user_adopted`'s clear). Nothing writes them
  > any more; removing them is its own change, not this phase's.
  > Review: the age threshold is applied at the DRAIN, so a page that never
  > exchanges again keeps its queue in memory until it is dropped. No sweeper
  > was written — the plan asked for the discard rule, not for a reaper.

- [x] **Phase 9**: The worker's request slot and the end-of-request exchange  `vast`
  - Pattern reference: `src/genro_asgi/spa/orchestration/spa_worker.py:1402` (`_serve_request`, where the request context lives) and the pre_refactoring shapes it keeps: `src/genro_asgi/spa/worker.py:1524` (`notifyDbEvents`), `:1569` (`dbevent_deposit`), `:1217` (`apply_forwarded`)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`; test rewrites — `tests/orchestration/test_contract_phase4_dbevents.py` (superseded assertions rewritten with the mechanism they photograph, foreman decision in `notes.md`), plus any orchestration test naming the dead helpers
  - Decisions:
    - Events born during a request accumulate on a slot of THAT request (an explicit per-request object threaded through the serving path — requests run on pool threads, so no module or instance global). `notifyDbEvents` keeps its full site signature, shapes the deposits with `dbevent_deposit` (unchanged) and lays them on the slot, filtered by the subscribed-tables cache; `local_only` keeps its deposits on the slot for the own collect alone, nothing reaches the wire.
    - The exchange happens at the end of EVERY request, empty-handed included: retiring the pendings is the reason.
    - The collect merges: own collectors (page collector + `user_view`, still local — the page listening to itself) with the retired pendings, by `change_ts`; species never mix.
    - STATE store writes retired by the exchange are applied to the user's Bag (`apply_forwarded`, `_original_ts`) BEFORE the collect runs.
    - `set_datachange`/`reset_datachanges`/`drop_datachanges` keep their full signatures and ALWAYS route through the desk — no local shortcut, the own page included. `_addressed_row`'s two `NotImplementedError` branches dissolve: the addressing IS the commander.
    - Dead and removed, tests following in the same phase: `deposit_dbevent`, `fan_out_local`, `worker.subscriptions`, the `dbevents` mailbox on the page item.
  - Details: build the slot and the exchange; rewrite the delivery half of the phase-3/4 in-tree contract copies to the new mechanism (the site-facing signatures they pin DO NOT move); copy the phase tests into `tests/orchestration/` and implement their red bodies.
  - Done: the plan's tests for this phase, copied into the test tree, pass; full suite green; ruff clean.

  > Done: `tests/orchestration/test_contract_phase9_request_exchange.py` — 9/9,
  > every `wf:contract:` line satisfied over a real lane (the site's own verbs on
  > a `SpaWorker`, a real `WorkerHandler` under a real `SpaCommander`, on a real
  > UDS); full suite 2078 passed, 2 skipped; `ruff check .` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`,
  > `src/genro_asgi/spa/orchestration/spa_commander.py` (NOT in the phase's
  > `Files:` — routing `reset_datachanges`/`drop_datachanges` through the desk
  > needed the two ops Phase 8 had no caller for),
  > `tests/orchestration/conftest.py` (the live-lane fixture the rewritten
  > contract files share), `tests/orchestration/test_contract_phase9_request_exchange.py`,
  > `tests/orchestration/test_contract_phase3_data_plane.py`,
  > `tests/orchestration/test_contract_phase4_dbevents.py`.
  > Decided here (no question could be asked, all recorded in `notes.md`): the
  > slot is a `RequestSlot` held in a `threading.local()` — the site's verbs take
  > no slot argument, and a request is served on ONE traffic-pool thread from end
  > to end, so the thread IS the request; the exchange is placed by
  > `collect_page`, the end-of-request drain the site already calls, which is why
  > it is the one place that can hand the retired pendings to the response of the
  > very request that produced them; the desk messages carry an `op` field, absent
  > meaning `set_datachange`, so Phase 8's contract file keeps passing unchanged.
  > Review: the `dbevents` mailbox on the page row SURVIVES in
  > `register_registry.py`, which the pre_refactoring worker shares and reads
  > (`spa/worker.py:1166`, `:1611`, `:2331`). The contract line "the page item
  > carries no dbevents mailbox" is honoured at the level this phase owns — the
  > new worker never writes nor reads it — and the field can only go at the Macro
  > 6 cutover, with the stack that needs it.
  > Review: `reset_datachanges` and `drop_datachanges` now act on the desk queue
  > ALONE. The pre_refactoring collector held the page's own captures and the
  > addressed deposits in one list, so a reset cleared both; with the captures
  > staying local and the deposits living at the desk, a reset toward one's own
  > page no longer discards what that page captured of its own store. This is
  > what "no local shortcut, the own page included" costs; a human may want the
  > verb to reach both sides.
  > Review: a page woken from the freezer gets its `table_subscriptions` back on
  > the row (`_install_page_subscriptions`) but nothing re-files them at the
  > desk — the only index there is now. Until it does, a woken page hears no
  > table events until it subscribes again. Re-filing needs a lane call from the
  > adoption path, which the phase does not own.
  > Review: TYTX rounds `change_ts` to the millisecond, so a change that crossed
  > the wire and one captured locally inside the same millisecond merge in an
  > order the clock cannot decide. The merge is by `change_ts` as specified; the
  > resolution is the wire's.

- [x] **Phase 10**: The global store lives only on the commander
  - Pattern reference: `src/genro_asgi/spa/global_store.py` (`GlobalStore`, `CapturingGlobalStore`, the lease shape — module untouched, it serves the production stack) and the pre_refactoring lock handlers in `src/genro_asgi/spa/commander.py` (grant carries the master, release applies the drained changes, FIFO, a dead holder releases)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `src/genro_asgi/spa/orchestration/worker_connector.py`, `src/genro_asgi/spa/orchestration/envelope_handler.py`, `src/genro_asgi/spa/orchestration/spa_commander.py`; test rewrites — `tests/orchestration/test_contract_phase5_global_store.py` and `test_orchestration_spa_worker_process.py` (foreman decision in `notes.md`)
  - Decisions:
    - No replicas: the master on the commander is the only copy. Verified licence: the 22-name site contract never reads the store directly — only `store_set`, `store_del` and the lock's granted copy.
    - `store_set`/`store_del` are CALLs on the lane, answered after the master applied: immediate, last-writer-wins, full shape.
    - `global_store_lock` is the pre_refactoring protocol on the lane: acquire → grant with the master's copy; release → drained changes applied in full shape (attributes included); FIFO; a holder or waiter whose worker dies releases without applying.
    - Removed with their machinery: `global_replica`, `global_register_item_tytx`, `_take_global_store`, `record_global_write`, `_global_writes`, the descent of the store on every frame, the presentation snapshot, `ENVELOPE_SLOT_GLOBAL_STORE`/`GLOBAL_WRITES_KEY`, `old_value` and the stale-refusal — and with them the coherence-review findings 1 and 2 dissolve.
  - Details: move the ops to the desk, transplant the lock protocol, strip the replica machinery everywhere it lives; rewrite the phase-5 in-tree contract copy on the new mechanics; copy the phase tests into `tests/orchestration/` and implement their red bodies.
  - Done: the plan's tests for this phase, copied into the test tree, pass; full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase10_global_store_desk.py` 8 passed; full suite 2075 passed, 2 skipped; `ruff check .` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `src/genro_asgi/spa/orchestration/worker_connector.py`, `src/genro_asgi/spa/orchestration/envelope_handler.py`, `src/genro_asgi/spa/orchestration/spa_commander.py`, `src/genro_asgi/spa/orchestration/worker_handler.py`, `tests/orchestration/test_contract_phase10_global_store_desk.py` (new), `tests/orchestration/test_contract_phase5_global_store.py` (deleted), `tests/orchestration/child_stub.py`, `tests/orchestration/test_orchestration_spa_worker_process.py`, `tests/orchestration/test_orchestration_worker_connector.py`, `tests/orchestration/test_orchestration_worker_handler.py`, `tests/orchestration/test_orchestration_envelope_chain.py`, `tests/orchestration/test_orchestration_foundations_e2e.py`, `tests/orchestration/test_orchestration_m2_e2e.py`
  > Decided here: `test_contract_phase5_global_store.py` was DELETED rather than
  > rewritten in place — this phase's own contract file IS its rewrite, subject by
  > subject, and a second copy of it would have been the only alternative reading
  > of the foreman's sanction. The commander's master stays a plain `Bag`: the
  > full-shape release borrows the replica shape for one statement
  > (`GlobalStore(global_register).apply_changes(...)`), so the vertex gained the
  > lock and nothing else. Two files outside `Files:` were touched and both were
  > forced: `worker_handler.py`, because `on_child_lost` is the one place a wire's
  > end is known and the death rule needs a caller; and the connector, which now
  > cancels a dead child's parked CALLs — without it a worker that died PARKED on
  > the grant would win it after the holder released and hold it forever, a
  > permanent silent deadlock of the whole pool's store. Full rationale in
  > `notes.md` under `## Phase 10`.

- [x] **Phase 11**: Coherence review and auto-fix of the redesign (final, mandatory)
  - Pattern reference: same as Phases 7..10 (cross-check against them)
  - Files: only the files written by Phases 7..10 (collect them from their `Files:` fields). Never touch a pre-existing file they did not modify.
  - Decisions: same auto-fix policy as Phase 6 — tool-fixable lint, unused imports, formatting; never logic, design or architecture, which go to the review file.
  - Details: convergence loop (max 3 cycles) of linter scoped to the file set → auto-fix → linter → test suite; stop early if a cycle makes no progress. Then REPLACE `.phased/active/accensione-genropy-piano-dati/review.md` with the three sections (**Auto-fixed**, **Flagged for human**, **Final state**) covering Phases 7-10, noting which findings of the Phase 6 review were dissolved by the redesign.
  - Done: `review.md` rewritten with the three sections, linter zero errors on the file set, full suite green.
  > Done: `review.md` rewritten — **Auto-fixed** (3 entries), **Flagged for human**
  > (9 findings), **What the redesign dissolved** (all 9 Phase 6 findings accounted
  > for: 4 dissolved, 5 standing), **Final state**; `ruff check` on the 21-file set
  > and over the whole tree — All checks passed; full suite 2075 passed, 2 skipped.
  > Files: `.phased/active/accensione-genropy-piano-dati/review.md` (rewritten),
  > `src/genro_asgi/spa/orchestration/spa_worker.py`,
  > `src/genro_asgi/spa/orchestration/spa_commander.py`,
  > `tests/orchestration/test_orchestration_group_handler.py`,
  > `tests/orchestration/test_orchestration_worker_handler.py`,
  > `tests/orchestration/test_orchestration_spa_worker_process.py`
  > Decided here: the file set was derived from `git diff 6ba6999..acb0bcc` rather
  > than transcribed from the four `Files:` fields, whose prose carries
  > parentheticals; the auto-fix stayed inside Phase 6's precedent (`__all__` order,
  > lines over 100) plus one contract divergence the redesign introduced — two
  > `wf:phase-7:new` markers on a docstring's first line instead of the definition
  > line. Rationale in `notes.md` under `## Phase 11`.
  > Review: finding 1 of `review.md` — `STATE_KINDS` declared verbatim on both
  > sides of the wire (`spa_worker.py:316`, `spa_commander.py:220`) — is the one
  > worth deciding before the second pass; the other eight are either standing
  > Phase 6 findings or prices already accepted.

- [x] **Phase 12**: The carried store re-attaches every user_view
  - Pattern reference: `src/genro_asgi/spa/worker.py:2333` (`adopt_carried_store` — the re-attach loop; its docstring names the reason: "Every page already watching the old Bag is re-attached ... so no captured change is lost in the swap")
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`
  - Decisions (panel finding 1, owner-ratified fix 2026-08-20 at the quality check):
    - `_install_carried_store`, on the non-resident path, after swapping the row's store walks every page of every connection of the user and re-attaches its `user_view` on the new Bag with the same `store_subscriptions`, re-fed with the old view's pending changes — the pre_refactoring shape, transcribed (governing imitation rule; the missing loop was the unlicensed divergence).
    - No signature moves; no other behaviour changes.
  - Details: transcribe the loop; the phase's contract tests are the panel's own reproducing probe turned into real tests (freeze → adopt → the window still captures). Copy `.phased/active/accensione-genropy-piano-dati/tests/phase-12/` into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass (every `wf:contract:` line satisfied); full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase12_carried_store_views.py` 3/3,
  > every `wf:contract:` line verbatim, no red body left; full suite 2078 passed,
  > 2 skipped; `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`,
  > `tests/orchestration/test_contract_phase12_carried_store_views.py` (new)
  > Decided here: the loop lives INSIDE `_install_carried_store`'s non-resident
  > branch — the swap and the re-attach are one gesture, exactly as
  > `adopt_carried_store` holds them; no new callable, so no marker. The third
  > contract test stages the pre-swap capture by calling the private seam under
  > `dispatch_lock` directly: the window between `_install_page_subscriptions`
  > and the swap is not reachable from the public verbs, and an implementation
  > test photographing the seam is what rule 10 licenses.

- [x] **Phase 13**: The desk is a projection of the page rows
  - Pattern reference: `src/genro_asgi/spa/orchestration/envelope_handler.py:369` (`on_new_page`), `:403` (`on_user_frozen`), `:409` (`on_user_adopted`) — the folds that already exist; `src/genro_asgi/spa/orchestration/spa_worker.py:613` (`add_worker_event`, the announcements the projection rides)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`, `src/genro_asgi/spa/orchestration/envelope_handler.py`, `src/genro_asgi/spa/orchestration/spa_commander.py`
  - Decisions (panel finding 2 + focus F6, owner-ratified design 2026-08-20: the row is the authority, the desk index is a projection rebuilt by the folds):
    - The `new_page` worker event carries the row's `table_subscriptions` (empty at birth, the replayed set at the wake); the vertex fold files the entries into the desk index.
    - The freeze and the login tail announce the pages' departure to the vertex (page ids on the events already leaving with those transitions); the fold clears the page's two desk queues, its index entries AND its `page_connection_map` row — what waits for a frozen user is lost, the desk docstring's own rule.
    - The adoption re-announces the pages with their sets; the commander rebuilds from there. NO new lane call: everything rides the announcements already going out with those events.
    - `subscribeTable` unchanged: the row first (authority), the projection in the same call, the reply still carrying the tables list.
    - The phase's tests pin the whole cleanup cascade (freeze, `drop_connection`, `drop_user` reaching the desk) — the coverage gap the panel reported: deleting any cleanup call must turn the suite red.
  - Details: extend the announcements' payloads, wire the folds, clear at the departures; copy `.phased/active/accensione-genropy-piano-dati/tests/phase-13/` into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass (every `wf:contract:` line satisfied); full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase13_desk_projection.py` 4/4,
  > every `wf:contract:` line verbatim; full suite 2082 passed, 2 skipped;
  > `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`,
  > `src/genro_asgi/spa/orchestration/envelope_handler.py`,
  > `src/genro_asgi/spa/orchestration/spa_commander.py`,
  > `tests/orchestration/test_contract_phase13_desk_projection.py` (new),
  > `tests/orchestration/test_orchestration_envelope_chain.py`,
  > `tests/orchestration/test_orchestration_spa_worker_departures.py`
  > Decided here: the pages' departure rides the existing `drop_pages` op — at
  > the vertex "gone from this process" and "gone for good" cost the same fold,
  > and inventing a second word would have added a handler with the same body.
  > The announcement is emitted inside `_release_rows` / `_release_login_rows`
  > (single writers of the removals), one event per connection, only when pages
  > exist. The wake announces `new_page` AFTER `_install_page_subscriptions`,
  > directly in `adopt_connection` — the announcement carries the replayed set,
  > which is the whole point of the projection. `install_page_subscriptions`
  > (marker) is the desk's own mutator the fold calls. Two implementation-test
  > files were rewritten with the mechanism they photograph (rule 10): the
  > hand-built `new_page` events gained the field, the departure assertions the
  > `drop_pages` announcement. A wild death still leaves the dead worker's desk
  > entries in place (no announcement survives it) — recorded for the second
  > pass, out of this phase's scope.

- [x] **Phase 14**: Unservable addresses are refused at the verb
  - Pattern reference: `src/genro_asgi/spa/worker.py:1358` (`set_datachange` — the pre_refactoring validates at write time and an illegal address fails ALONE, the request's other events untouched)
  - Files: `src/genro_asgi/spa/orchestration/spa_worker.py`
  - Decisions (panel finding 3 + the filtered-abort findings, owner-ratified fix 3a 2026-08-20):
    - `set_datachange` / `reset_datachanges` / `drop_datachanges` validate the address BEFORE laying anything on the request slot: a `kind` in `STATE_KINDS` other than `user_store`, a `filters=...` address, a target this pass does not deliver → explicit error raised in the caller's own call. Nothing half-filed ever reaches the desk; the bad call fails alone, exactly as the pre_refactoring.
    - The desk's own `NotImplementedError` branches STAY as the frontier backstop — existing code, not a new guard; after this phase no live path reaches them.
    - The dead-target leak (target gone between write and exchange) is closed by Phase 13's departure cleanup, not here — the verb validates against what the worker holds at write time, the desk queue of a page that dies later is cleared by its announced departure.
  - Details: add the write-time validation to the three verbs; copy `.phased/active/accensione-genropy-piano-dati/tests/phase-14/` into `tests/orchestration/`.
  - Done: the plan's tests for this phase, copied into the test tree, pass (every `wf:contract:` line satisfied); full suite green; ruff clean.
  > Done: `tests/orchestration/test_contract_phase14_verb_refusal.py` 3/3, every
  > `wf:contract:` line verbatim; full suite 2085 passed, 2 skipped;
  > `ruff check src/ tests/` clean.
  > Files: `src/genro_asgi/spa/orchestration/spa_worker.py`,
  > `tests/orchestration/test_contract_phase14_verb_refusal.py` (new)
  > Decided here: ONE private validator, `_refuse_unservable_address(op, kind,
  > target, filters)` (marker `wf:phase-14:new`), called by the three verbs
  > before anything lands on the slot — the same taxonomy Phase 3's
  > `_addressed_row` used: `NotImplementedError` for the branches the second
  > pass builds (filters, non-user_store STATE kinds), `KeyError` for a target
  > this worker does not hold (`target=None` included: with one worker of fact
  > a target not held does not exist). The desk's own `NotImplementedError`
  > branches stay as the frontier backstop; no live path reaches them now.

## Notes

- **Plan extension of 2026-08-20 (evening)**: Phases 7-11 implement the
  centralized-delivery redesign the owner dictated after Phases 1-6 ran —
  decision register: `temp/registro_ridisegno_consegna_centralizzata_2026-08-20.md`
  (the authority for every phase above; its §7/§7-bis list what supersedes the
  morning's decisions). The finalize was deliberately POSTPONED to after these
  phases (owner: never pay the multi-review on condemned code); ONE finalize
  closes the whole workflow.
- The scope stops inside genro-asgi. Fase 5 (bridge rebase) and Fase 6 (browser
  test on a real site) of `temp/piano_accensione_genropy_2026-08-19.md` are OUT:
  they become instructions for whoever works in genropy-asgi, shaped at the end
  of this workflow.
- Fase 4 of that same document (the child→parent CALL/EVENT lane) is SUPERSEDED
  by the ratified envelope mechanics (handoff §4.2 point 10): this plan's
  Phase 5 follows the handoff, not the older document.
- `.phased/roadmap.md` is NOT updated: this workflow covers the data-plane half
  of Macro 5 and declares it here, the M4 precedent (owner delegated the call,
  2026-08-20). The rest of Macro 5 — hard/soft boot liturgy, `recycle_worker`,
  observability, inter-worker delivery — is the second pass;
  `temp/liturgia_riavvio_orientamenti_2026-08-20.md` holds the owner's restart
  orientations for when that pass is planned.
- The pre_refactoring stack (`spa/worker.py`, `spa/commander.py`,
  `applications/spa_app.py`) is READ-ONLY throughout: it is the pattern source
  and the sentinel until Macro 6. The five `tests/test_spa_*.py` files the
  contract tests derive from stay untouched — derived, never moved.
- `spa/register_registry.py`, `spa/subscription_index.py` and
  `spa/global_store.py` are shared modules serving the production stack: NOT
  touched (owner decision 2, 2026-08-19).
- Every new public callable carries its `wf:phase-N:new` marker; names are
  proposals — ONE naming review runs at `/finalize-workflow`, per the owner's
  baptism prerogative.
- mypy is advisory and its baseline is 124 findings: not a gate, do not chase it.

## Suggested execution config
| Phase | Effort | Model |
|-------|--------|-------|
| Phase 1 | high | opus |
| Phase 2 | medium | opus |
| Phase 3 | medium | opus |
| Phase 4 | medium | opus |
| Phase 5 | high | opus |
| Phase 6 | xhigh | opus |
| Phase 7 | high | opus |
| Phase 8 | high | opus |
| Phase 9 | high | opus |
| Phase 10 | high | opus |
| Phase 11 | xhigh | opus |
| Phase 12 | medium | opus |
| Phase 13 | high | opus |
| Phase 14 | medium | opus |

## Quality check

> Quality check: 2026-08-20T16:56:26Z — commit cc09a7a — review panel, QA declined, findings 3 confirmed, 1 dismissed
