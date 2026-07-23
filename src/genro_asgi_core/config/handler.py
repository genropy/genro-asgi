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

"""ConfigurationHandler — owns the config builder and MATERIALIZES a server.

DIVERGENCE from the old repo (recorded per the phase plan): the old
``AsgiConfigRenderer`` mutated a LIVE server through ``apply_configuration``;
this handler MATERIALIZES a fresh ``AsgiServer`` instead — ``materialize()``
walks the built ``source`` tree, turns the sections into constructor kwargs
riding the D16 cooperative chain, instantiates ``AsgiServer(**kwargs)`` and
mounts the secondary apps. No post-hoc mutation of server state.

It subclasses ``genro_builders``' ``BuilderHandler`` only to run the recipe
(``add_builder`` → the builder's ``create``); the configuration is read back by
walking the ``SourceBag`` directly (``node.node_tag`` /
``node.fixed_attr_items()``), never through a renderer.

Section → constructor kwarg mapping (core 1a):

- ``server`` → ``host``/``port`` (the ``AsgiServer.serve`` defaults) plus
  ``max_threads`` (the ``WorkPool`` size, peeled by ``BaseServer``) and
  ``storage_key`` (the ``StorageMixin`` encryption key); its ``session``
  child → ``session_ttl`` (server-domain).
- ``middleware`` → ``middleware=`` ({name: bool | dict} switches).
- ``auth`` → ``auth=`` (the ``AuthCore`` config, handed verbatim).
- ``storage`` → ``storage=`` ({code: {path, encrypted}} mounts for the
  ``StorageMixin``); visible to every role.
- ``applications`` → ``primary=`` (the ``default`` app, mount ``/``) plus the
  secondary mounts (each mounted after construction; mount defaults to ``code``).
- ``databases`` → one ``db_handler_class(db_class(**params))`` per entry,
  registered on the server by ``code`` (core 1b).
- ``plugins`` → ``plugins=`` ({code: bool | dict} switches for the
  ``PluginMixin``); visible to every role.
- ``openapi``/nested ``groups``/nested ``configuration`` → read and SKIPPED
  with a debug log (valid config for other roles/macros — ``configuration``
  is the app's own opaque subtree, consumed at runtime — not an error).

App config-classes: the constructor takes the site recipe FIRST plus any
app-config builders (``ConfigurationHandler(site, MyServerAppConfig(...))``).
Each extra builder is claimed by the application it configures via class
identity — today only ``_server`` (``ServerApplication.config_class``); a
builder nobody claims is a boot error. The claimed config's values
(``admin_password``/``users``/``tokens``) LIFT to the server constructor
kwargs (root role only); without one the base default applies (empty recipe,
today's bare ``ServerApplication()``).

``materialize(role=..., app=...)`` computes the role's ``Projection`` of the
built tree (D15) and materializes THAT slice: ``root`` sees every section
above; the hosted roles (``worker``/``batch``, ``app=<code>`` required) see
only their application (as primary) plus ``databases`` and ``storage`` — never
the public
middleware, never auth or sessions, never the public listener address.
"""

from __future__ import annotations

import logging
from typing import Any

from genro_builders.builder import BuilderHandler

from ..application import BaseApplication
from ..applications.server_app import ServerApplication
from ..asgi_server import AsgiServer
from ..db import AsgiDbHandlerBase
from .configurable import ConfigError, resolve_pointers
from .projection import Projection

__all__ = ["ConfigurationHandler"]


class ConfigurationHandler(BuilderHandler):
    """Owns the ``AsgiConfigBuilder`` recipe and materializes an ``AsgiServer``."""

    def __init__(self, builder: Any, *app_configs: Any) -> None:
        super().__init__()
        self._builder = builder
        self._logger = logging.getLogger(f"{__name__}.{type(self).__name__}")
        self._server_app_config = self._claim_app_configs(app_configs)
        self.add_builder(builder, self._server_app_config)

    @property
    def builder(self) -> Any:
        """The mounted configuration builder (its recipe already run)."""
        return self._builder

    @property
    def server_app_config(self) -> Any:
        """The ``_server`` app's config builder (the claimed one or the default)."""
        return self._server_app_config

    def _claim_app_configs(self, app_configs: tuple[Any, ...]) -> Any:
        """Match each extra builder to the application it configures.

        The core knows ONE app by construction: ``_server`` — the claim is by
        class identity (``ServerApplication.config_class``, D4/D26), no name
        registry. A builder no application claims is an explicit boot error;
        so is a second config for the same app. No config at all = the base
        default (empty recipe → today's bare ``ServerApplication()``).
        """
        claimed = None
        for config in app_configs:
            if not isinstance(config, ServerApplication.config_class):
                raise ConfigError(
                    f"app-config builder {type(config).__name__!r}: "
                    "no application claims it"
                )
            if claimed is not None:
                raise ConfigError("duplicate config for the '_server' application")
            claimed = config
        return claimed if claimed is not None else ServerApplication.config_class()

    @property
    def logger(self) -> logging.Logger:
        """This handler's instance logger."""
        return self._logger

    def materialize(self, role: str = "root", app: str | None = None) -> AsgiServer:
        """Build a fresh ``AsgiServer`` from the (config, role) projection (D15).

        Computes the role's ``Projection`` of the built section tree, maps each
        visible section to its constructor kwarg, instantiates ``AsgiServer``
        and mounts the secondary apps. The hosted roles (``worker``/``batch``)
        name their application with ``app=<code>``. Sections with no core-1a
        applier are read and skipped with a debug log.
        """
        projection = Projection(self.builder.source, role=role, app=app)
        self.logger.debug("materializing role %r app %r", role, app)
        kwargs: dict[str, Any] = {}

        server_attrs = projection.server_attrs()
        if "host" in server_attrs:
            kwargs["host"] = server_attrs["host"]
        if "port" in server_attrs:
            kwargs["port"] = server_attrs["port"]
        if "max_threads" in server_attrs:
            kwargs["max_threads"] = server_attrs["max_threads"]
        if "storage_key" in server_attrs:
            kwargs["storage_key"] = server_attrs["storage_key"]

        self._apply_session(projection, kwargs)
        self._apply_server_app_config(projection, kwargs)

        middleware = projection.middleware_config()
        if middleware is not None:
            kwargs["middleware"] = middleware

        auth = projection.auth_config()
        if auth is not None:
            kwargs["auth"] = auth

        storage = projection.storage_config()
        if storage is not None:
            kwargs["storage"] = storage

        plugins = projection.plugins_config()
        if plugins is not None:
            kwargs["plugins"] = plugins

        primary, secondaries = self._build_applications(projection)
        kwargs["primary"] = primary

        if projection.section("openapi") is not None:
            self.logger.debug("config section 'openapi' has no core-1a applier; skipped")

        server = AsgiServer(**kwargs)
        for secondary in secondaries:
            server.mount(secondary)
        self._build_databases(projection, server)
        return server

    def _apply_session(self, projection: Projection, kwargs: dict[str, Any]) -> None:
        """Lift the ``server`` section's ``session`` child to ``session_ttl``.

        ``session`` is server-domain (sessions live on the server), so its
        ``ttl`` attribute becomes the ``session_ttl`` server kwarg. Absent for
        hosted roles (they never see ``server``).
        """
        node = projection.session_node()
        if node is None:
            return
        kwargs["session_ttl"] = dict(node.fixed_attr_items())["ttl"]

    def _apply_server_app_config(
        self, projection: Projection, kwargs: dict[str, Any]
    ) -> None:
        """Lift the ``_server`` config-class values to the server kwargs.

        Walks the claimed config builder's source (the base default is empty —
        nothing lifts): ``admin_password`` is a ``^pointer`` node value (a
        literal is a boot error — secrets stay out of recipes; resolved-empty
        is a boot error via ``resolve_pointers``), ``users``/``tokens`` are
        ``{mount, prefix}`` store descriptors. All three become the identity
        kwargs ``AuthMixin`` peels: the stores live on the server (Phase 3),
        so the VALUES lift while the config keeps the app's shape. Root-only:
        the identity surface belongs to the public process (D6). A repeated
        tag is a boot error (D16 strictness — a silently winning last node
        is never acceptable for identity config).
        """
        if projection.role != "root":
            return
        config = self.server_app_config
        seen: set[str] = set()
        for node in config.source:
            if node.node_tag in seen:
                raise ConfigError(
                    f"duplicate '{node.node_tag}' in the '_server' configuration"
                )
            seen.add(node.node_tag)
            if node.node_tag == "admin_password":
                raw = node.value
                if not (isinstance(raw, str) and raw.startswith("^")):
                    raise ConfigError(
                        "'_server' admin_password must be a ^pointer, not a literal"
                    )
                value, _attrs = resolve_pointers(config, node)
                kwargs["admin_password"] = value
            else:
                kwargs[node.node_tag] = dict(node.fixed_attr_items())

    def _build_databases(self, projection: Projection, server: AsgiServer) -> None:
        """Materialize the ``databases`` section: build and register each handler.

        Per D15 letter, each ``database`` entry becomes
        ``db_handler_class(db_class(**params))``, registered on ``server`` by
        its ``code``. The ``db_class`` is user-provided (imported in the
        recipe) — the core never imports db drivers.
        """
        for code, attrs in projection.databases_config().items():
            db_class = attrs["db_class"]
            db_handler_class = attrs["db_handler_class"] or AsgiDbHandlerBase
            handler = db_handler_class(db_class(**attrs["params"]))
            server.add_database(code, handler)

    def _build_applications(
        self, projection: Projection
    ) -> tuple[BaseApplication, list[BaseApplication]]:
        """Instantiate the projection's application cut: primary + secondary mounts.

        WHICH nodes the role sees (the primary, the secondaries if any) is the
        projection's call (``Projection.applications``); this method only
        instantiates them. A secondary's mount defaults to its ``code``.
        """
        primary_node, secondary_nodes = projection.applications()
        primary = self._instantiate_app(primary_node, mount_name="")
        secondaries: list[BaseApplication] = []
        for node in secondary_nodes:
            attrs = dict(node.fixed_attr_items())
            mount = attrs.get("mount") or attrs.get("code") or ""
            secondaries.append(self._instantiate_app(node, mount_name=str(mount)))
        return primary, secondaries

    def _instantiate_app(self, node: Any, mount_name: str) -> BaseApplication:
        """Instantiate one application node as ``app_class(mount_name=..., **kwargs)``.

        ``code``/``app_class``/``mount`` are consumed here; the remaining
        attributes are the app's constructor kwargs. ``app_class`` presence is
        guaranteed by the grammar (the ``application`` element declares it
        required), so it is popped unconditionally. Any nested section (e.g.
        ``groups``, or the RESERVED opaque ``configuration``) has no core-1a
        applier and is skipped with a debug log.
        """
        attrs = dict(node.fixed_attr_items())
        app_class: type[BaseApplication] = attrs.pop("app_class")
        attrs.pop("code", None)
        attrs.pop("mount", None)
        children = node.value
        if children is not None and hasattr(children, "nodes"):
            for child in children:
                self.logger.debug(
                    "application %r section %r has no core-1a applier; skipped",
                    mount_name or "/",
                    child.node_tag,
                )
        return app_class(mount_name=mount_name, **attrs)


if __name__ == "__main__":
    from .builder import AsgiConfigBuilder

    class _Recipe(AsgiConfigBuilder):
        def main(self, root: Any) -> None:
            root.server(host="127.0.0.1", port=8000)
            root.middleware(cors=True)
            apps = root.applications(default="shop")
            apps.application(code="shop", app_class=BaseApplication)

    handler = ConfigurationHandler(_Recipe(name="config"))
    built = handler.materialize()
    assert isinstance(built, AsgiServer)
    assert built.config_port == 8000
    assert built.primary.mount_name == ""

    worker = handler.materialize(role="worker", app="shop")
    assert isinstance(worker, AsgiServer)
    assert worker.config_port is None
    assert worker.authenticate({"headers": []}) is None
