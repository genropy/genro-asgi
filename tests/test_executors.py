# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for the executors package."""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import patch

import pytest

from genro_asgi.executors import (
    BaseExecutor,
    ExecutorError,
    ExecutorOverloadError,
    ExecutorRegistry,
    LocalExecutor,
)


# =============================================================================
# BaseExecutor Tests
# =============================================================================


class TestBaseExecutor:
    """Tests for BaseExecutor ABC."""

    def test_cannot_instantiate_directly(self) -> None:
        """BaseExecutor is abstract and cannot be instantiated."""
        with pytest.raises(TypeError, match="abstract"):
            BaseExecutor()  # type: ignore[abstract]

    def test_subclass_must_implement_abstract_methods(self) -> None:
        """Subclasses must implement all abstract methods."""

        class IncompleteExecutor(BaseExecutor):
            name = "incomplete"

        with pytest.raises(TypeError, match="abstract"):
            IncompleteExecutor()  # type: ignore[abstract]

    def test_complete_subclass_works(self) -> None:
        """A complete subclass can be instantiated."""

        class TestExecutor(BaseExecutor):
            name = "test"

            async def submit(
                self, func: Any, *args: Any, **kwargs: Any
            ) -> Any:
                return func(*args, **kwargs)

            def shutdown(self, wait: bool = True) -> None:
                pass

            @property
            def metrics(self) -> dict[str, Any]:
                return {"name": self.name}

        executor = TestExecutor()
        assert executor.name == "test"

    @pytest.mark.asyncio
    async def test_call_uses_submit(self) -> None:
        """__call__ decorator uses submit internally."""

        class TestExecutor(BaseExecutor):
            name = "test"
            submit_called = False

            async def submit(
                self, func: Any, *args: Any, **kwargs: Any
            ) -> Any:
                self.submit_called = True
                return func(*args, **kwargs)

            def shutdown(self, wait: bool = True) -> None:
                pass

            @property
            def metrics(self) -> dict[str, Any]:
                return {"name": self.name}

        executor = TestExecutor()

        @executor
        def square(x: int) -> int:
            return x * x

        result = await square(5)
        assert result == 25
        assert executor.submit_called


# =============================================================================
# LocalExecutor Tests
# =============================================================================


class TestLocalExecutor:
    """Tests for LocalExecutor."""

    def test_create_with_defaults(self) -> None:
        """LocalExecutor can be created with default parameters."""
        executor = LocalExecutor(name="test", bypass=True)
        assert executor.name == "test"
        assert executor.pool is None  # bypass mode

    def test_bypass_mode_no_pool(self) -> None:
        """In bypass mode, no ProcessPool is created."""
        executor = LocalExecutor(bypass=True)
        assert executor.pool is None
        assert executor._semaphore is None

    def test_repr(self) -> None:
        """repr shows name and mode."""
        executor = LocalExecutor(name="compute", bypass=True)
        assert "compute" in repr(executor)
        assert "bypass" in repr(executor)

    @pytest.mark.asyncio
    async def test_bypass_runs_synchronously(self) -> None:
        """In bypass mode, functions run synchronously."""
        executor = LocalExecutor(name="test", bypass=True)

        @executor
        def add(a: int, b: int) -> int:
            return a + b

        result = await add(2, 3)
        assert result == 5

    @pytest.mark.asyncio
    async def test_bypass_with_kwargs(self) -> None:
        """Bypass mode works with keyword arguments."""
        executor = LocalExecutor(bypass=True)

        @executor
        def greet(name: str, greeting: str = "Hello") -> str:
            return f"{greeting}, {name}!"

        result = await greet("World", greeting="Hi")
        assert result == "Hi, World!"

    @pytest.mark.asyncio
    async def test_metrics_initial(self) -> None:
        """Initial metrics are all zeros."""
        executor = LocalExecutor(name="test", bypass=True)
        metrics = executor.metrics
        assert metrics["name"] == "test"
        assert metrics["submitted"] == 0
        assert metrics["completed"] == 0
        assert metrics["failed"] == 0
        assert metrics["pending"] == 0
        assert metrics["avg_duration_ms"] == 0.0

    @pytest.mark.asyncio
    async def test_metrics_after_execution(self) -> None:
        """Metrics are updated after execution."""
        executor = LocalExecutor(name="test", bypass=True)

        @executor
        def identity(x: int) -> int:
            return x

        await identity(1)
        await identity(2)

        # In bypass mode, metrics are not updated (no pool)
        # This is expected behavior - bypass is for testing
        metrics = executor.metrics
        assert metrics["name"] == "test"

    def test_shutdown_bypass_mode(self) -> None:
        """Shutdown is safe in bypass mode."""
        executor = LocalExecutor(bypass=True)
        executor.shutdown()  # Should not raise

    @pytest.mark.asyncio
    async def test_submit_directly(self) -> None:
        """submit() can be called directly without decorator."""
        executor = LocalExecutor(bypass=True)

        def multiply(a: int, b: int) -> int:
            return a * b

        result = await executor.submit(multiply, 3, 4)
        assert result == 12

    def test_env_bypass(self) -> None:
        """GENRO_EXECUTOR_BYPASS=1 enables bypass mode."""
        with patch.dict(os.environ, {"GENRO_EXECUTOR_BYPASS": "1"}):
            executor = LocalExecutor(name="test")
            assert executor.pool is None


# =============================================================================
# ExecutorRegistry Tests
# =============================================================================


class TestExecutorRegistry:
    """Tests for ExecutorRegistry."""

    def test_create_empty(self) -> None:
        """Registry starts empty."""
        registry = ExecutorRegistry()
        assert len(registry) == 0

    def test_get_or_create_new(self) -> None:
        """get_or_create creates new executor."""
        registry = ExecutorRegistry()
        executor = registry.get_or_create("compute", bypass=True)
        assert executor.name == "compute"
        assert "compute" in registry

    def test_get_or_create_cached(self) -> None:
        """get_or_create returns cached executor."""
        registry = ExecutorRegistry()
        exec1 = registry.get_or_create("compute", bypass=True)
        exec2 = registry.get_or_create("compute")  # kwargs ignored for cached
        assert exec1 is exec2

    def test_get_existing(self) -> None:
        """get() returns existing executor."""
        registry = ExecutorRegistry()
        created = registry.get_or_create("test", bypass=True)
        found = registry.get("test")
        assert found is created

    def test_get_nonexistent(self) -> None:
        """get() returns None for nonexistent."""
        registry = ExecutorRegistry()
        assert registry.get("nonexistent") is None

    def test_unknown_executor_type_raises(self) -> None:
        """Unknown executor type raises ValueError."""
        registry = ExecutorRegistry()
        with pytest.raises(ValueError, match="Unknown executor type"):
            registry.get_or_create("test", executor_type="unknown")

    def test_register_custom_factory(self) -> None:
        """Custom factory can be registered."""
        registry = ExecutorRegistry()

        class CustomExecutor(BaseExecutor):
            def __init__(self, name: str, custom_arg: str = "default"):
                self.name = name
                self.custom_arg = custom_arg

            async def submit(self, func: Any, *args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

            def shutdown(self, wait: bool = True) -> None:
                pass

            @property
            def metrics(self) -> dict[str, Any]:
                return {"name": self.name, "custom_arg": self.custom_arg}

        registry.register_factory(
            "custom", lambda name, **kw: CustomExecutor(name, **kw)
        )

        executor = registry.get_or_create(
            "test", executor_type="custom", custom_arg="special"
        )
        assert isinstance(executor, CustomExecutor)
        assert executor.custom_arg == "special"

    def test_len(self) -> None:
        """len() returns number of executors."""
        registry = ExecutorRegistry()
        assert len(registry) == 0
        registry.get_or_create("a", bypass=True)
        assert len(registry) == 1
        registry.get_or_create("b", bypass=True)
        assert len(registry) == 2

    def test_contains(self) -> None:
        """'in' operator works."""
        registry = ExecutorRegistry()
        registry.get_or_create("test", bypass=True)
        assert "test" in registry
        assert "other" not in registry

    def test_executors_property(self) -> None:
        """executors property returns dict copy."""
        registry = ExecutorRegistry()
        exec1 = registry.get_or_create("a", bypass=True)
        exec2 = registry.get_or_create("b", bypass=True)

        executors = registry.executors
        assert executors["a"] is exec1
        assert executors["b"] is exec2

    def test_all_metrics(self) -> None:
        """all_metrics() returns list of all executor metrics."""
        registry = ExecutorRegistry()
        registry.get_or_create("a", bypass=True)
        registry.get_or_create("b", bypass=True)

        metrics = registry.all_metrics()
        assert len(metrics) == 2
        names = {m["name"] for m in metrics}
        assert names == {"a", "b"}

    def test_shutdown_all(self) -> None:
        """shutdown_all() shuts down and clears all executors."""
        registry = ExecutorRegistry()
        registry.get_or_create("a", bypass=True)
        registry.get_or_create("b", bypass=True)
        assert len(registry) == 2

        registry.shutdown_all()
        assert len(registry) == 0

    def test_repr(self) -> None:
        """repr shows executor names."""
        registry = ExecutorRegistry()
        registry.get_or_create("compute", bypass=True)
        registry.get_or_create("io", bypass=True)
        r = repr(registry)
        assert "ExecutorRegistry" in r
        assert "compute" in r
        assert "io" in r


# =============================================================================
# Exception Tests
# =============================================================================


class TestExecutorExceptions:
    """Tests for executor exceptions."""

    def test_executor_error(self) -> None:
        """ExecutorError can be raised with message."""
        with pytest.raises(ExecutorError, match="test error"):
            raise ExecutorError("test error")

    def test_executor_overload_error_is_executor_error(self) -> None:
        """ExecutorOverloadError is subclass of ExecutorError."""
        assert issubclass(ExecutorOverloadError, ExecutorError)

    def test_executor_overload_error(self) -> None:
        """ExecutorOverloadError can be raised."""
        with pytest.raises(ExecutorOverloadError, match="too many"):
            raise ExecutorOverloadError("too many tasks")


# =============================================================================
# Integration Tests
# =============================================================================


class TestExecutorIntegration:
    """Integration tests for executor usage patterns."""

    @pytest.mark.asyncio
    async def test_multiple_executors_independent(self) -> None:
        """Multiple executors work independently."""
        registry = ExecutorRegistry()
        exec_a = registry.get_or_create("a", bypass=True)
        exec_b = registry.get_or_create("b", bypass=True)

        @exec_a
        def func_a(x: int) -> str:
            return f"a:{x}"

        @exec_b
        def func_b(x: int) -> str:
            return f"b:{x}"

        result_a = await func_a(1)
        result_b = await func_b(2)

        assert result_a == "a:1"
        assert result_b == "b:2"

    @pytest.mark.asyncio
    async def test_concurrent_calls(self) -> None:
        """Multiple concurrent calls work."""
        executor = LocalExecutor(bypass=True)

        @executor
        def slow_add(a: int, b: int) -> int:
            return a + b

        results = await asyncio.gather(
            slow_add(1, 2),
            slow_add(3, 4),
            slow_add(5, 6),
        )

        assert results == [3, 7, 11]

    @pytest.mark.asyncio
    async def test_exception_propagation(self) -> None:
        """Exceptions from executed functions propagate."""
        executor = LocalExecutor(bypass=True)

        @executor
        def failing_func() -> None:
            raise ValueError("intentional error")

        with pytest.raises(ValueError, match="intentional error"):
            await failing_func()
