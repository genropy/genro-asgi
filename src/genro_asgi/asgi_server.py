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
PluginMixin, StorageMixin, TaskMixin, BaseServer``): the complete mono-process
async server of D22. ``TaskMixin`` sits after ``StorageMixin`` (it needs
``server.storage``) and before ``BaseServer`` (its lifespan hook must wrap the
base ``Lifespan``). The future internal (worker) server simply composes the SAME
base WITHOUT the auth mixin (D6 by construction — the base never learned about
the chain).

Its cooperative ``__init__`` peels the kwargs the frozen Macro 1
``BaseServer`` does not accept — ``host``/``port``/``external_url`` plus
``server_app`` (the ``_server`` config-class lift) — and forwards everything
else (``applications``, ``auth``, ``session_store``/``session_ttl``,
``middleware``/``middleware_registry``, ``plugins``/``plugin_registry``,
``storage``/``storage_key``, ``parent``) down the D16 chain. The peeled
``host``/``port`` become the defaults of ``serve``, so a config-built server
serves on its configured address unless the caller overrides it;
``server_app`` travels to ``_register_server_app``.

``host``/``port`` are the LISTENER; ``external_url`` is the server's PUBLIC
base address — the two differ behind a proxy and answer different questions.
The listener says where to bind; the public address is what the server calls
itself when it hands its own URL to a third party. Only one consumer needs it
today (an OIDC provider is given an absolute ``redirect_uri``, RFC 6749
§3.1.2), and it is DECLARED rather than derived from a request: the URI must
match the one registered with the provider — a deployment fact known to
whoever installs — and deriving it from the client-supplied ``Host`` would
build a value the provider then rejects. Missing it with a provider
configured is a boot error (``_check_oidc_external_url``), not an opaque
provider error at the first login.

Once the chain has run, ``__init__`` registers the automatic ``_server`` app
(``_register_server_app``, D4 "automatic, not configured"): a hand-built
``AsgiServer(applications=[...])`` exposes ``/_server/...`` exactly like a
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
from .tasks import TaskMixin

__all__ = ["AsgiServer"]


class AsgiServer(
    CommunicationMixin,
    AuthMixin,
    SessionMixin,
    MiddlewareMixin,
    PluginMixin,
    StorageMixin,
    TaskMixin,
    BaseServer,
):
    """The shipped composition: communication + auth + sessions + chain + plugins + storage + base.

    Constructor kwargs peeled here: ``host`` and ``port`` — the ``serve``
    defaults carried from the config's ``server`` section — ``external_url``,
    the server's public base address (trailing slash stripped), plus
    ``server_app``, the ``_server`` config-class lift forwarded to the
    automatically registered app. Every other kwarg flows to the capability
    mixins and the base (D16 cooperative init).
    """

    def __init__(self, **kwargs: Any) -> None:
        self._config_host: str | None = kwargs.pop("host", None)
        self._config_port: int | None = kwargs.pop("port", None)
        external_url: str | None = kwargs.pop("external_url", None)
        self._external_url: str | None = external_url.rstrip("/") if external_url else None
        self._server_app_kwargs: dict[str, Any] = kwargs.pop("server_app", {})
        super().__init__(**kwargs)
        self._register_server_app()
        self._check_oidc_external_url()

    def _register_server_app(self) -> None:
        """Register the automatic ``_server`` app (D4) unless one is already there.

        Runs at the end of ``__init__``, after the composed applications are
        registered, so the guard only matters when the composition already
        carries a ``_server`` app (idempotent). The peeled ``server_app``
        kwargs (the config-class lift: ``login`` policy, ``oidc`` providers)
        are forwarded here — the app peels them.
        """
        if "_server" not in self.applications:
            self.register_application(ServerApplication(**self._server_app_kwargs))

    def _check_oidc_external_url(self) -> None:
        """Refuse to boot when a provider is configured without ``external_url``.

        Runs right after the ``_server`` registration, the first moment both facts are
        known — the app carries the configured providers, the server carries its
        public address — and covers the config-materialized and the hand-built
        server with one check. An OIDC provider is handed the ABSOLUTE
        ``redirect_uri`` it must send the browser back to; without a public base
        address that URI cannot be built, so the configuration is incomplete and
        the server says so loudly instead of failing at the first login attempt
        with a provider-side error.
        """
        providers = getattr(self.applications.get("_server"), "oidc_providers", None)
        if providers and self.external_url is None:
            codes = ", ".join(sorted(providers))
            raise ValueError(
                f"oidc provider(s) {codes} configured but the server has no "
                "external_url: OIDC needs the public base URL to build the "
                "absolute redirect_uri (set server(external_url=...))"
            )

    @property
    def login_enabled(self) -> bool:
        """True when the ``_server`` app carries a registered auth method.

        The challenge negotiation (``ErrorMiddleware``) reads this to decide
        whether a 401 becomes a login redirect (browser) or a ``login_url``
        body (API). It reflects live state: ``ServerApplication`` registers the
        password method at construction, so its server has a login surface.
        """
        server_app = self.applications.get("_server")
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

    @property
    def external_url(self) -> str | None:
        """The server's public base URL, without a trailing slash (``None`` if unset).

        What the server calls ITSELF when it hands its own address to a third
        party — distinct from the ``host``/``port`` it binds to, which differ
        behind a proxy. Declared in the config's ``server`` section; the only
        consumer today is the OIDC ``redirect_uri``, which must be absolute.
        """
        return self._external_url

    def serve(self, host: str | None = None, port: int | None = None) -> None:
        """Boot uvicorn, defaulting host/port to the configured values.

        The caller's explicit ``host``/``port`` win; otherwise the config's
        ``server`` section is used, falling back to the ``BaseServer`` defaults
        (``127.0.0.1`` and an OS-assigned port).
        """
        resolved_host = host if host is not None else (self.config_host or "127.0.0.1")
        resolved_port = port if port is not None else (self.config_port if self.config_port is not None else 0)
        super().serve(host=resolved_host, port=resolved_port)
