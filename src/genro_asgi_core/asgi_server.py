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

"""AsgiServer — the shipped mono-process server composition (D22, D6, D16).

``AsgiServer`` stacks every core capability mixin over ``BaseServer`` in one
MRO (``CommunicationMixin, AuthMixin, SessionMixin, MiddlewareMixin,
PluginMixin, StorageMixin, BaseServer``): the complete mono-process async
server of D22. The future internal (worker) server simply composes the SAME
base WITHOUT the auth mixin (D6 by construction — the base never learned about
the chain).

Its cooperative ``__init__`` peels the kwargs the frozen Macro 1
``BaseServer`` does not accept — ``host``/``port`` plus ``server_app`` (the
``_server`` config-class lift) — and forwards everything else (``primary``,
``auth``, ``session_store``/``session_ttl``,
``middleware``/``middleware_registry``, ``plugins``/``plugin_registry``,
``storage``/``storage_key``, ``parent``) down the D16 chain. The peeled
``host``/``port`` become the defaults of ``serve``, so a config-built server
serves on its configured address unless the caller overrides it;
``server_app`` travels to ``_mount_server_app``.

Once the chain has run, ``__init__`` mounts the automatic ``_server`` app
(``_mount_server_app``, D4 "automatic, not configured"): a hand-built
``AsgiServer(primary=...)`` exposes ``/_server/...`` exactly like a
config-materialized one, and ``ConfigurationHandler.materialize`` never
special-cases it.
"""

from __future__ import annotations

from typing import Any

from .applications.server_app import ServerApplication
from .auth import AuthMixin
from .communication import CommunicationMixin
from .middleware import MiddlewareMixin
from .plugin_mixin import PluginMixin
from .server import BaseServer
from .session import SessionMixin
from .storage_mixin import StorageMixin

__all__ = ["AsgiServer"]


class AsgiServer(
    CommunicationMixin,
    AuthMixin,
    SessionMixin,
    MiddlewareMixin,
    PluginMixin,
    StorageMixin,
    BaseServer,
):
    """The shipped composition: communication + auth + sessions + chain + plugins + storage + base.

    Constructor kwargs peeled here: ``host`` and ``port`` — the ``serve``
    defaults carried from the config's ``server`` section — plus
    ``server_app``, the ``_server`` config-class lift forwarded to the
    auto-mounted app. Every other kwarg flows to the capability mixins and
    the base (D16 cooperative init).
    """

    def __init__(self, **kwargs: Any) -> None:
        self._config_host: str | None = kwargs.pop("host", None)
        self._config_port: int | None = kwargs.pop("port", None)
        self._server_app_kwargs: dict[str, Any] = kwargs.pop("server_app", {})
        super().__init__(**kwargs)
        self._mount_server_app()

    def _mount_server_app(self) -> None:
        """Mount the automatic ``_server`` app (D4) unless one is already there.

        Runs at the end of ``__init__`` — before any configured secondary is
        mounted — so the guard only matters for re-invocations (idempotent).
        The peeled ``server_app`` kwargs (the config-class lift: ``login``
        policy, ``oidc`` providers) are forwarded here — the app peels them.
        """
        if "_server" not in self.mounts:
            self.mount(ServerApplication(**self._server_app_kwargs))

    @property
    def login_enabled(self) -> bool:
        """True when the ``_server`` app carries a registered auth method.

        The challenge negotiation (``ErrorMiddleware``) reads this to decide
        whether a 401 becomes a login redirect (browser) or a ``login_url``
        body (API). It reflects live state: ``ServerApplication`` registers the
        password method at construction, so its server has a login surface.
        """
        server_app = self.mounts.get("_server")
        section = getattr(server_app, "auth_section", None)
        return bool(section is not None and section.methods)

    @property
    def config_host(self) -> str | None:
        """The host from the config's ``server`` section (``None`` if unset)."""
        return self._config_host

    @property
    def config_port(self) -> int | None:
        """The port from the config's ``server`` section (``None`` if unset)."""
        return self._config_port

    def serve(self, host: str | None = None, port: int | None = None) -> None:
        """Boot uvicorn, defaulting host/port to the configured values.

        The caller's explicit ``host``/``port`` win; otherwise the config's
        ``server`` section is used, falling back to the ``BaseServer`` defaults
        (``127.0.0.1`` and an OS-assigned port).
        """
        resolved_host = host if host is not None else (self.config_host or "127.0.0.1")
        resolved_port = port if port is not None else (self.config_port if self.config_port is not None else 0)
        super().serve(host=resolved_host, port=resolved_port)


if __name__ == "__main__":
    from .application import BaseApplication

    server = AsgiServer(
        primary=BaseApplication(),
        host="0.0.0.0",
        port=9000,
        auth={"basic": {"admin": {"password": "secret", "tags": "admin"}}},
        middleware={"cors": True},
    )
    assert server.config_host == "0.0.0.0"
    assert server.config_port == 9000
    assert server.authenticate({"headers": []}) is None
    assert server.session({}) is None
    assert isinstance(server.mounts["_server"], ServerApplication)
    assert server.login_enabled is True
