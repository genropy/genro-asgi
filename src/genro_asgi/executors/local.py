# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Local executor for CPU-bound work using ProcessPoolExecutor.

Purpose
=======
LocalExecutor wraps ProcessPoolExecutor to run blocking/CPU-bound functions
without freezing the async event loop. Supports backpressure via semaphore
and bypass mode for testing.

Features:
- ProcessPoolExecutor for true parallelism (bypasses GIL)
- Bypass mode (pool=None) for testing without spawning processes
- Backpressure via semaphore to limit pending tasks
- Metrics collection (submitted, completed, failed, avg duration)
- Clear error messages for pickle serialization failures

Definition::

    class LocalExecutor(BaseExecutor):
        __slots__ = ("name", "pool", "max_pending", "_semaphore", "_metrics")

        def __init__(
            self,
            name: str = "default",
            max_workers: int | None = None,
            initializer: Callable | None = None,
            initargs: tuple = (),
            max_pending: int = 100,
            bypass: bool = False,
        )
        async def submit(self, func: Callable, *args, **kwargs) -> Any
        def shutdown(self, wait: bool = True) -> None
        @property
        def metrics(self) -> dict

Example::

    from genro_asgi.executors import LocalExecutor

    executor = LocalExecutor(name="pdf", max_workers=2)

    @executor
    def generate_pdf(data):
        # CPU-bound work
        return create_pdf(data)

    # In async handler
    async def handle():
        result = await generate_pdf(report_data)

Bypass Mode::

    # For testing - no actual processes spawned
    executor = LocalExecutor(name="test", bypass=True)

    @executor
    def my_func(x):
        return x * 2

    result = await my_func(5)  # runs synchronously, returns 10

Environment Variable::

    # Set GENRO_EXECUTOR_BYPASS=1 to bypass all LocalExecutors
    import os
    os.environ['GENRO_EXECUTOR_BYPASS'] = '1'

Design Notes
============
- Uses asyncio.Semaphore for backpressure control
- Catches pickle.PicklingError for clear error messages
- Metrics are simple counters (Prometheus integration is optional)
- Decorated functions must be top-level (not lambdas/closures)
- Arguments and return values must be pickle-serializable
"""

from __future__ import annotations

import asyncio
import os
import pickle
import time
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, Callable

from .base import BaseExecutor, ExecutorError

__all__ = ["LocalExecutor"]


class LocalExecutor(BaseExecutor):
    """
    Executor using local ProcessPoolExecutor.

    Runs functions in separate processes for true parallelism,
    bypassing Python's GIL. Ideal for CPU-bound work.

    Attributes:
        name: Identifier for this executor (used in metrics/logging).
        pool: The ProcessPoolExecutor, or None in bypass mode.
        max_pending: Maximum pending tasks before backpressure.

    Example:
        >>> executor = LocalExecutor(name="compute", max_workers=4)
        >>>
        >>> @executor
        ... def heavy_work(data):
        ...     return process(data)
        >>>
        >>> result = await heavy_work(my_data)
    """

    __slots__ = ("name", "pool", "max_pending", "_semaphore", "_metrics")

    def __init__(
        self,
        name: str = "default",
        max_workers: int | None = None,
        initializer: Callable[..., None] | None = None,
        initargs: tuple[Any, ...] = (),
        max_pending: int = 100,
        bypass: bool = False,
    ) -> None:
        """
        Initialize LocalExecutor.

        Args:
            name: Identifier for metrics and logging.
            max_workers: Number of worker processes (default: CPU count).
            initializer: Function called once per worker at startup.
            initargs: Arguments passed to initializer.
            max_pending: Maximum concurrent pending tasks.
            bypass: If True, run synchronously without pool (for testing).
        """
        self.name = name
        self.max_pending = max_pending

        # Check environment for global bypass
        env_bypass = os.environ.get("GENRO_EXECUTOR_BYPASS") == "1"

        if bypass or env_bypass:
            self.pool = None
            self._semaphore: asyncio.Semaphore | None = None
        else:
            self.pool = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=initializer,
                initargs=initargs,
            )
            self._semaphore = asyncio.Semaphore(max_pending)

        self._metrics = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "total_duration_ms": 0.0,
        }

    @property
    def metrics(self) -> dict[str, Any]:
        """
        Return current executor metrics.

        Returns:
            Dict with name, pending, submitted, completed, failed, avg_duration_ms.
        """
        completed = self._metrics["completed"]
        return {
            "name": self.name,
            "mode": "bypass" if self.pool is None else "process",
            "pending": (
                self._metrics["submitted"]
                - self._metrics["completed"]
                - self._metrics["failed"]
            ),
            "submitted": self._metrics["submitted"],
            "completed": completed,
            "failed": self._metrics["failed"],
            "avg_duration_ms": (
                self._metrics["total_duration_ms"] / completed if completed > 0 else 0.0
            ),
        }

    async def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Submit a function for execution in the process pool.

        Args:
            func: The function to execute (must be top-level, pickle-able).
            *args: Positional arguments (must be pickle-able).
            **kwargs: Keyword arguments (must be pickle-able).

        Returns:
            The result of func(*args, **kwargs).

        Raises:
            ExecutorError: If serialization fails or execution errors.
            ExecutorOverloadError: If semaphore cannot be acquired.
        """
        # Bypass mode: run synchronously
        if self.pool is None:
            return func(*args, **kwargs)

        self._metrics["submitted"] += 1
        start = time.monotonic()

        try:
            if self._semaphore is not None:
                # Try to acquire semaphore (backpressure)
                try:
                    async with self._semaphore:
                        result = await self._execute(func, *args, **kwargs)
                except asyncio.CancelledError:
                    raise
            else:
                result = await self._execute(func, *args, **kwargs)

            self._metrics["completed"] += 1
            return result

        except ExecutorError:
            self._metrics["failed"] += 1
            raise
        except Exception:
            self._metrics["failed"] += 1
            raise

        finally:
            self._metrics["total_duration_ms"] += (time.monotonic() - start) * 1000

    async def _execute(
        self, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> Any:
        """Execute function in the process pool."""
        loop = asyncio.get_running_loop()
        call = partial(func, *args, **kwargs)

        try:
            return await loop.run_in_executor(self.pool, call)
        except pickle.PicklingError as e:
            raise ExecutorError(
                f"Cannot serialize arguments for {func.__name__}. "
                f"Ensure all args are pickle-serializable. Original: {e}"
            ) from e

    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the process pool.

        Args:
            wait: If True, wait for pending tasks to complete.
        """
        if self.pool is not None:
            self.pool.shutdown(wait=wait)

    def __repr__(self) -> str:
        """Return string representation."""
        mode = "bypass" if self.pool is None else "process"
        return f"LocalExecutor(name={self.name!r}, mode={mode})"


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        # Test bypass mode
        executor = LocalExecutor(name="test", bypass=True)
        print(f"Executor: {executor}")

        @executor
        def square(x: int) -> int:
            return x * x

        result = await square(5)  # type: ignore[misc]
        print(f"square(5) = {result}")
        print(f"Metrics: {executor.metrics}")

    asyncio.run(main())
