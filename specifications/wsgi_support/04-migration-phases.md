# Migration Phases

**Status**: Design Proposal
**Source**: migrate_docs/EN/asgi/arc/architecture.md

---

## Overview

Migration from WSGI to ASGI occurs in eight phases, each independently deployable with rollback capability.

| Phase | Description | gnrdaemon | Pages | Notes |
|-------|-------------|-----------|-------|-------|
| **0** | ASGI wrapper for WSGI | Unchanged | Ephemeral | Single entry point |
| **1** | Sticky sessions + PageRegistry | Reduced | Ephemeral | Multi-process (FUTURE) |
| **2** | NATS as alternative channel | Fallback | Ephemeral | Flag-based IPC (FUTURE) |
| **3** | Mono-process + PageRegistry for WS | Unchanged | Ephemeral + Live (WS) | Delay sticky adoption |
| **4** | All registries in-process | Eliminated | Ephemeral (fast load) | No daemon IPC |
| **5** | Resident pages | None | Resident | No reconstruction |
| **6** | Stabilization and testing | None | Resident | Bug fixing |
| **7** | Multi-process + sticky + scaling | None | Resident | Production ready |

**Note**: Phases 1-2 are deferred. The migration path is: 0 → 3 → 4 → 5 → 6 → 7

---

## Phase 0: ASGI Wrapper

**Goal**: AsgiServer as single entry point, wrapping the existing WSGI app. Infrastructure ready for WebSocket and Executors when needed.

### Architecture

```
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (NEW entry)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
        ┌───────────┐  ┌───────────┐  ┌───────────┐
        │ WSGI App  │  │ WebSocket │  │ Executors │
        │ (wrapped) │  │ (ready)   │  │ (ready)   │
        └─────┬─────┘  └───────────┘  └───────────┘
              │
              ▼
        ┌─────────────────┐
        │   gnrdaemon     │
        │  (unchanged)    │
        └─────────────────┘
```

### Changes

- **AsgiServer** becomes the single entry point (replaces Nginx routing to Gunicorn)
- **WSGI app** is wrapped and served by AsgiServer
- **WebSocket** infrastructure available if/when needed
- **Executors** infrastructure available if/when needed
- **gnrdaemon** unchanged - still handles all state

### What's Available (not necessarily used)

- WebSocket connections via AsgiServer
- ProcessPoolExecutor for CPU-bound tasks
- Modern async infrastructure

### gnrdaemon Role

- **Unchanged** - maintains global registry of pages and connections
- Handles broadcasts and shared events
- All state management as before

### Rollback

Revert to Nginx + Gunicorn direct setup (gnrdaemon unchanged).

---

## Phase 1: Local Orchestration (DEFERRED)

> **Note**: This phase is deferred. We proceed directly from Phase 0 to Phase 3 to delay sticky session complexity.

**Goal**: Introduce sticky sessions and process-local page registry.

### Architecture

```
                     ┌─────────────────┐
                     │   Nginx :8080   │
                     │ (sticky routing)│
                     └────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Process P1   │     │  Process P2   │     │  Process P3   │
│  users: 1-20  │     │  users: 21-40 │     │  users: 41-60 │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │PageRegistry│ │     │ │PageRegistry│ │     │ │PageRegistry│ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│  HTTP + WS    │     │  HTTP + WS    │     │  HTTP + WS    │
└───────┬───────┘     └───────┬───────┘     └───────┬───────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   gnrdaemon     │
                    │ (coordinator)   │
                    │ (reduced role)  │
                    └─────────────────┘
```

### Changes

- **Sticky routing** by user_id (nginx or internal router)
- **Page ID with process indicator** (`page_xxx|p01`)
- **Local PageRegistry** per process
- **Unified HTTP + WS** per process (AsgiServer)
- **gnrdaemon** becomes lightweight coordinator

### gnrdaemon Role (Reduced)

- Cross-process broadcasts only
- Fallback for legacy page IDs without process indicator
- User → process mapping (or move to DB)

### New Components

```python
# Process-local registry
class PageRegistry:
    def __init__(self):
        self._pages: dict[str, Page] = {}

    def get(self, page_id: str) -> Page | None:
        return self._pages.get(page_id)

    def register(self, page: Page) -> None:
        self._pages[page.page_id] = page
```

### Rollback

Disable sticky routing, re-enable gnrdaemon as primary registry.

---

## Phase 2: NATS as Alternative Channel (DEFERRED)

> **Note**: This phase is deferred. NATS integration will be considered later if needed.

**Goal**: Introduce NATS as an alternative IPC channel to Pyro. Both coexist, selected via flag.

### Architecture

```
                     ┌─────────────────┐
                     │   Nginx :8080   │
                     │ (sticky routing)│
                     └────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Process P1   │     │  Process P2   │     │  Process P3   │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │PageRegistry│ │     │ │PageRegistry│ │     │ │PageRegistry│ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│  HTTP + WS    │     │  HTTP + WS    │     │  HTTP + WS    │
└───────┬───────┘     └───────┬───────┘     └───────┬───────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
    ┌─────────────────┐             ┌─────────────────┐
    │   gnrdaemon     │             │      NATS       │
    │    (Pyro)       │             │   (pub/sub)     │
    │   [fallback]    │             │   [new option]  │
    └─────────────────┘             └─────────────────┘
              │                               │
              └───────────┬───────────────────┘
                          │
                   USE_NATS flag
                   selects channel
```

### Changes

- **NATS** introduced as alternative IPC channel
- **gnrdaemon** stays available as fallback
- **Flag-based selection**: `USE_NATS=1` or `USE_PYRO=1` (default: Pyro)
- **Gradual migration**: Test NATS with subset of users/processes

### Configuration

```python
# Environment variable selects IPC channel
import os

IPC_BACKEND = os.environ.get('IPC_BACKEND', 'pyro')  # 'pyro' or 'nats'

if IPC_BACKEND == 'nats':
    from .ipc_nats import publish_dbevent, subscribe_dbevent
else:
    from .ipc_pyro import publish_dbevent, subscribe_dbevent
```

### NATS for IPC

When NATS is selected:

```python
import nats

nc = await nats.connect("nats://localhost:4222")

# dbevent broadcast
await nc.publish("dbevent", json_payload)

# Each process subscribes and filters locally
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

### Rollback

Set `IPC_BACKEND=pyro` to revert to gnrdaemon.

---

## Phase 3: Mono-Process with PageRegistry for WebSocket

> **Note**: This is the first step after Phase 0. Using mono-process delays sticky session complexity.

**Goal**: Single process, multi-threaded. PageRegistry keeps pages alive for WebSocket push only. Ephemeral page lifecycle unchanged - pages still reconstructed from gnrdaemon.

### Architecture

```
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (mono-proc)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
        ┌───────────┐                  ┌───────────┐
        │ HTTP req  │                  │ WebSocket │
        │           │                  │           │
        │ Page      │                  │ Page      │
        │ REBUILD   │                  │ from      │
        │ (as now)  │                  │ REGISTRY  │
        └─────┬─────┘                  └─────┬─────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │  PageRegistry   │
                     │  (keeps pages   │
                     │   alive for WS) │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   gnrdaemon     │
                     │  (unchanged)    │
                     └─────────────────┘
```

### Key Concept

**Pages are still reconstructed for HTTP requests** (same as current behavior), but **also kept alive in PageRegistry** for WebSocket push.

```python
class PageRegistry:
    """Registry of live pages for WebSocket push only."""

    def __init__(self):
        self._pages: dict[str, Page] = {}

    def register(self, page: Page) -> None:
        """Keep page alive for WS push."""
        self._pages[page.page_id] = page

    def get_for_ws(self, page_id: str) -> Page | None:
        """Get live page for WebSocket operations."""
        return self._pages.get(page_id)

    def unregister(self, page_id: str) -> None:
        """Remove page when client disconnects."""
        self._pages.pop(page_id, None)
```

### Request Flow

**HTTP Request** (unchanged):

```
Client → AsgiServer → Page RECONSTRUCTED from gnrdaemon → Execute → Response → Page discarded
```

**WebSocket Push** (new):

```
dbevent → gnrdaemon → Process → PageRegistry.get_for_ws(page_id) → Live Page → WS Push
```

### What Changes

- **Single process** - No sticky routing needed
- **Multi-threaded** - Handles concurrent requests
- **PageRegistry** - Keeps pages alive for WS only
- **gnrdaemon** - Unchanged, still handles state and dbevent
- **Page ID** - No format change (no `|pXX` suffix)

### Benefits

- **Simpler deployment** - Single process, no routing complexity
- **Test PageRegistry** - Validate concept before multi-process
- **WebSocket enabled** - Push notifications to live pages
- **Backward compatible** - HTTP flow unchanged

### Rollback

Remove PageRegistry, disable WebSocket features.

---

## Phase 4: All Registries In-Process

**Goal**: Move ALL registries from gnrdaemon into the process. Ephemeral pages still reconstructed, but data is already in-process (no Pyro IPC).

### Architecture

```text
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (mono-proc)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
        ┌───────────┐                  ┌───────────┐
        │ HTTP req  │                  │ WebSocket │
        │           │                  │           │
        │ Page      │                  │ Page      │
        │ REBUILD   │                  │ from      │
        │ (fast!)   │                  │ REGISTRY  │
        └─────┬─────┘                  └─────┬─────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │  IN-PROCESS     │
                     │  ┌───────────┐  │
                     │  │PageRegistry│  │
                     │  │UserRegistry│  │
                     │  │ConnRegistry│  │
                     │  │GlobalReg   │  │
                     │  └───────────┘  │
                     └─────────────────┘
                              │
                              ✗ (no gnrdaemon)
```

### Key Concept

**gnrdaemon eliminated**. All registries (global, users, connections, pages) are now in-process.

Pages are still ephemeral (reconstructed per request), but reconstruction is **fast** because data is already in memory (no Pyro IPC overhead).

```python
class ProcessRegistries:
    """All registries previously in gnrdaemon, now in-process."""

    def __init__(self):
        self.global_registry: dict[str, Any] = {}
        self.users: dict[str, dict] = {}        # user_id → user data
        self.connections: dict[str, dict] = {}  # conn_id → connection data
        self.pages: dict[str, Page] = {}        # page_id → live page (for WS)

    def get_page_data(self, page_id: str) -> dict | None:
        """Get page state for reconstruction (fast, in-memory)."""
        return self._page_states.get(page_id)

    def save_page_data(self, page_id: str, state: dict) -> None:
        """Save page state after request."""
        self._page_states[page_id] = state
```

### Request Flow

**HTTP Request** (ephemeral page, fast reconstruction):

```text
Client → AsgiServer → ProcessRegistries.get_page_data() → Page REBUILT (in-memory, fast) → Execute → Save state → Response
```

**WebSocket Push** (unchanged from Phase 3):

```text
dbevent → ProcessRegistries → PageRegistry.get_for_ws(page_id) → Live Page → WS Push
```

### What Changes

- **gnrdaemon eliminated** - No more Pyro IPC
- **All registries in-process** - global, users, connections, pages
- **Fast reconstruction** - No network overhead
- **Pages still ephemeral** - Same lifecycle, just faster

### Benefits

- **No IPC latency** - All data in-process
- **Simpler architecture** - No external daemon
- **Same page lifecycle** - Minimal code changes

### Rollback

Re-enable gnrdaemon, configure registries to use Pyro.

---

## Phase 5: Resident Pages

**Goal**: Eliminate page reconstruction. Pages stay alive between requests.

### Architecture

```text
                     ┌─────────────────┐
                     │     Client      │
                     └────────┬────────┘
                              │
                              ▼
                     ┌─────────────────┐
                     │   AsgiServer    │
                     │   (mono-proc)   │
                     │   :8080         │
                     └────────┬────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
        ┌───────────┐                  ┌───────────┐
        │ HTTP req  │                  │ WebSocket │
        │           │                  │           │
        │ Page      │                  │ Page      │
        │ from      │    ◄── SAME ──►  │ from      │
        │ REGISTRY  │                  │ REGISTRY  │
        └─────┬─────┘                  └─────┬─────┘
              │                               │
              └───────────────┬───────────────┘
                              │
                     ┌────────▼────────┐
                     │  PageRegistry   │
                     │  (RESIDENT)     │
                     │                 │
                     │  Pages live     │
                     │  between reqs   │
                     └─────────────────┘
```

### Key Concept

**No more page reconstruction**. HTTP requests and WebSocket use the **same live page** from the registry.

```python
class PageRegistry:
    """Registry of RESIDENT pages."""

    def get_or_create(self, page_id: str, user_id: str) -> Page:
        """Get existing page or create new one."""
        if page_id not in self._pages:
            self._pages[page_id] = Page(page_id, user_id)
        return self._pages[page_id]
```

### Request Flow

**HTTP Request** (resident page):

```text
Client → AsgiServer → PageRegistry.get_or_create(page_id) → SAME Page → Execute → Response
```

**WebSocket Push** (same page):

```text
dbevent → PageRegistry.get(page_id) → SAME Page → WS Push
```

### What Changes

- **Pages are resident** - Live between requests
- **No reconstruction** - Same page object reused
- **Unified access** - HTTP and WS use same page

### Benefits

- **Zero reconstruction overhead** - Pages always ready
- **Consistent state** - Same page for HTTP and WS
- **Simpler code** - No save/restore logic

### Rollback

Re-enable ephemeral page lifecycle (Phase 4).

---

## Phase 6: Stabilization and Testing

**Goal**: Comprehensive testing and bug fixing of the new architecture.

### Focus Areas

1. **Memory management** - Page lifecycle, garbage collection
2. **Concurrency** - Thread safety, race conditions
3. **State consistency** - Page state across HTTP/WS
4. **Error handling** - Graceful degradation
5. **Performance** - Benchmarks, profiling

### Testing Strategy

```python
# Memory tests
def test_page_cleanup_on_disconnect():
    """Pages should be cleaned up when client disconnects."""
    pass

def test_no_memory_leaks():
    """Memory should not grow unbounded."""
    pass

# Concurrency tests
def test_concurrent_requests_same_page():
    """Multiple concurrent requests to same page."""
    pass

def test_ws_push_during_http_request():
    """WS push while HTTP request in progress."""
    pass

# State tests
def test_state_consistency_http_ws():
    """HTTP changes visible in WS and vice versa."""
    pass
```

### What Changes

- **No new features** - Focus on stability
- **Bug fixes** - Address issues found in testing
- **Documentation** - Update for new architecture

### Success Criteria

- [ ] All existing tests pass
- [ ] New architecture tests pass
- [ ] Memory stable under load
- [ ] No race conditions detected
- [ ] Performance meets or exceeds baseline

### Rollback

Revert to Phase 5 if critical issues found.

---

## Phase 7: Multi-Process with Sticky Sessions

**Goal**: Scale to multiple processes with sticky routing for production.

### Architecture

```text
                     ┌─────────────────┐
                     │   Load Balancer │
                     │ (sticky by user)│
                     └────────┬────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Process P1   │     │  Process P2   │     │  Process P3   │
│  users: 1-N   │     │  users: N-M   │     │  users: M-Z   │
│ ┌───────────┐ │     │ ┌───────────┐ │     │ ┌───────────┐ │
│ │PageRegistry│ │     │ │PageRegistry│ │     │ │PageRegistry│ │
│ │(resident)  │ │     │ │(resident)  │ │     │ │(resident)  │ │
│ └───────────┘ │     │ └───────────┘ │     │ └───────────┘ │
│  HTTP + WS    │     │  HTTP + WS    │     │  HTTP + WS    │
└───────────────┘     └───────────────┘     └───────────────┘
```

### Key Concept

**Sticky routing by user_id**. Each user always routes to the same process. Pages are resident within each process.

```python
def route_to_process(user_id: str, num_processes: int) -> int:
    """Deterministic routing: same user always goes to same process."""
    return hash(user_id) % num_processes
```

### Page ID with Process Indicator

```text
page_abc123def456|p02
                 └─┬─┘
           process indicator
```

### What Changes

- **Multi-process** - Scale horizontally
- **Sticky routing** - User → Process affinity
- **Page ID format** - Includes process indicator
- **Cross-process IPC** - For notifications (NATS or similar)

### Benefits

- **Horizontal scaling** - Add processes as needed
- **Process isolation** - Fault containment
- **Load distribution** - Users spread across processes

### Rollback

Revert to mono-process (Phase 6).

---

## Development Mode

For local development, simulate multi-process behavior:

```bash
# Single process (default)
gnr asgi serve --reload

# Simulated multi-process
gnr asgi serve --reload --local-balancer --max-processes 3
```

### Local Balancer Mode

- Starts multiple local processes
- Each with own event loop and PageRegistry
- Tests routing, balancing, cross-process communication
- Same code runs in production multi-machine setup

---

## Migration Timeline

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

```text
Now ─────────────────────────────────────────────────────────────────────────────────► Future

Phase 0          Phase 3              Phase 4              Phase 5         Phase 6         Phase 7
[ASGI Wrap]      [Mono+WS]            [No daemon]          [Resident]      [Testing]       [Scale]
    │                 │                    │                    │               │               │
    │   - AsgiServer  │   - PageRegistry   │   - All registries │   - Pages     │   - Bug fix   │   - Multi-proc
    │     entry point │     for WS only    │     in-process     │     resident  │   - Testing   │   - Sticky
    │   - WSGI wrap   │   - Ephemeral      │   - No Pyro IPC    │   - No rebuild│   - Stability │   - Scaling
    │   - gnrdaemon   │     pages +        │   - Fast rebuild   │   - HTTP=WS   │               │   - page_id|p
    │     unchanged   │     gnrdaemon      │                    │     same page │               │
```

### Success Criteria per Phase

**Phase 0**:

- [ ] AsgiServer serves as single entry point
- [ ] WSGI app wrapped and functional
- [ ] WebSocket infrastructure available
- [ ] Executors infrastructure available
- [ ] gnrdaemon unchanged, all tests pass

**Phase 1** (DEFERRED):

- [ ] Sticky routing works correctly
- [ ] PageRegistry maintains state across requests
- [ ] Page ID with process indicator (`page_xxx|p01`) works
- [ ] gnrdaemon only handles cross-process broadcasts

**Phase 2** (DEFERRED):

- [ ] NATS connection and pub/sub working
- [ ] IPC_BACKEND flag switches between Pyro and NATS
- [ ] dbevent broadcast via NATS working
- [ ] gnrdaemon available as fallback
- [ ] Gradual migration path validated

**Phase 3**:

- [ ] Mono-process multi-threaded app working
- [ ] PageRegistry keeps pages alive for WS
- [ ] HTTP requests still reconstruct pages (unchanged)
- [ ] WebSocket push to live pages working
- [ ] gnrdaemon unchanged, no page_id format change

**Phase 4**:

- [ ] All registries moved in-process
- [ ] gnrdaemon eliminated
- [ ] Pages still ephemeral but fast reconstruction
- [ ] No Pyro IPC overhead

**Phase 5**:

- [ ] Pages are resident (no reconstruction)
- [ ] HTTP and WS use same page object
- [ ] Page lifecycle managed by registry

**Phase 6**:

- [ ] All existing tests pass
- [ ] New architecture tests pass
- [ ] Memory stable under load
- [ ] No race conditions detected
- [ ] Performance meets or exceeds baseline

**Phase 7**:

- [ ] Multi-process deployment working
- [ ] Sticky routing by user_id
- [ ] Page ID with process indicator
- [ ] Cross-process IPC (NATS) for notifications
- [ ] Horizontal scaling validated
