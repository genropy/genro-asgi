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

The server is SELF-CONFIGURING: ``AsgiServer(config=source)`` builds its own
read door — a ``ConfigurationHandler`` over a ``config.py`` path, a recipe class,
a recipe instance or a ready handler — derives its constructor kwargs from it and
then runs the ordinary D16 cooperative chain. Nothing materializes a server from
the outside; the class that needs the values reads them. Explicitly passed
kwargs WIN over the configured ones, wholesale per kwarg
(``AsgiServer(config=Recipe, port=0)`` serves the recipe's site on an
OS-assigned port), and the handler stays reachable as ``server.config`` — the
read door applications delegate to. A bare ``AsgiServer(...)`` has
``config is None`` and behaves exactly as before.

Its cooperative ``__init__`` peels the kwargs the frozen Macro 1 ``BaseServer``
does not accept — ``host``/``port``/``external_url`` plus ``server_app`` (the
login-surface values of the ``authentication`` section) — and forwards
everything else (``applications``, ``auth``, ``session_store``/``session_ttl``,
``middleware``/``middleware_registry``, ``plugins``/``plugin_registry``,
``storage``/``storage_key``, ``parent``) down the D16 chain. The peeled
``host``/``port`` become the defaults of ``serve``, so a configured server
serves on its configured address unless the caller overrides it.

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
configured one, and no configuration path special-cases it. The configured
databases are registered right after, over the live server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genro_builders.builder import BuilderBase

from .applications.server_app import ServerApplication
from .auth import AuthMixin
from .communication import CommunicationMixin
from .config.elements import AsgiServerGrammar
from .config.default_config import DefaultConfig
from .config.handler import ConfigurationHandler
from .db import AsgiDbHandlerBase
from .middleware import MiddlewareMixin
from .plugin_mixin import PluginMixin
from .server import BaseServer
from .session import SessionMixin
from .storage_mixin import StorageMixin
from .tasks import TaskMixin

__all__ = ["AsgiServer"]

ConfigSource = str | Path | type | BuilderBase | ConfigurationHandler


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

    Constructor kwargs peeled here: ``config`` — the configuration source this
    server reads itself from — ``host`` and ``port`` (the ``serve`` defaults),
    ``external_url`` (the public base address, trailing slash stripped) and
    ``server_app`` (the login-surface values forwarded to the automatically
    registered ``_server`` app). Every other kwarg flows to the capability
    mixins and the base (D16 cooperative init).
    """

    grammar: type = AsgiServerGrammar

    def __init__(self, config: ConfigSource | None = None, **kwargs: Any) -> None:
        self._config = self._build_config(config)
        if self.config is not None:
            kwargs = {**self._configured_kwargs(self.config), **kwargs}
        self._config_host: str | None = kwargs.pop("host", None)
        self._config_port: int | None = kwargs.pop("port", None)
        external_url: str | None = kwargs.pop("external_url", None)
        self._external_url: str | None = external_url.rstrip("/") if external_url else None
        self._server_app_kwargs: dict[str, Any] = kwargs.pop("server_app", {})
        super().__init__(**kwargs)
        self._register_server_app()
        self._check_oidc_external_url()
        if self.config is not None:
            self._register_configured_databases(self.config)

    def _build_config(self, config: ConfigSource | None) -> ConfigurationHandler | None:
        """The read door over ``config``: a ready handler passes through, anything
        else (a ``config.py`` path, a recipe class, a recipe instance) is wrapped
        in one over the parent layers. ``None`` — a hand-built server — has no
        configuration at all.

        The site recipe is the TOP layer: ``DefaultConfig.parents_for()`` puts the
        package defaults under it, plus the defaults source the recipe itself
        declares (``default_config``). A handler handed in ready-made keeps
        whatever layering it was built with — its owner already decided.

        A ``config.py`` path is imported ONCE, here: the loaded class both
        answers ``default_config`` and becomes the handler's source, so a
        module-body side effect fires a single time per boot and the class the
        parents were computed from is the class the handler builds."""
        if config is None or isinstance(config, ConfigurationHandler):
            return config
        defaults = DefaultConfig()
        if isinstance(config, (str, Path)):
            config = defaults.recipe_class(config)
        return ConfigurationHandler(config, parents=defaults.parents_for(config))

    def _configured_kwargs(self, config: ConfigurationHandler) -> dict[str, Any]:
        """The constructor kwargs the configuration declares.

        One helper of the read door per section, each mapped to the kwarg the
        owning class peels; a section the recipe omits contributes nothing, so
        the composition's own defaults apply. ``applications`` are instantiated
        HERE — the recipe named the classes and their kwargs, and a recipe error
        surfaces as a boot error instead of a broken server.
        """
        kwargs: dict[str, Any] = config.server_kwargs()
        kwargs.update(config.identity_kwargs())
        for name, value in (
            ("middleware", config.middleware_config()),
            ("auth", config.auth_entries()),
            ("plugins", config.plugins_config()),
        ):
            if value is not None:
                kwargs[name] = value
        storage = config.storage_config()
        if storage is not None:
            kwargs["storage"], kwargs["storage_key"] = storage
        server_app = config.server_app_kwargs()
        if server_app:
            kwargs["server_app"] = server_app
        entries, default = config.applications()
        kwargs["applications"] = [app_class(**app_kwargs) for app_class, app_kwargs in entries]
        if default is not None:
            kwargs["default"] = default
        return kwargs

    def _register_configured_databases(self, config: ConfigurationHandler) -> None:
        """Build and register the configured database handlers over the live server.

        Each descriptor becomes ``db_handler_class(db_class(**params))``,
        registered by its ``code``; the default handler class is
        ``AsgiDbHandlerBase``. It runs after the cooperative chain because
        ``add_database`` needs the server, not its kwargs.
        """
        for descriptor in config.databases():
            db_class = descriptor["db_class"]
            handler_class = descriptor["db_handler_class"] or AsgiDbHandlerBase
            self.add_database(
                descriptor["code"], handler_class(db_class(**descriptor["params"]))
            )

    @property
    def config(self) -> ConfigurationHandler | None:
        """The read door over this server's configuration (``None`` when built bare).

        Callable as ``server.config("server.host")`` — the four-layer read stack
        of the ``ConfigurationHandler`` — and the door applications delegate to
        with their own ``applications.<code>.`` prefix.
        """
        return self._config

    def _register_server_app(self) -> None:
        """Register the automatic ``_server`` app (D4) unless one is already there.

        Runs at the end of ``__init__``, after the composed applications are
        registered, so the guard only matters when the composition already
        carries a ``_server`` app (idempotent). The peeled ``server_app``
        kwargs (the ``authentication`` login surface: ``login`` policy, ``oidc``
        providers) are forwarded here — the app peels them.
        """
        if "_server" not in self.applications:
            self.register_application(ServerApplication(**self._server_app_kwargs))

    def _check_oidc_external_url(self) -> None:
        """Refuse to boot when a provider is configured without ``external_url``.

        Runs right after the ``_server`` registration, the first moment both facts are
        known — the app carries the configured providers, the server carries its
        public address — and covers the configured and the hand-built server with
        one check. An OIDC provider is handed the ABSOLUTE ``redirect_uri`` it
        must send the browser back to; without a public base address that URI
        cannot be built, so the configuration is incomplete and the server says
        so loudly instead of failing at the first login attempt with a
        provider-side error.
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
