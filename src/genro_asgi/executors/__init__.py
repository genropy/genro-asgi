# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Executor package for offloading blocking/CPU-bound work.

This package provides executor implementations for running blocking functions
without freezing the async event loop.

Available executors:
- LocalExecutor: ProcessPoolExecutor for local CPU-bound work
- (future) RemoteExecutor: For distributed execution across machines

Usage::

    from genro_asgi.executors import ExecutorRegistry, LocalExecutor

    # Via registry (recommended)
    registry = ExecutorRegistry()
    executor = registry.get_or_create("pdf", executor_type="local", max_workers=2)

    @executor
    def generate_pdf(data):
        return create_pdf(data)

    # Direct usage
    executor = LocalExecutor(name="compute", max_workers=4)

    @executor
    def heavy_work(data):
        return process(data)

    result = await heavy_work(my_data)
"""

from .base import BaseExecutor, ExecutorError, ExecutorOverloadError
from .local import LocalExecutor
from .registry import ExecutorRegistry

__all__ = [
    "BaseExecutor",
    "ExecutorError",
    "ExecutorOverloadError",
    "ExecutorRegistry",
    "LocalExecutor",
]
