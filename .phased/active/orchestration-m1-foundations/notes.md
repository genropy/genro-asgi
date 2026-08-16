# Notes — orchestration-m1-foundations

## Phase 1
Two decisions surfaced by the executing chat were settled by the foreman
and folded into the plan (owner's standing expectation: the executor
must never ask the user — every choice is pre-made at planning):
1. read surface: bare payload + `get_item_header` (rule 11), no wrapper
   type (rejected: FrozenItem NamedTuple — a new type with nothing to
   carry beyond diagnostics);
2. lock lifecycle: delete_* never touches the lock; release_lock removes
   it and removes the folder when only the lock remains (rejected:
   delete-last-item removing folder+own-lock — two removal points for
   one lock).
Planning lesson for the next macros: batch EVERY baptism and micro-shape
question at plan time (the F39 session did it right; these two slipped).

Choices made during execution that the plan did not settle:
- `user_to_userkey` is REDEFINED in FreezeHandler rather than imported from
  `spa/commander.py`: the new subpackage must not depend on the machine that
  dies at the cutover. Same implementation (`quote(safe="")`), same one-way
  contract; the duplication disappears with the legacy commander.
- `delete_user_item` added beside the two deletes the plan listed: adoption
  reads then deletes BOTH item kinds, and a user store that could only be
  removed by wiping the whole folder would have forced callers to reach for
  `delete_user_folder` while the connections still matter.
- The item deletes raise `FileNotFoundError` on a missing file instead of
  passing in silence — a delete is issued for something just read, so an
  absence is a real anomaly. `delete_user_folder` is the exception: its goal
  is absence, so it is idempotent and verifies the result.
- The connection filename quotes the cid with the same one-way key as the
  user: a cid comes from a cookie, and no value of it may name a file outside
  its folder.
- `user_folders` is a property (naming rule 11: a pure reading with no
  arguments is a noun), scanning directory entries without opening any file —
  the shape the 4-step sweep consumes.
