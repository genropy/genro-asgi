# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Executor registry for managing multiple executor instances.

Purpose
=======
ExecutorRegistry manages named executor instances, providing lazy creation,
caching, and centralized shutdown. Supports multiple executor types
(local, remote) via factory pattern.

Features:
- Named executors with lazy creation
- Support for multiple executor types
- Centralized metrics collection
- Coordinated shutdown of all executors

Definition::

    class ExecutorRegistry:
        __slots__ = ("_executors", "_factories")

        def __init__(self)
        def register_factory(self, executor_type: str, factory: Callable) -> None
        def get_or_create(self, name: str, executor_type: str = "local", **kwargs) -> BaseExecutor
        def get(self, name: str) -> BaseExecutor | None
        def shutdown_all(self, wait: bool = True) -> None
        def all_metrics(self) -> list[dict]
        @property
        def executors(self) -> dict[str, BaseExecutor]

Example::

    from genro_asgi.executors import ExecutorRegistry

    registry = ExecutorRegistry()

    # Get or create named executors
    pdf_executor = registry.get_or_create("pdf", max_workers=2)
    ml_executor = registry.get_or_create("ml", max_workers=4)

    @pdf_executor
    def generate_pdf(data):
        return create_pdf(data)

    @ml_executor
    def predict(model, data):
        return model.predict(data)

    # Get metrics for all executors
    metrics = registry.all_metrics()

    # Shutdown all on application exit
    registry.shutdown_all()

Extensibility::

    # Register custom executor type
    from myapp.executors import RemoteExecutor

    registry.register_factory("remote", lambda **kw: RemoteExecutor(**kw))

    # Use remote executor
    executor = registry.get_or_create("cluster", executor_type="remote", url="...")

Design Notes
============
- Default factory creates LocalExecutor
- Executors are cached by name
- shutdown_all() should be called on application shutdown
- Thread-safe for read operations (creation should be done at startup)
"""

from __future__ import annotations

from typing import Any, Callable

from .base import BaseExecutor
from .local import LocalExecutor

__all__ = ["ExecutorRegistry"]


class ExecutorRegistry:
    """
    Registry for managing named executor instances.

    Provides centralized management of executors with lazy creation,
    caching, and coordinated shutdown.

    Attributes:
        executors: Dict of name -> executor instance.

    Example:
        >>> registry = ExecutorRegistry()
        >>> executor = registry.get_or_create("compute", max_workers=4)
        >>> registry.shutdown_all()
    """

    __slots__ = ("_executors", "_factories")

    def __init__(self) -> None:
        """Initialize ExecutorRegistry with default factories."""
        self._executors: dict[str, BaseExecutor] = {}
        self._factories: dict[str, Callable[..., BaseExecutor]] = {
            "local": self._create_local,
        }

    def _create_local(self, name: str, **kwargs: Any) -> LocalExecutor:
        """Factory for LocalExecutor."""
        return LocalExecutor(name=name, **kwargs)

    def register_factory(
        self,
        executor_type: str,
        factory: Callable[..., BaseExecutor],
    ) -> None:
        """
        Register a factory for a custom executor type.

        Args:
            executor_type: Type identifier (e.g., "remote", "hybrid").
            factory: Callable that creates executor instances.
                     Signature: factory(name: str, **kwargs) -> BaseExecutor

        Example:
            >>> registry.register_factory("remote", lambda name, **kw: RemoteExecutor(name, **kw))
        """
        self._factories[executor_type] = factory

    def get_or_create(
        self,
        name: str,
        executor_type: str = "local",
        **kwargs: Any,
    ) -> BaseExecutor:
        """
        Get existing executor or create new one.

        Args:
            name: Unique identifier for the executor.
            executor_type: Type of executor ("local" by default).
            **kwargs: Arguments passed to executor constructor.

        Returns:
            Executor instance (cached if already exists).

        Raises:
            ValueError: If executor_type is not registered.

        Example:
            >>> executor = registry.get_or_create("pdf", max_workers=2)
            >>> same_executor = registry.get_or_create("pdf")  # returns cached
        """
        if name in self._executors:
            return self._executors[name]

        if executor_type not in self._factories:
            available = ", ".join(self._factories.keys())
            raise ValueError(
                f"Unknown executor type: {executor_type!r}. " f"Available types: {available}"
            )

        factory = self._factories[executor_type]
        executor = factory(name=name, **kwargs)
        self._executors[name] = executor
        return executor

    def get(self, name: str) -> BaseExecutor | None:
        """
        Get executor by name without creating.

        Args:
            name: Executor identifier.

        Returns:
            Executor instance or None if not found.
        """
        return self._executors.get(name)

    def shutdown_all(self, wait: bool = True) -> None:
        """
        Shutdown all registered executors.

        Args:
            wait: If True, wait for pending tasks to complete.
        """
        for executor in self._executors.values():
            executor.shutdown(wait=wait)
        self._executors.clear()

    def all_metrics(self) -> list[dict[str, Any]]:
        """
        Collect metrics from all executors.

        Returns:
            List of metric dicts, one per executor.
        """
        return [executor.metrics for executor in self._executors.values()]

    @property
    def executors(self) -> dict[str, BaseExecutor]:
        """Return dict of all registered executors."""
        return dict(self._executors)

    def __len__(self) -> int:
        """Return number of registered executors."""
        return len(self._executors)

    def __contains__(self, name: str) -> bool:
        """Check if executor exists."""
        return name in self._executors

    def __repr__(self) -> str:
        """Return string representation."""
        names = list(self._executors.keys())
        return f"ExecutorRegistry(executors={names})"


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        registry = ExecutorRegistry()

        # Create executors
        exec1 = registry.get_or_create("compute", bypass=True)
        exec2 = registry.get_or_create("io", bypass=True)

        print(f"Registry: {registry}")
        print(f"Executor 1: {exec1}")
        print(f"Executor 2: {exec2}")

        # Use decorator
        @exec1
        def square(x: int) -> int:
            return x * x

        result = await square(7)  # type: ignore[misc]
        print(f"square(7) = {result}")

        # Metrics
        print(f"All metrics: {registry.all_metrics()}")

        # Shutdown
        registry.shutdown_all()
        print(f"After shutdown: {registry}")

    asyncio.run(main())
