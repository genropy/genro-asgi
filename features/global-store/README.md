# Global store

**Version**: 0.1 · **Last Updated**: 2026-08-22 · **Status**: 🔴 DA REVISIONARE

One master Bag living ONLY on the commander — no replicas. A worker
reads with a call on the lane (`store_get`), and writes through the lock:
the grant carries the true master state, the release applies exactly what
the holder drained. All-or-nothing without rollback machinery. Never files
or shared memory between processes.

Interactions: orchestration (the lane, the lock) · datachanges (its writes travel as changes).

## The lock: grant and release

```mermaid
sequenceDiagram
    participant W as SpaWorker (holder)
    participant C as SpaCommander
    W->>C: op_store_lock(request_id) — a CALL on the lane
    C->>C: global_lock.acquire (FIFO by construction)
    C-->>W: the grant — request_id + the master (to_tytx of global_register)
    W->>W: mutate the working copy (CapturingGlobalStore captures)
    W->>C: op_store_unlock(request_id, drained changes)
    C->>C: apply_changes on global_register · release · next waiter
```

A plain read never takes the lock: `store_get` is a CALL answering the
master's current value. A holder that dies (channel EOF) releases with the
master untouched — the interrupted body wrote nothing anywhere.
