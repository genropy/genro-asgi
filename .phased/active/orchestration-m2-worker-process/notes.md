# Notes — orchestration-m2-worker-process

## Review fixes — round 2

The re-review of the whole diff came back with six findings, every one of them
carried by an executed probe. Nothing outside `spa_worker.py` and
`tests/orchestration/` was touched; the suite went from 1827 to 1833 passing
(six new tests, three old ones re-shaped where a fix superseded what they
asserted). Every finding below carries the change and the proof that the change
is what holds it.

- **[R1] The quit cycle chews until the map is empty.** `execute_transfers`
  iterated ONE snapshot of the flag map. A man born while the worker was
  leaving, served, and named by a shot taken after that snapshot had no road
  left: his call was already closed, so no hook of his would fire again, and the
  cycle never looked twice — the flag stayed, the departures were never over,
  and the quit hung on a straggler nobody was carrying. In quit mode the cycle
  is now a loop: it re-reads the flag map at every pass and sleeps between two
  passes on `_transfers_changed` (set by a plan that leaves flags, and by every
  departure that ends), never on a clock. It comes back only when
  `_settle_transfers` says the departures are over, which is BOTH halves — no
  flag left AND nobody on his way out — because a flag popped by the man who is
  at that instant writing his parcels would otherwise let the quit leave from
  under him. An ordinary cycle is unchanged: one pass and back.
  *Neutralization:* putting the one-shot `for` back hangs
  `test_a_user_flagged_after_the_first_pass_leaves_with_the_quit_all_the_same`
  on its 5 s bound.
- **[R2] A failed pull drops the row.** `adopt_user`'s failure path put the row
  back to `frozen` and left it resident — an unknown user turned into a
  half-born one, contradicting F41's «no resident frozen row» and needing a
  reconciliation with the verdict that nobody wrote. Now the row goes whole
  (`_release_rows`, the same verb the freeze ends on), with a loud ERROR line;
  the parcel stays in the deposit and the mark stays on at the vertex, so the
  next request of his carries the verdict again and the adoption retries BY
  CONSTRUCTION — the unified row's own shape, no retry machinery. The sisters of
  the burst, who awaited a transition that ended in nothing, are woken with a
  failure of their own instead of being handed a row that is not there. This
  supersedes the Phase 2 note «A failed pull leaves the row `frozen`» (marked
  there). Two tests re-shaped, one added.
  *Neutralization:* restoring `item["state"] = "frozen"` fails all three (the
  retry story, the sisters' story, and the wait-limit story in the departures
  suite).
- **[R3] The write window closes, and the parcels travel as a photograph.**
  Two defects in one method. (a) `_get_user_parcels` handed the LIVE `Bag` to
  the service pool, where `FreezeHandler` pickles it under no lock of ours: the
  docstring's «photographed before it was handed over» was simply false. The
  handler pickles internally, so pre-pickled bytes would have changed what the
  adoption reads back off the disk; the smallest change that makes the sentence
  true is therefore a DEEP photograph under the dispatch lock — microseconds at
  the ratified 2 KB scale (F28), and nothing live crosses the pool boundary.
  (b) The pendings/row question was asked before the write and never again, so a
  call born DURING the write was photographed mid-flight and its user parked
  under it. It is now asked a third time, in the same locked breath as the
  announcement and the release of the rows, with the folder semaphore still
  held: a call born meanwhile takes the just-written parcels back off the
  deposit (`_drop_parcels` — dropping what is not there is the same outcome),
  leaves him active with his flag, and the tail of that very call is what parks
  him. The announcement moved INSIDE the semaphore for it, which is why
  `test_a_departure_that_falls_over_does_not_keep_the_worker_alive` had to be
  re-shaped: the `BreakingDeposit` breaks on the way OUT, after the parcels are
  written and the rows released, so both men really leave — what the containment
  buys is the exit being reached anyway, with the falls counted.
  *Neutralization:* forcing `leaving = True` parks a user with his call open
  (the born-during-the-write test); returning the parcels without `deepcopy`
  writes a mutation made during the stall onto the disk.
- **[R4] The D8 road goes through the claim.** `freeze_all_users` — the mass
  cycle of a lost wire — froze straight, so a user the transfer cycle was
  already carrying was asked for a second time and parked on the folder
  semaphore THIS worker was holding: a wait that can only end in the deadline,
  with a WARNING naming the worker as its own obstacle and a `freeze_failures`
  that means nothing. It now goes through `_claim_departure` /
  `_release_departure`, the one claim all three roads share (cycle, end-of-call
  hook, mass cycle).
  *Neutralization:* freezing straight logs «the deposit folder of mario is held
  by standard_0001» and counts the failure.
- **[R5] The terminal plan covers `unfreezing` rows.** During a quit a row
  mid-adoption was flagged by nobody — `plan_transfers` only judged the active —
  so the quit could not see it, reached `exit_process` and shut the service pool
  the pull was running on. A row mid-adoption is now a straggler like the man
  with a call open: the terminal plan cedes him, and `_execute_transfer` waits
  the transition on the sister event before freezing him (or finds R2's drop and
  has nothing left to do). The exit is behind the last of them.
  *Neutralization:* not flagging the non-active rows lets the quit exit while
  the pull is still parked, and the adoption then dies on a shut pool.
- **[R6+R7] Honesty and names.** (a) The `[5]` claim above said the gate half
  was proven; only the newborn test proved it, because the straggler test slept
  out the restarted gate before closing its call. That sleep is gone: the cycle
  is now given its turn on the shot and goes back to sleep, and the call ends
  INSIDE what a restarted gate would cost, so the hook is the only thing that
  can free him — and a shot that shut the gate again leaves the quit with nobody
  to wake it. Note that R1 changed what this test can see: with the chewing
  cycle a restarted gate is no longer fatal by itself, since the cycle re-passes
  on the shot; the falsifying shape is the one where the hook is alone.
  (b) Three private renames, by rule 11: `_freezable_item` → `_get_freezable_item`
  and `_user_parcels` → `_get_user_parcels` (pure readings that take an
  argument wear `get_`; the second's docstring now says what the two things it
  returns ARE — the payload of the store, and one parcel per connection), and
  `_transfers_running` → `_departing_users` (a set of users, named for what it
  holds and not for the routine that fills it). Mentions in these notes updated
  in place.

Two windows left standing, declared rather than papered over:

- **A call that closes during the abort of R3.** If a call born during the write
  ALSO closes in the instant between the re-question and the flag decision, its
  end finds the claim still taken and bounces, and the flag is then popped
  because the pendings are empty. Outside a quit the next shot re-flags him and
  nothing is lost. Inside a quit the cycle would settle with him resident and
  his parcels already dropped — he stays in a process that is leaving. Closing
  it needs `freeze_user` to tell went / refused / DEFERRED apart, which is a
  third outcome on a verb the round-1 ruling gave two; left for the owner.
- **The pull that lands just before its `open_request`.** `_serve_request` opens
  the pendings AFTER `_resolve_row` has adopted, so between the two there is no
  call on the registers. The R5 waiter can wake in exactly that gap and park the
  man whose request is being resolved; the request then rebuilds him through the
  ordinary births and is served, but the parcel just written stays on disk and
  he is resident in a worker that is leaving. Moving `open_request` before the
  adoption is the fix, and it is a change to the serving path, not to the
  departures.

## Review fixes

The whole-diff review of Macro 2 came back with eight findings, all confirmed by
executed probes. The owner ruled on the two design ones (F41 in the interview
register, design §7.1 + §7.5 amended with it). Every fix below is in
`spa_worker.py` and its tests; no other source module was touched, and the fixes
took the suite from 1812 to 1827 passing.

- **[1+2] The valve rejoined the one departure scheme.** `freeze_idle_users`
  was a road of its own: it froze on the spot, KEPT the row resident with an
  emptied store and a placement pointing at this worker, and queued the
  announcement behind. A user coming back inside that window found himself
  walled into an empty store, and a row reborn under him swallowed the verdict.
  The owner's ruling removed the second road instead of adding a rule to it. The
  verb is gone from the public surface; the idle criterion now lives inside
  `plan_transfers` — silence past `user_idle_freeze_delay`, judged on the real
  clocks, is one more reason for a `'T'`, and expiry still wins over it on the
  same user. `freeze_user` lost its `placement` parameter: EVERY freeze now
  removes the row whole and announces `user_frozen` with `placement=None`, the
  key kept as the protocol slot M3 will fill. `_release_rows` lost the in-place
  branch with it. *Neutralization:* putting the idle criterion back out of
  `plan_transfers` kills the three valve tests and the e2e; restoring the
  resident emptied row kills the e2e (the photo still shows him) and the
  departures story.
- **[3] One departure per user at a time.** The transfer cycle and the
  end-of-call hook could both be inside `freeze_user` for the same man, because
  the flag was only popped when the freeze was over. `_execute_transfer` now
  CLAIMS the departure under the dispatch lock, before its first await
  (`_departing_users`), and whoever arrives second finds nothing to do. Same
  method contains what goes wrong for one user — counted in `freeze_failures`,
  logged, and the cycle goes on — so `quit()` reaches `exit_process()` even when
  a departure raises where nothing else catches it. *Neutralization:* removing
  the claim makes the hook queue behind the semaphore this worker itself holds
  (the test's bounded `close_request` times out); removing the containment makes
  a `quit()` over a deposit that breaks on release raise instead of exiting.
- **[4] The pendings question is asked twice.** The row was judged once, before
  a wait for the folder semaphore that can last as long as another worker likes;
  a request born in that window was then photographed mid-flight. `freeze_user`
  asks again UNDER the semaphore (`_get_freezable_item`, the one place the three
  conditions live), and on a call born meanwhile it gives the semaphore back and
  leaves the user active — his flag stays, and the tail of that very call is
  what parks him. Same doctrine as `adopt_connection`'s double question: a check
  taken before the window it decides about decides nothing. *Neutralization:*
  dropping the second question writes his parcel while his call is open.
- **[5] `quit()` owns the plan.** A `plan_transfers` taken while the quit waited
  for a straggler reset the bookkeeping: flags cleared and the gate clock pushed
  forward, so the exit could be reached with somebody still on board, or never
  reached at all. In quit mode the plan is now terminal — every active user is
  ceded, no flag already given is taken back, and the gate already open is not
  shut again. *Neutralization:* the gate half was claimed proven by two tests;
  the re-review found only ONE of them falsifying — the newborn's — because the
  straggler test slept out the restarted gate before closing its call.
  Corrected in round 2 (see `[R6a]`): the straggler test now closes inside what
  a restarted gate would cost, and the two stand together. The
  flag-reset half is NOT falsifiable on its own: with `_quitting` in the
  decision every flag a reset could drop is re-derived in the same locked
  breath, so the property holds twice over. Removing BOTH halves kills both quit
  tests, which is the honest proof available. Left standing as the literal shape
  of the ruling — and noted for M3: a flagged user removed from the register by
  a drop cascade would leave a stale flag and a quit that never ends, which
  nothing in M2 can reach because no wire op drops a page or a connection.
- **[6] The dispatch lock never spans disk IO.** `_write_parcels` ran on the
  service pool and took the dispatch lock for the whole write, so a slow disk
  froze every mutation on the loop. The rows are now copied out under the lock
  (`_get_user_parcels`, memory work) and the write is handed to the pool with the
  lock let go. *Neutralization:* putting the lock back around the write makes a
  concurrent `add_page` wait out the whole stall.
- **[7] The semaphore wait got a floor and a voice.** It was an unbounded silent
  `while not take_lock: sleep`. The first miss now says at WARNING who is
  holding the folder — once per wait, not once per look — and the wait is bound
  by `DEPOSIT_LOCK_WAIT_LIMIT` (module constant, 30 s, the `TRANSFER_START_DELAY`
  precedent: a technical time, mirrored by a `deposit_lock_wait_limit` kwarg so
  a test can shrink it). Past it the operation aborts LOUD: an adoption raises
  and the caller's own REPLY carries the failure (one REPLY per CALL preserved,
  asserted over the wire), a freeze takes the B1 shape — user alive, counted,
  nothing announced. The docstring says what the bound is not: the per-order
  budget is the Commander's parking budget (F13), and arrives with M3.
  *Neutralization:* logging inside the loop gives many lines instead of one;
  removing the deadline hangs the bounded freeze test.
- **[8] The three vacuous coverages became real tests.** (a) a served http CALL
  now has to WRITE `last_rpc_ts` again — the row is pushed a minute into the
  past between two calls and the stamp must come back ahead of the first, where
  the old test only asked for a birth stamp; (b) a wake is a population change —
  with the long ttl the reply to the waking call must carry a photo and the next
  beat must not; (c) the guard on a row that is not `active` is asserted on a
  row mid-adoption, which is the only non-active state left now that no frozen
  row is resident. All three die when the behaviour they name is removed.

Two shapes the fixes needed and the texts did not spell:

- **`_get_freezable_item(user)`** — the three conditions of «he may leave now»
  (here, active, nobody calling) in one private reading, because they are now
  asked more than once in the same method and a copy would rot. Private, and
  wearing the `get_` prefix of rule 11 (a pure reading that takes an argument).
- **The e2e drives the shot, not the valve.** The story's own routing keys are
  now `/op/plan_transfers` and `/op/execute_transfers` beside `/op/quit`: the
  valve has no verb to call any more, so the driver orders the SHOT (whose reply
  carries the flags it decided) and then the CYCLE (whose reply, taken when the
  cycle is over, carries the `user_frozen` with placement `None` and the photo
  with his row gone). In the machine proper neither is an order at all — the
  shot belongs to whoever composes a due photo — which is what the key names
  say by naming the verbs they drive.

## Phase 5

No source module was touched. The choices below are all test-side, and the first
one is the finding the phase came back with.

- **The two orders are the test's own, because the wire has none.** `quit()` and
  `freeze_idle_users()` are verbs of `SpaWorker` that nothing routes to:
  `answer_call` knows the beat and the http form, and `WorkerEntry` ticks no
  valve. In a real child both are therefore unreachable from the parent. Rather
  than teach the protocol an op the design has not decided, or patch src from a
  test phase, the e2e's worker is `DrivenWorker` — a `SpaWorker` heir living in
  the test package, which is the place a consumer already extends the worker
  (the genropy-asgi bridge assigns `wsgi_app` there) — and it answers
  `/op/freeze_idle_users` and `/op/quit`, both declared in its own docstring as
  routing keys of this test and not of the protocol. The precedent is the M1
  `child_stub`, whose deposit orders are its own in exactly the same sense. The
  real callers are M3's: the group orders the departure, the metronome drives the
  valve.
- **The quit order is started before its reply is composed.** The owner's shot
  logic says the departure decision lives inside the photo, and the photo is
  taken while the reply envelope is built. So the order handler creates the
  `quit()` task, gives it its one turn (`await asyncio.sleep(0)` — enough,
  because `plan_transfers` is synchronous and `execute_transfers` parks on the
  gate) and only then replies: the flags are on the photo that answers the order.
  Proven by neutralization — without that turn the photo carries `None` for
  everybody.
- **The child's global store is read back through the site.** Nothing on the
  parent side can look inside the child, so the tiny site answers an
  `X-Global-Store` header with what the process holds; the assertion compares it
  with the handler's own `global_register_item_tytx`, which is what the
  presentation was answered with.
- **The photo ttl is 0 in this story.** Every envelope then carries a photo, so
  the story reads what the photo SAYS with no timing race; the throttle itself is
  Phase 4's test and is not re-proven here. The two grammars that ARE timings are
  shrunk through the spawn kwargs — `user_idle_freeze_delay` 0.5 s and
  `transfer_start_delay` 0.5 s (from the module's 2.0) — and every wait is
  bounded by a multiple, never by a measure.
- **The freeze announcements of `quit()` are lost with the wire.** Each parked
  user queues a `user_frozen` with placement `None`, and the worker closes the
  wire on its way out before any envelope carries them. Nothing is lost in
  substance — the flagged photo that answered the order already named everybody
  leaving — and the test asserts what survives instead: the parcels in the
  deposit, the folders, the free semaphores. Worth M3's eye when the fold decides
  what it reads.
- **Two users, on purpose.** One goes silent and is parked by the valve, the
  other speaks just before the order and is left alone: a valve that froze
  everybody would pass a one-user story.
- **The wild denunciation is asserted twice** — the group told
  (`on_worker_abort` with the handler and the users on board) and the WILD line
  in the handler's log — because that seam is the whole point of the chapter and
  the M3 change will have to move both.

## Phase 4

Names the phase needed and F40 does not carry. All of them are either inherited
verbatim from a class that already has them or composed of words the design uses
in this exact sense; each is open to a different ruling.

- **`WorkerEntry`** (the child shell) — inherited verbatim from the legacy
  `spa/worker_entry.py`, module path included, because it is the same object in
  the new machine. The two classes never meet (different packages, no import in
  either direction) and the legacy one dies at Macro 6; the alternative was
  coining a name for a thing that already has one.
- **`attach_stream(stream)`** — the legacy `attach_channel(channel)` with the
  object renamed to what is actually handed in (a `FrameStream`, not a channel:
  the multi-member switchboard is dead).
- **`send_presentation(config)`** — «presentation» is `worker_connector`'s own
  word for this frame («Read the presentation»), and the verb says who sends.
- **`receive_frames()`** — the child side of `WorkerConnector._receive_loop`, as
  a public verb because the shell drives it. Transitive, so it carries its
  object.
- **`on_wire_lost()`** — the exact mirror of the ratified
  `WorkerHandler.on_child_lost`, for the exact mirror fact: D8 calls the two
  guardians symmetric, so they are named symmetrically.
- **`handle_frame` / `answer_call` / `serve_http` / `send_reply` / `call`** —
  inherited from the legacy worker and the connector, same meaning in both (the
  homonymy check: `serve_http` still means «hand the http dict to the seam»,
  `send_reply` still means «answer this CALL with its sub-envelopes»).
  `serve_http` takes the WHOLE payload instead of `(http, identity)`: the row is
  resolved from the `http` dict, the `identity` and the `user_frozen` verdict
  together, and splitting them at the door would only put them back together.
- **`traffic_pool` / `service_pool`** — the design's own two words («pool del
  TRAFFICO», «pool di SERVIZIO»); the legacy `pool`/`http_pool` pair says
  nothing about which is which.
- **`rss_bytes`** — inherited from the legacy worker, turned into a property by
  rule 11 (a pure reading with no arguments). /proc-only, `None` on macOS, no
  dependency taken; the photo carries the counts either way.
- **`WORKER_SNAPSHOT_TTL = 0.5`** and **`CLOCK_NAMES`** — module constants. The
  first is the default of the baptised `worker_snapshot_ttl` grammar (the design
  cites «~500 ms»); the second names the three ratified clocks in one place,
  read by `_stamped` and by the photo.

Shapes the texts did not spell, and how they landed:

- **The photo's own shape.** Aggregates (`pid`, `name`, `group`, `rss_bytes`,
  `user_count`, `connection_count`, `page_count`), `connections` keyed by cid
  with the user and the three clocks, `users` keyed by identity with
  `{"item": ..., "transfer_flag": ...}`. The pair is a named dict rather than a
  two-element list: JSON has no tuple, and a reader that has to remember which
  slot is which is exactly what rule 9 forbids. The user item is PROJECTED —
  `state`, the three clocks, `connection_count` — because the register item
  carries a `Bag` store and a set of connections, neither of which is
  JSON-serializable and neither of which is the observer's business (the legacy
  `monitor_state` draws the same line).
- **The photo is attached, never pushed.** «Ogni cambio di popolazione manda la
  sua foto» is implemented as: a user-level announcement (`new_user`,
  `drop_user`, `user_frozen`, `user_adopted`) marks the photo due, and the next
  envelope out carries it whatever the ttl. There is no push road in M2 — the
  worker sends nothing on its own initiative, and the beat every 5 s is itself
  an envelope, so a population change is on the parent's desk within one beat.
  Inventing an EVENT path for the photo would have been inventing protocol.
- **The store replica is kept in the form it travels.** `global_register_item_tytx`
  is stored as the string that came down, replaced whole. Decoding it into a Bag
  belongs with the master that produces it (Macro 3): the M1 placeholder the
  handler answers today is not TYTX at all, and a child that tried to decode it
  would die at the handshake.
- **The cid of a request travels inside the `http` dict** (`http["cid"]`), which
  is what design §10 lists among what the front packs. It is read directly: a
  request that names no connection cannot be routed, and the KeyError comes back
  as the CALL's error REPLY.
- **The identity that equals the cid is the anonymous one.** The front hands
  `connection_user.get(cid, cid)`, so `identity == cid` means «nobody has folded
  him yet» and the row is born `guest_<cid>` through the worker's own naming
  (`add_connection(cid, None)`). One line at the door, no new name.
- **The http form stamps the connection and its user, not a page.** The form
  names no page (the page protocol is Macro 4's), so `refresh_chain`'s climb is
  reused one level down through the shared `_stamp_items`: `last_refresh_ts`
  plus `last_rpc_ts`, the real clock a real call proves.
- **Exactly one REPLY per CALL, whatever fails.** The row resolution, the
  pendings and the WSGI stitching are one `_serve_request` inside `serve_http`'s
  try: a deposit that refuses a parcel used to leave the caller waiting for its
  timeout. The refusal for a missing `wsgi_app` stays FIRST, as in the legacy —
  nothing is born on the registers for a request that was never served.
- **The pendings of the worker's own CALLs fail when the wire ends**, mirroring
  `WorkerConnector._fail_pending`: `call()` promises `ConnectionError`, so
  something has to raise it.
- **`exit_process` closes the wire.** That is what ends the read the shell is
  parked on, so `quit()` really returns the process; the pools are shut down
  with it. No `os._exit` anywhere: the shell returns from `asyncio.run` and the
  process ends by itself (proven by the real child exiting 0).
- **No SIGTERM handler.** The legacy entry had one because the commander asked
  politely; the M1 handler only SIGKILLs, so a handler for a signal nobody sends
  would be dead code.
- **An inbound EVENT is logged, not served on a task.** The ratified division of
  labour gives EVENT a task because it runs a consumer; there is no consumer
  downward in M2 (the one thing that travels down is the store, taken off the
  envelope before dispatch), so it says «not consumed yet» exactly as the parent
  side does for the other direction.
- **`ThreadPoolExecutor` directly**, not the legacy `WorkPool`: that class lives
  in `spa/worker.py` and is untouchable this macro. What the worker needs of it
  — run this callable on that pool — is one `run_in_executor`; the metrics
  `WorkPool` also carries have no reader here yet.
- **mypy** reports 8 advisory findings on the two modules, all of two kinds
  already present on `worker_handler.py`: attribute access on an Optional the
  lifecycle guarantees (`stream`, once attached) and `Any` out of a schemaless
  dict. Nothing silenced in code, `pyproject.toml` untouched.

## Phase 2 — post-land rename (owner, 2026-08-16)
The birth methods had been named after the announcements they emit
(`new_user`/`new_connection`/`new_page`). The owner ruled for naming
rule 11: a mutation opens with the verb — the methods are now
`add_user`/`add_connection`/`add_page` (the legacy daemon's own verb,
whose `add_user` announces `new_user`). The WIRE names stay `new_*` as
ratified in F40; only the methods changed. Renamed by the foreman in
its own commit, tests updated, announcements untouched.

## Phase 1

Three executor choices the plan did not spell out, all inside the ratified
retrofits and none of them a new baptism:

- **The two file-name constants followed their files.** F40 names the parcels
  and the verbs, not the constants that hold the parcel names. Leaving
  `USER_ITEM_NAME = "user_register_item.pickle"` would have produced exactly
  the "nomi solo parzialmente coerenti" F40 gives as its own reason, so they
  became `USER_REGISTER_ITEM_NAME` and `CONNECTION_REGISTER_ITEM_PREFIX`.
  They are module constants of `freeze_handler.py`, exported in its `__all__`
  and read by nobody outside it yet.
- **The child stub's deposit order was renamed with the verb it drives.**
  `WRITE_CONNECTION_ITEM_OP` / `write_connection_item` became
  `WRITE_CONNECTION_REGISTER_ITEM_OP` / `write_connection_register_item`
  (the routing key `/write_connection_register_item` with them). The stub's
  docstring declares its routing keys its own, but this one names the deposit
  operation it wraps, so it moved with the deposit vocabulary. The stub's
  other keys (`/emit_one_event`, `/go_mute`, the lock orders) were left alone.
- **`answer_occupancy` became `answer_ping`.** Forced by the done gate, which
  greps for the word `occupancy` in `tests/orchestration/`, and correct on its
  own terms: the stub method answers the beat.

Nothing else was touched. `worker_connector.py` was in the phase's allowed
file list but needed no change — it names neither the deposit items nor the
beat op. The legacy `spa/worker.py`, `spa/commander.py` and `channel/` still
carry the word `occupancy` in their own (untouched) vocabulary; the gate is
scoped to the new subpackage, and so was this phase.

## Phase 2

Executor choices the plan did not spell out. The first three are the ones that
deserve a ruling; the rest are consequences.

- **`adopt_connection` carries the user.** The plan writes
  `adopt_connection(cid)`, but a connection parcel lives inside the USER's
  folder and the deposit surface asks for both
  (`read_connection_register_item(user, cid)`) — the cid alone reaches nothing,
  and `user_to_userkey` goes one way so the folder cannot be found backwards.
  Landed as `adopt_connection(user, cid)`, in FreezeHandler's own argument
  order. No name was invented; only the missing argument was added.
- **The connection parcel shape.** Phase 2 READS a parcel Phase 3 has not yet
  written, so its shape had to be fixed here:
  `{"connection": {<clock fields>}, "pages": {page_id: {<clock fields>}}}`.
  The connection half carries no `user` (the folder already says whose it is)
  and no `pages` set (rebuilt from the pages half), so the adoption can feed
  both halves straight into `new_connection(cid, user, **fields)` and
  `new_page(page_id, cid, user, **fields)` — the schemaless passthrough of the
  mutators, no translation layer. Phase 3's freeze writes the mirror image.
- **The plural announcements needed keys.** `drop_pages` and `drop_connections`
  are inherited names that never had a handler in the legacy worker (reserved,
  unimplemented), so nothing said what they carry. They travel as
  `page_ids` / `session_ids` — sorted lists of the singular keys the inherited
  `drop_page`/`drop_connection` already use. A cascade speaks the plural once
  rather than N singulars: dropping a connection announces its pages as one
  `drop_pages`, dropping a user its connections as one `drop_connections`.
- **`refresh_chain(page_id, *clocks)`** — the name is the one the current core
  and the daemon both use for this climb, and the clocks are named by their
  own baptised names as positional arguments, so nothing new is exposed:
  `last_refresh_ts` is stamped by every contact, `last_user_ts` and
  `last_rpc_ts` only when the caller names them. No validation of the names
  (the three-questions rule: nobody asks for it, the callers are the worker's
  own dispatch).
- **`offer_event`** is the inherited queueing verb of the current core, with a
  simpler contract: it always queues, since there is no operational/lifecycle
  split here. The announcement is `{"op": ..., "worker": <name>, **payload}` —
  the legacy shape minus `seq`, which belongs to the outbox and its per-seq ack
  (the wire, Phase 4).
- **Every item is born stamped on all three clocks.** The legacy stamps only
  `last_refresh_ts` at birth and lets the others default; here a birth IS a
  real contact, so the valve and the expiry judge (which read the real clocks,
  F32) never meet a `None` and need no fallback to a start time.
- **`deposit_lock_retry_interval` arrived one phase early.** It is Phase 4's in
  the plan, but the adoption itself is what waits on a busy folder (§8.3, F27),
  and the wait had to be a coroutine on the loop from the start. Constructor
  kwarg with the baptised name, module default `DEPOSIT_LOCK_RETRY_INTERVAL =
  0.05` (the same value `worker_handler.WAIT_POLL_INTERVAL` uses for its own
  polls); Phase 4 has only to feed it from the grammar.
- **A user announced frozen with no parcel still wakes.** C4's third row
  ("mark on, file absent") is a declared problem, not a crash: the row goes
  `active` with an empty store, the miss is logged as a warning, and
  `user_adopted` is announced ANYWAY — the mark at the vertex must go off, or
  every later request re-carries the verdict and re-trips the adoption forever.
  Counting it is the Commander's, in Macro 3.
- **A failed pull leaves the row `frozen`.** If the deposit read raises, the
  row goes back from `unfreezing` to `frozen`, the sisters are woken, and the
  error propagates loud (B1's shape: the user stays where he is, nothing is
  silently half-done). Tested.
  **SUPERSEDED in review round 2 by F41** (which leaves NO frozen row resident,
  transitory or otherwise): a failed pull now drops the row whole — see
  `## Review fixes — round 2`, `[R2]`.
- **`adopt_connection` asks its question twice.** Once before the trip (a
  connection already held costs no disk at all — F9's «beta io non l'ho») and
  once after it, under the lock, because the trip is a handoff and a sister may
  have installed the connection meanwhile. The second is the legacy
  `wire_delivery` doctrine, not a guard: a check taken before the window it
  decides about decides nothing.
- **Deposit IO runs inline on the loop** in this phase — there is no service
  pool until Phase 4. Declared in the module docstring's closing paragraph so
  the move has a place to land.
- **mypy** reports one advisory finding on the new module
  (`_page_user` returning `Any` out of a schemaless item dict), the same
  category as the three it already reports on `worker_handler.py`. Nothing was
  silenced in code and `pyproject.toml` was outside the phase's file list.

## Phase 3

The names F40 does not carry, and why these. Every one of them is either
composed of words the register already uses in this exact sense or inherited
verbatim from an existing class; none is a coinage, and all five are open to a
different ruling.

- **`decide_departures` / `execute_departures`.** F40 baptises the SCHEME («lo
  schema delle partenze») and the flag, not the two methods. The register writes
  «il worker, allo scatto della foto, DECIDE LE PARTENZE», and `decide_*` is
  already a house verb (`decide_worker`); the pair decide/execute mirrors the
  Commander's own `build_plan`/`execute_plan`. `decide_departures` mutates (it
  remembers the flags and starts the gate clock), so it leads with the verb.
- **`open_request` / `close_request`.** Not new: they are `commander.py`'s own
  pair, where `close_request` ALREADY carries the behaviour this phase needs —
  the last live call of a user closing is what launches his move. Same meaning
  in both classes, which is what makes the homonymy legitimate rather than the
  transcription trap. The worker's pair drops the arguments it does not need
  (`worker`, `path`) and the bookkeeping is a plain count per user: minimal,
  and no id is asked of anybody in this phase.
- **`freeze_idle_users`.** The §7.5 valve had a Italian description and no verb.
  Composed of the phase's own words; a plain periodic check the tests call
  directly, since Phase 4 owns the task wiring.
- **`exit_process`.** Mirror of the ratified `WorkerHandler.launch_process`, and
  the transitive-verb rule wants the object in the name (the worker does not
  exit itself, it exits its process). The base only records the point was
  reached (`exited`); the shell of Phase 4 makes it real. No `os._exit` in
  library code.
- **`freeze_failures`.** B1 says the failed departure is «logged and counted»
  and nothing named the count. Read property over the private counter.

Shapes and signatures the plan did not spell:

- **`decide_departures(*, transfer_users=(), expiry_delay=math.inf)`.** The
  worker has no measures of its own yet, so the choice of whom to cede is handed
  in by the caller — the plan's «memory → fattest, load → costliest, preferring
  no in-flight calls» is documented on the parameter and is what Phase 4+ will
  compute. `expiry_delay` is likewise the caller's (grammar); `math.inf` as the
  default means «nobody is expired» without inventing a duration, and the same
  trick gives `user_idle_freeze_delay` a default that never fires — no `None`
  and no dead guard once the grammar feeds them.
- **The photo pairs are `{user: (item, flag)}`** — every user row, kept ones
  included, since F40 says the photo carries the pair per user. The flag is NOT
  written into the register item (F40: «il register item non lo porta»): it
  lives in a worker-side map that only `decide_departures` fills.
- **`group` is a constructor kwarg.** The deposit header asks for writer, cause
  and group; the worker knew the first two and nothing could supply the third.
  Default `""`, fed from above with the rest of the grammar in Phase 4; the
  header is diagnostic only, so an empty value is a poor label, never a wrong
  decision. `cause="freeze"` is the FreezeHandler docstring's own example.
- **`freeze_user` returns a bool** — went / stayed. The cycle needs to tell the
  two apart (a busy user is come back for, a refused write is not retried), and
  the hook needs it too.

Behaviour the texts imply and the code had to settle:

- **The gate is a clock, not a flag.** `decide_departures` records
  `now + transfer_start_delay`; `execute_departures` sleeps out the remainder
  and the end-of-call hook refuses to act before that instant. Without it a call
  closing INSIDE the gate window would park its user before the fold had parked
  him — exactly the race C1 closes. One derived truth instead of an oracle
  boolean somebody has to flip.
- **A freeze announces `user_frozen` and nothing else.** The rows leave memory
  with no `drop_*`: the fold's single mutator writes map + mark on the freeze
  announcement, and a `drop_user` beside it would say he is gone for good. The
  wake re-announces the births (Phase 2's adoption), so no announcement is lost.
- **The valve leaves the row behind, a departure does not.** With placement =
  the worker's own name the user row stays `frozen` with an emptied store (the
  memory is the whole point) and wakes in place; with placement `None` the row
  goes entirely — he is the vertex's to place now.
- **`quit()` reaches its freezes through the flagged cycle**, not through
  `freeze_all_users()`: at quit everybody IS flagged, so the two are the same
  set, and one code path is better than two. `freeze_all_users()` stays as the
  plain B2 mass cycle the plan asks for — its other caller is the D8 self-defense
  of Phase 4 (dead wire → freeze all, exit).
- **`quit()` waits for the stragglers.** A user with a call in flight is parked
  by the end of that call, so quit awaits the departure of the last flagged user
  before reaching the exit (an `asyncio.Event` set when the flag map empties):
  leaving earlier would truncate a response, which D10 forbids.
- **Frozen rows are never flagged**, quit included: F40 gives the active to the
  worker and the frozen to the vertex, and a frozen user's parcel is adoptable
  by whoever the vertex places him on.
- **A refused write leaves what it managed to write.** No cleanup was added: the
  user stays `active` and unannounced, so nobody will ever adopt that residue,
  and the sweep is what the deposit's own docstring points at.
- **mypy** now reports two advisory findings on the module, the second being
  `_last_real_activity` returning `Any` out of a schemaless item dict — the same
  category as the first. Nothing silenced in code.

## Phase 3 — post-land rename (owner, 2026-08-16)
The pair deciding and executing the departures had been named
`decide_departures`/`execute_departures`; the owner ruled for the
transfer family his own baptisms already use (`transfer_flag`,
`TRANSFER_START_DELAY`, and the ruling that the X too is a transfer —
to the cemetery): the methods are now **`plan_transfers`** /
**`execute_transfers`**, internal bookkeeping renamed with them.
"Departure" stays as the prose word for the concept (F40's «schema
delle partenze»); the code family speaks transfer. §14's dead
`build_plan`/`execute_plan` are the Commander's ladder — different
object, no collision. Renamed by the foreman in its own commit.

## Phase 4 — the shot logic, dictated (owner, 2026-08-16)
On a reply the worker checks whether more than `worker_snapshot_ttl`
(~500 ms) passed since the last shot — if so it takes the photo and
sends it, and THE DEPARTURE DECISION LIVES INSIDE THE SHOT. Departures
are never decided in a vacuum: the flagged photo is born inside an
outgoing envelope and leaves with it, so the announcement is immediate
by construction; a worker with no traffic still shoots on the beat
reply (5 s cadence > TTL). Consequence: no dedicated EVENT push is
needed and the 2-second gate always starts from an announcement already
sent. Wiring rule for M3 (and the Phase 5 e2e where applicable):
`plan_transfers` is invoked by the point that composes a due photo for
an outgoing envelope; the gate timer starts at that send. In M2 the
tests call `plan_transfers` directly, which is why the gap seemed to
exist. Design §7.1 amended with the dictation.
