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
