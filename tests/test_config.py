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

"""Config tests (Macro 2 Phase 6): dialect → ConfigurationHandler → AsgiServer.

A recipe subclasses ``AsgiConfigBuilder`` and declares the whole-site sections;
``ConfigurationHandler(recipe).materialize()`` MATERIALIZES an ``AsgiServer``
(no live-server mutation — the phase's recorded divergence from the old repo).
Requests are driven at the ASGI level (no uvicorn), the same style as
``test_session.py``.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import pytest
from genro_bag.resolvers import EnvResolver

from genro_asgi_core import (
    AsgiConfigBuilder,
    AsgiServer,
    BaseApplication,
    ConfigurationHandler,
)
from genro_asgi_core.applications.server_app import ServerAppConfig
from genro_asgi_core.config.configurable import ConfigError
from genro_asgi_core.exceptions import HTTPUnauthorized
from genro_asgi_core.middleware.base import BaseMiddleware
from genro_asgi_core.types import Message, Receive, Scope, Send

ADMIN_PW_ENV_VAR = "GENRO_TEST_ADMIN_PW"
OIDC_SECRET_ENV_VAR = "GENRO_TEST_OIDC_SECRET"


class ShopApp(BaseApplication):
    """Primary app: answers ``shop``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"shop"})


class ApiApp(BaseApplication):
    """Secondary app: answers ``api``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"api"})


class TwoAppConfig(AsgiConfigBuilder):
    """Two apps (shop default primary, api secondary), cors + basic auth, host/port."""

    def main(self, root: Any) -> None:
        root.server(host="0.0.0.0", port=9100)
        root.middleware(cors=True)
        root.auth(basic={"admin": {"password": "secret", "tags": "admin"}})
        apps = root.applications(default="shop")
        apps.application(code="shop", app_class=ShopApp)
        apps.application(code="api", app_class=ApiApp)


def build_two_app_server() -> AsgiServer:
    """Materialize the two-app server from a fresh recipe instance."""
    return ConfigurationHandler(TwoAppConfig(name="config")).materialize()


def chain_types(server: AsgiServer) -> list[str]:
    """The class names of the middlewares in the server's chain, outermost first."""
    names: list[str] = []
    node: object = server.middleware_chain
    while isinstance(node, BaseMiddleware):
        names.append(type(node).__name__)
        node = node.app
    return names


def basic_header(username: str, password: str) -> list[tuple[bytes, bytes]]:
    """An ``Authorization: Basic`` header list for the given credentials."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return [(b"authorization", f"Basic {token}".encode())]


async def http_get(server: AsgiServer, path: str) -> bytes:
    """Drive one GET through ``server`` at the ASGI level; return the response body."""
    scope: Scope = {"type": "http", "method": "GET", "path": path, "headers": []}
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


class TestMaterialize:
    def test_returns_asgi_server_with_config_host_port(self) -> None:
        server = build_two_app_server()
        assert isinstance(server, AsgiServer)
        assert server.config_host == "0.0.0.0"
        assert server.config_port == 9100

    def test_default_app_is_primary_others_are_mounts(self) -> None:
        server = build_two_app_server()
        assert isinstance(server.primary, ShopApp)
        assert server.primary.mount_name == ""
        assert set(server.mounts) == {"api", "_server"}
        assert isinstance(server.mounts["api"], ApiApp)


class TestDemux:
    async def test_serves_both_apps(self) -> None:
        server = build_two_app_server()
        assert await http_get(server, "/") == b"shop"
        assert await http_get(server, "/api") == b"api"


class TestMiddlewareChain:
    def test_chain_contains_cors_and_errors(self) -> None:
        types = chain_types(build_two_app_server())
        assert "CORSMiddleware" in types
        assert "ErrorMiddleware" in types


class TestAuth:
    def test_authenticate_verifies_configured_basic(self) -> None:
        server = build_two_app_server()
        scope: Scope = {"headers": basic_header("admin", "secret")}
        avatar = server.authenticate(scope)
        assert avatar is not None
        assert avatar.identity == "admin"
        assert "admin" in avatar.tags

    def test_wrong_password_raises_unauthorized(self) -> None:
        server = build_two_app_server()
        scope: Scope = {"headers": basic_header("admin", "wrong")}
        with pytest.raises(HTTPUnauthorized):
            server.authenticate(scope)


class TestSession:
    async def test_session_attached_after_a_request(self) -> None:
        server = build_two_app_server()
        scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent.append(message)

        await server(scope, receive, send)
        assert scope.get("session") is not None
        assert server.session(scope) is scope["session"]


class TestMaxThreads:
    async def test_recipe_max_threads_reaches_the_pool(self) -> None:
        class SizedPoolConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.server(host="127.0.0.1", port=8000, max_threads=2)
                apps = root.applications(default="shop")
                apps.application(code="shop", app_class=ShopApp)

        server = ConfigurationHandler(SizedPoolConfig(name="sized")).materialize()
        await server.run_sync(lambda: None)
        assert server.pool.executor._max_workers == 2


class TestGrammarValidation:
    def test_unknown_tag_raises(self) -> None:
        class BadConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.server(host="127.0.0.1", port=8000)
                root.nonexistent(foo=1)

        with pytest.raises(AttributeError):
            ConfigurationHandler(BadConfig(name="bad"))

    def test_application_without_app_class_rejected_by_grammar(self) -> None:
        class NoClassConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                apps = root.applications()
                apps.application(code="shop")

        with pytest.raises(ValueError, match="app_class"):
            ConfigurationHandler(NoClassConfig(name="noclass"))

    def test_database_without_db_class_rejected_by_grammar(self) -> None:
        class NoDbClassConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                apps = root.applications(default="shop")
                apps.application(code="shop", app_class=ShopApp)
                dbs = root.databases()
                dbs.database(code="default")

        with pytest.raises(ValueError, match="db_class"):
            ConfigurationHandler(NoDbClassConfig(name="nodbclass"))

    def test_mount_without_path_rejected_by_grammar(self) -> None:
        class NoPathConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                mounts = root.storage()
                mounts.mount(code="data")
                apps = root.applications(default="shop")
                apps.application(code="shop", app_class=ShopApp)

        with pytest.raises(ValueError, match="path"):
            ConfigurationHandler(NoPathConfig(name="nopath"))


class TestSkippedSections:
    def test_groups_databases_openapi_materialize_without_error(self) -> None:
        class OrchestrationConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.server(host="127.0.0.1", port=8000)
                apps = root.applications(default="shop")
                shop = apps.application(code="shop", app_class=ShopApp)
                groups = shop.groups(default="stable")
                groups.group(code="stable", workers=2)
                dbs = root.databases()
                dbs.database(code="default", db_class=object)
                root.openapi(title="Demo", version="1.0")

        server = ConfigurationHandler(OrchestrationConfig(name="orch")).materialize()
        assert isinstance(server, AsgiServer)
        assert isinstance(server.primary, ShopApp)
        assert set(server.mounts) == {"_server"}


class TestSingleAppNoDefault:
    def test_lone_app_becomes_primary_without_default(self) -> None:
        class OneAppConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                apps = root.applications()
                apps.application(code="only", app_class=ShopApp)

        server = ConfigurationHandler(OneAppConfig(name="one")).materialize()
        assert isinstance(server.primary, ShopApp)
        assert set(server.mounts) == {"_server"}


def storage_site_config(base_path: Path) -> AsgiConfigBuilder:
    """A site recipe with a plain ``idstore`` storage mount (for store wiring)."""

    class StorageSiteConfig(AsgiConfigBuilder):
        def main(self, root: Any) -> None:
            root.server(host="127.0.0.1", port=8000)
            mounts = root.storage()
            mounts.mount(code="idstore", path=str(base_path))
            apps = root.applications(default="shop")
            apps.application(code="shop", app_class=ShopApp)

    return StorageSiteConfig(name="config")


class IdentityServerAppConfig(ServerAppConfig):
    """A ``_server`` config: admin password by ``^pointer`` plus both stores."""

    def setup(self, data: Any) -> None:
        data["admin_pw"] = EnvResolver(ADMIN_PW_ENV_VAR)

    def main(self, root: Any) -> None:
        root.admin_password("^admin_pw")
        root.users(mount="idstore", prefix="users")
        root.tokens(mount="idstore", prefix="api_keys")


class TestServerAppConfigClass:
    """The ``_server`` app's config-class: claim, lift, defaults (design 2026-07-23)."""

    def test_no_config_uses_the_default_base(self) -> None:
        handler = ConfigurationHandler(TwoAppConfig(name="config"))
        assert isinstance(handler.server_app_config, ServerAppConfig)
        server = handler.materialize()
        assert server.user_store is None
        assert server.api_key_store is None

    def test_claimed_config_lifts_identity_kwargs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ADMIN_PW_ENV_VAR, "s3cret")
        handler = ConfigurationHandler(
            storage_site_config(tmp_path), IdentityServerAppConfig()
        )
        server = handler.materialize()
        assert server.user_store is not None
        assert server.api_key_store is not None
        admin = server.user_store.get("admin")
        assert admin is not None
        assert "SUPERADMIN" in admin["tags"]

    def test_admin_password_literal_is_a_boot_error(self, tmp_path: Path) -> None:
        class LiteralConfig(ServerAppConfig):
            def main(self, root: Any) -> None:
                root.admin_password("plain-secret")

        handler = ConfigurationHandler(storage_site_config(tmp_path), LiteralConfig())
        with pytest.raises(ConfigError, match="\\^pointer"):
            handler.materialize()

    def test_admin_password_pointer_resolving_empty_is_a_boot_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(ADMIN_PW_ENV_VAR, raising=False)
        handler = ConfigurationHandler(
            storage_site_config(tmp_path), IdentityServerAppConfig()
        )
        with pytest.raises(ConfigError, match="resolved empty"):
            handler.materialize()

    def test_duplicate_tag_in_config_is_a_boot_error(self, tmp_path: Path) -> None:
        class DoubledConfig(ServerAppConfig):
            def main(self, root: Any) -> None:
                root.users(mount="one")
                root.users(mount="two")

        handler = ConfigurationHandler(storage_site_config(tmp_path), DoubledConfig())
        with pytest.raises(ConfigError, match="duplicate 'users'"):
            handler.materialize()

    def test_unclaimed_app_config_is_a_boot_error(self) -> None:
        with pytest.raises(ConfigError, match="no application claims it"):
            ConfigurationHandler(TwoAppConfig(name="config"), TwoAppConfig(name="other"))

    def test_duplicate_server_config_is_a_boot_error(self) -> None:
        with pytest.raises(ConfigError, match="duplicate config"):
            ConfigurationHandler(
                TwoAppConfig(name="config"),
                ServerAppConfig(name="first"),
                ServerAppConfig(name="second"),
            )

    def test_hosted_role_never_lifts_identity(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ADMIN_PW_ENV_VAR, "s3cret")
        handler = ConfigurationHandler(
            storage_site_config(tmp_path), IdentityServerAppConfig()
        )
        worker = handler.materialize(role="worker", app="shop")
        assert worker.user_store is None
        assert worker.api_key_store is None


class LoginSurfaceConfig(ServerAppConfig):
    """A ``_server`` config: lockout policy plus two OIDC providers."""

    def setup(self, data: Any) -> None:
        data["oidc_secret"] = EnvResolver(OIDC_SECRET_ENV_VAR)

    def main(self, root: Any) -> None:
        root.login(max_attempts=3, backoff=10)
        root.oidc(
            code="corp",
            issuer="https://idp.example.com",
            client_id="corp-client",
            client_secret="^oidc_secret",
            scopes="openid profile",
            identity_claim="preferred_username",
            tags=["staff"],
        )
        root.oidc(
            code="public",
            issuer="https://accounts.example.org",
            client_id="pub-client",
        )


class TestServerAppLift:
    """The login-surface lift: ``login()``/``oidc()`` → ``server_app=`` → the app."""

    def test_lift_reaches_the_server_app(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(OIDC_SECRET_ENV_VAR, "oidc-s3cret")
        server = ConfigurationHandler(
            TwoAppConfig(name="config"), LoginSurfaceConfig()
        ).materialize()
        app = server.mounts["_server"]
        assert app.login_policy == {"max_attempts": 3, "backoff": 10}
        assert set(app.oidc_providers) == {"corp", "public"}
        corp = app.oidc_providers["corp"]
        assert corp["client_secret"] == "oidc-s3cret"
        assert corp["scopes"] == "openid profile"
        assert corp["identity_claim"] == "preferred_username"
        assert corp["tags"] == ["staff"]

    def test_oidc_defaults_apply_per_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(OIDC_SECRET_ENV_VAR, "oidc-s3cret")
        server = ConfigurationHandler(
            TwoAppConfig(name="config"), LoginSurfaceConfig()
        ).materialize()
        public = server.mounts["_server"].oidc_providers["public"]
        assert public == {
            "issuer": "https://accounts.example.org",
            "client_id": "pub-client",
            "scopes": "openid email profile",
            "identity_claim": "email",
            "tags": [],
        }

    def test_no_config_leaves_the_bare_app(self) -> None:
        app = build_two_app_server().mounts["_server"]
        assert app.login_policy == {}
        assert app.oidc_providers == {}

    def test_client_secret_literal_is_a_boot_error(self) -> None:
        class LiteralSecretConfig(ServerAppConfig):
            def main(self, root: Any) -> None:
                root.oidc(
                    code="corp",
                    issuer="https://idp.example.com",
                    client_id="corp-client",
                    client_secret="plain-secret",
                )

        handler = ConfigurationHandler(
            TwoAppConfig(name="config"), LiteralSecretConfig()
        )
        with pytest.raises(ConfigError, match="\\^pointer"):
            handler.materialize()

    def test_client_secret_pointer_resolving_empty_is_a_boot_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(OIDC_SECRET_ENV_VAR, raising=False)
        handler = ConfigurationHandler(
            TwoAppConfig(name="config"), LoginSurfaceConfig()
        )
        with pytest.raises(ConfigError, match="resolved empty"):
            handler.materialize()

    def test_duplicate_oidc_code_is_a_boot_error(self) -> None:
        class DoubledCodeConfig(ServerAppConfig):
            def main(self, root: Any) -> None:
                root.oidc(code="corp", issuer="https://a.example.com", client_id="a")
                root.oidc(code="corp", issuer="https://b.example.com", client_id="b")

        handler = ConfigurationHandler(
            TwoAppConfig(name="config"), DoubledCodeConfig()
        )
        with pytest.raises(ConfigError, match="duplicate oidc code"):
            handler.materialize()

    def test_missing_oidc_code_is_a_boot_error(self) -> None:
        class NoCodeConfig(ServerAppConfig):
            def main(self, root: Any) -> None:
                root.oidc(issuer="https://idp.example.com", client_id="x")

        handler = ConfigurationHandler(TwoAppConfig(name="config"), NoCodeConfig())
        with pytest.raises(ConfigError, match="'code'"):
            handler.materialize()

    def test_hosted_role_never_lifts_the_login_surface(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(OIDC_SECRET_ENV_VAR, "oidc-s3cret")
        handler = ConfigurationHandler(
            TwoAppConfig(name="config"), LoginSurfaceConfig()
        )
        worker = handler.materialize(role="worker", app="shop")
        app = worker.mounts["_server"]
        assert app.login_policy == {}
        assert app.oidc_providers == {}


class TestSessionTtl:
    def test_session_child_reaches_the_store_ttl(self) -> None:
        class SessionConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                srv = root.server(host="127.0.0.1", port=8000)
                srv.session(ttl=1234)
                apps = root.applications(default="shop")
                apps.application(code="shop", app_class=ShopApp)

        server = ConfigurationHandler(SessionConfig(name="config")).materialize()
        assert server.session_store.create().meta["ttl"] == 1234


class TestConfigurationTag:
    def test_configuration_subtree_is_read_and_skipped(self) -> None:
        class ConfiguredAppConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.server(host="127.0.0.1", port=8000)
                apps = root.applications(default="shop")
                shop = apps.application(code="shop", app_class=ShopApp)
                shop.configuration(theme="dark", max_items=10)

        server = ConfigurationHandler(ConfiguredAppConfig(name="config")).materialize()
        assert isinstance(server.primary, ShopApp)
        assert set(server.mounts) == {"_server"}
