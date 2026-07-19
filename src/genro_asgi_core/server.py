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

"""The base server: primary app, secondary mounts, ASGI dispatch, uvicorn boot.

``BaseServer`` is the common substrate of every server (SPECIFICATION.md §4,
D2): it REQUIRES the primary application (``primary=`` kwarg; missing raises
``TypeError``) and keeps secondary applications in a mounts dict keyed by
``mount_name`` — the one demux mechanism of D3. At the base,
``authenticate()`` answers nobody (``None``) and ``session()`` answers none
(``None``). It owns exactly one thread pool (D2): ``run_sync()`` dispatches a
blocking handler onto it via ``loop.run_in_executor`` while async handlers stay
on the loop; the pool is provisioned lazily on first use and torn down at
shutdown.

As an ASGI callable, ``__call__`` dispatches on the scope type: ``http`` runs
the D3 demux (first path segment → matching mount with that segment stripped,
otherwise the primary with the full path); ``websocket`` runs ``on_websocket``,
whose DEFAULT is the empty socket of D7 (accepts nothing, closes cleanly with
code 1000); ``lifespan`` runs the ``Lifespan`` handler (ordered startup,
reverse shutdown, error isolation). Each http dispatch is registered in the
``RequestRegistry`` (``requests``) for the span of the request — the current
request and the in-flight picture. ``serve()`` boots uvicorn programmatically.

Cooperative init (D16): peels its own kwargs (``primary``) and, as the end of
the chain, raises ``TypeError`` naming any leftover kwargs. Mixins go BEFORE
``BaseServer`` in the MRO.

Ownership channel (one direction): attaching the primary and ``mount()`` both
assign ``app.server = self``; the app-side setter enforces exactly-once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

import uvicorn

from .application import BaseApplication
from .lifespan import Lifespan
from .pool import WorkPool
from .registry import RequestRegistry

if TYPE_CHECKING:
    from .types import Receive, Scope, Send

__all__ = ["BaseServer"]


class BaseServer:
    """Base server owning the primary application and the secondary mounts.

    Constructor kwargs peeled here: ``primary`` — the always-present primary
    application (D2), answering ``/`` and everything no mount claims.
    """

    def __init__(self, **kwargs: Any) -> None:
        if "primary" not in kwargs:
            raise TypeError(f"{type(self).__name__} requires a primary application (primary=...)")
        primary: BaseApplication = kwargs.pop("primary")
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(
                f"{type(self).__name__}.__init__() got unexpected keyword arguments: {unexpected}"
            )
        super().__init__()
        self._primary = primary
        self._mounts: dict[str, BaseApplication] = {}
        self._uvicorn: uvicorn.Server | None = None
        self._pool = WorkPool(self)
        self._lifespan = Lifespan(self)
        self._registry = RequestRegistry(self)
        primary.server = self

    @property
    def primary(self) -> BaseApplication:
        """The primary application: answers ``/`` and the unclaimed rest."""
        return self._primary

    @property
    def mounts(self) -> dict[str, BaseApplication]:
        """Secondary applications keyed by ``mount_name`` (may be empty)."""
        return self._mounts

    def mount(self, app: BaseApplication) -> None:
        """Register ``app`` as a secondary mount keyed by its ``mount_name``.

        Assigns the ownership channel (``app.server = self``). A secondary
        without a ``mount_name`` cannot be demuxed and a claimed name cannot
        be claimed twice: both raise ``ValueError``.
        """
        name = app.mount_name
        if not name:
            raise ValueError("a secondary application requires a non-empty mount_name")
        if name in self.mounts:
            raise ValueError(f"mount_name already claimed: {name}")
        app.server = self
        self.mounts[name] = app

    @property
    def lifespan(self) -> Lifespan:
        """The ``Lifespan`` handler managing this server's startup/shutdown."""
        return self._lifespan

    @property
    def pool(self) -> WorkPool:
        """The server's single thread pool for blocking (sync) handlers."""
        return self._pool

    @property
    def requests(self) -> RequestRegistry:
        """The registry of in-flight requests and the current one."""
        return self._registry

    async def run_sync(self, fn: Callable[..., Any], *args: Any) -> Any:
        """Dispatch blocking ``fn`` onto the pool (the app-side sync protocol).

        Apps call ``self.server.run_sync(...)`` for blocking work so it runs
        off the event loop; async handlers simply stay on the loop and never
        touch the pool.
        """
        return await self.pool.run(fn, *args)

    def authenticate(self, request: Any) -> Any:
        """Base answer: nobody (``None``). Auth capabilities override this."""
        return None

    def session(self, request: Any) -> Any:
        """Base answer: none (``None``). Session capabilities override this."""
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI entry point: dispatch on the scope type.

        ``http`` runs the D3 demux (registering the request in ``requests`` for
        the span of the dispatch); ``websocket`` runs ``on_websocket`` (the
        empty socket by default); ``lifespan`` runs the ``Lifespan`` handler.
        Any other type is an ASGI protocol error.
        """
        scope_type = scope["type"]
        if scope_type == "http":
            item = self.requests.register(scope)
            try:
                app, target = self.demux(scope)
                await app(target, receive, send)
            finally:
                self.requests.unregister(item)
        elif scope_type == "websocket":
            await self.on_websocket(scope, receive, send)
        elif scope_type == "lifespan":
            await self.lifespan(scope, receive, send)
            # The lifespan handler returns once shutdown is acked; tear the
            # pool down here (a no-op unless a sync dispatch provisioned it).
            self.pool.shutdown(wait=True)
        else:
            raise ValueError(f"unsupported ASGI scope type: {scope_type}")

    def demux(self, scope: Scope) -> tuple[BaseApplication, Scope]:
        """D3 demux: pick the app for an http scope and the scope it receives.

        First path segment matching a mount → that app, with the segment
        stripped from ``path`` (the forwarded path is rebuilt from the same
        remainder used to find the segment, so ``//api/x`` forwards ``/x``);
        anything else (including ``/``) → the primary with the full path
        unchanged.
        """
        path = scope["path"]
        rest = path.lstrip("/")
        segment, _, remainder = rest.partition("/")
        app = self.mounts.get(segment)
        if app is None:
            return self.primary, scope
        sub_scope = dict(scope)
        sub_scope["path"] = "/" + remainder
        return app, sub_scope

    async def on_websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        """The empty websocket socket (D7): consume the connect, close cleanly.

        The base accepts nothing and closes with code 1000. The websocket motor
        (Q1) overrides this hook in a later macro.
        """
        await receive()
        await send({"type": "websocket.close", "code": 1000})

    @property
    def uvicorn_server(self) -> uvicorn.Server | None:
        """The uvicorn ``Server`` once ``serve()`` has built it (else ``None``).

        Callers that boot the server in a background thread read the bound port
        from ``uvicorn_server.servers[0].sockets[0].getsockname()`` after
        ``uvicorn_server.started`` turns true.
        """
        return self._uvicorn

    def serve(self, host: str = "127.0.0.1", port: int = 0) -> None:
        """Boot uvicorn programmatically, serving this server (blocking).

        Builds ``uvicorn.Config``/``uvicorn.Server`` and runs it. ``port=0``
        lets the OS assign an ephemeral port, discoverable via
        ``uvicorn_server`` once started.
        """
        self._uvicorn = uvicorn.Server(uvicorn.Config(self, host=host, port=port))
        self._uvicorn.run()


if __name__ == "__main__":
    server = BaseServer(primary=BaseApplication())
    server.mount(BaseApplication(mount_name="api"))
    assert server.primary.server is server
    assert "api" in server.mounts
    assert server.authenticate(None) is None
    assert server.session(None) is None
