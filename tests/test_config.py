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

"""Config tests: the ``asgiconfig`` dialect, the read door, the self-configuring server.

A recipe subclasses ``AsgiConfigBuilder`` and declares the site sections under
one ``configuration`` root; ``AsgiServer(config=source)`` builds its own
``ConfigurationHandler`` over that source, derives its kwargs from it and stays
reachable as ``server.config``. Requests are driven at the ASGI level (no
uvicorn), the same style as ``test_session.py``.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
import pytest
from genro_bag.resolvers import EnvResolver
from genro_storage import StorageManager

from genro_asgi import (
    AsgiConfigBuilder,
    AsgiServer,
    BaseApplication,
    ConfigError,
    ConfigurationHandler,
)
from genro_asgi.__main__ import AppsRegistry
from genro_asgi.applications.spa_app import SpaApplication
from genro_asgi.config import HOME_ENV, BaseConfiguration, DefaultConfig
from genro_asgi.exceptions import HTTPUnauthorized
from genro_asgi.spa.orchestration.spa_commander import ORDERS_LOGGER_NAME
from genro_asgi.middleware.base import BaseMiddleware
from genro_asgi.spa.orchestration import GroupHandler, SpaCommander
from genro_asgi.storage_mixin import DEFAULT_SITE_MOUNT
from genro_asgi.types import Message, Receive, Scope, Send

ADMIN_PW_ENV_VAR = "GENRO_TEST_ADMIN_PW"
OIDC_SECRET_ENV_VAR = "GENRO_TEST_OIDC_SECRET"


class ShopApp(BaseApplication):
    """Root app: answers ``shop``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"shop"})


class ApiApp(BaseApplication):
    """Secondary app: answers ``api``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"api"})


class TwoAppConfig(AsgiConfigBuilder):
    """Two apps (shop on the root, api secondary), cors + basic auth, host/port.

    Declares ``external_url`` too — the whole-site recipe of these tests, and a
    site that configures an OIDC provider must name its public base address (the
    absolute ``redirect_uri`` prefix) or the server refuses to boot. The
    without-``external_url`` case is covered on its own in ``test_oidc.py``.
    """

    def main(self, root: Any) -> None:
        cfg = root.configuration()
        cfg.server(host="0.0.0.0", port=9100, external_url="https://shop.example.com")
        cfg.middleware(cors=True)
        self.authentication_section(cfg)
        self.applications_section(cfg)

    def authentication_section(self, cfg: Any) -> None:
        """One Basic user, handed to ``AuthCore`` through ``credentials``."""
        creds = cfg.authentication().credentials()
        creds.basic_user(username="admin", password="secret", tags="admin")

    def applications_section(self, cfg: Any) -> None:
        """``shop`` claims the site root, ``api`` answers its own mount."""
        apps = cfg.applications(default="shop")
        apps.application(code="shop", mount="", app_class=ShopApp)
        apps.application(code="api", app_class=ApiApp)


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


async def http_status_headers(
    server: AsgiServer, path: str
) -> tuple[int, list[tuple[bytes, bytes]]]:
    """Drive one GET through ``server``; return its status and response headers."""
    scope: Scope = {"type": "http", "method": "GET", "path": path, "headers": []}
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"], start["headers"]


class TestSelfConfiguringServer:
    def test_server_section_reaches_the_serve_defaults(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        assert server.config_host == "0.0.0.0"
        assert server.config_port == 9100
        assert server.external_url == "https://shop.example.com"

    def test_default_app_answers_the_root_others_are_mounts(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        assert isinstance(server.root_application, ShopApp)
        assert server.root_application.mount == ""
        assert set(server.applications) == {"shop", "api", "_server"}
        assert isinstance(server.applications["api"], ApiApp)

    def test_a_bare_server_has_no_configuration(self) -> None:
        assert AsgiServer(applications=[ShopApp(mount="")]).config is None

    def test_the_handler_stays_reachable_as_the_read_door(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        assert isinstance(server.config, ConfigurationHandler)
        assert server.config("server.host") == "0.0.0.0"
        assert server.config("server.port") == 9100

    def test_an_explicit_kwarg_wins_over_the_configured_one(self) -> None:
        server = AsgiServer(config=TwoAppConfig, port=0)
        assert server.config_port == 0
        assert server.config_host == "0.0.0.0"       # untouched kwargs still apply

    def test_a_recipe_instance_is_accepted(self) -> None:
        assert AsgiServer(config=TwoAppConfig(name="site")).config_port == 9100

    def test_a_ready_handler_is_adopted_as_is(self) -> None:
        handler = ConfigurationHandler(TwoAppConfig)
        server = AsgiServer(config=handler)
        assert server.config is handler

    def test_a_config_py_path_is_loaded(self, tmp_path: Path) -> None:
        module = tmp_path / "config.py"
        module.write_text(
            "from genro_asgi.config import AsgiConfigBuilder\n"
            "\n"
            "\n"
            "class ServerConfiguration(AsgiConfigBuilder):\n"
            "    def main(self, root):\n"
            "        cfg = root.configuration()\n"
            "        cfg.server(host='127.0.0.1', port=8123)\n"
        )
        server = AsgiServer(config=module)
        assert server.config_port == 8123
        assert set(server.applications) == {"_server"}


class TestDemux:
    async def test_serves_both_apps(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        assert await http_get(server, "/") == b"shop"
        assert await http_get(server, "/api") == b"api"


class TestMiddlewareChain:
    def test_chain_contains_cors_and_errors(self) -> None:
        types = chain_types(AsgiServer(config=TwoAppConfig))
        assert "CORSMiddleware" in types
        assert "ErrorMiddleware" in types

    def test_an_explicit_switch_off_survives_the_read(self) -> None:
        class NoCorsConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.middleware(cors=False)
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        assert "CORSMiddleware" not in chain_types(AsgiServer(config=NoCorsConfig))


class TestCredentials:
    def test_basic_user_is_verified_by_the_auth_core(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        scope: Scope = {"headers": basic_header("admin", "secret")}
        avatar = server.authenticate(scope)
        assert avatar is not None
        assert avatar.identity == "admin"
        assert "admin" in avatar.tags

    def test_wrong_password_raises_unauthorized(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        scope: Scope = {"headers": basic_header("admin", "wrong")}
        with pytest.raises(HTTPUnauthorized):
            server.authenticate(scope)

    def test_bearer_token_is_verified_by_its_identity(self) -> None:
        class BearerConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                creds = cfg.authentication().credentials()
                creds.bearer_token(identity="svc", token="sk_live_xyz", tags="api")
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        server = AsgiServer(config=BearerConfig)
        scope: Scope = {"headers": [(b"authorization", b"Bearer sk_live_xyz")]}
        avatar = server.authenticate(scope)
        assert avatar is not None
        assert avatar.identity == "svc"
        assert avatar.tags == ["api"]

    def test_jwt_entries_stay_an_ordered_list(self) -> None:
        class JwtConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                creds = cfg.authentication().credentials()
                creds.jwt(name="hmac", secret="topsecret")
                creds.jwt(name="rsa", public_key="PUBKEY", algorithm="RS256")
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        entries = ConfigurationHandler(JwtConfig).auth_entries()
        assert [entry["name"] for entry in entries["jwt"]] == ["hmac", "rsa"]
        assert entries["jwt"][0]["algorithm"] == "HS256"        # signature default
        assert entries["jwt"][1]["public_key"] == "PUBKEY"

    def test_no_credentials_section_arms_no_backend(self) -> None:
        class BareConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().applications().application(
                    code="shop", mount="", app_class=ShopApp
                )

        assert ConfigurationHandler(BareConfig).auth_entries() is None


class TestSession:
    async def test_session_attached_after_a_request(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent.append(message)

        await server(scope, receive, send)
        assert scope.get("session") is not None
        assert server.session(scope) is scope["session"]

    def test_session_child_reaches_the_store_ttl(self) -> None:
        class SessionConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000).session(ttl=1234)
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        server = AsgiServer(config=SessionConfig)
        assert server.session_store.create().meta["ttl"] == 1234


class TestMaxThreads:
    async def test_recipe_max_threads_reaches_the_pool(self) -> None:
        class SizedPoolConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000, max_threads=2)
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        server = AsgiServer(config=SizedPoolConfig)
        await server.run_sync(lambda: None)
        assert server.pool.executor._max_workers == 2


class TestGrammarValidation:
    def test_unknown_tag_raises(self) -> None:
        class BadConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().nonexistent(foo=1)

        with pytest.raises(AttributeError):
            ConfigurationHandler(BadConfig)

    def test_a_section_outside_the_root_is_rejected(self) -> None:
        class LooseConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.server(host="127.0.0.1")

        with pytest.raises(ValueError, match="parent_tags"):
            ConfigurationHandler(LooseConfig)

    def test_application_without_app_class_rejected_by_grammar(self) -> None:
        class NoClassConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().applications().application(code="shop")

        with pytest.raises(ValueError, match="app_class"):
            ConfigurationHandler(NoClassConfig)

    def test_a_mount_without_base_path_is_rejected_by_the_foreign_grammar(self) -> None:
        # The storage subtree is validated by genro-storage's own signatures,
        # not by this dialect: the error comes from THERE.
        class NoBasePathConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().storage(app=StorageManager).local(name="data")

        with pytest.raises(ValueError, match="base_path"):
            ConfigurationHandler(NoBasePathConfig)

    def test_storage_without_app_is_rejected_by_the_grammar(self) -> None:
        # ``app`` cannot be defaulted in the signature: the subbuilder
        # reference reads the CALL SITE, so an omitted ``app`` would silently
        # leave the node a leaf of this dialect. It is required instead.
        class NoAppConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().storage()

        with pytest.raises(ValueError, match="app"):
            ConfigurationHandler(NoAppConfig)

    def test_an_empty_application_code_is_a_boot_error(self) -> None:
        # code="" would file the subtree under an empty label while the app
        # registers under its class-name fallback: the read door would then
        # never reach the written values, so the fold refuses to boot.
        class EmptyCodeConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.applications().application(code="", mount="", app_class=ShopApp)

        with pytest.raises(ConfigError, match="non-empty"):
            AsgiServer(config=EmptyCodeConfig)

    def test_a_second_server_section_is_rejected(self) -> None:
        class TwiceConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1")
                cfg.server(host="0.0.0.0")

        with pytest.raises(ValueError):
            ConfigurationHandler(TwiceConfig)


class TestSkippedSections:
    def test_openapi_and_databases_boot_without_error(self) -> None:
        class OrchestrationConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000)
                cfg.applications(default="shop").application(
                    code="shop", mount="", app_class=ShopApp
                )
                cfg.databases().database(code="default", db_class=object)
                cfg.openapi(title="Demo", version="1.0")

        server = AsgiServer(config=OrchestrationConfig)
        assert isinstance(server.root_application, ShopApp)
        assert set(server.applications) == {"shop", "_server"}
        assert server.config("openapi.title") == "Demo"


class TestSingleAppNoDefault:
    def test_lone_app_answers_its_own_mount_not_the_root(self) -> None:
        # Nothing elects an application: a lone app derives its mount from its
        # code like every other, so the site root stays unclaimed.
        class OneAppConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().applications().application(
                    code="only", app_class=ShopApp
                )

        server = AsgiServer(config=OneAppConfig)
        assert set(server.applications) == {"only", "_server"}
        assert server.root_application is None
        assert isinstance(server.application_at("only"), ShopApp)

    def test_lone_app_claims_the_root_by_declaring_an_empty_mount(self) -> None:
        # The compatibility mechanism: one app served at unchanged URLs.
        class RootAppConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().applications().application(
                    code="only", mount="", app_class=ShopApp
                )

        server = AsgiServer(config=RootAppConfig)
        assert isinstance(server.root_application, ShopApp)
        assert server.root_application.code == "only"


class TestDefaultRedirect:
    async def test_root_redirects_to_the_default_when_nobody_claims_it(self) -> None:
        class MountsOnlyConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                apps = root.configuration().applications(default="shop")
                apps.application(code="shop", app_class=ShopApp)
                apps.application(code="api", app_class=ApiApp)

        server = AsgiServer(config=MountsOnlyConfig)
        assert server.root_application is None
        assert server.default_application is server.applications["shop"]
        status, headers = await http_status_headers(server, "/")
        assert status == 307
        assert dict(headers)[b"location"] == b"/shop/"

    def test_a_default_naming_no_application_is_a_boot_error(self) -> None:
        class GhostDefaultConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().applications(default="ghost").application(
                    code="shop", app_class=ShopApp
                )

        with pytest.raises(ValueError, match="ghost"):
            AsgiServer(config=GhostDefaultConfig)


def storage_site_config(base_path: Path) -> type[AsgiConfigBuilder]:
    """A site recipe with an ``idstore`` mount and the key the credential stores need."""

    class StorageSiteConfig(AsgiConfigBuilder):
        def setup(self, data: Any) -> None:
            """The mount path travels through the datastore, not a closure."""
            data["base_path"] = str(base_path)

        def main(self, root: Any) -> None:
            cfg = root.configuration()
            cfg.server(host="127.0.0.1", port=8000)
            cfg.storage(
                app=StorageManager, storage_key=Fernet.generate_key().decode()
            ).local(name="idstore", base_path=self.data["base_path"])
            cfg.applications(default="shop").application(
                code="shop", mount="", app_class=ShopApp
            )
            self.identity_section(cfg)

        def identity_section(self, cfg: Any) -> None:
            """Bootstrap admin plus both identity stores on ``idstore``."""
            auth = cfg.authentication()
            auth.admin_password(EnvResolver(ADMIN_PW_ENV_VAR))
            auth.users(mount="idstore", prefix="users")
            auth.tokens(mount="idstore", prefix="api_keys")

    return StorageSiteConfig


class TestStorageSection:
    """``storage`` → genro-storage's own ``list[dict]`` plus the section key."""

    def test_the_section_flattens_to_genro_storage_configuration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GENRO_TEST_STORAGE_KEY", "k1,k2")

        class StorageConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                self.storage_section(root.configuration())

            def storage_section(self, cfg: Any) -> None:
                s = cfg.storage(
                    app=StorageManager,
                    storage_key=EnvResolver("GENRO_TEST_STORAGE_KEY"),
                )
                s.local(name="site", base_path=".")
                s.s3(name="uploads", bucket="shop-media", default_encrypted="shopspa")

        mounts, storage_key = ConfigurationHandler(StorageConfig).storage_config()
        assert storage_key == "k1,k2"
        assert mounts == [
            {"name": "site", "protocol": "local", "base_path": "."},
            {
                "name": "uploads",
                "protocol": "s3",
                "bucket": "shop-media",
                "default_encrypted": "shopspa",
            },
        ]

    def test_no_storage_section_leaves_the_default_manager(self) -> None:
        assert ConfigurationHandler(TwoAppConfig).storage_config() is None


class TestIdentitySection:
    """``authentication`` → the identity kwargs ``AuthMixin`` peels."""

    def test_no_identity_configured_leaves_the_stores_unwired(self) -> None:
        server = AsgiServer(config=TwoAppConfig)
        assert server.user_store is None
        assert server.api_key_store is None

    def test_stores_and_bootstrap_admin_reach_the_server(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ADMIN_PW_ENV_VAR, "s3cret")
        server = AsgiServer(config=storage_site_config(tmp_path))
        assert server.user_store is not None
        assert server.api_key_store is not None
        admin = server.user_store.get("admin")
        assert admin is not None
        assert "SUPERADMIN" in admin["tags"]

    def test_admin_password_literal_is_rejected_by_the_grammar(self) -> None:
        class LiteralConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().authentication().admin_password("plain-secret")

        with pytest.raises(ValueError, match="node_value"):
            AsgiServer(config=LiteralConfig)

    def test_admin_password_resolving_empty_is_a_boot_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(ADMIN_PW_ENV_VAR, raising=False)
        with pytest.raises(ConfigError, match="resolved empty"):
            AsgiServer(config=storage_site_config(tmp_path))

    def test_a_second_users_element_is_rejected_by_the_grammar(self) -> None:
        class DoubledConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                auth = root.configuration().authentication()
                auth.users(mount="one")
                auth.users(mount="two")

        with pytest.raises(ValueError):
            ConfigurationHandler(DoubledConfig)


class LoginSurfaceConfig(TwoAppConfig):
    """The two-app site plus a lockout policy and two OIDC providers."""

    def authentication_section(self, cfg: Any) -> None:
        """The login surface: policy, one confidential and one public provider."""
        auth = cfg.authentication()
        auth.login(max_attempts=3, backoff=10)
        oidc = auth.oidc()
        oidc.provider(
            code="corp",
            issuer="https://idp.example.com",
            client_id="corp-client",
            client_secret=EnvResolver(OIDC_SECRET_ENV_VAR),
            scopes="openid profile",
            identity_claim="preferred_username",
            tags=["staff"],
        )
        oidc.provider(
            code="public",
            issuer="https://accounts.example.org",
            client_id="pub-client",
        )


class TestLoginSurface:
    """``authentication.login``/``.oidc`` → ``server_app=`` → the ``_server`` app."""

    def test_the_login_surface_reaches_the_server_app(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(OIDC_SECRET_ENV_VAR, "oidc-s3cret")
        app = AsgiServer(config=LoginSurfaceConfig).applications["_server"]
        assert app.login_policy == {"max_attempts": 3, "backoff": 10}
        assert set(app.oidc_providers) == {"corp", "public"}
        corp = app.oidc_providers["corp"]
        assert corp["client_secret"] == "oidc-s3cret"
        assert corp["scopes"] == "openid profile"
        assert corp["identity_claim"] == "preferred_username"
        assert corp["tags"] == ["staff"]

    def test_provider_defaults_apply_per_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(OIDC_SECRET_ENV_VAR, "oidc-s3cret")
        app = AsgiServer(config=LoginSurfaceConfig).applications["_server"]
        assert app.oidc_providers["public"] == {
            "issuer": "https://accounts.example.org",
            "client_id": "pub-client",
            "scopes": "openid email profile",
            "identity_claim": "email",
            "tags": [],
        }

    def test_no_login_section_leaves_the_bare_app(self) -> None:
        app = AsgiServer(config=TwoAppConfig).applications["_server"]
        assert app.login_policy == {}
        assert app.oidc_providers == {}

    def test_a_provider_without_a_code_is_rejected_by_the_collection(self) -> None:
        class NoCodeConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().authentication().oidc().provider(
                    issuer="https://idp.example.com", client_id="x"
                )

        with pytest.raises(ValueError, match="code"):
            ConfigurationHandler(NoCodeConfig)

    def test_a_duplicate_provider_code_is_rejected_by_the_collection(self) -> None:
        class DoubledCodeConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                oidc = root.configuration().authentication().oidc()
                oidc.provider(code="corp", issuer="https://a.example.com", client_id="a")
                oidc.provider(code="corp", issuer="https://b.example.com", client_id="b")

        with pytest.raises(ValueError, match="corp"):
            ConfigurationHandler(DoubledCodeConfig)


class TestTasksConfig:
    """The ``tasks()`` child of ``server`` lifts to the ``tasks=`` kwarg."""

    def test_tasks_disabled_via_recipe(self) -> None:
        class TasksOffConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000).tasks(enabled=False)
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        server = AsgiServer(config=TasksOffConfig)
        assert server.tasks_enabled is False
        with pytest.raises(RuntimeError, match="disabled"):
            server.tasks

    def test_tuning_reaches_scheduler_and_store(self) -> None:
        class TunedConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000).tasks(tick_seconds=5, mount="site")
                cfg.applications().application(code="shop", mount="", app_class=ShopApp)

        server = AsgiServer(config=TunedConfig)
        assert server.tasks_enabled is True                  # enabled defaults on
        assert server.tasks.scheduler.tick_seconds == 5.0
        assert server.tasks.task_store.mount == "site"       # explicit override

    def test_direct_dict_kwarg(self) -> None:
        server = AsgiServer(applications=[ShopApp(mount="")],
                            tasks={"enabled": True, "tick_seconds": 3})
        assert server.tasks.scheduler.tick_seconds == 3.0
        assert server.tasks_config == {"tick_seconds": 3}    # enabled peeled away

    def test_a_child_under_tasks_is_rejected_by_the_grammar(self) -> None:
        class StrayChildConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000).tasks().middleware()

        with pytest.raises(ValueError, match="parent"):
            ConfigurationHandler(StrayChildConfig)


class SpaPoolConfig(AsgiConfigBuilder):
    """The ``orchestration`` subtree with every key of both rungs, and two groups.

    The second group declares nothing but its child: what it leaves out is what
    the objects' own defaults answer for, which is the read stack's whole
    contract.
    """

    def main(self, root: Any) -> None:
        cfg = root.configuration()
        cfg.server(host="127.0.0.1", port=8000)
        front = cfg.applications().application(
            code="shop", mount="", app_class=SpaApplication
        )
        self.commander_section(front)

    def commander_section(self, front: Any) -> None:
        """The orchestration, the vertex under it, then its groups on two interpreters."""
        commander = front.orchestration().commander(
            frozen_users_path="/srv/shop/frozen_users",
            instance_dir="/srv/shop/instance",
            memory_max_percent=75.0,
            machine_memory_alarm_percent=85.0,
            orchestration_log_path="/srv/shop/logs/orchestration.log",
            orchestration_log_max_bytes=2_000_000,
            orchestration_log_backup_count=3,
            user_expiry_hours=480.0,
            guest_expiry_hours=12.0,
        )
        groups = commander.groups()
        groups.group(
            name="stable",
            memory_max_percent=80.0,
            worker_memory_max_percent=40.0,
            occupancy_max_percent=70.0,
            restart_occupancy_max_percent=90.0,
            reception_reserved_percent=30.0,
            new_user_occupancy_percent=4.0,
            newcomer_reserve_count=2,
            worker_max_users=16,
            cpu_retirement_quiet_seconds=75.0,
            user_idle_freeze_minutes=45.0,
            entry_module="genro_asgi.spa.orchestration.worker_entry",
            executable="/srv/shop/.venvs/stable/bin/python",
            worker_class="myshop.app:ShopWorker",
            main_threadpool_size=8,
            aux_threadpool_size=2,
            worker_kwargs={"site_path": "/srv/shop"},
            engine_factory="myshop.app:ShopEngineFactory",
            engine_kwargs={"source": "/srv/shop"},
        )
        groups.group(name="canary", entry_module="genro_asgi.spa.orchestration.worker_entry")


class ElectedGroupConfig(SpaPoolConfig):
    """The same pool, with the group that receives a newcomer elected by name."""

    def commander_section(self, front: Any) -> None:
        commander = front.orchestration().commander(
            frozen_users_path="/srv/shop/frozen_users"
        )
        groups = commander.groups(default="canary")
        groups.group(name="stable", entry_module="genro_asgi.spa.orchestration.worker_entry")
        groups.group(name="canary", entry_module="genro_asgi.spa.orchestration.worker_entry")


class TestCommanderSection:
    """``orchestration`` → its own three words, ``commander`` → the vertex's kwargs
    and one kwargs set per group."""

    def test_the_orchestration_node_is_read_on_its_own_path(self) -> None:
        """The three words of the node, and the commander one rung below it."""

        class ProfiledPoolConfig(SpaPoolConfig):
            def commander_section(self, front: Any) -> None:
                orchestration = front.orchestration(
                    profiles_path="/srv/shop/profiles",
                    profile_name="busy_hours",
                    control_enabled=True,
                )
                orchestration.commander(
                    frozen_users_path="/srv/shop/frozen_users"
                ).groups().group(name="stable")

        handler = ConfigurationHandler(ProfiledPoolConfig)

        assert handler.orchestration_kwargs("shop") == {
            "profiles_path": "/srv/shop/profiles",
            "profile_name": "busy_hours",
            "control_enabled": True,
        }
        assert handler.commander_kwargs("shop") == {
            "frozen_users_path": "/srv/shop/frozen_users"
        }
        assert set(handler.group_kwargs("shop")) == {"stable"}

    def test_an_orchestration_that_declares_no_commander_reads_as_none(self) -> None:
        """The node alone: its words are there, and there is no vertex to build."""

        class BareOrchestrationConfig(SpaPoolConfig):
            def commander_section(self, front: Any) -> None:
                front.orchestration(control_enabled=True)

        handler = ConfigurationHandler(BareOrchestrationConfig)

        assert handler.orchestration_kwargs("shop") == {"control_enabled": True}
        assert handler.commander_kwargs("shop") is None
        assert handler.group_kwargs("shop") == {}

    def test_the_recipe_elects_the_group_that_receives_a_newcomer(self) -> None:
        kwargs = ConfigurationHandler(ElectedGroupConfig).commander_kwargs("shop")

        assert kwargs["default_group"] == "canary"

    def test_the_vertex_reads_its_own_policies_and_not_the_workers_path(self) -> None:
        handler = ConfigurationHandler(SpaPoolConfig)

        assert handler.commander_kwargs("shop") == {
            "frozen_users_path": "/srv/shop/frozen_users",
            "memory_max_percent": 75.0,
            "machine_memory_alarm_percent": 85.0,
            "orchestration_log_path": "/srv/shop/logs/orchestration.log",
            "orchestration_log_max_bytes": 2_000_000,
            "orchestration_log_backup_count": 3,
            "user_expiry_hours": 480.0,
            "guest_expiry_hours": 12.0,
        }

    def test_a_group_reads_its_policies_the_two_paths_and_its_childs_identity(self) -> None:
        groups = ConfigurationHandler(SpaPoolConfig).group_kwargs("shop")

        assert set(groups) == {"stable", "canary"}
        assert groups["stable"] == {
            "frozen_users_path": "/srv/shop/frozen_users",
            "instance_dir": "/srv/shop/instance",
            "memory_max_percent": 80.0,
            "worker_memory_max_percent": 40.0,
            "occupancy_max_percent": 70.0,
            "restart_occupancy_max_percent": 90.0,
            "reception_reserved_percent": 30.0,
            "new_user_occupancy_percent": 4.0,
            "newcomer_reserve_count": 2,
            "worker_max_users": 16,
            # The retirement's quiet is a policy of the GROUP (#43): how long
            # the CPU must stay silent before the closure judge resumes.
            "cpu_retirement_quiet_seconds": 75.0,
            # The silence is the GROUP's own policy: it is the rung that judges
            # who has gone quiet, and the child measures nothing.
            "user_idle_freeze_minutes": 45.0,
            "entry_module": "genro_asgi.spa.orchestration.worker_entry",
            "executable": "/srv/shop/.venvs/stable/bin/python",
            "worker_class": "myshop.app:ShopWorker",
            "main_threadpool_size": 8,
            "aux_threadpool_size": 2,
            # The one key the CHILD reads is his: his group's name.
            "worker_kwargs": {"site_path": "/srv/shop", "group": "stable"},
            # And how its workers are born: a template builds the engine once and
            # forks every one of them out of it.
            "engine_factory": "myshop.app:ShopEngineFactory",
            "engine_kwargs": {"source": "/srv/shop"},
        }

    def test_a_group_that_declares_only_its_child_leaves_every_default_alone(self) -> None:
        canary = ConfigurationHandler(SpaPoolConfig).group_kwargs("shop")["canary"]

        assert canary == {
            "frozen_users_path": "/srv/shop/frozen_users",
            "instance_dir": "/srv/shop/instance",
            "entry_module": "genro_asgi.spa.orchestration.worker_entry",
            "worker_kwargs": {"group": "canary"},
        }

    def test_the_pool_keys_reach_the_vertex_and_the_group_that_read_them(self, tmp_path) -> None:
        groups = ConfigurationHandler(SpaPoolConfig).group_kwargs("shop")
        commander_kwargs = ConfigurationHandler(SpaPoolConfig).commander_kwargs("shop")
        commander_kwargs["frozen_users_path"] = tmp_path / "frozen_users"
        commander_kwargs["orchestration_log_path"] = tmp_path / "orchestration.log"

        commander = SpaCommander(**commander_kwargs)
        group = GroupHandler(
            commander,
            "stable",
            memory_concession_bytes=commander.memory_concession_bytes,
            **dict(
                groups["stable"],
                instance_dir=tmp_path / "instance",
                frozen_users_path=tmp_path / "frozen_users",
            ),
        )

        assert commander.memory_max_percent == 75.0
        assert commander.machine_memory_alarm_percent == 85.0
        assert commander.user_expiry_hours == 480.0
        assert commander.guest_expiry_hours == 12.0
        # The three log keys land on the rotating handler itself, not just in
        # the kwargs dict: the file, its size, how many are kept.
        attached, = logging.getLogger(ORDERS_LOGGER_NAME).handlers
        assert attached.maxBytes == 2_000_000
        assert attached.backupCount == 3
        assert group.occupancy_max_percent == 70.0
        assert group.restart_occupancy_max_percent == 90.0
        assert group.reception_reserved_percent == 30.0
        assert group.new_user_occupancy_percent == 4.0
        assert group.newcomer_reserve_count == 2
        assert group.worker_max_users == 16
        assert group.memory_max_percent == 80.0
        assert group.worker_memory_max_percent == 40.0
        # The new word of #43 lands on the built group, exactly as declared.
        assert group.cpu_retirement_quiet_seconds == 75.0
        # The silence it judges is its own, and never travels down to the child.
        assert group.user_idle_freeze_minutes == 45.0
        # And what the group hands its workers is what a WorkerHandler is built
        # with: the identity of the child, the two paths, the child's own kwargs.
        assert group.worker_settings == {
            "frozen_users_path": tmp_path / "frozen_users",
            "instance_dir": tmp_path / "instance",
            "entry_module": "genro_asgi.spa.orchestration.worker_entry",
            "executable": "/srv/shop/.venvs/stable/bin/python",
            "worker_class": "myshop.app:ShopWorker",
            "main_threadpool_size": 8,
            "aux_threadpool_size": 2,
            "worker_kwargs": {"site_path": "/srv/shop", "group": "stable"},
        }
        # The two engine keys are NOT among those: they are the group's own, and
        # what they reach is the template it owns.
        assert group.template.launch_payload == {
            "name": "template-stable",
            "engine_factory": "myshop.app:ShopEngineFactory",
            "kwargs": {"source": "/srv/shop"},
        }

    def test_a_group_that_declares_no_engine_factory_owns_no_template(self, tmp_path) -> None:
        groups = ConfigurationHandler(SpaPoolConfig).group_kwargs("shop")
        commander = SpaCommander(tmp_path / "frozen_users")

        group = GroupHandler(
            commander,
            "canary",
            memory_concession_bytes=commander.memory_concession_bytes,
            **dict(
                groups["canary"],
                instance_dir=tmp_path / "instance",
                frozen_users_path=tmp_path / "frozen_users",
            ),
        )

        assert group.template is None

    def test_a_site_with_no_pool_declares_no_orchestration_at_all(self) -> None:
        handler = ConfigurationHandler(TwoAppConfig)
        assert handler.orchestration_kwargs("shop") is None
        assert handler.commander_kwargs("shop") is None
        assert handler.group_kwargs("shop") == {}

    def test_the_pool_section_travels_through_a_real_server(self) -> None:
        server = AsgiServer(config=SpaPoolConfig)
        assert server.config.commander_kwargs("shop")["memory_max_percent"] == 75.0
        assert set(server.config.group_kwargs("shop")) == {"stable", "canary"}

    def test_a_group_outside_its_collection_is_rejected_by_the_grammar(self) -> None:
        class StrayGroupConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                front = cfg.applications().application(
                    code="shop", mount="", app_class=SpaApplication
                )
                front.orchestration().commander().group(name="stable")

        with pytest.raises(ValueError, match="parent"):
            ConfigurationHandler(StrayGroupConfig)

    def test_the_pool_is_not_a_section_of_the_site_dialect(self) -> None:
        """A pool belongs to the front that owns it, so the root has no words for it."""

        class TopLevelPoolConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().orchestration()

        with pytest.raises(AttributeError, match="orchestration"):
            ConfigurationHandler(TopLevelPoolConfig)


class ParametrizedShop(ShopApp):
    """An app whose grammar is the inherited minimal one (``parameters``)."""

    code = "shop"


class TestMountedAppGrammar:
    """``application(app_class=...)`` mounts ``app_class.grammar`` for the subtree."""

    def test_the_apps_own_subtree_is_read_through_the_handler(self) -> None:
        class ParamConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                cfg = root.configuration()
                cfg.server(host="127.0.0.1", port=8000)
                shop = cfg.applications(default="shop").application(
                    code="shop", mount="", app_class=ParametrizedShop
                )
                shop.parameters(theme="dark", max_items=10)

        server = AsgiServer(config=ParamConfig)
        assert server.config("applications.shop.parameters.theme") == "dark"
        assert server.config("applications.shop.parameters.max_items") == 10

    def test_the_envelope_attributes_are_the_apps_constructor_kwargs(self) -> None:
        class KwargConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().applications().application(
                    code="outlet", mount="outlet", app_class=ShopApp
                )

        server = AsgiServer(config=KwargConfig)
        assert server.applications["outlet"].mount == "outlet"

    def test_an_undeclared_child_of_the_mounted_grammar_raises(self) -> None:
        class StrayConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                shop = root.configuration().applications().application(
                    code="shop", mount="", app_class=ShopApp
                )
                shop.catalog(title="x")

        with pytest.raises(AttributeError):
            ConfigurationHandler(StrayConfig)


class TestReadStack:
    """The four layers, on this dialect."""

    def test_written_value_wins(self) -> None:
        assert ConfigurationHandler(TwoAppConfig)("server.port") == 9100

    def test_signature_default_is_resolved_at_read_time(self) -> None:
        class ProviderConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().authentication().oidc().provider(
                    code="corp", issuer="https://idp.example.com"
                )

        handler = ConfigurationHandler(ProviderConfig)
        assert handler("authentication.oidc.corp.scopes") == "openid email profile"

    def test_call_site_default_applies_to_an_unwritten_value(self) -> None:
        handler = ConfigurationHandler(TwoAppConfig)
        assert handler("server.max_threads", default=7) == 7

    def test_a_missing_path_is_a_noisy_key_error(self) -> None:
        handler = ConfigurationHandler(TwoAppConfig)
        with pytest.raises(KeyError, match="server.tls"):
            handler("server.tls")


def write_defaults_recipe(
    base_dir: Path, filename: str = "config.py", mount_path: str = "/srv/deployment"
) -> Path:
    """A recipe file in *base_dir* deviating from the package defaults.

    ``mount_path`` needs to be a directory that EXISTS only where the recipe
    reaches a real ``StorageManager`` — genro-storage's local backend validates
    the anchor at ``configure()`` time, never at recipe time.
    """
    path = base_dir / filename
    path.write_text(
        "from typing import Any\n"
        "\n"
        "from genro_asgi.config import BaseConfiguration\n"
        "\n"
        "\n"
        "class DeploymentConfiguration(BaseConfiguration):\n"
        "    def server_section(self, cfg: Any) -> None:\n"
        "        cfg.server(host='10.0.0.1', port=9999)\n"
        "\n"
        "    def storage_mounts(self, section: Any) -> None:\n"
        f"        section.local(name='site', base_path={mount_path!r})\n",
        encoding="utf-8",
    )
    return path


class TestParentRecipes:
    """``BaseConfiguration`` + the declared defaults layer + the site recipe.

    ``DefaultConfig.parents_for()`` is what ``AsgiServer`` hands the handler: the
    package defaults lowest, the recipe's own defaults source over them, the site
    recipe last and winning.
    """

    def test_a_site_inherits_the_default_site_mount_and_adds_its_key(
        self, tmp_path: Path
    ) -> None:
        class KeyOnlyConfig(BaseConfiguration):
            storage_key = "k1"

        parents = DefaultConfig(tmp_path).parents_for(KeyOnlyConfig)
        mounts, storage_key = ConfigurationHandler(KeyOnlyConfig, parents=parents).storage_config()
        assert storage_key == "k1"
        assert mounts == [{**DEFAULT_SITE_MOUNT, "base_path": str(Path.cwd())}]

    def test_only_the_package_defaults_are_layered_without_a_defaults_recipe(
        self, tmp_path: Path
    ) -> None:
        assert DefaultConfig(tmp_path).parents_for(BaseConfiguration) == [BaseConfiguration]

    def test_the_conventional_recipe_joins_the_chain_when_its_file_exists(
        self, tmp_path: Path
    ) -> None:
        declared = write_defaults_recipe(tmp_path)
        assert DefaultConfig(tmp_path).parents_for(BaseConfiguration) == [
            BaseConfiguration,
            declared,
        ]

    def test_the_defaults_layer_overrides_the_base_and_loses_to_the_site(
        self, tmp_path: Path
    ) -> None:
        write_defaults_recipe(tmp_path)

        class SiteConfig(AsgiConfigBuilder):
            """Says one thing only: the layers under it supply everything else."""

            def main(self, root: Any) -> None:
                root.configuration().server(host="127.0.0.1")

        parents = DefaultConfig(tmp_path).parents_for(SiteConfig)
        handler = ConfigurationHandler(SiteConfig, parents=parents)
        assert handler("server.host") == "127.0.0.1"      # the site wins
        assert handler("server.port") == 9999             # the defaults layer holds
        mounts, _ = handler.storage_config()              # over the package default
        assert mounts == [{**DEFAULT_SITE_MOUNT, "base_path": "/srv/deployment"}]

    def test_a_key_only_section_without_parents_yields_no_mount(self) -> None:
        """The guard: a storage section with no mount child is not a crash."""

        class KeyOnlyConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().storage(app=StorageManager, storage_key="k1")

        mounts, storage_key = ConfigurationHandler(KeyOnlyConfig).storage_config()
        assert mounts == []
        assert storage_key == "k1"


class TestDeclaredDefaultConfig:
    """``default_config`` on the recipe: which defaults source, declared by the recipe.

    Unset (or ``True``) takes the conventional ``<base_dir>/config.py`` when it is
    there, ``False`` takes nothing, a path takes that file and must find it.
    """

    def test_unset_takes_the_conventional_file(self, tmp_path: Path) -> None:
        declared = write_defaults_recipe(tmp_path)

        class SiteConfig(BaseConfiguration):
            pass

        assert SiteConfig.default_config is None
        assert DefaultConfig(tmp_path).parents_for(SiteConfig) == [BaseConfiguration, declared]

    def test_true_reads_the_conventional_file_like_an_unset_attribute(
        self, tmp_path: Path
    ) -> None:
        declared = write_defaults_recipe(tmp_path)

        class SiteConfig(BaseConfiguration):
            default_config = True

        assert DefaultConfig(tmp_path).parents_for(SiteConfig) == [BaseConfiguration, declared]

    def test_false_refuses_the_layer_even_when_the_file_is_there(self, tmp_path: Path) -> None:
        write_defaults_recipe(tmp_path)

        class SiteConfig(BaseConfiguration):
            default_config = False

        assert DefaultConfig(tmp_path).parents_for(SiteConfig) == [BaseConfiguration]

    def test_an_explicit_path_is_layered_from_wherever_it_lives(self, tmp_path: Path) -> None:
        elsewhere = write_defaults_recipe(tmp_path, filename="shared_defaults.py")

        class SiteConfig(BaseConfiguration):
            default_config = str(elsewhere)

        parents = DefaultConfig(tmp_path).parents_for(SiteConfig)
        assert parents == [BaseConfiguration, elsewhere]
        assert ConfigurationHandler(SiteConfig, parents=parents)("server.port") == 9999

    def test_an_explicit_path_that_does_not_exist_is_a_config_error(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent.py"

        class SiteConfig(BaseConfiguration):
            default_config = missing

        with pytest.raises(ConfigError, match="does not exist"):
            DefaultConfig(tmp_path).parents_for(SiteConfig)

    def test_a_config_py_source_declares_its_own_default_config(self, tmp_path: Path) -> None:
        """The attribute is read off the recipe class a path source defines."""
        write_defaults_recipe(tmp_path)
        site = tmp_path / "site.py"
        site.write_text(
            "from genro_asgi.config import BaseConfiguration\n"
            "\n"
            "\n"
            "class SiteConfiguration(BaseConfiguration):\n"
            "    default_config = False\n",
            encoding="utf-8",
        )
        assert DefaultConfig(tmp_path).parents_for(site) == [BaseConfiguration]

    def test_a_config_py_source_must_define_exactly_one_recipe(self, tmp_path: Path) -> None:
        site = tmp_path / "site.py"
        site.write_text("value = 1\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="exactly one ConfigBuilder subclass"):
            DefaultConfig(tmp_path).parents_for(site)


class TestHomeResolution:
    """``base_dir``: the explicit argument, then ``GENRO_ASGI_HOME``, then ``~``."""

    def test_the_env_var_is_the_default_base_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(HOME_ENV, str(tmp_path))
        assert DefaultConfig().base_dir == tmp_path
        assert DefaultConfig().path == tmp_path / "config.py"

    def test_the_explicit_argument_wins_over_the_env_var(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(HOME_ENV, str(tmp_path / "from_env"))
        assert DefaultConfig(tmp_path / "explicit").base_dir == tmp_path / "explicit"

    def test_the_home_directory_is_the_last_resort(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(HOME_ENV, raising=False)
        assert DefaultConfig().base_dir == Path.home() / ".genroasgi"

    def test_the_cli_registry_follows_the_same_variable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(HOME_ENV, str(tmp_path))
        assert AppsRegistry().base_dir == tmp_path
        assert AppsRegistry().apps_dir == tmp_path / "apps"


class TestServerLayersTheDeclaredDefaults:
    """The production wiring: ``AsgiServer(config=...)`` layers what the recipe declares."""

    def test_the_server_reads_the_conventional_defaults_recipe(
        self, genro_asgi_home: Path
    ) -> None:
        write_defaults_recipe(genro_asgi_home, mount_path=str(genro_asgi_home))

        class SiteConfig(AsgiConfigBuilder):
            def main(self, root: Any) -> None:
                root.configuration().server(host="127.0.0.1")

        server = AsgiServer(config=SiteConfig)
        assert server.config is not None
        assert server.config("server.host") == "127.0.0.1"      # the site wins
        assert server.config("server.port") == 9999             # from the defaults layer

    def test_a_recipe_declining_the_layer_sees_only_the_package_defaults(
        self, genro_asgi_home: Path
    ) -> None:
        write_defaults_recipe(genro_asgi_home)

        class SiteConfig(BaseConfiguration):
            default_config = False

        server = AsgiServer(config=SiteConfig)
        assert server.config is not None
        with pytest.raises(KeyError, match="server.port"):
            server.config("server.port")
