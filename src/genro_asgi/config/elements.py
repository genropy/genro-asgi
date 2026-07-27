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

- ``server`` — runtime options (``host``, ``port``, ``external_url``,
  ``max_threads``, ``storage_key``). ``host``/``port`` feed
  ``AsgiServer.serve``; ``external_url`` is the server's public base address
  (the OIDC ``redirect_uri`` prefix); ``max_threads`` sizes the server's thread
  pool (peeled by ``BaseServer``, handed to ``WorkPool``); ``storage_key``
  installs at-rest encryption on the server's storage (core 1b).
- ``middleware`` — one ``{name: bool | dict}`` switch per middleware.
- ``storage`` — mounts of the server's ``LocalStorage`` (core 1b); visible to
  every role (survival infrastructure).
- ``auth`` — the credential config (``basic``/``bearer``/``jwt`` kwargs) handed
  verbatim to ``AuthCore`` via the ``auth=`` server kwarg.
- ``applications``/``application`` — the app collection keyed by ``code``; the
  optional ``default`` names the target of the 307 from ``/``. Each app
  derives its mount from ``code`` unless it declares ``mount``, and
  ``mount=""`` is the site root.
- ``groups``/``group`` — grammar only (orchestration package).
- ``databases``/``database`` — grammar only (core 1b).
- ``plugins``/``plugin`` — router plugins armed onto every routed app
  (``PluginMixin``); visible to every role (a worker needs the same router
  behavior).
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

from typing import Any

from genro_builders.builder import element

from ..tasks.mixin import TaskConfigElements


class AsgiConfigElements(TaskConfigElements):
    """Element mixin for the ``asgiconfig`` dialect. Grammar only.

    The sections are top-level elements built directly on the recipe root;
    a section's kwargs are stored as the node's attributes and read back at
    materialization time. Capability-owned companions are composed explicitly
    (``TaskConfigElements`` — the ``tasks`` child of ``server``, owned by
    ``TaskMixin``).
    """

    @element(sub_tags="session,tasks")
    def server(
        self,
        host: str | None = None,
        port: int | None = None,
        external_url: str | None = None,
        max_threads: int | None = None,
        storage_key: str | None = None,
    ) -> None:
        """Server runtime options: ``host``, ``port``, ``external_url``,
        ``max_threads``, ``storage_key``.

        ``host``/``port`` become the defaults of ``AsgiServer.serve``.

        ``external_url`` (str, optional) is the server's PUBLIC base address —
        what the server calls itself when it hands its own URL to a third party
        (``https://shop.example.com``; a trailing slash is stripped). It is not
        the listener: behind a proxy the bind address and the public address
        differ, and only the latter is meaningful to an outside caller. Required
        when an ``oidc()`` provider is configured — the provider is given an
        absolute ``redirect_uri`` — and a boot error when missing there.

        ``max_threads`` sizes the server's thread pool: ``BaseServer`` peels
        it and hands it to ``WorkPool`` (omitted, the stdlib default
        ``min(32, cpu + 4)`` applies).

        ``storage_key`` (str, optional) installs at-rest encryption on the
        server's storage (comma-separated Fernet keys — first encrypts, all
        decrypt for rotation). Pass the secret as a ``^pointer`` to an
        ``EnvResolver`` so it stays out of the recipe, never a literal::

            def setup(self, data):
                data["storage_key"] = EnvResolver("GENRO_STORAGE_KEY")

            def main(self, root):
                root.server(host="127.0.0.1", port=8000, storage_key="^storage_key")

        Configured but resolved empty is an explicit boot error (no silent
        degradation); omit it to run the encrypted mounts dormant.

        Children (server-domain, each materialized to a server kwarg):
        ``session`` (the session TTL) and ``tasks`` (the task backbone —
        declared by ``TaskConfigElements``, the ``config_grammar`` companion
        ``TaskMixin`` owns). The ``_server`` app's identity surface is NOT
        configured here — it has its own config-class (``ServerAppConfig``,
        see ``applications/server_app.py``) passed to the handler alongside
        the site recipe.
        """

    @element(sub_tags="", parent_tags="server")
    def session(self, ttl: int) -> None:
        """Session options: ``ttl`` (seconds, REQUIRED — the grammar rejects a
        session without it) → the server's ``session_ttl`` kwarg (the default
        store's TTL). Server-domain, so it lives under ``server``, not under an
        application."""

    @element(sub_tags="")
    def middleware(
        self,
        errors: bool | dict | None = None,
        wellknown: bool | dict | None = None,
        logging: bool | dict | None = None,
        cors: bool | dict | None = None,
        auth: bool | dict | None = None,
        session: bool | dict | None = None,
    ) -> None:
        """Global middleware switches: one ``{name: bool | dict}`` kwarg per
        middleware. A dict value enables the middleware and becomes its
        constructor options. The names are the core's own registry
        (``middleware.default_registry()``); one registered through
        ``middleware_registry=`` is not configurable here."""

    @element(sub_tags="")
    def auth(
        self,
        basic: bool | dict | None = None,
        bearer: bool | dict | None = None,
        jwt: bool | dict | None = None,
    ) -> None:
        """Credential config: ``basic``/``bearer``/``jwt`` kwargs handed
        verbatim to ``AuthCore`` through the server's ``auth=`` kwarg."""

    @element(sub_tags="mount", collection_key="code")
    def storage(self) -> None:
        """Collection of storage mounts, each keyed by ``code``. Materialized in
        core 1b as the server's ``LocalStorage`` (one ``add_mount`` per child).
        Visible to EVERY role (survival infrastructure — the spool lives on
        it), unlike ``middleware``/``auth`` which stay root-only."""

    @element(sub_tags="", parent_tags="storage")
    def mount(self, path: str, code: str | None = None, encrypted: bool = False) -> None:
        """One storage mount: ``code`` (the collection key), ``path`` (the
        filesystem path, relative to the server base dir unless absolute,
        REQUIRED — the grammar rejects a mount without it) and optional
        ``encrypted`` (bool, default False — encrypt at rest, which requires
        the server's ``storage_key``)."""

    @element(sub_tags="application", collection_key="code")
    def applications(self, default: str | None = None) -> None:
        """Collection of applications, each keyed by its ``code``. The optional
        ``default`` attribute names the application ``/`` **redirects to** (307)
        when no application answers the site root; it elects nothing."""

    @element(sub_tags="*", parent_tags="applications")
    def application(
        self,
        app_class: type,
        code: str | None = None,
        mount: str | None = None,
        **app_kwargs: Any,
    ) -> None:
        """One application: ``code`` (the collection key), ``app_class`` (the
        imported class, REQUIRED — the grammar rejects an application without
        it), optional ``mount`` plus the app's constructor kwargs. ``mount`` is
        the URL prefix and defaults to ``code``; ``mount=""`` is the site root —
        the one application answering ``/`` and every unclaimed path. Children
        are unconstrained (``sub_tags="*"``): the core reads only the app's own
        attributes and delegates the rest."""

    @element(sub_tags="*", parent_tags="application")
    def configuration(self, **options: Any) -> None:
        """The application's own configuration (RESERVED tag): opaque to the
        core, which reads and skips it — the site dialect never validates an
        app's internal grammar (distributed configuration). Today it carries
        free attributes; the machinery that fills and mounts its subtree with
        the app's own dialect is a future macro."""

    @element(sub_tags="group", collection_key="code", parent_tags="application")
    def groups(self, default: str | None = None) -> None:
        """Collection of worker groups for a multi-worker application, keyed by
        ``code``; the optional ``default`` names the group used when none is
        asked for. Grammar only in core 1a — materialized by the orchestration
        package; read and skipped here."""

    @element(sub_tags="", parent_tags="groups")
    def group(
        self,
        code: str | None = None,
        workers: int | None = None,
        python: str | None = None,
    ) -> None:
        """One worker group: ``code`` (the collection key), ``workers`` (the
        pool size) and optional ``python`` (the interpreter). Grammar only in
        core 1a."""

    @element(sub_tags="database", collection_key="code")
    def databases(self) -> None:
        """Collection of database descriptors, each keyed by ``code``. Grammar
        only in core 1a — the server-side handlers arrive in core 1b; read and
        skipped here."""

    @element(sub_tags="", parent_tags="databases")
    def database(
        self,
        db_class: type,
        code: str | None = None,
        db_handler_class: type | None = None,
        **params: Any,
    ) -> None:
        """One database: ``code`` (the registry key), ``db_class`` (REQUIRED —
        the grammar rejects a database without it) and its connection kwargs.
        Grammar only in core 1a."""

    @element(sub_tags="plugin", collection_key="code")
    def plugins(self) -> None:
        """Collection of router plugins, each keyed by ``code``. Materialized as
        the server's ``plugins=`` switches (``PluginMixin``): the server arms
        every enabled plugin onto each routed app it hosts. Visible to EVERY
        role — a worker hosting an app needs the same router behavior."""

    @element(sub_tags="", parent_tags="plugins")
    def plugin(self, code: str | None = None, enabled: bool = True, **options: Any) -> None:
        """One router plugin: ``code`` (the collection key), optional
        ``enabled`` (bool, default True — set False to leave it unarmed) and
        arbitrary options handed to ``router.plug(code, **options)``."""

    @element(sub_tags="")
    def openapi(
        self,
        title: str | None = None,
        version: str | None = None,
        description: str | None = None,
    ) -> None:
        """OpenAPI metadata: ``title``, ``version``, ``description``. Grammar
        only in core 1a — the OpenAPI application arrives in core 1c; read and
        skipped here."""
