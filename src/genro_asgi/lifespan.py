"""ASGI Lifespan management.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

from typing import Callable, Awaitable


class Lifespan:
    """ASGI Lifespan event manager.

    Manages application startup and shutdown events.
    """

    def __init__(self) -> None:
        """Initialize lifespan manager."""
        self.startup_handlers: list[Callable[[], Awaitable[None]]] = []
        self.shutdown_handlers: list[Callable[[], Awaitable[None]]] = []

    def on_startup(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """Register a startup handler.

        Args:
            func: Async function to call on startup

        Returns:
            The registered function (for use as decorator)
        """
        self.startup_handlers.append(func)
        return func

    def on_shutdown(self, func: Callable[[], Awaitable[None]]) -> Callable[[], Awaitable[None]]:
        """Register a shutdown handler.

        Args:
            func: Async function to call on shutdown

        Returns:
            The registered function (for use as decorator)
        """
        self.shutdown_handlers.append(func)
        return func

    async def run_startup(self) -> None:
        """Run all startup handlers."""
        for handler in self.startup_handlers:
            await handler()

    async def run_shutdown(self) -> None:
        """Run all shutdown handlers."""
        for handler in self.shutdown_handlers:
            await handler()
