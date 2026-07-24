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

"""The server's single thread pool for blocking work (SPECIFICATION.md §4, D2).

``WorkPool`` wraps one ``concurrent.futures.ThreadPoolExecutor`` and is held by
the server as a dual parent-child (``self.server``). Async handlers stay on the
event loop; only sync handlers reach the pool, dispatched through
``BaseServer.run_sync`` via ``loop.run_in_executor``.

Lazily provisioned (invariant #1 — build lazily on the running loop): the
executor is created on the first dispatch, never at boot, and torn down at
lifespan shutdown only if it was ever provisioned.
"""

from __future__ import annotations

import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .server import BaseServer

__all__ = ["WorkPool"]


class WorkPool:
    """One thread pool for blocking (sync) handlers, owned by the server.

    Constructor kwarg: ``max_threads`` — the executor's ``max_workers``
    (``None`` uses the stdlib default, ``min(32, cpu + 4)``). Threads are
    named ``genro-pool*`` so a handler can assert it ran off the loop.
    """

    def __init__(self, server: BaseServer, max_threads: int | None = None) -> None:
        self.server = server
        self._max_threads = max_threads
        self._executor: ThreadPoolExecutor | None = None

    @property
    def provisioned(self) -> bool:
        """Whether the executor exists yet (a sync dispatch has happened)."""
        return self._executor is not None

    @property
    def executor(self) -> ThreadPoolExecutor:
        """The pool's executor, created on first access (lazy provisioning)."""
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_threads,
                thread_name_prefix="genro-pool",
            )
        return self._executor

    async def run(self, fn: Callable[..., Any], *args: Any) -> Any:
        """Run blocking ``fn`` on a pool thread, provisioning on first call.

        The caller's context is copied into the worker thread (what
        ``asyncio.to_thread`` does), so a sync handler sees the loop-side
        ContextVars — e.g. the registry's current request.
        """
        loop = asyncio.get_running_loop()
        ctx = contextvars.copy_context()
        return await loop.run_in_executor(self.executor, ctx.run, fn, *args)

    def shutdown(self, wait: bool = True) -> None:
        """Tear the executor down — a no-op if it was never provisioned.

        Resets the lazy slot so a later dispatch re-provisions: a server
        reused through repeated ``serve()`` rounds keeps working.
        """
        if self.provisioned:
            self.executor.shutdown(wait=wait)
            self._executor = None


if __name__ == "__main__":
    import threading

    from .application import BaseApplication
    from .server import BaseServer

    server = BaseServer(primary=BaseApplication())
    assert server.pool.provisioned is False

    async def main() -> None:
        name = await server.pool.run(lambda: threading.current_thread().name)
        assert name.startswith("genro-pool"), name
        assert server.pool.provisioned is True
        server.pool.shutdown()

    asyncio.run(main())
