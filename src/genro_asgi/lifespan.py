# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
ASGI Lifespan Management.

Purpose
=======
ServerLifespan handles the ASGI lifespan protocol for AsgiServer,
managing startup/shutdown sequences for mounted applications.

Features:
- Full ASGI lifespan protocol support
- Startup and shutdown handlers for mounted apps
- Support for sync and async handlers on sub-apps
- Error handling with proper ASGI messages

Definition::

    class ServerLifespan:
        __slots__ = ("server",)

        def __init__(self, server: AsgiServer)
        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None
        async def startup(self) -> None
        async def shutdown(self) -> None

Example::

    from genro_asgi import AsgiServer

    server = AsgiServer()
    # ServerLifespan is created automatically
    # server.lifespan handles all lifespan events

Design Notes
============
- ServerLifespan holds reference to server as `self.server`
- Sub-apps can define on_startup/on_shutdown methods (sync or async)
- Errors during startup send lifespan.startup.failed
- Errors during shutdown are logged but don't prevent completion
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Awaitable

from .types import Receive, Scope, Send

if TYPE_CHECKING:
    from .servers import AsgiServer

__all__ = ["ServerLifespan"]


class ServerLifespan:
    """
    ASGI Lifespan handler for AsgiServer.

    Manages the lifespan protocol, coordinating startup and shutdown
    of all mounted applications.

    Attributes:
        server: The AsgiServer instance this lifespan manages.

    Example:
        >>> # Automatically created by AsgiServer
        >>> server = AsgiServer()
        >>> # server.lifespan is a ServerLifespan instance
    """

    __slots__ = ("server", "_logger", "_started")

    def __init__(self, server: AsgiServer) -> None:
        """
        Initialize ServerLifespan.

        Args:
            server: The AsgiServer instance to manage.
        """
        self.server = server
        self._logger = logging.getLogger("genro_asgi.lifespan")
        self._started = False

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send  # noqa: ARG002
    ) -> None:
        """
        Handle ASGI lifespan protocol.

        Args:
            scope: ASGI scope dict (type="lifespan").
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        while True:
            message = await receive()
            msg_type = message["type"]

            if msg_type == "lifespan.startup":
                try:
                    await self.startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as e:
                    self._logger.exception("Startup failed")
                    await send({
                        "type": "lifespan.startup.failed",
                        "message": str(e),
                    })
                    return

            elif msg_type == "lifespan.shutdown":
                try:
                    await self.shutdown()
                except Exception:
                    self._logger.exception("Shutdown error")
                finally:
                    await send({"type": "lifespan.shutdown.complete"})
                return

    async def startup(self) -> None:
        """
        Execute startup sequence.

        Calls on_startup on all mounted apps.
        Apps can define on_startup as sync or async method.
        """
        self._logger.info("AsgiServer starting up...")

        # Sub-apps
        for path, app in self.server.apps.items():
            if hasattr(app, "on_startup"):
                self._logger.debug(f"Starting app at {path}")
                await self._call_handler(app, "on_startup")

        self._started = True
        self._logger.info("AsgiServer started")

    async def shutdown(self) -> None:
        """
        Execute shutdown sequence.

        Calls on_shutdown on all mounted apps in reverse order.
        Apps can define on_shutdown as sync or async method.
        Errors are logged but don't prevent other apps from shutting down.
        """
        self._logger.info("AsgiServer shutting down...")

        # Sub-apps in reverse order
        for path, app in reversed(list(self.server.apps.items())):
            if hasattr(app, "on_shutdown"):
                self._logger.debug(f"Stopping app at {path}")
                try:
                    await self._call_handler(app, "on_shutdown")
                except Exception:
                    self._logger.exception(f"Error shutting down app at {path}")

        self._started = False
        self._logger.info("AsgiServer stopped")

    async def _call_handler(self, app: object, method_name: str) -> None:
        """
        Call a handler method on an app (sync or async).

        Args:
            app: The application object.
            method_name: Name of the method to call.
        """
        handler = getattr(app, method_name)
        if callable(handler):
            result = handler()
            if hasattr(result, "__await__"):
                await result


# Keep old Lifespan class for backwards compatibility
class Lifespan:
    """ASGI Lifespan event manager (standalone version).

    Manages application startup and shutdown events via decorators.
    For use in standalone applications, not AsgiServer.
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
