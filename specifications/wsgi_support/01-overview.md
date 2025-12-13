# Legacy WSGI Integration

**Status**: Draft - Design Discussion
**Last Updated**: 2025-11-28

---

## Context

Migrating from a legacy architecture based on:

- **Gunicorn**: WSGI workers serving SPA pages
- **Tornado**: WebSocket handling
- **gnrdaemon**: Pyro-based in-memory state server (registries)
- **Nginx**: Routing between Tornado and Gunicorn

Current flow:
```
Client SPA
    │
    ├── page_id (22 char unique)
    ├── connection_id (22 char unique)
    └── local JS state

    │ HTTP request
    ▼

Gunicorn Worker (ephemeral)
    │
    ├── receives page_id, connection_id, user_id
    ├── reconstructs Page context from gnrdaemon (Pyro)
    │       │
    │       ▼
    │   gnrdaemon (persistent Pyro server)
    │   ├── global registry
    │   ├── users registry {user_id: data}
    │   ├── connections registry {conn_id: data}
    │   └── pages registry {page_id: data}
    │
    ├── executes business logic
    ├── writes state back to gnrdaemon
    └── responds and dies
```

**Problem with current architecture:**

- gnrdaemon is a bottleneck (single Pyro server, one request at a time)
- Page reconstruction on every request adds latency
- IPC overhead (Pyro) for every state access

---

## Goal: Eliminate gnrdaemon

Keep Page objects alive in-process, eliminating:

- Pyro IPC latency
- Page reconstruction overhead
- Single-point-of-failure daemon

---

## Proposed Architecture: Sticky Sessions by User

Route users to specific processes. Each process maintains its own page registry.

```
                    Load Balancer / Router
                    (sticky by user_id)
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   Process P1         Process P2         Process P3
   users: 1-20        users: 21-40       users: 41-60
   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
   │ PageRegistry│    │ PageRegistry│    │ PageRegistry│
   │ {id1: Page} │    │ {id5: Page} │    │ {id9: Page} │
   │ {id2: Page} │    │ {id6: Page} │    │ {id10: Page}│
   │ {id3: Page} │    │ {id7: Page} │    │   ...       │
   └─────────────┘    └─────────────┘    └─────────────┘
```

### Routing Strategy

```python
def get_process_for_user(user_id: str, num_processes: int) -> int:
    """Deterministic routing: same user always goes to same process."""
    return hash(user_id) % num_processes
```

Or with explicit mapping for more control:

```python
# Lookup table (could be in shared config or external store)
user_process_map: dict[str, int] = {
    'user_001': 0,
    'user_002': 0,
    'user_003': 1,
    # ...
}
```

---

## Open Questions

### 1. WebSocket Routing

**Ideal**: HTTP and WS for same user → same process

```
User 1 ──HTTP──→ P1 ──→ Page object
User 1 ──WS────→ P1 ──→ same Page object (direct access!)
```

**Question**: Can we guarantee WS sticky routing same as HTTP?

Options:
- Single process handles both HTTP and WS (AsgiServer with mounted apps)
- Separate WS process with forwarding to correct HTTP process

### 2. Cross-Process Communication

When User 2 (on P2) needs to notify User 1 (on P1):

```
User 2 ──HTTP──→ P2 ──→ notify(user_1, message)
                           │
                           ▼ NATS publish
                          P1 ──→ User 1's Page ──→ WS ──→ Client
```

**Decision**: NATS for all cross-process communication.

Each process subscribes to relevant topics and filters locally. See "NATS for IPC" section below.

### 3. Failover

If P1 dies, pages for users 1-20 are lost.

**Options**:

- **Accept it**: Pages get reconstructed on next request (lazy recovery)
- **Replicate state**: Periodic snapshot to disk or peer process
- **Stateless fallback**: If page not found, reconstruct from DB

**Likely choice**: Accept lazy recovery (same as current behavior if gnrdaemon restarts)

### 4. Dynamic Scaling

Adding/removing processes requires re-routing users.

**Options**:

- **Consistent hashing**: Minimize re-routing when processes change
- **Fixed pool**: Don't scale dynamically, size for peak load
- **Graceful migration**: Drain connections before removing process

---

## Integration with AsgiServer

### Option A: Single Process (HTTP + WS)

```python
server = AsgiServer()
server.mount("/api", LegacyWsgiApp())  # Wrapped WSGI
server.mount("/ws", WebSocketApp())    # Native ASGI WS

# Both share same PageRegistry in-process
```

**Pros**: No IPC needed for same-user operations
**Cons**: Single process limits concurrency

### Option B: Multi-Process with Routing

```python
# Main process (router)
router = AsgiServer()
router.mount("/", StickyRouter(
    workers=[P1, P2, P3],
    route_by='user_id'
))

# Each worker process
worker = AsgiServer()
worker.mount("/api", BusinessApp())
worker.mount("/ws", WebSocketApp())
worker.page_registry = PageRegistry()  # Local to this process
```

**Pros**: Better concurrency, process isolation
**Cons**: Needs IPC for cross-user operations

---

## NATS for IPC

NATS replaces gnrdaemon for all cross-process communication:

```python
import nats

# Connect to NATS
nc = await nats.connect("nats://localhost:4222")

# Publish dbevent (broadcast to all processes)
await nc.publish("dbevent", json.dumps(payload).encode())

# Subscribe to dbevent
async def on_dbevent(msg):
    data = json.loads(msg.data)
    for page in local_registry.get_subscribed(data["table"]):
        page.store.add_changes(data)

await nc.subscribe("dbevent", cb=on_dbevent)
```

Topics:
- `dbevent` - Database change notifications (broadcast)
- `user.{id}.notify` - User-specific notifications
- `system.broadcast` - System-wide messages

**Why NATS**:
- Single binary (~10MB), easy to deploy
- Sub-millisecond latency
- Pub/Sub + Request/Reply patterns
- Multi-host ready (cluster native)
- CNCF project, actively maintained

---

## PageRegistry

Local registry for each process:

```python
class PageRegistry:
    """In-process registry of live Page objects."""

    def __init__(self):
        self._pages: dict[str, Page] = {}
        self._user_pages: dict[str, set[str]] = {}  # user_id → set of page_ids

    def register(self, page: Page) -> None:
        """Register a new page."""
        self._pages[page.page_id] = page
        self._user_pages.setdefault(page.user_id, set()).add(page.page_id)

    def unregister(self, page_id: str) -> None:
        """Remove a page from registry."""
        page = self._pages.pop(page_id, None)
        if page:
            self._user_pages.get(page.user_id, set()).discard(page_id)

    def get(self, page_id: str) -> Page | None:
        """Get page by ID."""
        return self._pages.get(page_id)

    def get_user_pages(self, user_id: str) -> list[Page]:
        """Get all pages for a user."""
        page_ids = self._user_pages.get(user_id, set())
        return [self._pages[pid] for pid in page_ids if pid in self._pages]

    def __len__(self) -> int:
        return len(self._pages)
```

---

## Migration Path

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

### Phase 0: ASGI Wrapper

- AsgiServer as single entry point
- WSGI app wrapped and served by AsgiServer
- WebSocket and Executors available if needed
- gnrdaemon unchanged

### Phase 1: Sticky Sessions + PageRegistry (DEFERRED)

- Sticky routing by user_id
- Page ID with process indicator (`page_xxx|p01`)
- Local PageRegistry per process
- gnrdaemon reduced to coordinator for cross-process

### Phase 2: NATS as Alternative Channel (DEFERRED)

- NATS introduced as alternative IPC channel
- gnrdaemon stays available as fallback
- Flag-based selection: `IPC_BACKEND=pyro` or `IPC_BACKEND=nats`
- Gradual migration: test NATS with subset of processes

### Phase 3: Mono-Process + PageRegistry for WS

- Single process, multi-threaded (delays sticky session complexity)
- PageRegistry keeps pages alive for WebSocket push only
- HTTP requests still reconstruct pages (unchanged behavior)
- gnrdaemon unchanged, no page_id format change

### Phase 4: All Registries In-Process

- All registries (global, users, connections, pages) moved in-process
- gnrdaemon eliminated
- Pages still ephemeral but fast reconstruction (no Pyro IPC)

### Phase 5: Resident Pages

- Pages stay alive between requests (no reconstruction)
- HTTP and WS use same page object
- Page lifecycle managed by registry

### Phase 6: Stabilization and Testing

- Comprehensive testing and bug fixing
- Memory management, concurrency, state consistency
- No new features, focus on stability

### Phase 7: Multi-Process + Sticky Sessions

- Scale to multiple processes
- Sticky routing by user_id
- Page ID with process indicator (`page_xxx|p01`)
- Cross-process IPC (NATS) for notifications

---

## Notes

- This document captures design discussion, not final decisions
- Each stage should be independently deployable
- Rollback path must exist at each stage
