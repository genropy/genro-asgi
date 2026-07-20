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

"""AsgiConfigElements — grammar for the ``asgiconfig`` dialect (D15).

The config recipe describes the WHOLE site (D15), even where core 1a does not
materialize every section. Each ``@element`` is a top-level section built
directly on the recipe root (``root.server(...)``, ``root.applications(...)``);
there is no enclosing ``config`` node. A section's kwargs become the node's
attributes (read back by ``ConfigurationHandler.materialize`` via
``node.node_tag`` / ``node.fixed_attr_items()``).

Sections and their 1a fate:

- ``server`` — runtime options (``host``, ``port``, ``max_threads``). ``host``/
  ``port`` feed ``AsgiServer.serve``; ``max_threads`` has no 1a applier and is
  skipped (BaseServer, frozen in Macro 1, builds its pool without it).
- ``middleware`` — one ``{name: bool | dict}`` switch per middleware.
- ``auth`` — the credential config (``basic``/``bearer``/``jwt`` kwargs) handed
  verbatim to ``AuthCore`` via the ``auth=`` server kwarg.
- ``applications``/``application`` — the app collection keyed by ``code``; the
  optional ``default`` names the primary (served on ``/``). Each app derives
  its mount from ``code`` unless it declares ``mount``.
- ``groups``/``group`` — grammar only (orchestration package).
- ``databases``/``database`` — grammar only (core 1b).
- ``openapi`` — grammar only (core 1c).

A recipe subclasses ``AsgiConfigBuilder`` and overrides ``main(self, root)``;
application classes are imported by the recipe and passed as objects::

    from myshop.app import Application as Shop

    def main(self, root):
        root.server(host="127.0.0.1", port=8000)
        root.middleware(cors=True)
        apps = root.applications(default="shop")
        apps.application(code="shop", app_class=Shop)
"""

from __future__ import annotations

from genro_builders.builder import element


class AsgiConfigElements:
    """Element mixin for the ``asgiconfig`` dialect. Grammar only.

    The sections are top-level elements built directly on the recipe root;
    a section's kwargs are stored as the node's attributes and read back at
    materialization time.
    """

    @element(sub_tags="")
    def server(self) -> None:
        """Server runtime options: ``host``, ``port``, ``max_threads``.

        ``host``/``port`` become the defaults of ``AsgiServer.serve``.
        ``max_threads`` is declared but has no core-1a applier (the frozen
        Macro 1 ``BaseServer`` sizes its pool without a kwarg): it is read
        and skipped, valid config for a later macro.
        """

    @element(sub_tags="")
    def middleware(self) -> None:
        """Global middleware switches: one ``{name: bool | dict}`` kwarg per
        middleware. A dict value enables the middleware and becomes its
        constructor options."""

    @element(sub_tags="")
    def auth(self) -> None:
        """Credential config: ``basic``/``bearer``/``jwt`` kwargs handed
        verbatim to ``AuthCore`` through the server's ``auth=`` kwarg."""

    @element(sub_tags="application", collection_key="code")
    def applications(self) -> None:
        """Collection of applications, each keyed by its ``code``. The optional
        ``default`` attribute names the app served as the primary (mount
        ``/``)."""

    @element(sub_tags="*", parent_tags="applications")
    def application(self) -> None:
        """One application: ``code`` (the collection key), optional ``mount``,
        ``app_class`` (the imported class) plus its constructor kwargs. ``mount``
        defaults to ``code`` for a secondary; the ``default`` app is the primary
        (mount ``/``). Children are unconstrained (``sub_tags="*"``): the core
        reads only the app's own attributes and delegates the rest."""

    @element(sub_tags="group", collection_key="code", parent_tags="application")
    def groups(self) -> None:
        """Collection of worker groups for a multi-worker application, keyed by
        ``code``. Grammar only in core 1a — materialized by the orchestration
        package; read and skipped here."""

    @element(sub_tags="", parent_tags="groups")
    def group(self) -> None:
        """One worker group: ``code`` (the collection key), ``workers`` (the
        pool size) and optional ``python`` (the interpreter). Grammar only in
        core 1a."""

    @element(sub_tags="database", collection_key="code")
    def databases(self) -> None:
        """Collection of database descriptors, each keyed by ``code``. Grammar
        only in core 1a — the server-side handlers arrive in core 1b; read and
        skipped here."""

    @element(sub_tags="", parent_tags="databases")
    def database(self) -> None:
        """One database: ``code`` (the registry key), ``db_class`` and its
        connection kwargs. Grammar only in core 1a."""

    @element(sub_tags="")
    def openapi(self) -> None:
        """OpenAPI metadata: ``title``, ``version``, ``description``. Grammar
        only in core 1a — the OpenAPI application arrives in core 1c; read and
        skipped here."""


if __name__ == "__main__":
    from typing import Any

    from genro_builders.builder import BuilderBase, BuilderHandler

    class _Demo(BuilderBase, AsgiConfigElements):
        def main(self, root: Any) -> None:
            root.server(host="127.0.0.1", port=8000)
            apps = root.applications(default="shop")
            apps.application(code="shop", app_class=object)

    demo = _Demo(name="config")
    BuilderHandler().add_builder(demo)
    tags = [node.node_tag for node in demo.source]
    assert tags == ["server", "applications"], tags
