# Notes — orchestration-m2-worker-process

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
