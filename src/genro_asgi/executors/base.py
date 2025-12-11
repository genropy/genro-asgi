# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Base executor interface and exceptions.

Purpose
=======
Defines the abstract base class for all executor implementations and
common exceptions. All executors (local, remote, hybrid) must implement
the BaseExecutor interface.

Definition::

    class BaseExecutor(ABC):
        name: str

        @abstractmethod
        async def submit(self, func: Callable, *args, **kwargs) -> Any
            '''Submit a function for execution.'''

        @abstractmethod
        def shutdown(self, wait: bool = True) -> None
            '''Shutdown the executor.'''

        @property
        @abstractmethod
        def metrics(self) -> dict[str, Any]
            '''Return executor metrics.'''

        def __call__(self, func: Callable) -> Callable
            '''Decorator interface - wraps func to use submit().'''

Exceptions::

    ExecutorError
        Base exception for executor operations.

    ExecutorOverloadError(ExecutorError)
        Raised when executor has too many pending tasks (backpressure).

Design Notes
============
- BaseExecutor provides __call__ for decorator pattern (uses submit internally)
- Subclasses only need to implement submit(), shutdown(), metrics
- Metrics dict must include: name, pending, submitted, completed, failed
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import wraps
from typing import Any, Callable, TypeVar

__all__ = ["BaseExecutor", "ExecutorError", "ExecutorOverloadError"]

F = TypeVar("F", bound=Callable[..., Any])


class ExecutorError(Exception):
    """Base exception for executor operations."""

    pass


class ExecutorOverloadError(ExecutorError):
    """Raised when executor has too many pending tasks."""

    pass


class BaseExecutor(ABC):
    """
    Abstract base class for all executor implementations.

    Provides a common interface for local and remote executors.
    Implements the decorator pattern via __call__ which uses submit().

    Subclasses must implement:
    - submit(): Execute function asynchronously
    - shutdown(): Clean up resources
    - metrics: Return performance metrics

    Attributes:
        name: Identifier for this executor instance.

    Example:
        >>> class MyExecutor(BaseExecutor):
        ...     async def submit(self, func, *args, **kwargs):
        ...         return func(*args, **kwargs)
        ...     def shutdown(self, wait=True): pass
        ...     @property
        ...     def metrics(self): return {"name": self.name}
        >>>
        >>> executor = MyExecutor("test")
        >>>
        >>> @executor
        ... def my_func(x):
        ...     return x * 2
        >>>
        >>> result = await my_func(5)  # returns 10
    """

    name: str

    @abstractmethod
    async def submit(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Submit a function for execution.

        Args:
            func: The function to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

        Returns:
            The result of func(*args, **kwargs).

        Raises:
            ExecutorError: If execution fails.
            ExecutorOverloadError: If too many tasks are pending.
        """
        ...

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None:
        """
        Shutdown the executor and release resources.

        Args:
            wait: If True, wait for pending tasks to complete.
        """
        ...

    @property
    @abstractmethod
    def metrics(self) -> dict[str, Any]:
        """
        Return executor metrics.

        Returns:
            Dict containing at minimum:
            - name: Executor name
            - pending: Number of pending tasks
            - submitted: Total submitted tasks
            - completed: Total completed tasks
            - failed: Total failed tasks
        """
        ...

    def __call__(self, func: F) -> F:
        """
        Decorate a function to run in this executor.

        Args:
            func: The function to wrap.

        Returns:
            Async wrapper that runs func via submit().
        """

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await self.submit(func, *args, **kwargs)

        return wrapper  # type: ignore[return-value]

    def __repr__(self) -> str:
        """Return string representation."""
        return f"{self.__class__.__name__}(name={self.name!r})"


if __name__ == "__main__":
    # Quick validation that ABC works
    print("BaseExecutor is abstract - cannot instantiate directly")

    try:
        BaseExecutor()  # type: ignore[abstract]
    except TypeError as e:
        print(f"  Expected error: {e}")
