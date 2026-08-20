
## Phase 3

The local data plane landed as five public verbs on `SpaWorker` plus one private
resolver, and the choice worth recording is what was NOT transcribed: the
pre_refactoring's `exchange_message` → `route_datachange` → `apply_datachange`
chain. Its whole job is to shape a flat, readable message a commander can route
— an ascent this pass does not build. Locally the switch collapses to one
register lookup, so the three ops (`set_datachange`, `reset_datachanges`,
`drop_datachanges`) act on the row directly and share `_addressed_row`, which
is the single seam the second pass reopens for the filtered broadcast and the
store address. Both are `NotImplementedError` with the op named, not silence:
the plan's own rule that a target this worker does not hold is an explicit
error applies just as much to an address whose branch does not exist yet.

Rejected: keeping the message envelope now "so the ascent slots in later". It
would have been a data shape with no reader, and the marker of where the ascent
attaches is better carried by one named resolver than by a chain of four
methods that only ever take their first branch.

## Phase 4

The plan said "the drop verbs of Phase 2 learn to call `subscriptions.drop_page`";
the call went instead into `_remove_page_item`, the single-writer mutator all six
removal paths already funnel through (`drop_page`, `drop_connection`, `drop_user`,
the freeze and the two transfer paths). Same outcome for the drop verbs, and the
freeze is covered for free — its parcel carries `table_subscriptions`, so the
index must empty when the page leaves and fill again when it wakes. That second
half is `_install_page_subscriptions`, which now re-subscribes each replayed table
into the index rather than only re-filling the row's set: without it a woken page
would declare subscriptions the fan-out could not see.

`notifyDbEvents` drops two things the pre_refactoring does. The ascent
(`outbox.offer(shape_ascending(...))`) has no code in this pass, per the plan.
`invalidate_table_cache` has no subject: the new worker holds no table cache and
no cache observers, so there was nothing to invalidate — a call would have been a
name with no object behind it. When the cache is transcribed it lands here, in the
non-`local_only` branch, exactly where the pre_refactoring has it.

`dbevent_deposit` keeps its pre_refactoring spelling although it is a pure reading
with arguments, which project rule 11 would spell `get_`: the governing rule of
this workflow is that toward the site the new worker imitates the pre_refactoring
in full, and this method's name is part of what the bridge and the ops read.

## Phase 5

**The lock asks nobody, and it is sync only.** The pre_refactoring
`global_store_lock` is a round trip — the request ascends as `store_lock`, the
grant comes back carrying the master, the drained changes travel back with
`store_unlock` — and its `GlobalStoreLease` supports `with` and `async with`
because the vehicle follows the handler. Neither survives the ratified mechanics:
the `WorkerConnector` asymmetry forbids the child from asking anything, so there
is no grant to wait for and nothing to await. The new form is therefore a plain
`@contextlib.contextmanager` on the worker: the body mutates a working copy of
the replica, and at a clean exit the drained changes apply locally and queue as
derived writes. Sync only is honest rather than reduced — the hosted site reaches
the worker through `WsgiSeam` on the traffic pool, so every call of the site is
on a thread, and a `with` needing no await is usable from a coroutine as it
stands. `GlobalStoreLease` in `spa/global_store.py` is left untouched: it serves
the production stack until the cutover.

**The intermediate nodes are not queued.** A body writing `x.y` where `x` did not
exist produces two captures, the autocreated `x` carrying a whole Bag and the
leaf. Only the leaf is queued: the master autocreates `x` itself, and forwarding
the Bag would replace the master's whole `x` subtree with this replica's copy of
it. The pre_refactoring could forward it safely because there the working copy WAS
the master at grant time; here it is a replica that may be a beat behind.

**`old_value` is read at the exit, not at the entry.** The replica is not touched
while the body runs — the writes land at the exit — so the value the derived write
was computed from is still there to read when it is queued. A descending envelope
replacing the replica mid-body would make that read the new value and the write
would be applied rather than refused: accepted, being the same order of rarity as
the refusal itself and the owner's declared risk.

**`_take_global_store` now hydrates as well as files.** The field
`global_register_item_tytx` stays — it is what the tests of the wire assert and
what the descent literally carried — and `global_replica.load_snapshot` is called
on it. That gave the slot a meaning it did not have before, so the two placeholder
strings in `test_orchestration_spa_worker_process.py` (`GLOBAL_STORE`, "a later
store") became real encoded stores through a `master_store` helper: an
implementation test rewritten with the implementation it photographs, per project
rule 10.

**The vertex is the only reader of the writes slot.** `CommanderEnvelopeHandler`
overrides `work_on_envelope` to read `global_writes` BEFORE the photo and the
worker events, and `on_global_writes` hands the hydrated list to
`SpaCommander.apply_global_writes`, which owns `global_register`. No layer below
holds a copy of the master, so no layer below has anything to do about them.

## Run inspection

- First launch (11:21) died at Phase 1 after 3m43s on an API 529 Overloaded —
  server-side, before any edit: no stale `[>]`, tree untouched. Relaunched at
  11:26; the run below is the relaunch.
- 6/6 phases green, zero repairs, zero reopens. Wall times: 20m47s / 11m10s /
  6m28s / 6m18s / 21m33s / 12m17s — the two `high` phases (1 and 5) are the
  long ones, as sized.
- Advisory mypy moved 124 → 146 in Phase 1 (all one category: `Register.get`
  typed `dict | None` where the flat dict raised) and stayed there through
  Phase 5. Candidate for a per-module override, human call.
- Phase 6 wrote `review.md`: 2 auto-fixes (cosmetic, behaviour-identical),
  9 flagged items — none blocking, the substantive ones are the global-store
  write shape dropping Bag attributes (item 1, decide before the inter-worker
  delivery) and the replica left divergent after a refused derived write
  (item 2, consequence of the accepted risk, pair with a descent when a second
  writer exists).
- 16 `wf:phase-N:new` markers stand for the finalize naming review; review.md
  item 4 adds `deposit_dbevent` (word-order twin of the transcribed
  `dbevent_deposit`) to that agenda.

## Plan extension (2026-08-20 evening) — foreman decisions

The owner dictated a redesign of the delivery after Phases 1-6 ran: decision
register in `temp/registro_ridisegno_consegna_centralizzata_2026-08-20.md`,
implemented by the appended Phases 7-11. Foreman decisions binding the
executing children:

- **Contract-test amendments are sanctioned.** The in-tree copies of
  `test_contract_phase4_dbevents.py` (Phase 9) and
  `test_contract_phase5_global_store.py` plus the placeholder-store assertions
  of `test_orchestration_spa_worker_process.py` (Phase 10) photograph
  mechanisms the redesign kills; the phases named rewrite their delivery
  assertions to the new mechanism. The SITE-FACING signatures those files pin
  (notifyDbEvents, subscribeTable, set_datachange, store_set, store_del,
  global_store_lock and their return shapes) DO NOT move.
- **The condemned names get no baptism** (owner's rule: only survivors):
  deposit_dbevent, fan_out_local, worker.subscriptions, record_global_write,
  global_replica, GLOBAL_WRITES_KEY, ENVELOPE_SLOT_GLOBAL_STORE die with their
  code and their markers.
- **Ratified renames ride Phase 7**: ENVELOPE_SLOT_WORKER_EVENTS /
  ENVELOPE_SLOT_WORKER_SNAPSHOT / ENVELOPE_SLOT_PRESENTATION in
  worker_connector.py (wire values unchanged) + the two stray literals of
  M2/M3 start using them.
- **The finalize is postponed** to after Phase 11 — one naming review, one
  consolidation, on what survives.

## Phase 8

Decisions this phase took that the plan did not settle (no question could be
asked):

- **The queues are plain lists, not `DataChangeCollector`s.** The collector was
  the obvious reuse — it already coalesces on `key` and carries `drop`/`reset`
  for Phase 9 — but it is a Bag *observer*: putting one at the desk means a dead
  Bag per page whose only purpose is to be subscribed to. The coalescing it
  performs is one comprehension (`pending["key"] != change["key"]`), so the list
  reproduces the daemon's dedup faithfully with no dead object and nothing for a
  reader to wonder about ("which Bag does the commander have?" — none).
- **`serve_child_call` cascades, and the desk dispatches by name.** The connector
  asks `WorkerHandler.serve_child_call(path, data)` (Phase 7's hook); the handler
  hands it to `SpaCommander.delivery_desk.serve_child_call`, which calls
  `op_<segment>` with the payload as keyword arguments — the same "dispatch by
  name" the envelope chain uses for `on_<op>`. An op that does not exist raises
  `AttributeError`, which the wire already turns into an error REPLY. The handler
  writes nothing: it is the rung the call climbs.
- **`STATE_KINDS` is redefined at the vertex, not imported.** It is declared in
  `spa_worker.py` — the child's module — and importing it would make the parent
  process depend on the whole worker module (`WsgiSeam`, `RegisterRegistry`). The
  house pattern for exactly this is already in the tree: `GUEST_PREFIX` is
  redefined in `envelope_handler.py` and in `spa_worker.py` with its ratified
  value and a comment saying why.
- **A filtered address raises `NotImplementedError` at the desk.** Phase 9 says
  the two `NotImplementedError` branches of `_addressed_row` dissolve because
  "the addressing IS the commander" — but resolving a filter needs a page surface
  answering `field:value`, which the new vertex does not have (`page_connection_map`
  carries the owner and nothing else). So the branch MOVED rather than dissolved:
  same declared behaviour, one rung up. Building the page surface is its own
  work and belongs to whoever decides the filtered broadcast.
- **The contract tests place the desk CALLs themselves.** The verbs that will
  place them — `subscribeTable` and the end-of-request exchange — are the
  worker's half and are Phase 9's `Files:`. The tests therefore open a real lane
  (a `SpaWorker` on one end, a real `WorkerHandler` under a real `SpaCommander`
  on the other, over a real UDS) and call `/desk/subscribe_table` and
  `/desk/exchange` directly. Every `wf:contract:` assertion is taken as written,
  at the layer this phase owns; the first test's "before it answers" is proved by
  the answer itself carrying the table in its `tables` list.
- **`drop_connection` had to be routed too.** It deleted its pages straight out
  of `page_connection_map` instead of going through `drop_page`, so the desk
  would never have heard about them. It now calls `delivery_desk.drop_page` per
  page, which is what makes the `drop_user` cascade reach the queues.

## Phase 9

Decisions this phase took that the plan did not settle (no question could be
asked):

- **The slot is a `RequestSlot` on a `threading.local()`.** The plan asked for
  "an explicit per-request object threaded through the serving path", but the
  site's verbs (`notifyDbEvents`, `set_datachange`, `collect_page`) take no slot
  argument and their signatures do not move. A request is served on ONE
  traffic-pool thread from end to end, so the thread IS the request: the slot is
  opened on that thread by `_serve_on_thread` just before the WSGI stitching, and
  every verb called during the request finds it by asking for `request_slot`. A
  dict keyed by `page_id` was the alternative and is wrong: two parallel requests
  from the same page would share one slot, which is exactly what the contract's
  first line forbids.
- **`collect_page` is where the exchange happens.** The exchange has to precede
  the collect (the caller's own events must come back in the same response) and
  the collect composes what the browser reads, so the only place that can hold
  both is the drain the site already calls at the end of its request. Putting the
  exchange after the pool work in `_serve_request` would have exchanged AFTER the
  site had already collected, which reverses the contract. Consequence: the
  exchange happens on every request that has a page — a request that names no
  page has no queue to retire and nothing to send.
- **The desk messages carry an `op`, and its absence means `set_datachange`.**
  `reset_datachanges` and `drop_datachanges` had to reach the desk queue too, and
  Phase 8's `file_datachange` knew one behaviour. It now dispatches on `op` and
  treats a message without one as the set — which is what Phase 8's own contract
  file sends, so that file passes untouched.
- **`spa_commander.py` was touched, outside the phase's `Files:`.** The two ops
  above live at the desk; there is nowhere else they can live once the queue does.
- **The live-lane fixture moved to `tests/orchestration/conftest.py`.** Three
  contract files now need a real worker under a real commander (the verbs place
  lane calls), and `verb()` runs them on one dedicated thread so a test IS a
  request. Phase 8's own `XT_DeskLane` copy was left alone: it places raw desk
  CALLs, not the site's verbs, and rewriting a closed phase's harness buys
  nothing.

## Phase 10

Decisions this phase took that the plan did not settle (no question could be
asked):

- **`test_contract_phase5_global_store.py` was DELETED, not rewritten in place.**
  The foreman sanctioned rewriting its delivery assertions to the new mechanism;
  read literally, every assertion of it that survives the redesign is already in
  this phase's own contract file, verbatim in subject: `store_set` answering the
  path, `store_del` removing the node rather than nulling it, the lock's grant,
  the release and the body that raises. Rewriting it in place would have produced
  a second copy of `test_contract_phase10_global_store_desk.py`, so the rewrite
  landed as that file, under the phase that owns the mechanics. What died with no
  successor is only what photographed the dead machinery: the writes slot, the
  descent on every frame, `old_value` and the stale refusal.
- **The commander's master stays a plain `Bag`, and the full-shape apply borrows
  the replica shape for one statement.** `GlobalStore(self.spa_commander.global_register).apply_changes(...)`
  — the class is exactly "a global-store Bag written from outside", which is what
  the master is at release time, so the release needed no code of its own and no
  second attribute on the vertex. `global_register` keeps its name and its type:
  every reader of it (the monitor, the tests) is untouched.
- **The lock lives on the vertex (`SpaCommander.global_lock`), its ops on the
  desk.** The same split as the pre_refactoring: the lock belongs to the store,
  the handlers belong where the messages arrive. `GlobalStoreLock` and
  `GlobalStoreLease` are reused from the untouched `spa/global_store.py`, so the
  worker's half is three methods — `global_store_lock` returning the lease,
  `acquire_global_lock`, `release_global_lock` — with the same names the
  pre_refactoring worker uses for them.
- **`worker_handler.py` was touched, outside the phase's `Files:`.** The death
  rule needs a caller, and `WorkerHandler.on_child_lost` is the one place a wire's
  end is known; it now asks the desk for `release_worker_lock(self.name)` first.
- **The connector cancels the dead child's parked CALLs.** Without it, a worker
  parked as a WAITER on the grant whose process dies would still win the lock
  when the holder released, and hold it forever: a permanent silent deadlock of
  the whole pool's store, which is the one outcome the owner's
  probability-weighted rule refuses. `_cancel_child_calls` in
  `worker_connector.py` fires on wire loss, for every parked call and not only
  the lock's.
- **The descent now carries nothing at all.** `CommanderEnvelopeHandler.__call__`
  had to stay (the group layer calls it) and returns `{}` for every envelope,
  presentation included; the worker's `send_presentation` still READS the answer,
  which is what tells it the wire is up. Four test doubles that played the fold
  answered with the store and now answer with nothing (`child_stub.py`,
  `test_orchestration_spa_worker_process.py`) or with a payload of their own
  (`test_orchestration_worker_connector.py`, whose subject is the connector's
  asymmetry and not what the chain composes).
- **Advisory mypy: 146 findings, unchanged from Phase 1's measurement.** Nothing
  chased, per the plan.

## Phase 11

**The file set was taken from the commits, not from the prose.** The phase says
«collect them from their `Files:` fields», and those fields carry parenthetical
prose («NOT in the phase's `Files:` — …», «(deleted)»). The union was therefore
derived from `git diff --name-only 6ba6999..acb0bcc -- src tests` and checked
against the four notes: 21 living files plus the one Phase 10 deleted, which is
exactly what the notes claim between them. A prose list transcribed by hand is
the one input of this phase that could silently omit a file.

**The auto-fix stayed inside Phase 6's precedent, deliberately.** Same policy,
same two categories — `__all__` order and lines over the declared 100 — plus one
the redesign introduced: two `wf:phase-7:new` markers sitting on the first line
of a docstring instead of the definition line. That third one is a contract
divergence (`refs/contracts.md`), not taste, and moving a comment cannot change
behaviour; the suite was re-run after it anyway. Everything the wider ruff
selection reports was left where Phase 6 left it: `pyproject.toml` states that
adopting a rule is a per-rule decision, and this phase is not the place to make
nine of them at once.

**No convergence cycle was needed.** The frozen selection (`E4,E7,E9,F`) was
already clean on the file set before the first edit and after the last, and the
suite was green at the baseline: the loop the phase describes converged on its
first pass, so it ran once and stopped rather than spending two more cycles
proving the same thing.

**The one finding worth a decision before the second pass** is finding 1, the
duplicated `STATE_KINDS`: it is the routing decision of the whole data plane
written twice, once per vertex, with no import between them. The rest either
stands from Phase 6 (size, `drop_connection`, the two old long lines) or is a
price the owner has already accepted (the collect_page tiraggio, the one-request
staleness of the source filter).

## Run inspection (phases 7-11, launcher 6.20.0)

- 5/5 phases green, zero repairs, zero reopens, no plan-defect consults. Wall
  times: 7 18m / 8 22m / 9 20m26s / 10 17m24s / 11 15m33s (approx from logs).
- THE RECURRING ANOMALY: the pre-commit permission hook denied `git commit` to
  the unattended sessions of phases 7, 8, 10 and 11 (phase 9 got through). Each
  phase left its work fully staged, the owner's unrelated dirty files
  deliberately excluded, and the foreman landed the commit verbatim
  (d39775a, e69728e, acb0bcc, a15b074). Known quirk (memory
  phased-workflow-tooling-quirks: «landare dalla madre»); intermittent — worth
  reporting upstream to the plugin/hook owner.
- Phase 9 recorded in `notes.md` the threading.local choice for the request
  slot (site verbs take no slot argument; one request = one traffic-pool
  thread), sanctioned by the phase-11 review as no divergence.
- Phase 10 deleted `test_contract_phase5_global_store.py` (its rewrite IS the
  phase-10 contract file) and had to touch `worker_handler.py` and
  `worker_connector.py` beyond its Files: — both forced by the death rule
  (cancel a dead child's parked CALLs so a dead waiter cannot win the store
  grant and jam it).
- Phase 11 REPLACED review.md accounting for every phase-6 finding: 1, 2, 4, 5
  dissolved by the redesign; 3 (size alarm, grew: SpaWorker 2575 lines), 6
  (detach on raise, moved), 7 (drop_connection homonymy), 8, 9 survive.
  New findings for the human: STATE_KINDS declared twice (one per side of the
  wire, no import between them); the exchange rides collect_page rather than
  the request tail (events of a never-collecting request die on the slot —
  provisional pull, but worth the owner's eye); the source filter can be one
  request stale (single-worker: irrelevant; second pass decides).
- mypy advisory: 148 at phase 7, still one category (Register.get dict|None).

## Plan extension (2026-08-20, quality check) — foreman decisions

The panel review at the quality check (report: the run's tasks output
`w8fqxvym7`, presented to the owner) confirmed 3 findings, all silent data
loss; the owner chose to fix before stamping. Phases 12-14 implement the
ratified fixes:

- **Phase 12** (finding 1): `_install_carried_store` transcribes the
  pre_refactoring's `adopt_carried_store` re-attach loop — the missing half
  was an unlicensed divergence from the imitation rule.
- **Phase 13** (finding 2 + F6, owner's design): the page row's
  `table_subscriptions` is the single authority; the desk index is a
  PROJECTION rebuilt by the vertex folds from the announcements. `new_page`
  carries the set, the freeze/login tail announce the pages' departure (desk
  queues, index entries and `page_connection_map` cleared), the adoption
  re-announces with the sets. No new lane call. This supersedes the panel-era
  reading of F6 (dismissed only because the freeze never cleaned).
- **Phase 14** (finding 3, option "refuse at the verb"): the three datachange
  verbs validate the address BEFORE the slot; unservable shapes (non-user_store
  STATE kinds, filters, unheld targets) raise in the caller's own call. The
  desk's NotImplementedError branches stay as frontier backstop. This also
  closes the unverified filtered-abort findings (a bad call fails alone).

Findings NOT bought here (recorded for the second pass): the dbevents of a
never-collecting request (cross-user loss — worth the owner's eye when the
exchange placement is revisited), the stale prose naming the dead replica in
five modules, STATE_KINDS declared twice (F1).
