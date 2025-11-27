# Block 08c: TaskManager

**Status**: DA REVISIONARE
**Dependencies**: 08b-executor.py

---

## Overview

The TaskManager provides a dedicated system for **long-running background jobs** that:
- Run independently of ASGI request/response cycles
- Can be queried for status and results
- Support optional progress reporting
- Are isolated from the main worker processes

This is another key differentiator from Starlette.

---

## API Design

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

---

## Source Code

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

T = TypeVar("T")


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

        await tasks.shutdown()
    """

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

        self._started = False

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

        return task_id

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

        return self._tasks[task_id]

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

        return cancelled

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

        return tasks

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

        return len(to_remove)
```

---

## Tests

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

---

## Integration with Application

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

---

## Usage Example

```python
from genro_asgi import Application

app = Application()

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

---

## Checklist

- [ ] Create `src/genro_asgi/tasks.py`
- [ ] Create `tests/test_tasks.py`
- [ ] Run `pytest tests/test_tasks.py`
- [ ] Run `mypy src/genro_asgi/tasks.py`
- [ ] Run `ruff check src/genro_asgi/tasks.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

---

## Commit Message

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
