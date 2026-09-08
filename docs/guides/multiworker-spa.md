# Multiworker SPA integration

> **Status:** Draft; implementation checked against the development source on 2026-09-08.

The `genro-asgi` distribution contains two top-level Python packages:

| Package | Responsibility |
|---|---|
| `genro_asgi` | Server, routed apps, HTTP, WSX, middleware and core services |
| `genro_asgi_multiworker_spa` | SPA front, commander, worker processes, registers and hosted-app adapters |

There is no separate `[spa]` extra. Importing the core does not load SPA
orchestration. Since 0.44 the old `genro_asgi.spa` and
`genro_asgi.applications.spa_app` paths have no compatibility re-exports. Update
configuration strings (`entry_module`, `worker_class`, `python -m`) as well as
Python imports.

```python
from genro_asgi_multiworker_spa.spa_app import SpaApplication
from genro_asgi_multiworker_spa.orchestration.spa_worker import SpaWorker
from genro_asgi_multiworker_spa.environ import AsgiSeam, WsgiSeam
```

## Composing the front and pool

Mount a `SpaApplication` in the server and declare its `orchestration` subtree,
with a `commander` and worker groups. See the
[configuration recipe](configuration.md#the-pool-subtree-orchestration-its-commander-and-its-groups).
This requires a real hosted application and worker class; an empty base worker
can serve control orders but cannot serve an HTTP application.

The front owns HTTP translation and the connection cookie. The hosted site
supplies the connection id; the front writes it as `spa_connection_id`. The
commander owns placement and global indexes. All pages of one user share a
worker and that user's store. A user moving through freeze/unfreeze meets the
same barrier whether arriving by HTTP or WSX. Worker failure can require the
affected users to restart their application state.

Use one orchestrated application per server. The inspector detects a second
attach when enabled, but there is no unconditional general boot validation of
that restriction. Configure the group policies and read the pool's status;
there is no fixed worker-count setting in this configuration.

## Hosting ASGI or WSGI

A consumer's `SpaWorker` subclass assigns its hosted application to `asgi_app`.
For a WSGI-only site it may assign `wsgi_app` instead: `hosted_app_seam` wraps it
with `AsgiSeam(WsgiSeam(wsgi_app, worker))`. Assigning both is a boot error.
For a mixed site the consumer's ASGI router delegates legacy paths through a
`WsgiSeam`; the core has no special legacy path prefixes.

`WsgiSeam` runs the synchronous callable through the worker's traffic pool. The
worker's request context follows the thread. The hosted scope/environ carries
`genro.identity` and, for a page message, `genro.page_id` and `genro.reply_path`.
The hosted ASGI scope has an empty `root_path` and a mount-relative path. A
consumer doing additional WSGI routing must set `root_path`/`path` consistently
for `SCRIPT_NAME` and `PATH_INFO`.

The front packs a **complete request body** and the adapters collect the
**complete response body** before replying. This worker path provides neither
streaming uploads nor incremental HTTP downloads/SSE. An endless hosted response
never completes its call. Serve streaming routes directly on the core when that
behavior is required; see [Streaming](streaming.md).

Worker lifecycle events belong to the request that produced them and travel on
that request's reply. Events created outside a served request use their own
announcement call. The bridge's database events, datachanges, subscriptions and
GenroPy-specific delivery code live in `genropy-asgi`; they are not services of
this package.

## Global store

`worker.global_store` is a client of one commander-owned `dict[str, Any]`. Keys
are literal strings (`"a.b"` is one key); values must survive the TYTX transport.
There are no replicas or process-shared mutable objects.

The simple `get`, `set` and `delete` methods are synchronous: use them on a worker
pool thread, not its event-loop thread. `get(key, default)` returns the default
only for an absent key; a stored `None` stays `None`. A read-modify-write lease
works with `with` on a pool thread or `async with` on the worker loop:

```python
# Inside a synchronous handler running on a worker pool thread:
with worker.global_store.for_update("visits") as turn:
    turn.value = (turn.value if turn.exists else 0) + 1
```

```python
# Inside asynchronous worker code:
async with worker.global_store.for_update("settings") as turn:
    if not turn.exists:
        turn.value = {}
    turn.value["theme"] = "dark"
```

These are integration fragments requiring a live connected worker. The lease
yields itself with a private `value` and `exists`. Exit publishes the complete
value by replacement; omitting the key leases and replaces the entire dictionary.
One FIFO lock protects **all** operations, even reads of unrelated keys. Keep
turns short; never perform a nested turn or call `get`/`set`/`delete` from the
context already holding one (it raises instead of waiting on itself).

An exception in the block or `turn.abort()` prevents publication. `abort()` keeps
the lock until the block exits. Decode/encode failures also release without
applying. If the commit reply is lost, `GlobalStoreCommitUnconfirmed` means the
value **may already be published**: the client does not retry or pretend the
commit was aborted. The store does not promise persistence across commander
restarts; arrange durable storage separately when your application needs it.
