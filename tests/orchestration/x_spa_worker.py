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

"""The instrumentation every end-to-end story needs from its child, and no story.

Two things, and both are apparatus rather than subject. The MEMORY a process
declares replaces the reading of ``/proc/self/status``, which macOS has not, so a
story whose subject is occupancy stays readable on every platform; the number
travels in the child's own ``worker_kwargs``, which is how the grammar configures
the class it names. The DRIVER'S DOOR carries the two orders the protocol does
not: the shot and the cycle that follows it are verbs of the worker and nobody in
the machine proper orders them — no clock calls ``plan_transfers`` yet — so a
story that needs a frozen user reaches them through the subclass.

What the site IS belongs to the story: this class wires ``wsgi_app`` to ``site``
and each story writes that method.
"""

from __future__ import annotations

from typing import Any

from genro_asgi.spa.orchestration import SpaWorker

#: The two orders of the driver: flag whoever is due, then let the flagged go.
PLAN_ORDER = "/op/plan_transfers"
EXECUTE_ORDER = "/op/execute_transfers"


class X_SpaWorker(SpaWorker):
    """A worker that declares its memory and answers the driver's two orders."""

    def __init__(self, name: str, *, declared_rss_bytes: int = 0, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.declared_rss_bytes = declared_rss_bytes
        self.wsgi_app = self.site

    @property
    def rss_bytes(self) -> int:
        """What this process declares it holds, in bytes."""
        return self.declared_rss_bytes

    def site(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        """The WSGI callable of the story this child belongs to.

        Args:
            environ: the PEP 3333 environ the seam built.
            start_response: the PEP 3333 callable.

        Returns:
            The body, in one chunk.
        """
        raise NotImplementedError(f"{type(self).__name__} has no site")

    async def answer_call(self, frame: Any) -> None:
        """Answer the driver's two orders, and hand everything else upstairs.

        Args:
            frame: the CALL as it came off the wire.

        Acts through the verb the order names, and through the reply it sends.
        """
        if frame.path == PLAN_ORDER:
            self.plan_transfers()
            await self.send_reply(frame, result={})
        elif frame.path == EXECUTE_ORDER:
            await self.execute_transfers()
            await self.send_reply(frame, result={})
        else:
            await super().answer_call(frame)
