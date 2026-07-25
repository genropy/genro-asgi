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

"""ServerApplication: the automatic ``_server`` system app (D4).

``ServerApplication`` is the server's own application — the system surface
every server exposes under ``/_server`` without configuring it (D4:
"automatic, not configured"). ``AsgiServer`` mounts one at the end of its
``__init__`` (``_register_server_app``), so a hand-built
``AsgiServer(applications=[...])`` gets it exactly like a config-materialized one;
``ConfigurationHandler.materialize`` never special-cases it. The demux finds
it through the ordinary mount table — there is no dedicated demux logic.

It extends ``OpenApiApplication`` (REST + OpenAPI; the MCP face on
``_server`` is out of this wave), so ``/_server/_meta/`` carries the usual
schema/docs/index endpoints, and adds:

- ``index`` — the ``/_server/`` descriptor: title and the attached section
  names (JSON — no HTML in code);
- ``sections`` / ``attach_section(section, name)`` — the registry of system
  sections: ``attach_section`` links a ``RoutingClass`` under ``name``
  (endpoints at ``/_server/<name>/...``) and records it so introspection
  surfaces (the index today, monitors later) can enumerate them;
- the PASSWORD login surface (core 1d wave 1): ``login`` (JSON POST →
  ``UserStore.verify`` → ``Avatar`` → ``request.session.attach_avatar``),
  ``login_page`` (HTML GET, the descriptor-driven ``resources/login.html``
  read at USE time), ``logout`` and the public ``login_methods`` — dual-mode
  by TWO routes, never in-handler ``Accept`` sniffing. The methods live in an
  ``AuthSection`` attached under ``auth`` (``ensure_auth_section`` /
  ``register_auth_method``); ``PasswordMethod`` is registered at construction.
  ``login`` enforces the store-backed lockout (REVIEW #9): the per-identity
  failure counter (``failed_attempts``/``last_failed_at``) rides the UserStore
  record with exponential backoff; the policy comes from the config's
  ``login()`` element (``login_policy``, defaults 5 attempts / 30s base).

Handlers stay PURE: they return values and never touch cookies or an ambient
request/response (the old ``self.server.request`` idiom must never be
reintroduced). Login attaches the avatar to the existing session in place —
the id never changes, so no login-time cookie exists. A handler that needs the
live request DECLARES an UNANNOTATED ``_request`` parameter: ``bind_kwargs``
injects the per-dispatch ``Request`` for that name — the same declarative
convention ``body_data`` follows — and the handler reaches the server through
``_request.server``. Leaving it unannotated keeps it out of the pydantic model
(and thus the public OpenAPI schema); the pydantic wrapper, seeing no type hint,
passes it straight through instead of routing it into validation. The ``_``
prefix is the injected-name convention ``bind_kwargs`` matches in the neutral
``fields`` block. ``pydantic`` and ``openapi`` are fixed server structure (armed
on every router by ``PluginMixin``), so the handler signatures are always
captured and per-entry OpenAPI controls (``openapi_method``) always take effect.

The future internal server (a D8 orchestration concern) is a SUBCLASS that
overrides what it needs — not a profile flag on this class: no code exists for
a consumer that does not exist yet.

Identity: ``code`` and ``mount`` are both declared ``"_server"`` as class
attributes — the system mount is a D4 invariant, and three cross-file
references hardcode ``/_server/...`` (``PasswordMethod``'s ``action``,
``LOGIN_PAGE_URL``, ``login.html``'s fetch), so moving this app elsewhere
404s them.

Kwargs peeled by the cooperative ``__init__`` (D16): ``login`` and ``oidc``
are the values the config-class lift carries (the ``server_app=`` server kwarg,
forwarded by ``_register_server_app``): the lockout policy dict and the
per-``code`` OIDC provider dicts, stored as ``login_policy``/``oidc_providers``
(consumed by the lockout check and the ``OidcMethod`` registration). The rest
flows down the chain. A hand-built ``AsgiServer(applications=[...])`` passes
nothing, so the defaults (empty dicts) keep today's bare app.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, ClassVar

from genro_builders.builder import BuilderBase, element
from genro_routes import RoutingClass, route

from ..auth import AuthMethod, OidcMethod, PasswordMethod
from ..session import Avatar
from .openapi import RESOURCES_DIR, OpenApiApplication
from .server_sections import AuthSection, TasksSection, TokensSection, UsersSection

if TYPE_CHECKING:
    from genro_routes import RouterNode

    from ..request import Request

__all__ = ["ServerAppConfig", "ServerAppConfigElements", "ServerApplication"]

LOCKOUT_MAX_ATTEMPTS = 5
LOCKOUT_BACKOFF_SECONDS = 30.0


class ServerAppConfigElements:
    """Config grammar of ``ServerApplication`` — the dialect of its config-class.

    NOT composed into the site dialect: an application's configuration is a
    SEPARATE builder (distributed config), and ``_server``'s is the one the
    core knows how to mount by construction. Declares the identity surface:
    ``admin_password`` (a ``^pointer`` node value) plus ``users()``/``tokens()``
    store descriptors. All three are LIFTED to the SERVER constructor kwargs
    (``AuthMixin`` peels them): the stores live on the server (Phase 3) — the
    config keeps the app's shape, the runtime stays where it is. The login
    surface (``login()`` policy, ``oidc()`` providers) lifts as the single
    ``server_app=`` server kwarg instead: those values belong to THIS app,
    which peels them when ``AsgiServer`` forwards them at mount time.
    """

    @element(sub_tags="")
    def admin_password(self) -> None:
        """The SUPERADMIN bootstrap password as a ``^pointer`` node value —
        never a literal (secrets stay out of recipes). Resolved at materialize
        time; configured-but-empty is a boot error."""

    @element(sub_tags="")
    def users(self) -> None:
        """Identity store descriptor: ``{mount, prefix}`` (or omitted for the
        default) — the ``users=`` kwarg ``AuthMixin`` peels."""

    @element(sub_tags="")
    def tokens(self) -> None:
        """Api-key store descriptor: ``{mount, prefix}`` — the ``tokens=`` kwarg
        ``AuthMixin`` peels."""

    @element(sub_tags="")
    def login(self) -> None:
        """Login-surface policy: lockout tuning (``max_attempts``, ``backoff``)
        — the ``login=`` kwarg ``ServerApplication`` peels (``server_app`` lift)."""

    @element(sub_tags="")
    def oidc(self) -> None:
        """One OIDC provider (repeatable, keyed by ``code``): ``issuer``,
        ``client_id``, ``client_secret`` (a ``^pointer``, optional — public
        client), ``scopes``, ``identity_claim``, ``tags`` — folded into the
        ``oidc=`` kwarg ``ServerApplication`` peels (``server_app`` lift)."""


class ServerAppConfig(BuilderBase, ServerAppConfigElements):
    """The ``_server`` app's config-class: the base IS the default.

    ``main()`` declares nothing, so materializing the base yields today's bare
    ``ServerApplication()`` — no configuration, no regression. A site
    personalizes ``_server`` by subclassing this in its ``config.py`` and
    passing the subclass to ``ConfigurationHandler`` alongside the site
    recipe; the handler claims it by class identity
    (``ServerApplication.config_class``), no name registry.
    """

    _name = "server_app"

    def main(self, root: Any) -> None:
        """Default ``_server`` configuration: nothing to declare."""


class ServerApplication(OpenApiApplication):
    """System endpoints of a server, auto-mounted under ``/_server`` (D4).

    Carries the public server's system surface: the password login surface and
    the sections attached through ``attach_section``, listed by the ``index``
    descriptor. The future internal server (a D8 orchestration concern) will be
    a SUBCLASS overriding what it needs — not a profile flag on this class.
    """

    openapi_info: ClassVar[dict[str, Any]] = {
        "title": "genro-asgi server endpoints",
        "version": "1.0.0",
    }
    config_class = ServerAppConfig
    code = "_server"
    mount = "_server"

    def __init__(self, **kwargs: Any) -> None:
        self._login_policy: dict[str, Any] = kwargs.pop("login", {})
        self._oidc_providers: dict[str, dict[str, Any]] = kwargs.pop("oidc", {})
        self._sections: dict[str, RoutingClass] = {}
        self._auth_section: AuthSection | None = None
        super().__init__(**kwargs)
        self.register_auth_method(PasswordMethod(self, "password"))
        for code, provider in self.oidc_providers.items():
            method_id = self._oidc_method_id(code)
            self.register_auth_method(OidcMethod(self, method_id, code, provider))
        self.attach_section(UsersSection(self), name="users")
        self.attach_section(TokensSection(self), name="tokens")
        self.attach_section(TasksSection(self), name="tasks")

    @staticmethod
    def _oidc_method_id(code: str) -> str:
        """The mount name of the OIDC method for ``code`` under ``_server/auth``.

        The colon form is legal on the router and through the server demux (a
        boot-time verification): if a future router rejected it, the fallback is
        the single-line change ``f"oidc_{code}"``.
        """
        return f"oidc:{code}"

    @property
    def login_policy(self) -> dict[str, Any]:
        """The lockout policy from the config's ``login()`` element (may be empty)."""
        return self._login_policy

    @property
    def oidc_providers(self) -> dict[str, dict[str, Any]]:
        """OIDC provider configs from the ``oidc()`` elements, keyed by code."""
        return self._oidc_providers

    @property
    def sections(self) -> dict[str, RoutingClass]:
        """Attached system sections keyed by their mount segment (may be empty)."""
        return self._sections

    @property
    def auth_section(self) -> AuthSection | None:
        """The ``auth`` section carrying the login methods, or ``None``."""
        return self._auth_section

    def attach_section(self, section: RoutingClass, name: str) -> None:
        """Attach ``section`` under ``name`` and record it in ``sections``.

        Links the section's router into this app (endpoints at
        ``/_server/<name>/...``) and keeps it enumerable for the
        introspection surfaces (the ``index`` descriptor today).
        """
        self.route.add_branches({"name": name, "instance": section})
        self.sections[name] = section

    def ensure_auth_section(self) -> AuthSection:
        """The ``auth`` section, attached under ``auth`` on first use."""
        if self._auth_section is None:
            section = AuthSection(self)
            self.attach_section(section, name="auth")
            self._auth_section = section
        return self._auth_section

    def register_auth_method(self, method: AuthMethod) -> None:
        """Register a login method in the ``auth`` section (created on demand)."""
        self.ensure_auth_section().register(method)

    def bind_kwargs(self, node: RouterNode, request: Request) -> dict[str, Any]:
        """Inject the live ``Request`` into handlers that declare ``_request``.

        Extends the base reconciliation with the declarative seam the login
        surface needs: when the node's neutral ``params`` block declares a
        ``_request`` parameter, the per-dispatch ``Request`` is bound to it
        (overriding any same-named wire value). Handlers leave ``_request``
        unannotated so it stays out of the pydantic model — and therefore out of
        the public OpenAPI schema — while still being visible in the neutral
        ``fields`` this method reads. No ambient state — the request travels as
        an ordinary argument, exactly like ``body_data``.
        """
        kwargs = super().bind_kwargs(node, request)
        fields = node.params.get("fields") or []
        if any(f["name"] == "_request" for f in fields):
            kwargs["_request"] = request
        return kwargs

    def _lock_seconds_remaining(self, record: dict[str, Any]) -> float:
        """Seconds left in ``record``'s lockout window, ``0.0`` when not locked.

        The window opens after ``max_attempts`` consecutive failures and lasts
        ``backoff * 2**(failed_attempts - max_attempts)`` seconds from the last
        failure — exponential backoff, tuned by the config's ``login()`` policy
        (``login_policy``; defaults 5 attempts / 30s base).
        """
        policy = self.login_policy
        failed = record.get("failed_attempts", 0)
        max_attempts = policy.get("max_attempts", LOCKOUT_MAX_ATTEMPTS)
        if failed < max_attempts:
            return 0.0
        backoff = policy.get("backoff", LOCKOUT_BACKOFF_SECONDS)
        window = backoff * 2 ** (failed - max_attempts)
        return max(0.0, record.get("last_failed_at", 0.0) + window - time.time())

    @route()
    def index(self) -> dict[str, Any]:
        """The ``/_server/`` descriptor: title and section names."""
        return {
            "title": self.api_info.get("title", type(self).__name__),
            "sections": sorted(self.sections),
        }

    @route(media_type="application/json", openapi_method="post")
    def login(self, identity: str = "", password: str = "", _request=None) -> dict[str, Any]:
        """Authenticate against the server's UserStore and attach the identity.

        The JSON convergence point of every ``form`` method: verifies the
        credentials (``UserStore.verify`` — the record key is ``identity``),
        builds the ``Avatar`` and attaches it to the request's session in place
        (``_request.session.attach_avatar``) — the session id never changes at
        login, so the client's cookie stays valid and no ``Set-Cookie`` is
        involved. The server's ``user_store`` is wired in the next wave (Macro
        5b): until then a server without one answers the error shape.

        The ``next`` return path is NOT a login parameter: the challenge
        redirects to ``login_page?next=...`` and the page script owns the
        post-success redirect — ``login`` itself never sees it and posts carry
        only the credentials.

        Enforces the server-side lockout (REVIEW #9): the failure counter
        lives ON the user's store record (``failed_attempts`` /
        ``last_failed_at``), so it survives restarts and is shared across
        processes on a shared store. After ``max_attempts`` consecutive
        failures the identity is refused until the exponential-backoff window
        (``_lock_seconds_remaining``) has passed; refused attempts never touch
        the counter — an attacker hammering a locked identity cannot extend a
        legitimate user's lock — and a success resets it. Known-identity
        failures surface the server-computed ``remaining_attempts``; unknown
        identities have no record, hence no counter and no such field. Per-IP
        rate limiting is a future middleware concern, not this handler's.

        The method is POST by declaration (``openapi_method="post"``): with
        ``_request`` hidden from the schema (see below) the remaining fields
        are all scalar, so the guesser would otherwise pick GET.

        Args:
            identity: The record key to verify (NOT the old ``username``).
            password: The password to verify.
            _request: The live ``Request``, injected by ``bind_kwargs``. Left
                unannotated so it stays out of the pydantic model — and thus out
                of the public OpenAPI request body — while the ``_`` prefix is
                the injected-name convention ``bind_kwargs`` matches.

        Returns:
            ``{session_id, identity, tags}`` on success; ``{"error": ...}`` on
            missing/invalid credentials, active lockout, or when no user store
            is wired — with ``remaining_attempts`` when the identity has a
            record.

        Note:
            Route: POST /_server/login
        """
        if not identity or not password:
            return {"error": "Identity and password are required"}
        user_store = getattr(_request.server, "user_store", None)
        if user_store is None:
            return {"error": "Login is not available"}
        record = user_store.get(identity)
        if record is not None and self._lock_seconds_remaining(record) > 0:
            return {"error": "Too many failed attempts"}
        verified = user_store.verify(identity, password)
        if verified is None:
            if record is None:
                return {"error": "Invalid credentials"}
            record["failed_attempts"] = record.get("failed_attempts", 0) + 1
            record["last_failed_at"] = time.time()
            user_store.save(record)
            max_attempts = self.login_policy.get("max_attempts", LOCKOUT_MAX_ATTEMPTS)
            remaining = max(0, max_attempts - record["failed_attempts"])
            return {"error": "Invalid credentials", "remaining_attempts": remaining}
        if verified.get("failed_attempts"):
            verified["failed_attempts"] = 0
            verified["last_failed_at"] = 0.0
            user_store.save(verified)
        avatar = Avatar(verified["identity"], verified["tags"])
        session = _request.session
        session.attach_avatar(avatar)
        return {"session_id": session.id, "identity": avatar.identity, "tags": avatar.tags}

    @route(media_type="text/html")
    def login_page(self, next: str = "") -> str:
        """Serve the descriptor-driven HTML login page (GET, dual-mode twin of ``login``).

        The page builds itself from ``login_methods`` and posts credentials to
        the method's ``action`` (``/_server/login``). Read at USE time so a
        template swap needs no re-import. ``next`` is accepted so the challenge
        redirect's query binds; the page script consumes it client-side.

        Note:
            Route: GET /_server/login_page
        """
        return (RESOURCES_DIR / "login.html").read_text()

    @route(media_type="application/json")
    def logout(self, session_id: str = "") -> dict[str, Any]:
        """Destroy a session.

        Deletes the session from the store. No error if the session is unknown.

        Args:
            session_id: Session token to invalidate.

        Returns:
            ``{"status": "ok"}`` (always succeeds).

        Note:
            Route: POST /_server/logout
        """
        if session_id:
            self.server.session_store.delete(session_id)
        return {"status": "ok"}

    @route(media_type="application/json")
    def login_methods(self) -> dict[str, Any]:
        """Public descriptors of the active auth methods (NO ``auth_rule``).

        The login page builds itself from this: register a method, its
        descriptor (and therefore its button/form) appears. Deliberately public
        — a caller must see the methods before it can authenticate. Empty list
        when no login surface is active.

        Returns:
            ``{"methods": [descriptor, ...]}`` in registration order.

        Note:
            Route: GET /_server/login_methods
        """
        section = self.auth_section
        return {"methods": section.descriptors() if section is not None else []}
