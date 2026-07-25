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

"""ASGI lifespan protocol: ordered startup, reverse shutdown, error isolation.

``Lifespan`` is constructed with the server it manages (dual parent-child:
``self.server``, SPECIFICATION.md §4). On ``lifespan.startup`` it runs
``on_startup`` on the server's applications in registration order; on
``lifespan.shutdown`` it runs ``on_shutdown`` in REVERSE order. Hooks may
be sync or async, detected with ``inspect.iscoroutinefunction`` at call time.

A hook that raises is logged and the sequence CONTINUES: one app's error
never blocks the others, and uvicorn always receives the matching
``.complete`` message — app errors are isolated, never abort the protocol.
"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .application import BaseApplication
    from .server import BaseServer
    from .types import Receive, Scope, Send

__all__ = ["Lifespan"]


class Lifespan:
    """ASGI lifespan handler, held by the server as a dual parent-child."""

    def __init__(self, server: BaseServer) -> None:
        self.server = server
        self._logger = logging.getLogger(__name__)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:  # noqa: ARG002
        """Drive the ASGI lifespan protocol: startup then shutdown, both acked."""
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await self.startup()
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def startup(self) -> None:
        """Run ``on_startup`` in registration order."""
        for app in self._apps():
            await self._run_hook(app, "on_startup")

    async def shutdown(self) -> None:
        """Run ``on_shutdown`` in REVERSE order."""
        for app in reversed(self._apps()):
            await self._run_hook(app, "on_shutdown")

    def _apps(self) -> list[BaseApplication]:
        """The server's applications, in registration order."""
        return list(self.server.applications.values())

    async def _run_hook(self, app: BaseApplication, name: str) -> None:
        """Call ``app``'s hook; a raise is logged, the sequence continues."""
        handler = getattr(app, name)
        try:
            if inspect.iscoroutinefunction(handler):
                await handler()
            else:
                handler()
        except Exception:
            self._logger.exception("%s.%s raised", type(app).__name__, name)
