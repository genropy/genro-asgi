# Missing Documentation - 03_application_system

Paragraphs present in source documents but not in specifications.

## Source: initial_specifications/wsgi_support/05-deployment-strategy.md

**Status**: Design Proposal
**Source**: migrate_docs/EN/asgi/arc/architecture.md

To manage system versions in a controlled manner and allow safe transitions between releases, the orchestrator supports a **Green/Blue/Canary deployment strategy**.

```
                    ┌─────────────────────┐
                    │    Orchestrator     │
                    │  (routes by flag)   │
                    └──────────┬──────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│    GREEN      │      │     BLUE      │      │    CANARY     │
│  (stable)     │      │  (candidate)  │      │ (experimental)│
│   v1.2.3      │      │   v1.3.0-rc   │      │   v1.4.0-dev  │
│               │      │               │      │               │
│  users: 90%   │      │  users: 8%    │      │  users: 2%    │
└───────────────┘      └───────────────┘      └───────────────┘
```

| Color | Purpose | Stability | User Base |
|-------|---------|-----------|-----------|
| **Green** | Stable production | High | Majority (default) |
| **Blue** | Candidate for next release | Medium | Selected testers |
| **Canary** | Experimental features | Low | Developers/beta testers |

Each user has a `flag` field in their record:

```python
# User table field
flag: Literal['gr', 'bl', 'can'] = 'gr'  # Default: green
```

```python
def assign_user_to_color(user_record: dict) -> str:
    """Map user flag to process color."""
    flag = user_record.get('flag', 'gr')
    return {
        'gr': 'green',
        'bl': 'blue',
        'can': 'canary'
    }.get(flag, 'green')

def select_process_for_user(user_id: str, color: str) -> str:
    """Select a process of the specified color."""
    available = [p for p in process_registry if p['color'] == color]
    if not available:
        # Fallback to green if no processes of requested color
        available = [p for p in process_registry if p['color'] == 'green']
    # Load balance among available processes
    return min(available, key=lambda p: len(p['users']))
```

Each process declares its color at registration:

```python
process_registry = {
    'p01': {'color': 'green', 'version': '1.2.3', 'users': ['user_a', 'user_b']},
    'p02': {'color': 'green', 'version': '1.2.3', 'users': ['user_c']},
    'p03': {'color': 'blue', 'version': '1.3.0-rc', 'users': ['user_d']},
    'p04': {'color': 'canary', 'version': '1.4.0-dev', 'users': ['user_e']},
}
```

```
Day 1: Deploy v1.3.0-rc to Blue processes
       - 8% of users (flag='bl') test new version
       - Monitor errors, performance

Day 3: If stable, promote Blue to Green
       - Update Green processes to v1.3.0
       - Blue becomes next candidate slot

```
Emergency: Deploy hotfix to all Green processes
           - Blue/Canary unaffected
           - Immediate rollout to 90% of users
```

```
Problem detected in Blue:
  - Stop routing new users to Blue
  - Existing Blue users moved to Green
  - Blue processes revert or shut down
```

```python
# Process declares its color at startup
process = AsgiProcess(
    color='green',      # or 'blue', 'canary'
    version='1.2.3',
    max_users=50
)
process.register_with_orchestrator()
```

```python
# orchestrator_config.py
DEPLOYMENT_CONFIG = {
    'colors': {
        'green': {'min_processes': 2, 'max_processes': 10},
        'blue': {'min_processes': 1, 'max_processes': 3},
        'canary': {'min_processes': 1, 'max_processes': 1},
    },
    'default_color': 'green',
    'fallback_color': 'green',  # If requested color unavailable
}
```

```python
# Track metrics by color
metrics = {
    'green': {
        'requests': 10000,
        'errors': 5,
        'avg_latency_ms': 45,
    },
    'blue': {
        'requests': 800,
        'errors': 2,
        'avg_latency_ms': 52,
    },
    'canary': {
        'requests': 200,
        'errors': 10,  # ⚠️ Higher error rate!
        'avg_latency_ms': 120,
    },
}
```

- **Blue error rate > Green**: Pause Blue rollout
- **Canary error rate spike**: Auto-disable Canary
- **Green capacity low**: Scale up Green processes

```python
# Move user to Blue for testing
update_user(user_id='user_123', flag='bl')

# Move user back to stable
update_user(user_id='user_123', flag='gr')

# Bulk update for beta program
update_users(
    where={'role': 'beta_tester'},
    set={'flag': 'bl'}
)
```

```python
# User opts into beta
if user.can_join_beta:
    user.flag = 'bl'
    user.save()
```

| Aspect | Benefit |
|--------|---------|
| **Safe releases** | Test with subset before full rollout |
| **Instant rollback** | Route users back to Green immediately |
| **A/B testing** | Compare performance between versions |
| **Gradual rollout** | Increase Blue percentage over time |
| **Developer access** | Canary for internal testing |
| **Isolation** | Bug in Blue doesn't affect Green |

The Green/Blue/Canary strategy can be used during the WSGI→ASGI migration.

**Actual path**: 0 → 3 → 4 → 5 → 6 → 7 (Phases 1-2 deferred)

| Phase | Green | Blue | Canary |
|-------|-------|------|--------|
| **0** | ASGI wraps WSGI | - | - |
| **3** | Mono-process + WS | - | New features |
| **4** | No daemon (in-process) | - | Testing |
| **5** | Resident pages | - | New features |
| **6** | Stabilization | Testing | Bug fixes |
| **7** | Multi-process stable | Next version | Experimental |

- **Phase 0**: Single entry point, WSGI wrapped, gnrdaemon unchanged
- **Phase 3**: Mono-process, PageRegistry for WS, ephemeral pages, gnrdaemon unchanged
- **Phase 4**: All registries in-process, gnrdaemon eliminated, fast reconstruction
- **Phase 5**: Resident pages, no reconstruction, HTTP=WS same page
- **Phase 6**: Testing and stabilization, bug fixing
- **Phase 7**: Multi-process, sticky routing, NATS for IPC, horizontal scaling

- **Phase 1**: Sticky sessions (deferred to Phase 7)
- **Phase 2**: NATS alternative (deferred, integrated in Phase 7)

This allows gradual migration with mono-process first, then scaling to multi-process once stable.

## Source: initial_specifications/interview/answers/D-routing.md

**Date**: 2025-12-13
**Status**: Verified
**Verified in**: `dispatcher.py`, genro-routes documentation

genro-asgi uses **genro-routes** for routing. Full documentation in:
`specifications/dependencies/genro-routes.md`

```text
Request path: /shop/products/list
       ↓
Selector: "shop/products/list"  (path.strip("/"))
       ↓
router.get(selector)
       ↓
Handler (RoutingClass method)
```

1. **Path → Selector**: `selector = path.strip("/") or "index"`
2. **Selector → Handler**: `handler = router.get(selector)`
3. **If handler is a Router** (not a method):
   - Look for `index` in sub-router
   - If no index → **show `members()` as HTML** (navigation)
4. **Handler invocation**:
   - If first parameter is `request`/`req` → `handler(request, **query_params)`
   - Otherwise → `handler(**query_params)`

```python
server.router.attach_instance(shop_app, name="shop")
# Now: /shop/products → router.get("shop/products") → shop_app.products()
```

- **`router.members()`**: router structure (entries, child routers)
- **`router.openapi()`**: OpenAPI schema generated from type hints
- **Lazy mode**: `members(lazy=True)` returns callable instead of expanding

Plugin = middleware at individual method level, runtime configurable.

**Use in genro-asgi** (potential):

- Authentication on specific methods
- Delegation to executors
- Python debug on specific methods
- Permissions and filters

**Available hooks**: `on_decore`, `wrap_handler`, `allow_entry`, `entry_metadata`, `configure`

**Runtime configuration**: `routedclass.configure("router:plugin/selector", ...)`

## Source: initial_specifications/interview/answers/L-external-apps.md

**A:** Yes. External ASGI apps (Starlette, FastAPI, Litestar, etc.) can be mounted on AsgiServer. They can optionally gain access to server resources via the `AsgiServerEnabler` mixin.

Any ASGI callable can be mounted:

```yaml
# config.yaml
apps:
  api:
    module: "myapp:app"  # FastAPI/Starlette instance
```

The app works as-is, but has no access to server resources.

To access server resources (config, logger, executors), use `AsgiServerEnabler`:

```python
from fastapi import FastAPI
from genro_asgi import AsgiServerEnabler

class MyFastAPI(FastAPI, AsgiServerEnabler):
    """FastAPI app with access to AsgiServer resources."""
    pass

@app.get("/info")
def info():
    if app.binder:
        app.binder.logger.info("Request received")
        return {"debug": app.binder.config.debug}
    return {"debug": False}
```

1. **`AsgiServerEnabler`** is a mixin class (no `__call__`)
2. Put it **LAST** in inheritance (so framework's `__call__` is used)
3. When mounted on AsgiServer, server sets `app.binder = ServerBinder(self)`
4. **`ServerBinder`** provides controlled access to:
   - `binder.config` - server configuration
   - `binder.logger` - server logger
   - `binder.executor(name)` - named executor pools

Apps using `AsgiServerEnabler` still work standalone:

```python
# When mounted on AsgiServer
app.binder  # → ServerBinder instance

# When running standalone (uvicorn myapp:app)
app.binder  # → None
```

Always check `if app.binder:` before using server resources.

```python
# genro_asgi/utils/binder.py

class ServerBinder:
    """Controlled interface to server resources."""

def __init__(self, server):
        self._server = server

@property
    def config(self):
        return self._server.config

@property
    def logger(self):
        return self._server.logger

def executor(self, name="default", **kwargs):
        return self._server.executor(name, **kwargs)

class AsgiServerEnabler:
    """Mixin for external apps that need server access."""
    binder: ServerBinder | None = None
```

| Scenario | Solution |
|----------|----------|
| External app, no server features needed | Just mount it |
| External app needs config/logger | Use `AsgiServerEnabler` mixin |
| New app for genro-asgi | Inherit from `AsgiApplication` |

- `AsgiServerEnabler` is **optional** - only for apps needing server resources
- Mixin pattern preserves framework's behavior
- `binder` is `None` when running standalone
- `AsgiApplication` (for native apps) inherits from `RoutingClass`, not `AsgiServerEnabler`

## Source: initial_specifications/interview/answers/A-identity.md

**Date**: 2025-12-13
**Status**: Verified

genro-asgi is an **ASGI server as an instance with state**, not a function.

Unlike other frameworks (FastAPI, Starlette) that use global functions/apps:

```python
# Other frameworks - global state
app = FastAPI()
app.state.db = ...  # pollutes shared space

# genro-asgi - isolated instances
server = AsgiServer()      # instance with its own state
server.apps["shop"] = ...  # each app is an isolated instance
```

- `del server` → everything garbage collected, zero residue
- Clean testing: each test creates fresh instances
- Multi-tenant: same process, different servers
- Hot reload without residue

Every object created by the parent maintains a reference to the parent with a semantic name:

```python
# Server creates Dispatcher
self.dispatcher = Dispatcher(self)

# Dispatcher has ref to server
class Dispatcher:
    def __init__(self, server):
        self.server = server  # semantic name, NOT "_parent"
```

This pattern applies to the entire chain: Server → Dispatcher, Server → Router, Server → Lifespan, etc.

**Never pollute Python's shared space**:

- NO mutable global variables at module level
- NO `global` keyword
- NO singleton via module
- State always inside instances

**Rule added to**: `~/.claude/CLAUDE.md` (Rule 5) and project `CLAUDE.md`.

## Source: initial_implementation_plan/archive/08c-tasks.md

**Status**: DA REVISIONARE
**Dependencies**: 08b-executor.py

The TaskManager provides a dedicated system for **long-running background jobs** that:
- Run independently of ASGI request/response cycles
- Can be queried for status and results
- Support optional progress reporting
- Are isolated from the main worker processes

This is another key differentiator from Starlette.

```python
# Submit a task
task_id = app.tasks.submit(job_func, *args, **kwargs)

# Query status
status = await app.tasks.status(task_id)
# Returns: "pending" | "running" | "completed" | "failed"

# Get result (waits if not complete)
result = await app.tasks.result(task_id)

# Cancel a task
cancelled = await app.tasks.cancel(task_id)

# List all tasks
all_tasks = app.tasks.list_tasks()
```

**File**: `src/genro_asgi/tasks.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""TaskManager for long-running background jobs."""

from __future__ import annotations

import asyncio
import uuid
from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, TypeVar

class TaskStatus(str, Enum):
    """Status of a background task."""

PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class TaskInfo:
    """Information about a background task."""

task_id: str
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    progress: float | None = None  # 0.0 to 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

class TaskManager:
    """Manager for long-running background tasks.

Provides a dedicated process pool for batch jobs and long-running
    operations that should not block ASGI workers.

Example:
        tasks = TaskManager(max_workers=4)
        await tasks.startup()

# Submit a long-running job
        task_id = tasks.submit(process_large_dataset, dataset_path)

# Check status
        status = await tasks.status(task_id)

# Get result when ready
        result = await tasks.result(task_id)

def __init__(self, max_workers: int = 4) -> None:
        """Initialize the TaskManager.

Args:
            max_workers: Maximum concurrent background tasks.
        """
        self._max_workers = max_workers
        self._pool: ProcessPoolExecutor | None = None
        self._tasks: dict[str, TaskInfo] = {}
        self._futures: dict[str, Future] = {}
        self._started = False

@property
    def is_running(self) -> bool:
        """Check if task manager is running."""
        return self._started

async def startup(self) -> None:
        """Start the task manager.

Called automatically during application lifespan startup.
        """
        if self._started:
            return

self._pool = ProcessPoolExecutor(
            max_workers=self._max_workers,
        )
        self._started = True

async def shutdown(self, wait: bool = True, cancel_pending: bool = False) -> None:
        """Shutdown the task manager.

Args:
            wait: If True, wait for running tasks to complete.
            cancel_pending: If True, cancel pending tasks before shutdown.

Called automatically during application lifespan shutdown.
        """
        if not self._started:
            return

if cancel_pending:
            for task_id, future in self._futures.items():
                if not future.done():
                    future.cancel()
                    self._tasks[task_id].status = TaskStatus.CANCELLED

if self._pool:
            self._pool.shutdown(wait=wait)
            self._pool = None

def submit(
        self,
        func: Callable[..., T],
        *args: Any,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        """Submit a long-running task for background execution.

Note: func must be picklable (top-level function).

Args:
            func: Picklable callable to execute.
            *args: Positional arguments for func.
            task_id: Optional custom task ID. Generated if not provided.
            metadata: Optional metadata to attach to the task.
            **kwargs: Keyword arguments for func.

Returns:
            The task ID for tracking.

Raises:
            RuntimeError: If task manager is not started.

Example:
            def export_report(user_id, format):
                # Long-running export...
                return report_path

task_id = tasks.submit(export_report, 123, format="pdf")
        """
        if not self._started or self._pool is None:
            raise RuntimeError("TaskManager not started. Call startup() first.")

if task_id is None:
            task_id = str(uuid.uuid4())

# Create task info
        info = TaskInfo(
            task_id=task_id,
            status=TaskStatus.PENDING,
            created_at=datetime.now(),
            metadata=metadata or {},
        )
        self._tasks[task_id] = info

# Submit to pool
        if kwargs:
            from functools import partial
            func = partial(func, **kwargs)

future = self._pool.submit(func, *args)
        self._futures[task_id] = future

# Update status when task starts/completes
        future.add_done_callback(
            lambda f: self._on_task_done(task_id, f)
        )

# Mark as running (approximately - it's in the queue)
        info.status = TaskStatus.RUNNING
        info.started_at = datetime.now()

def _on_task_done(self, task_id: str, future: Future) -> None:
        """Callback when a task completes."""
        info = self._tasks.get(task_id)
        if info is None:
            return

info.completed_at = datetime.now()

if future.cancelled():
            info.status = TaskStatus.CANCELLED
        elif future.exception() is not None:
            info.status = TaskStatus.FAILED
            info.error = str(future.exception())
        else:
            info.status = TaskStatus.COMPLETED

async def status(self, task_id: str) -> TaskStatus:
        """Get the status of a task.

Args:
            task_id: The task ID to check.

Returns:
            The current task status.

Raises:
            KeyError: If task_id is not found.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")

return self._tasks[task_id].status

async def info(self, task_id: str) -> TaskInfo:
        """Get full information about a task.

Args:
            task_id: The task ID to query.

Returns:
            TaskInfo with full task details.

Raises:
            KeyError: If task_id is not found.
        """
        if task_id not in self._tasks:
            raise KeyError(f"Task not found: {task_id}")

async def result(self, task_id: str, timeout: float | None = None) -> Any:
        """Get the result of a completed task.

Waits for the task to complete if still running.

Args:
            task_id: The task ID to get result for.
            timeout: Maximum seconds to wait. None for no timeout.

Returns:
            The result of the task function.

Raises:
            KeyError: If task_id is not found.
            asyncio.TimeoutError: If timeout exceeded.
            Exception: If the task raised an exception.
        """
        if task_id not in self._futures:
            raise KeyError(f"Task not found: {task_id}")

future = self._futures[task_id]
        loop = asyncio.get_running_loop()

# Wait for completion in thread pool to not block
        return await asyncio.wait_for(
            loop.run_in_executor(None, future.result),
            timeout=timeout,
        )

async def cancel(self, task_id: str) -> bool:
        """Cancel a pending or running task.

Args:
            task_id: The task ID to cancel.

Returns:
            True if successfully cancelled, False otherwise.

Raises:
            KeyError: If task_id is not found.
        """
        if task_id not in self._futures:
            raise KeyError(f"Task not found: {task_id}")

future = self._futures[task_id]
        cancelled = future.cancel()

if cancelled:
            self._tasks[task_id].status = TaskStatus.CANCELLED
            self._tasks[task_id].completed_at = datetime.now()

def list_tasks(
        self,
        status: TaskStatus | None = None,
    ) -> list[TaskInfo]:
        """List all tasks, optionally filtered by status.

Args:
            status: Optional status to filter by.

Returns:
            List of TaskInfo objects.
        """
        tasks = list(self._tasks.values())

if status is not None:
            tasks = [t for t in tasks if t.status == status]

def clear_completed(self) -> int:
        """Remove completed, failed, and cancelled tasks from tracking.

Returns:
            Number of tasks cleared.
        """
        to_remove = [
            task_id
            for task_id, info in self._tasks.items()
            if info.status in (
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
            )
        ]

for task_id in to_remove:
            del self._tasks[task_id]
            del self._futures[task_id]

**File**: `tests/test_tasks.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for the TaskManager module."""

import asyncio
import time
import pytest

from genro_asgi.tasks import TaskManager, TaskStatus, TaskInfo

class TestTaskManager:
    """Tests for TaskManager class."""

@pytest.fixture
    async def tasks(self):
        """Provide a started task manager."""
        tm = TaskManager(max_workers=2)
        await tm.startup()
        yield tm
        await tm.shutdown(wait=True)

async def test_startup_shutdown(self):
        """Test task manager lifecycle."""
        tm = TaskManager()
        assert not tm.is_running

await tm.startup()
        assert tm.is_running

await tm.shutdown()
        assert not tm.is_running

async def test_submit_and_result(self, tasks):
        """Test submitting a task and getting result."""
        task_id = tasks.submit(simple_task, 5)

assert task_id is not None
        result = await tasks.result(task_id)
        assert result == 10

async def test_submit_with_custom_id(self, tasks):
        """Test submitting with custom task ID."""
        task_id = tasks.submit(simple_task, 3, task_id="my-task-123")

assert task_id == "my-task-123"
        result = await tasks.result(task_id)
        assert result == 6

async def test_submit_with_metadata(self, tasks):
        """Test submitting with metadata."""
        task_id = tasks.submit(
            simple_task, 1,
            metadata={"user_id": 42, "type": "export"}
        )

info = await tasks.info(task_id)
        assert info.metadata["user_id"] == 42
        assert info.metadata["type"] == "export"

async def test_status_tracking(self, tasks):
        """Test status changes during task lifecycle."""
        task_id = tasks.submit(slow_task, 0.2)

# Should be running
        status = await tasks.status(task_id)
        assert status == TaskStatus.RUNNING

# Wait for completion
        await tasks.result(task_id)

status = await tasks.status(task_id)
        assert status == TaskStatus.COMPLETED

async def test_info(self, tasks):
        """Test getting task info."""
        task_id = tasks.submit(simple_task, 1)
        await tasks.result(task_id)

info = await tasks.info(task_id)

assert isinstance(info, TaskInfo)
        assert info.task_id == task_id
        assert info.status == TaskStatus.COMPLETED
        assert info.created_at is not None
        assert info.completed_at is not None
        assert info.error is None

async def test_failed_task(self, tasks):
        """Test handling of failed tasks."""
        task_id = tasks.submit(failing_task)

with pytest.raises(ValueError, match="Task failed"):
            await tasks.result(task_id)

info = await tasks.info(task_id)
        assert info.status == TaskStatus.FAILED
        assert "Task failed" in info.error

async def test_result_timeout(self, tasks):
        """Test result timeout."""
        task_id = tasks.submit(slow_task, 1.0)

with pytest.raises(asyncio.TimeoutError):
            await tasks.result(task_id, timeout=0.1)

async def test_task_not_found(self, tasks):
        """Test error on unknown task ID."""
        with pytest.raises(KeyError, match="not found"):
            await tasks.status("nonexistent-task")

with pytest.raises(KeyError, match="not found"):
            await tasks.result("nonexistent-task")

async def test_list_tasks(self, tasks):
        """Test listing all tasks."""
        tasks.submit(simple_task, 1, task_id="task-1")
        tasks.submit(simple_task, 2, task_id="task-2")
        tasks.submit(simple_task, 3, task_id="task-3")

all_tasks = tasks.list_tasks()
        assert len(all_tasks) == 3

task_ids = {t.task_id for t in all_tasks}
        assert task_ids == {"task-1", "task-2", "task-3"}

async def test_list_tasks_filtered(self, tasks):
        """Test listing tasks filtered by status."""
        tasks.submit(simple_task, 1, task_id="quick-1")
        tasks.submit(slow_task, 0.5, task_id="slow-1")

# Wait for quick task
        await tasks.result("quick-1")

completed = tasks.list_tasks(status=TaskStatus.COMPLETED)
        assert len(completed) == 1
        assert completed[0].task_id == "quick-1"

async def test_clear_completed(self, tasks):
        """Test clearing completed tasks."""
        tasks.submit(simple_task, 1, task_id="task-1")
        tasks.submit(simple_task, 2, task_id="task-2")

await tasks.result("task-1")
        await tasks.result("task-2")

cleared = tasks.clear_completed()
        assert cleared == 2

assert len(tasks.list_tasks()) == 0

async def test_cancel_task(self, tasks):
        """Test cancelling a task."""
        # Submit a slow task
        task_id = tasks.submit(slow_task, 5.0)

# Try to cancel immediately
        # Note: cancellation may or may not succeed depending on timing
        cancelled = await tasks.cancel(task_id)

# Either cancelled or already running
        status = await tasks.status(task_id)
        assert status in (TaskStatus.CANCELLED, TaskStatus.RUNNING, TaskStatus.COMPLETED)

async def test_not_started_error(self):
        """Test error when task manager not started."""
        tm = TaskManager()

with pytest.raises(RuntimeError, match="not started"):
            tm.submit(simple_task, 1)

# Top-level functions for ProcessPoolExecutor (must be picklable)
def simple_task(n: int) -> int:
    """Simple task that doubles input."""
    return n * 2

def slow_task(duration: float) -> str:
    """Task that takes time to complete."""
    time.sleep(duration)
    return "done"

def failing_task() -> None:
    """Task that always fails."""
    raise ValueError("Task failed intentionally")
```

After implementing this block, `applications.py` will include:

```python
from .tasks import TaskManager

class Application:
    def __init__(self, ...):
        ...
        self.executor = Executor()
        self.tasks = TaskManager()

async def _handle_lifespan(self, scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await self.executor.startup()
                await self.tasks.startup()
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.tasks.shutdown(wait=True)
                await self.executor.shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return
```

```python
from genro_asgi import Application

# In a request handler
async def start_export(request):
    user_id = request.query_params.get("user_id")

# Submit long-running export job
    task_id = app.tasks.submit(
        generate_report,
        user_id,
        metadata={"type": "export", "user": user_id}
    )

return JSONResponse({"task_id": task_id})

async def check_export(request):
    task_id = request.query_params.get("task_id")

info = await app.tasks.info(task_id)

return JSONResponse({
        "task_id": info.task_id,
        "status": info.status.value,
        "created_at": info.created_at.isoformat(),
    })
```

- [ ] Create `src/genro_asgi/tasks.py`
- [ ] Create `tests/test_tasks.py`
- [ ] Run `pytest tests/test_tasks.py`
- [ ] Run `mypy src/genro_asgi/tasks.py`
- [ ] Run `ruff check src/genro_asgi/tasks.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

```
feat(tasks): add TaskManager for long-running jobs

- Add TaskManager class with ProcessPoolExecutor
- Implement submit(), status(), result(), cancel()
- Add TaskInfo dataclass for task metadata
- Support task listing and filtering by status
- Add clear_completed() for cleanup
- Add comprehensive tests

This provides background job support that Starlette lacks.
```

## Source: plan_2025_12_29/1-applications.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `src/genro_asgi/application.py` (115 linee)
**Test**: `tests/test_basic.py`
**Data**: 2025-12-29

Il documento originale proponeva:
- `AsgiApplication` come base class per app montate
- Costruttore con `server` passato come primo argomento
- Router automatico `self.main`
- Property `server`, `request`, `response`
- Hooks `on_init()`, `on_startup()`, `on_shutdown()`
- Metodo `load_resource()` delegato al server
- Class variable `openapi_info`

**Stato nel documento**: Marcato come "fatto" ma con discrepanze.

```python
class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer.

Provides default `main` router and `index()` method. Subclasses define
    `openapi_info` for metadata and add routes with @route() decorator.
    """

openapi_info: ClassVar[dict[str, Any]] = {}

def __init__(self, **kwargs: Any) -> None:
        """Initialize app with default main router."""
        self.base_dir = kwargs.pop("base_dir", None)
        self.main = Router(self, name="main")
        self.on_init(**kwargs)

def on_init(self, **kwargs: Any) -> None:
        """Called after base initialization. Override for custom setup.

Args:
            **kwargs: Parameters from config.yaml app definition.
        """
        pass

@property
    def server(self) -> AsgiServer | None:
        """Return the server that mounted this app (semantic alias for _routing_parent)."""
        return getattr(self, "_routing_parent", None)

def on_startup(self) -> None:
        """Called when server starts. Override for custom initialization.

Can be sync or async. Called after all apps are mounted.
        """
        pass

def on_shutdown(self) -> None:
        """Called when server stops. Override for custom cleanup.

Can be sync or async. Called in reverse order of startup.
        """
        pass

def load_resource(self, *args: str, name: str) -> Any:
        """Load resource via server's ResourceLoader, prepending this app's mount name."""
        if not self.server:
            return None
        mount_name = getattr(self, "_mount_name", "")
        return self.server.load_resource(mount_name, *args, name=name)

@route(meta_mime_type="text/html")
    def index(self) -> str:
        """Return HTML splash page. Override for custom index."""
        info = getattr(self, "openapi_info", {})
        title = info.get("title", self.__class__.__name__)
        version = info.get("version", "")
        description = info.get("description", "")
        # ... genera HTML
```

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `openapi_info` | `ClassVar[dict]` | Metadati OpenAPI (title, version, description) |

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `base_dir` | `Path \| None` | Directory base dell'app (da config) |
| `main` | `Router` | Router principale creato automaticamente |
| `_mount_name` | `str` | Nome mount settato dal server |
| `_routing_parent` | `AsgiServer` | Riferimento al server (da genro-routes) |

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `server` | `AsgiServer \| None` | Alias semantico per `_routing_parent` |

| Hook | Quando | Uso Tipico |
|------|--------|------------|
| `on_init(**kwargs)` | Dopo `__init__` base | Setup da parametri config.yaml |
| `on_startup()` | Server startup (async ok) | Connessioni DB, cache |
| `on_shutdown()` | Server shutdown (async ok) | Cleanup risorse |

| Metodo | Signature | Descrizione |
|--------|-----------|-------------|
| `load_resource` | `(*args, name: str) -> Any` | Carica risorsa via ResourceLoader |
| `index` | `() -> str` | Endpoint default, ritorna HTML splash |

```python
class MyApp(AsgiApplication):
    openapi_info = {"title": "My API", "version": "1.0.0"}

@route()  # Usa self.main automaticamente (unico router)
    def hello(self):
        return {"message": "Hello!"}
```

```python
class ShopApp(AsgiApplication):
    openapi_info = {
        "title": "Shop API",
        "version": "1.0.0",
        "description": "E-commerce API"
    }

def on_init(self, connection_string: str = "sqlite:shop.db", **kwargs):
        """Riceve parametri da config.yaml apps.shop"""
        self.connection_string = connection_string
        self.db_engine = create_engine(connection_string)

def on_startup(self):
        """Connetti al database."""
        self.db = self.db_engine.connect()

def on_shutdown(self):
        """Disconnetti dal database."""
        self.db.close()

@route()
    def products(self):
        return {"products": self.db.execute("SELECT * FROM products")}
```

```python
class AdminApp(AsgiApplication):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.backoffice = Router(self, name="backoffice")

@route()  # ERRORE: ambiguo, quale router?
    def index(self):
        pass

@route("main")  # Esplicito: usa self.main
    def public_index(self):
        return {"status": "public"}

@route("backoffice")  # Esplicito: usa self.backoffice
    def admin_index(self):
        return {"status": "admin only"}
```

```python
# Mount apps
for name, (cls, kwargs) in self.config.get_app_specs().items():
    base_dir = kwargs.get("base_dir")
    if base_dir and str(base_dir) not in sys.path:
        sys.path.insert(0, str(base_dir))

instance = cls(**kwargs)           # NON passa self
    instance._mount_name = name        # Setta nome mount
    self.apps[name] = instance
    self.router.attach_instance(instance, name=name)  # genro-routes setta _routing_parent
```

1. Server legge `apps:` da config.yaml
2. Per ogni app: istanzia con `cls(**kwargs)`
3. Setta `_mount_name` per identificazione
4. Chiama `attach_instance` che:
   - Registra le route
   - Setta `_routing_parent = server`

```yaml
apps:
  shop:
    module: "main:ShopApp"
    connection_string: "postgresql://localhost/shop"
    cache_ttl: 3600

_swagger:
    module: "applications.swagger:SwaggerApp"
```

- I kwargs vengono passati a `on_init()`
- Il prefisso `_` indica app di sistema (convenzione)

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Costruttore | `__init__(self, server, **kwargs)` | `__init__(self, **kwargs)` |
| Accesso al server | Passato nel costruttore | Via property `server` che legge `_routing_parent` |
| Binding parent | Nel costruttore | Via `attach_instance()` di genro-routes |
| Property `request` | Proposta | NON implementata (usa `server.request`) |
| Property `response` | Proposta | NON implementata (usa `server.response`) |

Il piano originale prevedeva il server passato nel costruttore:

```python
# PIANO (non implementato)
class AsgiApplication:
    def __init__(self, server, **kwargs):
        self.server = server
```

L'implementazione usa genro-routes che gestisce automaticamente la relazione parent-child:

```python
# IMPLEMENTAZIONE
class AsgiApplication(RoutingClass):
    def __init__(self, **kwargs):
        # server NON passato

@property
    def server(self):
        return getattr(self, "_routing_parent", None)  # settato da attach_instance
```

**Vantaggi**:
- Disaccoppiamento: app non richiede server nel costruttore
- Testabilità: istanziare app senza server per unit test
- Consistenza: stesso meccanismo di genro-routes per tutti i parent-child

- Test creazione app minimale
- Test routing con @route()
- Test hooks on_init/startup/shutdown
- Test load_resource

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/8-storage.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `src/genro_asgi/storage.py` (396 linee)
**Test**: `tests/test_storage.py` (50+ test)
**Data**: 2025-12-29

Il documento originale proponeva:
- `LocalStorage` come implementazione filesystem-only di genro-storage API
- Mount predefiniti via metodi `mount_*`
- Mount configurati via `add_mount()`
- `LocalStorageNode` per operazioni su file/directory
- API compatibile con futuro genro-storage

```python
"""LocalStorage - Filesystem-only storage with genro-storage compatible API.

This module provides a minimal storage implementation that uses the same API
as genro-storage, but only supports local filesystem. When genro-storage
becomes available, simply change the import:

# Before (local only)
    from genro_asgi.storage import LocalStorage

# After (full genro-storage)
    from genro_storage import StorageManager as LocalStorage
"""
```

Interface che definisce l'API per qualsiasi backend storage:

```python
@runtime_checkable
class StorageNode(Protocol):
    """Abstract interface for storage nodes."""

@property
    def fullpath(self) -> str:
        """Return "mount:path" complete."""
        ...

@property
    def path(self) -> str:
        """Return path without mount."""
        ...

@property
    def exists(self) -> bool: ...

@property
    def isfile(self) -> bool: ...

@property
    def isdir(self) -> bool: ...

@property
    def basename(self) -> str: ...

@property
    def mimetype(self) -> str: ...

def read_bytes(self) -> bytes: ...

def read_text(self, encoding: str = "utf-8") -> str: ...

def child(self, *parts: str) -> StorageNode: ...

def children(self) -> list[StorageNode]: ...
```

Implementazione filesystem del protocol:

```python
class LocalStorageNode:
    """Storage node for local filesystem."""

__slots__ = ("_storage", "_mount", "_path")

def __init__(self, storage: LocalStorage, mount: str, path: str) -> None:
        self._storage = storage
        self._mount = mount
        self._path = path

@property
    def fullpath(self) -> str:
        """Return "mount:path" complete."""
        return f"{self._mount}:{self._path}" if self._path else self._mount

@property
    def path(self) -> str:
        """Return path without mount."""
        return self._path

@property
    def _absolute_path(self) -> Path:
        """Absolute filesystem path (internal)."""
        base = self._storage._resolve_mount(self._mount)
        return base / self._path if self._path else base

@property
    def exists(self) -> bool:
        return self._absolute_path.exists()

@property
    def isfile(self) -> bool:
        return self._absolute_path.is_file()

@property
    def isdir(self) -> bool:
        return self._absolute_path.is_dir()

@property
    def size(self) -> int:
        """Size in bytes. 0 if doesn't exist."""
        path = self._absolute_path
        return path.stat().st_size if path.exists() and path.is_file() else 0

@property
    def basename(self) -> str:
        return Path(self._path).name if self._path else ""

@property
    def suffix(self) -> str:
        return Path(self._path).suffix if self._path else ""

@property
    def ext(self) -> str:
        """Extension without dot."""
        suffix = self.suffix
        return suffix[1:] if suffix else ""

@property
    def mimetype(self) -> str:
        mime, _ = mimetypes.guess_type(self._path)
        return mime or "application/octet-stream"

@property
    def parent(self) -> LocalStorageNode:
        """Return parent directory node."""
        parent_path = str(Path(self._path).parent)
        if parent_path == ".":
            parent_path = ""
        return LocalStorageNode(self._storage, self._mount, parent_path)

def read_bytes(self) -> bytes:
        return self._absolute_path.read_bytes()

def read_text(self, encoding: str = "utf-8") -> str:
        return self._absolute_path.read_text(encoding=encoding)

def read(self, mode: str = "r", encoding: str = "utf-8") -> str | bytes:
        """mode='r' for text, mode='rb' for binary."""
        if "b" in mode:
            return self.read_bytes()
        return self.read_text(encoding=encoding)

def write_bytes(self, data: bytes) -> bool:
        path = self._absolute_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True

def write_text(self, text: str, encoding: str = "utf-8") -> bool:
        path = self._absolute_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return True

def child(self, *parts: str) -> LocalStorageNode:
        """Return a child node."""
        child_path = "/".join([self._path, *parts]) if self._path else "/".join(parts)
        return LocalStorageNode(self._storage, self._mount, child_path)

def children(self) -> list[LocalStorageNode]:
        """List children if it's a directory."""
        path = self._absolute_path
        if not path.is_dir():
            return []
        result = []
        mount_base = self._storage._resolve_mount(self._mount)
        for child in path.iterdir():
            child_rel = str(child.relative_to(mount_base))
            result.append(LocalStorageNode(self._storage, self._mount, child_rel))
        return result
```

Manager per accesso storage con sistema mount:

```python
class LocalStorage:
    """Storage manager filesystem-only.

Mount resolution order (see _resolve_mount):
    1. Method mount_{prefix}() → dynamic, overridable via subclass
    2. Dict _mounts → configured from config.yaml
    3. ValueError if not found
    """

__slots__ = ("_mounts", "_base_dir")

def __init__(self, base_dir: str | Path | None = None) -> None:
        self._mounts: dict[str, Path] = {}
        self._base_dir = Path(base_dir).resolve() if base_dir else Path.cwd()
```

```python
def mount_site(self) -> Path:
    """Volume predefinito: directory base del server."""
    return self._base_dir
```

```python
def _resolve_mount(self, prefix: str) -> Path:
    """Resolve a mount prefix to an absolute Path.

Resolution order:
    1. Method mount_{prefix}() if exists → call it (dynamic)
    2. _mounts dict → configured mounts from add_mount/configure
    3. ValueError if not found
    """
    # 1. Check for predefined method
    method = getattr(self, f"mount_{prefix}", None)
    if method is not None and callable(method):
        result = method()
        return Path(result) if not isinstance(result, Path) else result

# 2. Check configured mounts
    if prefix in self._mounts:
        return self._mounts[prefix]

raise ValueError(f"Mount '{prefix}' not found")
```

```python
def configure(self, source: list[dict[str, Any]]) -> None:
    """Configure mount points from list of dicts."""
    for config in source:
        self.add_mount(config)

def add_mount(self, config: dict[str, Any]) -> None:
    """Add a single mount point.
    Args: config = {'name': str, 'type': 'local', 'path': str}
    """
    name = config["name"]
    mount_type = config.get("type", "local")

if mount_type != "local":
        raise ValueError(f"LocalStorage only supports type='local'")

if name in self._mounts:
        raise ValueError(f"Mount '{name}' already exists")

path = Path(config["path"])
    if not path.is_absolute():
        path = self._base_dir / path

self._mounts[name] = path.resolve()

def delete_mount(self, name: str) -> None:
    """Remove a mount point."""
    self._mounts.pop(name, None)

def get_mount_names(self) -> list[str]:
    """List configured mount names."""
    return list(self._mounts.keys())

def has_mount(self, name: str) -> bool:
    """True if mount exists (predefined method or configured)."""
    method = getattr(self, f"mount_{name}", None)
    if method is not None and callable(method):
        return True
    return name in self._mounts

def node(self, mount_or_path: str, *path_parts: str) -> LocalStorageNode:
    """Create a storage node.

Examples:
        storage.node('site:resources/logo.png')
        storage.node('site', 'resources', 'logo.png')
        storage.node('site:resources', 'images', 'logo.png')
    """
    mount, path = self._parse_mount_path(mount_or_path)

if not self.has_mount(mount):
        raise ValueError(f"Mount '{mount}' not found")

if path_parts:
        if path:
            path = "/".join([path, *path_parts])
        else:
            path = "/".join(path_parts)

return LocalStorageNode(self, mount, path)
```

```python
node = storage.node("site:resources/logo.png")
# mount = "site", path = "resources/logo.png"
```

```python
node = storage.node("site", "resources", "logo.png")
# mount = "site", path = "resources/logo.png"
```

```python
node = storage.node("site:resources", "images", "logo.png")
# mount = "site", path = "resources/images/logo.png"
```

```python
# Sempre disponibile
storage = LocalStorage(base_dir="/app")
node = storage.node("site:file.txt")  # usa mount_site()
```

```python
storage.add_mount({
    "name": "uploads",
    "type": "local",
    "path": "/var/uploads"
})
node = storage.node("uploads:image.png")
```

I metodi `mount_*` hanno **priorità** sui mount configurati:

```python
class MyStorage(LocalStorage):
    def mount_site(self):
        return Path("/custom/site")

storage = MyStorage()
storage._mounts["site"] = Path("/other")
# storage._resolve_mount("site") → /custom/site (metodo vince)
```

```python
def __init__(self, ...):
    # ...
    self.storage = LocalStorage(self.base_dir)
    self.resource_loader = ResourceLoader(self)
```

```python
def get_resources_node(self, level: Any) -> LocalStorageNode | None:
    storage = self.server.storage
    mount_name = f"_resources_{id(level)}"

if not storage.has_mount(mount_name):
        storage.add_mount({
            "name": mount_name,
            "type": "local",
            "path": str(path),
        })

return storage.node(mount_name)
```

```python
class ProjectStorage(LocalStorage):
    """Storage con mount custom per il progetto."""

def mount_cache(self) -> Path:
        return self._base_dir / ".cache"

def mount_uploads(self) -> Path:
        return Path("/var/uploads")

def mount_temp(self) -> Path:
        return Path("/tmp/myproject")

# Uso
storage = ProjectStorage(base_dir="/app")
storage.node("cache:data.json")    # /app/.cache/data.json
storage.node("uploads:image.png")  # /var/uploads/image.png
storage.node("temp:export.csv")    # /tmp/myproject/export.csv
```

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Protocol | Proposto | `StorageNode` implementato |
| Subclass mount | Proposto | Funziona via `mount_*` methods |
| write_* methods | Non menzionati | Implementati |
| parent property | Non menzionato | Implementato |

Nessuna differenza significativa - l'implementazione segue il piano con alcune aggiunte.

`tests/test_storage.py` contiene 50+ test:

### TestLocalStorageNode
- `test_fullpath` - Formato corretto
- `test_exists_true/false` - Verifica esistenza
- `test_isfile/isdir` - Tipo nodo
- `test_size` - Dimensione file
- `test_basename/suffix/ext` - Parsing nome
- `test_mimetype_*` - Guess MIME type
- `test_parent` - Navigazione parent
- `test_read_*` - Lettura contenuto
- `test_write_*` - Scrittura contenuto
- `test_child` - Navigazione child
- `test_children` - Lista directory

### TestLocalStorage
- `test_add_mount` - Aggiunta mount
- `test_add_mount_relative_path` - Path relativi
- `test_add_mount_invalid_type` - Errore tipo non local
- `test_add_mount_duplicate` - Errore duplicato
- `test_delete_mount` - Rimozione mount
- `test_configure_from_list` - Config multipla
- `test_node_*` - Creazione nodi

### TestMountResolution
- `test_resolve_mount_predefined_site` - Metodo predefinito
- `test_resolve_mount_config` - Mount configurato
- `test_resolve_mount_method_priority` - Priorità metodo su config
- `test_subclass_custom_mount` - Mount in subclass

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/15-asgiapplication-refactor.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `src/genro_asgi/application.py` (115 linee)
**Data**: 2025-12-29

Il documento originale proponeva:
- Router di default `self.main` creato automaticamente
- `main_router = "main"` class var per `@route()` senza argomenti
- `index()` di default che genera splash page da `openapi_info`
- Obbligo di chiamare `super().__init__()` se si sovrascrive `__init__`

```python
"""AsgiApplication - Base class for ASGI applications."""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, ClassVar
from genro_routes import Router, RoutingClass, route

if TYPE_CHECKING:
    from .server import AsgiServer

class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer.

Provides default `main` router and `index()` method. Subclasses define
    `openapi_info` for metadata and add routes with @route() decorator.

class MyApp(AsgiApplication):
            openapi_info = {"title": "My API", "version": "1.0.0"}

@route()  # Uses the only router (self.main) automatically
            def hello(self):
                return "Hello!"

def __init__(self):
                super().__init__()
                self.backoffice = Router(self, name="backoffice")

@route("backoffice")  # Must specify when multiple routers
            def admin(self):
                return "Admin panel"
    """

openapi_info: ClassVar[dict[str, Any]] = {}

def __init__(self, **kwargs: Any) -> None:
        """Initialize app with default main router."""
        self.base_dir = kwargs.pop("base_dir", None)
        self.main = Router(self, name="main")
        self.on_init(**kwargs)

def on_init(self, **kwargs: Any) -> None:
        """Called after base initialization. Override for custom setup.

Args:
            **kwargs: Parameters from config.yaml app definition.
        """
        pass

@property
    def server(self) -> AsgiServer | None:
        """Return the server that mounted this app (semantic alias for _routing_parent)."""
        return getattr(self, "_routing_parent", None)

def on_startup(self) -> None:
        """Called when server starts. Override for custom initialization.

Can be sync or async. Called after all apps are mounted.
        """
        pass

def on_shutdown(self) -> None:
        """Called when server stops. Override for custom cleanup.

Can be sync or async. Called in reverse order of startup.
        """
        pass

def load_resource(self, *args: str, name: str) -> Any:
        """Load resource via server's ResourceLoader, prepending this app's mount name."""
        if not self.server:
            return None
        mount_name = getattr(self, "_mount_name", "")
        return self.server.load_resource(mount_name, *args, name=name)

@route(meta_mime_type="text/html")
    def index(self) -> str:
        """Return HTML splash page. Override for custom index."""
        info = getattr(self, "openapi_info", {})
        title = info.get("title", self.__class__.__name__)
        version = info.get("version", "")
        description = info.get("description", "")

version_html = f"<p>Version: {version}</p>" if version else ""
        desc_html = f"<p>{description}</p>" if description else ""

return f"""<!DOCTYPE html>
<html>
<head><title>{title}</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }}
h1 {{ color: #333; }}
</style>
</head>
<body>
<h1>{title}</h1>
{version_html}
{desc_html}
</body>
</html>"""
```

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `openapi_info` | `ClassVar[dict]` | Metadati OpenAPI (title, version, description) |

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `base_dir` | `Path \| None` | Directory base dell'app (da config) |
| `main` | `Router` | Router principale creato automaticamente |
| `_mount_name` | `str` | Nome mount settato dal server |
| `_routing_parent` | `AsgiServer` | Riferimento al server (da genro-routes) |

| Nome | Tipo | Descrizione |
|------|------|-------------|
| `server` | `AsgiServer \| None` | Alias semantico per `_routing_parent` |

| Hook | Quando | Uso Tipico |
|------|--------|------------|
| `on_init(**kwargs)` | Dopo `__init__` base | Setup da parametri config.yaml |
| `on_startup()` | Server startup (async ok) | Connessioni DB, cache |
| `on_shutdown()` | Server shutdown (async ok) | Cleanup risorse |

| Metodo | Signature | Descrizione |
|--------|-----------|-------------|
| `load_resource` | `(*args, name: str) -> Any` | Carica risorsa via ResourceLoader |
| `index` | `() -> str` | Endpoint default, ritorna HTML splash |

```python
class MyApp(AsgiApplication):
    openapi_info = {"title": "My API", "version": "1.0.0"}

@route()  # Usa self.main automaticamente (unico router)
    def hello(self):
        return {"message": "Hello!"}

# index() ereditato genera splash page automatica
```

```python
class ShopApp(AsgiApplication):
    openapi_info = {
        "title": "Shop API",
        "version": "1.0.0",
        "description": "E-commerce API"
    }

def on_init(self, connection_string: str = "sqlite:shop.db", **kwargs):
        """Riceve parametri da config.yaml apps.shop"""
        self.connection_string = connection_string
        self.db_engine = create_engine(connection_string)

def on_startup(self):
        """Connetti al database."""
        self.db = self.db_engine.connect()

def on_shutdown(self):
        """Disconnetti dal database."""
        self.db.close()

@route()
    def products(self):
        return {"products": self.db.execute("SELECT * FROM products")}
```

```python
class AdminApp(AsgiApplication):
    openapi_info = {"title": "Admin API", "version": "1.0.0"}

def __init__(self, **kwargs):
        super().__init__(**kwargs)  # OBBLIGATORIO - crea self.main
        self.backoffice = Router(self, name="backoffice")

@route()  # → self.main
    def public_index(self):
        return {"status": "public"}

@route("backoffice")  # → self.backoffice
    def admin_index(self):
        return {"status": "admin only"}
```

```python
class AuthDemo(AsgiApplication):
    openapi_info = {"title": "Auth Demo", "version": "1.0.0"}

def __init__(self, **kwargs):
        super().__init__(**kwargs)  # crea self.main
        self.public = PublicArea()   # RoutingClass child
        self.staff = StaffArea()     # RoutingClass child

@route()
    def index(self):
        return "Auth Demo: /public, /staff"

class PublicArea(RoutingClass):
    """Sub-area - usa RoutingClass, non AsgiApplication."""

def __init__(self):
        self.api = Router(self, name="api")

@route("api")
    def welcome(self):
        return "Public welcome"
```

Il decoratore `@route()` di `genro_routes` quando chiamato senza argomenti:
1. Cerca l'unico router disponibile sulla classe
2. Se `self.main` è l'unico router, lo usa automaticamente
3. Se ci sono più router, solleva errore (ambiguità)

```python
@route()  # OK se c'è solo self.main
def hello(self):
    pass

@route("main")  # Esplicito, funziona sempre
def hello2(self):
    pass

@route("backoffice")  # Usa altro router
def admin(self):
    pass
```

Il metodo `index()` genera HTML dalla configurazione `openapi_info`:

```python
@route(meta_mime_type="text/html")
def index(self) -> str:
    """Return HTML splash page. Override for custom index."""
    info = getattr(self, "openapi_info", {})
    title = info.get("title", self.__class__.__name__)
    version = info.get("version", "")
    description = info.get("description", "")
    # ...
```

```html
<!DOCTYPE html>
<html>
<head><title>Shop API</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
h1 { color: #333; }
</style>
</head>
<body>
<h1>Shop API</h1>
<p>Version: 1.0.0</p>
<p>E-commerce API</p>
</body>
</html>
```

1. **DEVE chiamare `super().__init__(**kwargs)`** se sovrascrive `__init__`
2. **`@route()` senza argomenti** usa l'unico router se non ambiguo
3. **Router aggiuntivi** devono essere creati DOPO `super().__init__()`
4. **Sub-aree** usano `RoutingClass` direttamente, non `AsgiApplication`
5. **`openapi_info`** è un class var che popola la splash page
6. **`on_init()`** riceve i kwargs da config.yaml

```
Server monta app
    │
    ▼
cls(**kwargs)
    │
    ├── __init__(**kwargs)
    │       ├── self.base_dir = kwargs.pop("base_dir")
    │       ├── self.main = Router(self, name="main")
    │       └── self.on_init(**kwargs)
    │               └── Setup custom (DB connection, etc.)
    │
    ├── instance._mount_name = name
    │
    └── self.router.attach_instance(instance, name=name)
            └── Setta instance._routing_parent = server
```

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| `main_router` class var | Proposto | ❌ Non presente (genro-routes deduce) |
| `@route()` senza args | Proposto | ✅ Funziona con unico router |
| `super().__init__()` | Obbligatorio | ✅ Obbligatorio |
| `on_init()` hook | Non menzionato | ✅ Implementato |
| Splash page HTML | Proposto | ✅ Implementato |
| CSS inline | Non specificato | ✅ Presente |

Il piano proponeva `main_router = "main"` come class variable. Nell'implementazione attuale, genro-routes deduce automaticamente il router quando c'è un unico router disponibile. Questo evita la necessità di specificare `main_router`.

Tutti i test passano dopo il refactoring:

```bash
pytest tests/ -x -q
# 339 passed
```

**Ultimo aggiornamento**: 2025-12-29

