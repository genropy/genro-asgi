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

"""AsgiServerGrammar — the configuration grammar of ``AsgiServer``.

The grammar the server class exposes as ``AsgiServer.grammar``: one
``configuration`` root (the contrib ``ConfigBuilder`` element, OVERRIDDEN here
with the full closed section list) whose sections describe the whole site.
Every section is a singleton (``[0:1]``), so labels are clean and every path is
stable and hand-writable: ``configuration.server``,
``configuration.authentication.oidc.<code>``,
``configuration.applications.<code>``.

Authoring conventions inherited from contrib/config:

- attributes are ANNOTATED, so their signature defaults reach the read stack of
  ``ConfigurationHandler`` (an unannotated parameter never enters
  ``call_args_validations``);
- an attribute whose value may come from outside (env, file, url) is annotated
  ``<type> | BagResolver`` and receives the resolver IN PLACE — there are no
  ``^pointer`` strings in this dialect;
- the recipe orchestrates in ``main`` and delegates each section to a method
  taking the PARENT node.

Sections:

- ``server`` — the runtime options (``host``, ``port``, ``external_url``,
  ``max_threads``) plus the server-domain children ``session``
  (the session TTL) and ``tasks`` (declared by ``TaskGrammar``, the class that
  peels ``tasks=``).
- ``middleware`` — one ``{name: bool | dict}`` switch per middleware.
- ``authentication`` — the whole identity surface: the bootstrap
  ``admin_password``, the ``users``/``tokens`` store descriptors, the ``login``
  lockout policy, the ``oidc`` provider collection and the ``credentials``
  handed to ``AuthCore``.
- ``storage`` — the mount point of genro-storage's own grammar: the mounts of
  the server's ``StorageManager``, plus the section's ``storage_key``.
- ``applications`` — the app collection keyed by ``code``; each entry MOUNTS
  the grammar its ``app_class`` carries.
- ``databases`` — one descriptor per database handler.
- ``plugins`` — the router plugins armed on every routed app.
- ``openapi`` — the OpenAPI metadata (grammar only in core 1a).
- ``commander`` — the SPA pool: the vertex's paths and policies, plus the
  ``groups`` collection, one entry per group of workers.

A recipe subclasses ``AsgiConfigBuilder`` and overrides ``main(self, root)``;
application classes are imported and passed as objects::

    from myshop.app import Application as Shop

    class ServerConfiguration(AsgiConfigBuilder):
        def main(self, root):
            cfg = root.configuration()
            cfg.server(host="127.0.0.1", port=8000)
            cfg.middleware(cors=True)
            cfg.applications(default="shop").application(code="shop", app_class=Shop)
"""

from __future__ import annotations

from typing import Any

from genro_bag import BagResolver
from genro_builders.builder import element

from ..tasks.mixin import TaskGrammar


class AsgiServerGrammar(TaskGrammar):
    """Configuration grammar of ``AsgiServer``: the site layout, reading elsewhere.

    Grammar only — the runtime reads the built tree through
    ``ConfigurationHandler``, never through this class. Capability-owned
    companions are composed explicitly (``TaskGrammar`` — the ``tasks`` child of
    ``server``, owned by ``TaskMixin``).
    """

    @element(
        sub_tags=(
            "server[0:1],middleware[0:1],authentication[0:1],storage[0:1],"
            "applications[0:1],databases[0:1],plugins[0:1],openapi[0:1],"
            "commander[0:1]"
        ),
        node_label="configuration",
    )
    def configuration(self) -> None:
        """Root element of the configuration document (one per recipe).

        Overrides the contrib root with the full section list of this dialect.
        Each section is a singleton, so its label IS its tag and every path
        below it is stable.
        """

    @element(parent_tags="configuration", sub_tags="session[0:1],tasks[0:1]")
    def server(
        self,
        host: str | BagResolver = None,
        port: int | BagResolver = None,
        external_url: str | BagResolver = None,
        max_threads: int | BagResolver = None,
    ) -> None:
        """Server runtime options.

        ``host``/``port`` become the defaults of ``AsgiServer.serve``.

        ``external_url`` is the server's PUBLIC base address — what the server
        calls itself when it hands its own URL to a third party
        (``https://shop.example.com``; a trailing slash is stripped). It is not
        the listener: behind a proxy the bind address and the public address
        differ, and only the latter is meaningful to an outside caller. Required
        when an ``oidc`` provider is configured — the provider is given an
        absolute ``redirect_uri`` — and a boot error when missing there.

        ``max_threads`` sizes the server's thread pool: ``BaseServer`` peels it
        and hands it to ``WorkPool`` (omitted, the stdlib default
        ``min(32, cpu + 4)`` applies).

        Children are server-domain: ``session`` (the session TTL) and ``tasks``
        (the task backbone, declared by ``TaskGrammar``).
        """

    @element(parent_tags="server", sub_tags="")
    def session(self, ttl: int) -> None:
        """Session options: ``ttl`` (seconds, REQUIRED — the grammar rejects a
        session without it) → the server's ``session_ttl`` kwarg. Server-domain,
        so it lives under ``server``, not under an application."""

    @element(parent_tags="configuration", sub_tags="")
    def middleware(
        self,
        errors: bool | dict = None,
        wellknown: bool | dict = None,
        logging: bool | dict = None,
        cors: bool | dict = None,
        auth: bool | dict = None,
        session: bool | dict = None,
    ) -> None:
        """Global middleware switches: one ``{name: bool | dict}`` kwarg per
        middleware. A dict value enables the middleware and becomes its
        constructor options. The names are the core's own registry
        (``middleware.default_registry()``); one registered through
        ``middleware_registry=`` is not configurable here."""

    @element(
        parent_tags="configuration",
        sub_tags=(
            "admin_password[0:1],users[0:1],tokens[0:1],"
            "login[0:1],oidc[0:1],credentials[0:1]"
        ),
        node_label="authentication",
    )
    def authentication(self) -> None:
        """The server's whole identity surface.

        Both the identity STORES (``admin_password``, ``users``, ``tokens`` →
        the kwargs ``AuthMixin`` peels) and the LOGIN surface (``login``,
        ``oidc`` → forwarded to the ``_server`` application) are configured
        here: one section for one subject, whichever object consumes the value.
        """

    @element(parent_tags="authentication", sub_tags="")
    def admin_password(self, node_value: BagResolver = None) -> None:
        """The SUPERADMIN bootstrap password as the NODE VALUE, supplied by a
        resolver — never a literal (secrets stay out of recipes; the signature
        rejects a literal at the recipe line). Resolving empty, or to anything
        but a string, is a boot error."""

    @element(parent_tags="authentication", sub_tags="")
    def users(self, mount: str = None, prefix: str = None) -> None:
        """Identity store descriptor: ``{mount, prefix}`` (or empty for the
        default) — the ``users=`` kwarg ``AuthMixin`` peels."""

    @element(parent_tags="authentication", sub_tags="")
    def tokens(self, mount: str = None, prefix: str = None) -> None:
        """Api-key store descriptor: ``{mount, prefix}`` — the ``tokens=`` kwarg
        ``AuthMixin`` peels."""

    @element(parent_tags="authentication", sub_tags="")
    def login(self, max_attempts: int = None, backoff: float = None) -> None:
        """Login-surface policy: lockout tuning (``max_attempts``, ``backoff``)
        — forwarded to ``ServerApplication``, which peels ``login=``."""

    @element(
        parent_tags="authentication",
        sub_tags="provider",
        collection_key="code",
        node_label="oidc",
    )
    def oidc(self) -> None:
        """Collection of OIDC providers, each labelled by its ``code`` — stable
        paths ``authentication.oidc.<code>``."""

    @element(parent_tags="oidc", sub_tags="")
    def provider(
        self,
        code: str,
        issuer: str = None,
        client_id: str = None,
        client_secret: str | BagResolver = None,
        scopes: str = "openid email profile",
        identity_claim: str = "email",
        tags: str | list = None,
    ) -> None:
        """One OIDC provider: ``code`` (the collection key, REQUIRED),
        ``issuer``, ``client_id``, ``client_secret`` (optional — a public client
        has none; give it a resolver), plus the defaulted ``scopes``,
        ``identity_claim`` and ``tags``."""

    @element(
        parent_tags="authentication",
        sub_tags="basic_user,bearer_token,jwt",
        node_label="credentials",
    )
    def credentials(self) -> None:
        """The header credentials handed to ``AuthCore``.

        Three repeatable children, one per backend. They are NOT a keyed
        collection: the three tags key differently (``username``, ``identity``,
        nothing at all for ``jwt``, which is an ordered list), so the handler
        folds them into ``AuthCore``'s own shapes by reading each child.
        """

    @element(parent_tags="credentials", sub_tags="")
    def basic_user(
        self,
        username: str,
        password: str | BagResolver = None,
        tags: str = None,
    ) -> None:
        """One HTTP Basic user: ``username`` (REQUIRED — the ``AuthCore`` key),
        ``password`` (give it a resolver) and comma-separated ``tags``."""

    @element(parent_tags="credentials", sub_tags="")
    def bearer_token(
        self,
        identity: str,
        token: str | BagResolver = None,
        tags: str = None,
    ) -> None:
        """One static Bearer token: ``identity`` (REQUIRED — the identity the
        token authenticates as), ``token`` (give it a resolver) and
        comma-separated ``tags``."""

    @element(parent_tags="credentials", sub_tags="")
    def jwt(
        self,
        name: str = None,
        secret: str | BagResolver = None,
        public_key: str | BagResolver = None,
        algorithm: str = "HS256",
        tags: str = None,
    ) -> None:
        """One JWT verifier (repeatable, an ORDERED list — the first that
        verifies wins): ``secret`` (shared HMAC material, the only kind that may
        also SIGN) or ``public_key`` (verify only), the ``algorithm``, an
        optional ``name`` and comma-separated ``tags``."""

    @element(parent_tags="configuration", _meta={"subbuilder": "app:grammar"})
    def storage(self, app: type, storage_key: str | BagResolver = None) -> None:
        """The server's storage, and the MOUNT POINT of genro-storage's grammar.

        This dialect declares NO storage vocabulary of its own: ``app``
        (``StorageManager``, REQUIRED — the subbuilder reference reads the call
        site, so it cannot be defaulted in the signature) carries the grammar
        governing this node's children, and the mounts are written in
        genro-storage's own words — one element per protocol, the tag IS the
        protocol. The elements hang DIRECTLY under this node: the envelope is
        transparent to containment, so the foreign ``mounts`` collection is not
        part of the recipe.

        ``storage_key`` is the at-rest key material of the whole section
        (comma-separated Fernet keys — the first encrypts, all decrypt, for
        rotation), and belongs here rather than on ``server`` because it is
        meaningless without the mounts it unlocks. Give it a resolver so the
        secret stays out of the recipe — a resolver, never a lambda, since a
        callback does not serialize::

            from genro_bag.resolvers import EnvResolver
            from genro_storage import StorageManager

            def storage_section(self, cfg):
                s = cfg.storage(app=StorageManager,
                                storage_key=EnvResolver("GENRO_STORAGE_KEY"))
                s.local(name="site", base_path=".")
                s.s3(name="uploads", bucket="shop-media",
                     default_encrypted="shopspa")

        Omitted entirely, the server builds its default manager: the single
        ``site:`` mount on the deployment directory.
        """

    @element(parent_tags="configuration", sub_tags="application", collection_key="code")
    def applications(self, default: str = None) -> None:
        """Collection of applications, each labelled by its ``code``. The
        optional ``default`` names the application ``/`` **redirects to** (307)
        when no application answers the site root; it elects nothing."""

    @element(parent_tags="applications", _meta={"subbuilder": "app_class:grammar"})
    def application(
        self,
        app_class: type,
        code: str = None,
        mount: str = None,
        **app_kwargs: Any,
    ) -> None:
        """One application, and the MOUNT POINT of its own grammar.

        ``app_class`` (the imported class, REQUIRED) carries the grammar
        governing this node's children (``app_class.grammar``, subbuilder by
        reference): the site dialect never validates an app's internal
        vocabulary, the app itself declares it. ``code`` is the collection key,
        ``mount`` the URL prefix (defaulting to ``code``; ``mount=""`` is the
        site root — the one application answering ``/`` and every unclaimed
        path). Remaining kwargs are the app's own constructor kwargs and stay
        open — the envelope's attributes belong to THIS grammar, only its
        children live in the mounted one.
        """

    @element(parent_tags="configuration", sub_tags="database", collection_key="code")
    def databases(self) -> None:
        """Collection of database descriptors, each labelled by its ``code``."""

    @element(parent_tags="databases", sub_tags="")
    def database(
        self,
        db_class: type,
        code: str = None,
        db_handler_class: type = None,
        **params: Any,
    ) -> None:
        """One database: ``code`` (the registry key), ``db_class`` (REQUIRED —
        the grammar rejects a database without it), the optional
        ``db_handler_class`` (``AsgiDbHandlerBase`` when omitted) and the
        connection kwargs handed to ``db_class(**params)``. The ``db_class`` is
        user-provided — the core never imports db drivers."""

    @element(parent_tags="configuration", sub_tags="plugin", collection_key="code")
    def plugins(self) -> None:
        """Collection of router plugins, each labelled by its ``code``.
        Materialized as the server's ``plugins=`` switches (``PluginMixin``):
        the server arms every enabled plugin onto each routed app it hosts."""

    @element(parent_tags="plugins", sub_tags="")
    def plugin(self, code: str = None, enabled: bool = True, **options: Any) -> None:
        """One router plugin: ``code`` (the collection key), optional
        ``enabled`` (set False to leave it unarmed) and arbitrary options handed
        to ``router.plug(code, **options)``."""

    @element(parent_tags="commander", sub_tags="group", collection_key="name")
    def groups(self, default: str = None) -> None:
        """Collection of worker groups, each labelled by its ``name`` — stable paths
        ``commander.groups.<name>``. A group is the workers built from ONE grammar:
        the same child, the same policies.

        The optional ``default`` ELECTS the group that receives whoever arrives
        with no past; omitted, the first group declared is the one. Unlike
        ``applications.default``, which is a redirect destination and elects
        nothing, this one decides where a newcomer is born."""

    @element(parent_tags="groups", sub_tags="")
    def group(
        self,
        name: str = None,
        memory_max_percent: float | BagResolver = None,
        worker_memory_max_percent: float | BagResolver = None,
        occupancy_max_percent: float | BagResolver = None,
        restart_occupancy_max_percent: float | BagResolver = None,
        reception_reserved_percent: float | BagResolver = None,
        new_user_occupancy_percent: float | BagResolver = None,
        newcomer_reserve_count: int | BagResolver = None,
        user_idle_freeze_minutes: float | BagResolver = None,
        entry_module: str = None,
        executable: str | BagResolver = None,
        worker_class: str = None,
        main_threadpool_size: int | BagResolver = None,
        aux_threadpool_size: int | BagResolver = None,
        worker_kwargs: dict = None,
    ) -> None:
        """One group of workers: its own policies, and the identity of its child.

        ``name`` is the collection key and names the group's workers too
        (``<name>_0001``), so it is short — a worker's name is its socket's.

        **Nothing here says how many workers there are.** The group brings its
        reception into being at boot and then grows on demand and shrinks by
        waste, so the count is a reading and never a setting.

        The POLICIES: ``memory_max_percent`` is this group's share of the
        server's concession and ``worker_memory_max_percent`` what ONE worker may
        hold of that share (the same word one rung down — the cascade is machine,
        concession, quota, worker); ``occupancy_max_percent`` is how full a worker
        gets before it stops admitting and ``restart_occupancy_max_percent`` where
        a process is replaced instead of kept; ``reception_reserved_percent`` is
        what the reception keeps free for the trade only it has;
        ``new_user_occupancy_percent`` is what a user nobody has ever measured is
        expected to cost, and ``newcomer_reserve_count`` how many of that size
        must always find room — the group grows at its own round before anybody
        is refused. ``user_idle_freeze_minutes`` is the silence past which a
        worker parks a user in the freezer.

        The IDENTITY of the child: ``entry_module`` (what ``python -m`` runs),
        ``executable`` (the interpreter — a group is how two versions of a site
        live side by side), ``worker_class`` (the ``module:Class`` the child
        loads), the two thread pool sizes, and ``worker_kwargs``, the grammar that
        class is built with. The two paths are the installation's and are declared
        once, on ``commander``.
        """

    @element(parent_tags="configuration", sub_tags="groups[0:1]")
    def commander(
        self,
        frozen_users_path: str | BagResolver = None,
        instance_dir: str | BagResolver = None,
        memory_max_percent: float | BagResolver = None,
        machine_memory_alarm_percent: float | BagResolver = None,
        orchestration_log_path: str | BagResolver = None,
        orchestration_log_max_bytes: int | BagResolver = None,
        orchestration_log_backup_count: int | BagResolver = None,
        user_expiry_hours: float | BagResolver = None,
        guest_expiry_hours: float | BagResolver = None,
    ) -> None:
        """The SPA pool: the vertex's own policies, and the groups under it.

        The two PATHS of the installation, declared once here and shared by every
        group: ``frozen_users_path`` is the freezer root — the vertex reads what a
        worker wrote there, so it is one root for the whole machine — and
        ``instance_dir`` holds the sockets.

        ``memory_max_percent`` is what this server may hold OF THE MACHINE (the
        concession; omitted, all of it), and every percentage below is a share of
        it. ``machine_memory_alarm_percent`` is the health line of the whole
        machine, past which nothing grows. The freezer's own storage answers to no
        key: under a tenth free the log says so and the machine asks for more.

        ``orchestration_log_path`` (+ ``_max_bytes`` / ``_backup_count``) is the
        file every order lands on — who decided, what, on whom, with which numbers
        and how it ended; omitted, the rows stay on the logger.

        ``user_expiry_hours`` / ``guest_expiry_hours`` are the ages a FROZEN user
        is kept for before the machine forgets him whole. A guest is shorter: he
        is a browser, not a person the machine knows.

        Technical times — the beat, the patience of a departure, the cadences —
        are module constants and not grammar: an installation tunes policies, not
        clocks.
        """

    @element(parent_tags="configuration", sub_tags="")
    def openapi(
        self,
        title: str = None,
        version: str = None,
        description: str = None,
    ) -> None:
        """OpenAPI metadata: ``title``, ``version``, ``description``. Grammar
        only in core 1a — the OpenAPI application arrives in core 1c; read and
        skipped here."""
