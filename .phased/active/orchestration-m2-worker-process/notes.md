# Notes — orchestration-m2-worker-process

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
