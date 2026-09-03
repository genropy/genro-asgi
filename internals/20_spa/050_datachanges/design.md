# Datachanges distribution

**Version**: 0.1 · **Last Updated**: 2026-09-03 · **Status**: 🔴 DA REVISIONARE

**The need.** What one page changes, the other pages that care must see — without every page polling the world.

How a change produced on one page reaches the pages that must see it:
a page's queue empties on the worker, delivery is ADDRESSED through the
`DeliveryDesk` — never broadcast, never per-worker snapshots.

**Where a page's own changes are queued.** The page register row carries
`datachanges` and `datachanges_idx`. `RegisterRegistry.subscribe_page_store`
attaches to the row's store a subscriber under the id
`page_store:<register_item_id>`: every update, insert, delete and transaction
mutation whose path falls under a prefix in `page["subscribed_paths"]` is
appended to `datachanges` with `key.reason == "serverChange"`, autocreated
parents skipped, prefixes matched segment-aware. `SpaWorker.collect_page`
empties the queue and resets the index. The queue is a row field, so it travels
in the parcel through a freeze and a transfer. Every access to a row and to its
Bag takes the row's exclusive re-entrant `item_lock`. The user store keeps its
`user_view` — another round.

**Where an addressed change goes.** `set_datachange`, `reset_datachanges` and
`drop_datachanges` name a target. A target page of the CALLER'S OWN user living
on this worker is served on the spot: `RegisterRegistry.append_page_datachange`
appends the change to that row under its `item_lock` and stamps the next
`datachanges_idx`, so the addressed write and the `serverChange` subscriber share
one list and one index. The same user is the condition because his freeze waits
for the caller's own pending call. Any other address — a page of another user
even on this worker, `filters`, the STATE kinds — leaves at once from the request
thread as one CALL to `/desk/on_datachange`, filed the moment the verb runs; the
desk judges existence and a target nobody holds comes back as a `KeyError` at the
verb. What the desk hands back at a page's exchange is appended to that row
through the same `append_page_datachange`, then retired by `collect_page`.

Interactions: dbevents (same desk) · global-store · orchestration (the lane carries them).

## The delivery

```mermaid
flowchart LR
    P["producing page (its SpaWorker empties the row queues)"] -->|up the lane| C[SpaCommander]
    C --> D["DeliveryDesk
    subscriptions · pending mailboxes · age-bounded events"]
    D -->|ADDRESSED, never broadcast| T["the subscribed pages' workers"]
    T -->|interim: ping/collect pull| B[browser]
```

The last hop is the provisional one: the final design pushes over websocket.
