# Global store — current state

**Version**: 0.2 · **Last Updated**: 2026-09-08 · **Status**: 🔴 DA REVISIONARE

The feature's local memory: what exists TODAY on develop, with the
decisions that shaped it. Update it in the same change that alters the behaviour.

2026-08-22: the replica-era seams (`snapshot`/`load_snapshot`, `/global/*` paths) were removed (a79449e); a site restore does NOT restore the global store.

2026-09-08 (issue #74): the master is one `dict[str, Any]` on the commander — `SpaCommander.global_register`, built by `new_global_store` — with literal string keys and opaque values. Built:

- `GlobalStoreLock` on the commander: one `asyncio.Lock` plus `holder`, `holder_worker` and `holder_key`. Every operation waits on it, reads of other keys included.
- `GlobalStoreOperations` on the commander's dispatcher: `/commander/store/{get,set,del,lock,unlock}`. `get` answers `exists` beside `value`. A non-string key raises `TypeError`.
- `SpaWorker.global_store`, a `GlobalStoreClient`: `get`, `set`, `delete`, `for_update`.
- `GlobalStoreLease`, the turn: `with` or `async with`, yielding itself with `value` and `exists`, plus `abort()`. The exit sends the COMPLETE value with `apply=True`; the commander replaces the selected key, or the whole dictionary when no key was selected. A body that raises, a grant that does not decode, a value that does not encode and an aborted turn release with `apply=False`.
- `GlobalStoreCommitUnconfirmed`: the commit left and the wire failed before the reply. Nothing is retried.
- The death protocol: `WorkerHandler.on_child_lost` calls `GlobalStoreOperations.release_worker_lock`, which frees only that worker's turn and applies nothing. No lease timer, no expiry.

Removed in the same change: the master Bag, the worker-side `store_get`/`store_set`/`store_del`, the read that took no lock, `CapturingGlobalStore`, the change batch on the release and `apply_global_store_changes`. Operations on the store are by key, never by path.
