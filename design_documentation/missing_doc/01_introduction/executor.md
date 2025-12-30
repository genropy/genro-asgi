## Source: initial_implementation_plan/archive/08b-executor.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types.py, 07-lifespan.py

The Executor provides a unified execution subsystem for running:
- **Blocking tasks** in a ThreadPoolExecutor (sync I/O, legacy libraries)
- **CPU-bound tasks** in a ProcessPoolExecutor (heavy computation)

This is a key differentiator from Starlette, which does not include integrated execution pools.

```python
# Access via application
result = await app.executor.run_blocking(func, *args, **kwargs)
result = await app.executor.run_process(func, *args, **kwargs)

# Or standalone
from genro_asgi import Executor

executor = Executor()
await executor.startup()
result = await executor.run_blocking(sync_function, arg1, arg2)
await executor.shutdown()
```

**File**: `src/genro_asgi/executor.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Unified execution subsystem for blocking and CPU-bound tasks."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

class Executor:
    """Unified executor for blocking and CPU-bound tasks.

Provides two execution pools:
    - ThreadPoolExecutor for blocking I/O operations
    - ProcessPoolExecutor for CPU-intensive work

Example:
        executor = Executor(max_threads=10, max_processes=4)
        await executor.startup()

# Run blocking I/O
        result = await executor.run_blocking(sync_db_query, "SELECT ...")

# Run CPU-bound work
        result = await executor.run_process(heavy_computation, data)

await executor.shutdown()
    """

def __init__(
        self,
        max_threads: int = 40,
        max_processes: int | None = None,
    ) -> None:
        """Initialize the executor.

Args:
            max_threads: Maximum threads for blocking tasks. Default 40.
            max_processes: Maximum processes for CPU tasks. Default is CPU count.
        """
        self._max_threads = max_threads
        self._max_processes = max_processes
        self._thread_pool: ThreadPoolExecutor | None = None
        self._process_pool: ProcessPoolExecutor | None = None
        self._started = False

@property
    def is_running(self) -> bool:
        """Check if executor is running."""
        return self._started

async def startup(self) -> None:
        """Start the execution pools.

Called automatically during application lifespan startup.
        """
        if self._started:
            return

self._thread_pool = ThreadPoolExecutor(
            max_workers=self._max_threads,
            thread_name_prefix="genro_blocking_"
        )
        self._process_pool = ProcessPoolExecutor(
            max_workers=self._max_processes
        )
        self._started = True

async def shutdown(self, wait: bool = True) -> None:
        """Shutdown the execution pools.

Args:
            wait: If True, wait for pending tasks to complete.

Called automatically during application lifespan shutdown.
        """
        if not self._started:
            return

if self._thread_pool:
            self._thread_pool.shutdown(wait=wait)
            self._thread_pool = None

if self._process_pool:
            self._process_pool.shutdown(wait=wait)
            self._process_pool = None

async def run_blocking(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run a blocking function in the thread pool.

Use for:
        - Legacy database drivers (non-async)
        - File system operations
        - Blocking network calls
        - Synchronous library compatibility

Args:
            func: Synchronous callable to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

Returns:
            The result of func(*args, **kwargs).

Raises:
            RuntimeError: If executor is not started.
            Exception: Any exception raised by func.

Example:
            def read_file(path):
                with open(path) as f:
                    return f.read()

content = await executor.run_blocking(read_file, "/path/to/file")
        """
        if not self._started or self._thread_pool is None:
            raise RuntimeError("Executor not started. Call startup() first.")

loop = asyncio.get_running_loop()

if kwargs:
            func = partial(func, **kwargs)

return await loop.run_in_executor(self._thread_pool, func, *args)

async def run_process(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run a CPU-bound function in the process pool.

Use for:
        - Heavy data processing
        - Image/audio transformation
        - Compression or hashing
        - Numerical computation

Note: func must be picklable (top-level function, not lambda/closure).

Args:
            func: Picklable callable to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

Returns:
            The result of func(*args, **kwargs).

Raises:
            RuntimeError: If executor is not started.
            Exception: Any exception raised by func.

Example:
            def compress_data(data):
                import zlib
                return zlib.compress(data)

compressed = await executor.run_process(compress_data, large_data)
        """
        if not self._started or self._process_pool is None:
            raise RuntimeError("Executor not started. Call startup() first.")

loop = asyncio.get_running_loop()

if kwargs:
            func = partial(func, **kwargs)

return await loop.run_in_executor(self._process_pool, func, *args)

# Default executor instance (optional, for simple use cases)
_default_executor: Executor | None = None

def get_executor() -> Executor:
    """Get the default executor instance.

Creates one if it doesn't exist. For most applications,
    use app.executor instead.
    """
    global _default_executor
    if _default_executor is None:
        _default_executor = Executor()
    return _default_executor
```

**File**: `tests/test_executor.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for the Executor module."""

import asyncio
import time
import pytest

from genro_asgi.executor import Executor, get_executor

class TestExecutor:
    """Tests for Executor class."""

@pytest.fixture
    async def executor(self):
        """Provide a started executor."""
        ex = Executor(max_threads=4, max_processes=2)
        await ex.startup()
        yield ex
        await ex.shutdown()

async def test_startup_shutdown(self):
        """Test executor lifecycle."""
        ex = Executor()
        assert not ex.is_running

await ex.startup()
        assert ex.is_running

await ex.shutdown()
        assert not ex.is_running

async def test_double_startup(self):
        """Test that double startup is safe."""
        ex = Executor()
        await ex.startup()
        await ex.startup()  # Should not raise
        assert ex.is_running
        await ex.shutdown()

async def test_double_shutdown(self):
        """Test that double shutdown is safe."""
        ex = Executor()
        await ex.startup()
        await ex.shutdown()
        await ex.shutdown()  # Should not raise
        assert not ex.is_running

async def test_run_blocking_simple(self, executor):
        """Test run_blocking with a simple function."""
        def add(a, b):
            return a + b

result = await executor.run_blocking(add, 2, 3)
        assert result == 5

async def test_run_blocking_with_kwargs(self, executor):
        """Test run_blocking with keyword arguments."""
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

result = await executor.run_blocking(greet, "World", greeting="Hi")
        assert result == "Hi, World!"

async def test_run_blocking_io(self, executor, tmp_path):
        """Test run_blocking with actual I/O."""
        test_file = tmp_path / "test.txt"
        content = "Hello, Executor!"

def write_file(path, data):
            with open(path, "w") as f:
                f.write(data)

def read_file(path):
            with open(path) as f:
                return f.read()

await executor.run_blocking(write_file, test_file, content)
        result = await executor.run_blocking(read_file, test_file)
        assert result == content

async def test_run_blocking_not_started(self):
        """Test run_blocking raises if not started."""
        ex = Executor()

with pytest.raises(RuntimeError, match="not started"):
            await ex.run_blocking(lambda: None)

async def test_run_blocking_exception(self, executor):
        """Test that exceptions propagate correctly."""
        def failing_func():
            raise ValueError("Test error")

with pytest.raises(ValueError, match="Test error"):
            await executor.run_blocking(failing_func)

async def test_run_process_simple(self, executor):
        """Test run_process with a simple function."""
        # Note: Must use top-level function for pickling
        result = await executor.run_process(cpu_bound_add, 10, 20)
        assert result == 30

async def test_run_process_cpu_bound(self, executor):
        """Test run_process with CPU-bound work."""
        result = await executor.run_process(cpu_bound_sum, 1000000)
        assert result == sum(range(1000000))

async def test_run_process_not_started(self):
        """Test run_process raises if not started."""
        ex = Executor()

with pytest.raises(RuntimeError, match="not started"):
            await ex.run_process(cpu_bound_add, 1, 2)

async def test_concurrent_blocking(self, executor):
        """Test multiple concurrent blocking tasks."""
        def slow_task(n):
            time.sleep(0.1)
            return n * 2

start = time.time()
        results = await asyncio.gather(
            executor.run_blocking(slow_task, 1),
            executor.run_blocking(slow_task, 2),
            executor.run_blocking(slow_task, 3),
            executor.run_blocking(slow_task, 4),
        )
        elapsed = time.time() - start

assert results == [2, 4, 6, 8]
        # Should run in parallel, so less than 0.4s
        assert elapsed < 0.3

class TestGetExecutor:
    """Tests for get_executor function."""

def test_get_executor_returns_executor(self):
        """Test that get_executor returns an Executor."""
        ex = get_executor()
        assert isinstance(ex, Executor)

def test_get_executor_singleton(self):
        """Test that get_executor returns same instance."""
        ex1 = get_executor()
        ex2 = get_executor()
        assert ex1 is ex2

# Top-level functions for ProcessPoolExecutor (must be picklable)
def cpu_bound_add(a: int, b: int) -> int:
    """Simple add for process pool test."""
    return a + b

def cpu_bound_sum(n: int) -> int:
    """CPU-bound sum for process pool test."""
    return sum(range(n))
```

After implementing this block, `applications.py` will be updated to include:

```python
class Application:
    def __init__(self, ...):
        ...
        self.executor = Executor()

async def _handle_lifespan(self, scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await self.executor.startup()
                # ... other startup
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.executor.shutdown()
                # ... other shutdown
                await send({"type": "lifespan.shutdown.complete"})
                return
```

- [ ] Create `src/genro_asgi/executor.py`
- [ ] Create `tests/test_executor.py`
- [ ] Run `pytest tests/test_executor.py`
- [ ] Run `mypy src/genro_asgi/executor.py`
- [ ] Run `ruff check src/genro_asgi/executor.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

```
feat(executor): add unified execution subsystem

- Add Executor class with ThreadPoolExecutor and ProcessPoolExecutor
- Implement run_blocking() for sync I/O operations
- Implement run_process() for CPU-bound tasks
- Add startup/shutdown lifecycle management
- Add comprehensive tests

This provides a key advantage over Starlette which lacks
integrated execution pools.
```

