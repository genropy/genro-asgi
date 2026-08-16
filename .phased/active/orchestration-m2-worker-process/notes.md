# Notes — orchestration-m2-worker-process

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
