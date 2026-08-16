# Notes — orchestration-m1-foundations

## Phase 1
Two decisions surfaced by the executing chat were settled by the foreman
and folded into the plan (owner's standing expectation: the executor
must never ask the user — every choice is pre-made at planning):
1. read surface: bare payload + `get_item_header` (rule 11), no wrapper
   type (rejected: FrozenItem NamedTuple — a new type with nothing to
   carry beyond diagnostics);
2. lock lifecycle: drop_* never touches the lock; release_lock removes
   it and removes the folder when only the lock remains (rejected:
   drop-last-item removing folder+own-lock — two removal points for
   one lock).
Planning lesson for the next macros: batch EVERY baptism and micro-shape
question at plan time (the F39 session did it right; these two slipped).

Choices made during execution that the plan did not settle:
- `user_to_userkey` is REDEFINED in FreezeHandler rather than imported from
  `spa/commander.py`: the new subpackage must not depend on the machine that
  dies at the cutover. Same implementation (`quote(safe="")`), same one-way
  contract; the duplication disappears with the legacy commander.
- The three removals were born as `delete_*`, the only ones in `src/`: the
  owner named `drop_` the house verb (2026-08-16) and they were renamed —
  `drop_user_item`, `drop_connection_item`, `drop_user_folder`.
- `drop_user_item` added beside the two drops the plan listed: adoption
  reads then drops BOTH item kinds, and a user store that could only be
  removed by wiping the whole folder would have forced callers to reach for
  `drop_user_folder` while the connections still matter.
- The item drops were written raising `FileNotFoundError` on a missing file;
  the owner OVERRULED it (2026-08-16): a drop asks for absence, and a thing
  already gone is that same outcome. All three drops are now idempotent —
  `drop_user_folder` additionally verifies the result. The reason that
  settled it: the cleanup after a dead worker is the ordinary caller, and it
  walks over parcels the dead one may or may not have written.
- The connection filename quotes the cid with the same one-way key as the
  user: a cid comes from a cookie, and no value of it may name a file outside
  its folder.
- `user_folders` is a property (naming rule 11: a pure reading with no
  arguments is a noun), scanning directory entries without opening any file —
  the shape the 4-step sweep consumes.

## Phase 2
The phase was executed with three callbacks handed to the connector at
construction (`on_handshake`, `on_event`, `on_closed`). The owner OVERRULED
the shape and the substance behind it on 2026-08-16, in the review that
followed; what is written below is the settled state, with the reasons.

**No callbacks: the wire asks the handler it already holds.** The connector
keeps `self.worker_handler` from birth, so a callback passed in the
constructor was a second road to the same object. The three surfaces the wire
uses, all baptised by the owner, all implemented in Phase 3:
`global_register_item_tytx` (property — the whole global store, TYTX-encoded,
asked at the instant the child presents itself so it is never stale),
`on_child_message(frame)` (an EVENT arrived from the child),
`on_child_lost()` (the wire died on its own). The same string
`global_register_item_tytx` is the key of the reply payload: not a second
name, the same one.

**The store goes WHOLE, and the version number is abolished.** The version
existed so a newborn could tell which deltas were already inside its snapshot.
The owner ruled that the master replaces the replica entire — at the
presentation like at every later change — so there are no deltas to order and
nothing to number. The measured ground: the global store is kilobytes and
changes about once every three hours, so resending all of it to every worker
costs nothing. This AMENDS design v3 §12 ("delta, FIFO per filo" and "numero di
versione su ogni variazione") and kills the `genroasgi_global_store_version`
metric of §13.2.

- `wait_connected()`: Phase 3 says "spawn → wait handshake (via
  WorkerConnector) → serving", so the wait needs a surface. It is the mirror
  of `ChannelClient.wait_closed()` and, like it, carries no deadline of its
  own — the caller wraps it in its own `asyncio.wait_for`.
- The child's presentation payload (pid, config echo) is no longer handed to
  anybody: it reaches the log. Nothing consumes it today, and Phase 3 can
  expose a reading on the connector if it turns out to need it.

## Baptism round for Phase 3 (owner, 2026-08-16)
Held BEFORE launching the phase, the lesson of Phase 2 applied: every public
name Phase 3 needs was decided by the owner first, so the executor asks
nobody. The names are listed in the phase's `Decisions:`; what follows is
what the round changed beyond naming.

- **A verb never stands alone** (new house rule from the owner): a method
  name carries its object — `launch_process()`, not `launch()`. Applied to
  every verb baptised here; worth promoting into the meta CLAUDE.md naming
  rules, which today only say "a mutation leads with the verb".
- **The bonifica leaves the WorkerHandler** (owner's correction, mid-round).
  The design gave the handler a cleanup that had to remove semaphores
  "wherever they are" — i.e. write on indexes owned by the Commander. Now
  the handler only denounces (`on_worker_abort`), the group unhooks, the
  Commander cleans. Two consequences: Phase 3 no longer touches the
  FreezeHandler at all, and the death path matches the one-level-up shape
  used everywhere else. Design v3 amended.
- **No counters on the handler.** Read against the §13.2 table: every
  per-worker family is a gauge fed by the photo, every counter is aggregate
  (`orders_total` by kind/outcome, `relogins_total` by cause) and belongs to
  the Commander — which, after the correction above, is also the one doing
  the cleanup it would be counting. The orchestration log (§4.6) carries a
  line per order AND per wild death (owner: a wild death is nobody's order,
  but it is the event that starts everything).
- **`freezed_users` → `frozen_users`**: the F39 folder name was not English.
  No code carried it — only the plan text.
- The 16 Prometheus families of §13.2 stay `[BATTESIMO]`: they are exposed in
  Macro 5, and naming them tonight would have been naming what nothing yet
  produces.
- CALL/REPLY/EVENT are REDEFINED here with the same values instead of
  imported from `channel/hub.py`: same reasoning as Phase 1's
  `user_to_userkey` — the hub dies in Macro 6 and the new subpackage must not
  hold a reference to it. `REGISTER_METHOD`/`REGISTER_PATH`/`Frame`/
  `FrameStream` ARE imported: `channel/frame.py` survives.
- An inbound CALL from the child is logged as an unexpected envelope, exactly
  as the hub does today: the parent side has no ratified CALL consumer, and
  inventing one here would be a protocol decision, not an implementation
  choice.
- A second connection arriving while the wire is taken is refused and closed,
  the resident stays: the hub's ratified precedent for a duplicate. C2
  guarantees the case cannot happen (the successor is spawned only after the
  OS confirms the predecessor's death), so this is the noisy-error branch of
  the weighted-simplicity rule, never a silent replacement.
- No REGISTER timeout on the accept side (the hub has 10s): the deadline
  belongs to whoever waits for the handshake after a spawn, and a child that
  connects and stays mute is exactly what the Phase 3 probe kills.
- No check on the UDS path length: an over-long path fails at `bind` with an
  explicit OSError, which is the error the caller needs. The limit met us in
  the flesh anyway — the tests bind under a short `mkdtemp` root, because
  pytest's `tmp_path` alone is already past the ~100 character cap. That IS
  the reason worker names are short (E17), and the test module says so.
