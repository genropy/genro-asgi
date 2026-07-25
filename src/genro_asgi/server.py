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

"""The base server: the applications it serves, ASGI dispatch, uvicorn boot.

``BaseServer`` is the common substrate of every server (SPECIFICATION.md §4,
D2): it is composed with its applications (``applications=`` kwarg, a list)
and keeps them in a dict keyed by each app's ``code``, plus a private index by
``mount`` — the one demux mechanism of D3. The set of applications is fixed at
construction; registration is internal. At the base,
``authenticate()`` answers nobody (``None``) and ``session()`` answers none
(``None``). It owns exactly one thread pool (D2): ``run_sync()`` dispatches a
blocking handler onto it via ``loop.run_in_executor`` while async handlers stay
on the loop; the pool is provisioned lazily on first use and torn down at
shutdown.

As an ASGI callable, ``__call__`` dispatches on the scope type: ``http`` runs
the D3 demux — first path segment → the app mounted there with that segment
stripped; else the app on the site root with the full path; else a 307 from
``/`` to the declared ``default``; else 404 — ``websocket`` runs
``on_websocket``,
whose DEFAULT is the empty socket of D7 (accepts nothing, closes cleanly with
code 1000); ``lifespan`` runs the ``Lifespan`` handler (ordered startup,
reverse shutdown, error isolation). Each http dispatch is registered in the
``RequestRegistry`` (``requests``) for the span of the request — the current
request and the in-flight picture. ``serve()`` boots uvicorn programmatically.

Cooperative init (D16): peels its own kwargs (``applications``,
``max_threads``) and, as the end of the chain, raises ``TypeError`` naming any
leftover kwargs. Mixins go BEFORE ``BaseServer`` in the MRO.

Ownership channel (one direction): registering an application assigns
``app.server = self``; the app-side setter enforces exactly-once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterable

import uvicorn

from .application import BaseApplication
from .lifespan import Lifespan
from .pool import WorkPool
from .registry import RequestRegistry
from .response import Response

if TYPE_CHECKING:
    from .types import ASGIApp, Receive, Scope, Send

__all__ = ["BaseServer"]


class BaseServer:
    """Base server owning the applications it was composed with.

    Constructor kwargs peeled here: ``applications`` — the applications this
    server serves — ``default`` — the ``code`` of the application ``/``
    redirects to when nothing answers the root (an unknown code raises
    ``ValueError``) — and ``max_threads`` — the pool's worker count, handed to
    ``WorkPool`` (``None`` keeps the stdlib default).
    """

    def __init__(self, **kwargs: Any) -> None:
        applications: Iterable[BaseApplication] = kwargs.pop("applications", ())
        default: str | None = kwargs.pop("default", None)
        max_threads: int | None = kwargs.pop("max_threads", None)
        if kwargs:
            unexpected = ", ".join(sorted(kwargs))
            raise TypeError(
                f"{type(self).__name__}.__init__() got unexpected keyword arguments: {unexpected}"
            )
        super().__init__()
        self._applications: dict[str, BaseApplication] = {}
        self._by_mount: dict[str, BaseApplication] = {}
        self._databases: dict[str, Any] = {}
        self._uvicorn: uvicorn.Server | None = None
        self._pool = WorkPool(self, max_threads=max_threads)
        self._lifespan = Lifespan(self)
        self._registry = RequestRegistry(self)
        for app in applications:
            self.register_application(app)
        self._default = default
        if default is not None and default not in self.applications:
            raise ValueError(f"default names no served application: {default!r}")

    @property
    def applications(self) -> dict[str, BaseApplication]:
        """The served applications keyed by their ``code``."""
        return self._applications

    @property
    def root_application(self) -> BaseApplication | None:
        """The application on the site root (``mount == ""``), ``None`` if there is none.

        It answers ``/`` and every path no other mount claims. A server of
        mounts only has none: then ``/`` redirects to the ``default`` if one is
        declared, and an unclaimed path is a 404.
        """
        return self.application_at("")

    @property
    def default_application(self) -> BaseApplication | None:
        """The application ``/`` redirects to, ``None`` if no ``default`` was declared.

        It elects nothing: the redirect is the whole of its meaning, and it is
        only consulted when no application answers the root.
        """
        return self.applications[self._default] if self._default is not None else None

    def application_at(self, mount: str) -> BaseApplication | None:
        """The application answering under the URL prefix ``mount`` (``None`` if none)."""
        return self._by_mount.get(mount)

    def register_application(self, app: BaseApplication) -> None:
        """Register ``app`` under its ``code`` and its ``mount``.

        Assigns the ownership channel (``app.server = self``). Internal: the
        set of applications is fixed at construction, so the callers are
        ``__init__`` and the composition layers building a server. A claimed
        code and a claimed mount both raise ``ValueError``.
        """
        mount = app.code if app.mount is None else app.mount
        if app.code in self.applications:
            raise ValueError(f"application code already claimed: {app.code}")
        if mount in self._by_mount:
            raise ValueError(f"mount already claimed: {mount!r}")
        app.server = self
        self.applications[app.code] = app
        self._by_mount[mount] = app

    @property
    def databases(self) -> dict[str, Any]:
        """Database handlers keyed by their config ``code`` (may be empty)."""
        return self._databases

    def add_database(self, code: str, handler: Any) -> None:
        """Register ``handler`` under ``code``. A claimed code raises ``ValueError``."""
        if code in self.databases:
            raise ValueError(f"database code already registered: {code}")
        self.databases[code] = handler

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
                item.run_cleanups()
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

    def demux(self, scope: Scope) -> tuple[ASGIApp, Scope]:
        """D3 demux: pick what answers an http scope, and the scope it receives.

        One rule, four branches: the first path segment matching a mount → that
        app, with the segment stripped from ``path`` (the forwarded path is
        rebuilt from the same remainder used to find the segment, so ``//api/x``
        forwards ``/x``); else the application on the site root, with the full
        path unchanged; else, for ``/`` itself with a ``default`` declared, a
        **307** to that application's mount carrying the query string over;
        else **404**. ``/`` on a server WITH a root application matches its
        empty mount in the first branch, which forwards the same ``/``.
        """
        path = scope["path"]
        rest = path.lstrip("/")
        segment, _, remainder = rest.partition("/")
        app = self.application_at(segment)
        if app is not None:
            sub_scope = dict(scope)
            sub_scope["path"] = "/" + remainder
            return app, sub_scope
        root = self.root_application
        if root is not None:
            return root, scope
        default = self.default_application if not rest else None
        if default is not None:
            return self.redirect_to_default(default, scope), scope
        return Response(content="Not Found", status_code=404, media_type="text/plain"), scope

    def redirect_to_default(self, app: BaseApplication, scope: Scope) -> Response:
        """A 307 to ``app``'s mount, preserving the query string.

        307 and not 301/302: the method and the body must survive the hop, so a
        ``POST /`` reaches the default application as a POST.
        """
        location = f"/{app.mount}/"
        query = scope.get("query_string", b"")
        if query:
            location = f"{location}?{query.decode('latin-1')}"
        return Response(status_code=307, headers={"location": location})

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
