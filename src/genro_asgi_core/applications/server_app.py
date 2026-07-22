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
``__init__`` (``_mount_server_app``), so a hand-built
``AsgiServer(primary=...)`` gets it exactly like a config-materialized one;
``ConfigurationHandler.materialize`` never special-cases it. The demux finds
it through the ordinary mount table — there is no dedicated demux logic.

It extends ``OpenApiApplication`` (REST + OpenAPI; the MCP face on
``_server`` is out of this wave), so ``/_server/_meta/`` carries the usual
schema/docs/index endpoints, and adds:

- ``index`` — the ``/_server/`` descriptor: title, active profile and the
  attached section names (JSON — no HTML in code);
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
  ``register_auth_method``); the FULL profile registers ``PasswordMethod``
  at construction (the minimal profile is the internal server, D6 — no
  login surface).

Handlers stay PURE: they return values and never touch cookies or an ambient
request/response (the old ``self.server.request`` idiom must never be
reintroduced). Login attaches the avatar to the existing session in place —
the id never changes, so no login-time cookie exists. A handler that needs the
live request DECLARES a ``request`` parameter: ``bind_kwargs`` injects the
per-dispatch ``Request`` for declared names — the same declarative convention
``body_data`` follows — and the handler reaches the server through
``request.server``. The app plugs the genro-routes ``pydantic`` plugin on its
own router at construction, so its handler signatures are always captured
(the JSON body spread and the ``request`` detection both read the neutral
``params`` block) regardless of the owning server's plugin config.

FULL vs MINIMAL is a ``profile`` on this ONE class, chosen by the server
(``AsgiServer.server_app_profile``), not a class split — the internal-server
class is an orchestration concern (D8). Per D4 the OpenAPI docs surface is a
FULL feature: the ``minimal`` profile defaults ``docs`` to ``"off"`` (the
Swagger page 404s); later phases gate the full-only sections on the profile.

Kwargs peeled by the cooperative ``__init__`` (D16): ``profile`` (``"full"``,
the default, or ``"minimal"``; anything else raises ``ValueError``).
``mount_name`` defaults to ``"_server"``; the rest flows down the chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from genro_routes import RoutingClass, route

from ..auth.auth_method import AuthMethod, PasswordMethod
from ..session import Avatar
from .openapi import RESOURCES_DIR, OpenApiApplication
from .server_sections import AuthSection

if TYPE_CHECKING:
    from genro_routes import RouterNode

    from ..request import Request

__all__ = ["ServerApplication"]

PROFILES = ("full", "minimal")


class ServerApplication(OpenApiApplication):
    """System endpoints of a server, auto-mounted under ``/_server`` (D4).

    One class, two profiles: ``full`` (the public server) and ``minimal``
    (the future internal server; in this wave a test-only composition).
    System sections attach through ``attach_section`` and are listed by the
    ``index`` descriptor; the FULL profile carries the password login surface.
    """

    openapi_info: ClassVar[dict[str, Any]] = {
        "title": "genro-asgi-core server endpoints",
        "version": "1.0.0",
    }

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("mount_name", "_server")
        profile: str = kwargs.pop("profile", "full")
        if profile not in PROFILES:
            raise ValueError(f"unknown _server profile: {profile!r}")
        if profile == "minimal":
            kwargs.setdefault("docs", "off")
        self._profile = profile
        self._sections: dict[str, RoutingClass] = {}
        self._auth_section: AuthSection | None = None
        super().__init__(**kwargs)
        self.route.plug("pydantic")
        if self.profile == "full":
            self.register_auth_method(PasswordMethod(self, "password"))

    @property
    def profile(self) -> str:
        """The active profile — ``"full"`` or ``"minimal"`` (D4)."""
        return self._profile

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
        self.attach_instance(section, name=name)
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
        """Inject the live ``Request`` into handlers that declare ``request``.

        Extends the base reconciliation with the declarative seam the login
        surface needs: when the node's neutral ``params`` block declares a
        ``request`` parameter, the per-dispatch ``Request`` is bound to it
        (overriding any same-named wire value). No ambient state — the request
        travels as an ordinary argument, exactly like ``body_data``.
        """
        kwargs = super().bind_kwargs(node, request)
        fields = node.params.get("fields") or []
        if any(f["name"] == "request" for f in fields):
            kwargs["request"] = request
        return kwargs

    @route()
    def index(self) -> dict[str, Any]:
        """The ``/_server/`` descriptor: title, profile and section names."""
        return {
            "title": self.api_info.get("title", type(self).__name__),
            "profile": self.profile,
            "sections": sorted(self.sections),
        }

    @route(media_type="application/json")
    def login(
        self, identity: str = "", password: str = "", next: str = "", request: Any = None
    ) -> dict[str, Any]:
        """Authenticate against the server's UserStore and attach the identity.

        The JSON convergence point of every ``form`` method: verifies the
        credentials (``UserStore.verify`` — the record key is ``identity``),
        builds the ``Avatar`` and attaches it to the request's session in place
        (``request.session.attach_avatar``) — the session id never changes at
        login, so the client's cookie stays valid and no ``Set-Cookie`` is
        involved. The server's ``user_store`` is wired in the next wave (Macro
        5b): until then a server without one answers the error shape.

        Args:
            identity: The record key to verify (NOT the old ``username``).
            password: The password to verify.
            next: Return path set by the login challenge redirect. Accepted so
                the URL binds; consumed by the page script, ignored here.
            request: The live ``Request``, injected by ``bind_kwargs``.

        Returns:
            ``{session_id, identity, tags}`` on success, ``{"error": ...}`` on
            missing/invalid credentials or when no user store is wired.

        Note:
            Route: POST /_server/login
        """
        if not identity or not password:
            return {"error": "Identity and password are required"}
        user_store = getattr(request.server, "user_store", None)
        if user_store is None:
            return {"error": "Login is not available"}
        record = user_store.verify(identity, password)
        if record is None:
            return {"error": "Invalid credentials"}
        avatar = Avatar(record["identity"], record["tags"])
        session = request.session
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
        when no login surface is active (the minimal profile).

        Returns:
            ``{"methods": [descriptor, ...]}`` in registration order.

        Note:
            Route: GET /_server/login_methods
        """
        section = self.auth_section
        return {"methods": section.descriptors() if section is not None else []}


if __name__ == "__main__":
    app = ServerApplication()
    assert app.mount_name == "_server"
    assert app.profile == "full"
    assert app.docs_style == "swagger"
    node = app.route.node("/")
    assert node.error is None, node.error
    data = node()
    assert data == {
        "title": "genro-asgi-core server endpoints",
        "profile": "full",
        "sections": ["auth"],
    }
    assert app.login_methods() == {
        "methods": [
            {"id": "password", "kind": "form", "label": "Sign in", "action": "/_server/login"}
        ]
    }
    assert app.login() == {"error": "Identity and password are required"}
    # login's credentialed path needs the dispatch-injected request; it is
    # covered end-to-end (store absent, invalid creds, success) by test_login_flow.py.
    assert "<title>Sign in</title>" in app.login_page()
    minimal = ServerApplication(profile="minimal")
    assert minimal.profile == "minimal"
    assert minimal.docs_style == "off"
    assert minimal.auth_section is None
    assert minimal.login_methods() == {"methods": []}
    try:
        ServerApplication(profile="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for an unknown profile")
