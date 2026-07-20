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
  ``storage_key`` (the ``StorageMixin`` encryption key).
- ``middleware`` → ``middleware=`` ({name: bool | dict} switches).
- ``auth`` → ``auth=`` (the ``AuthCore`` config, handed verbatim).
- ``storage`` → ``storage=`` ({code: {path, encrypted}} mounts for the
  ``StorageMixin``); visible to every role.
- ``applications`` → ``primary=`` (the ``default`` app, mount ``/``) plus the
  secondary mounts (each mounted after construction; mount defaults to ``code``).
- ``databases`` → one ``db_handler_class(db_class(**params))`` per entry,
  registered on the server by ``code`` (core 1b).
- ``openapi``/nested ``groups`` → read and SKIPPED with a debug log (valid
  config for other roles/macros, not an error).

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
from ..asgi_server import AsgiServer
from ..db import AsgiDbHandlerBase
from .projection import Projection

__all__ = ["ConfigurationHandler"]


class ConfigurationHandler(BuilderHandler):
    """Owns the ``AsgiConfigBuilder`` recipe and materializes an ``AsgiServer``."""

    def __init__(self, builder: Any) -> None:
        super().__init__()
        self._builder = builder
        self._logger = logging.getLogger(f"{__name__}.{type(self).__name__}")
        self.add_builder(builder)

    @property
    def builder(self) -> Any:
        """The mounted configuration builder (its recipe already run)."""
        return self._builder

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

        middleware = projection.middleware_config()
        if middleware is not None:
            kwargs["middleware"] = middleware

        auth = projection.auth_config()
        if auth is not None:
            kwargs["auth"] = auth

        storage = projection.storage_config()
        if storage is not None:
            kwargs["storage"] = storage

        primary, secondaries = self._build_applications(projection)
        kwargs["primary"] = primary

        if projection.section("openapi") is not None:
            self.logger.debug("config section 'openapi' has no core-1a applier; skipped")

        server = AsgiServer(**kwargs)
        for secondary in secondaries:
            server.mount(secondary)
        self._build_databases(projection, server)
        return server

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
        attributes are the app's constructor kwargs. Any nested section (e.g.
        ``groups``) has no core-1a applier and is skipped with a debug log.
        """
        attrs = dict(node.fixed_attr_items())
        app_class: type[BaseApplication] | None = attrs.pop("app_class", None)
        if app_class is None:
            raise ValueError(f"application {attrs.get('code')!r} missing app_class")
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
