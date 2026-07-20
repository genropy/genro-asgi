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

"""Projection tests (Macro 2 Phase 7): (config, role) materialization (D15).

ONE shared recipe describes the whole site (two apps, middleware, auth,
groups); every role materializes its own slice from the SAME config object —
D15's "dev and prod use the SAME config, each process its slice". Requests
are driven at the ASGI level (no uvicorn), the same style as
``test_config.py``.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from genro_asgi_core import (
    AsgiConfigBuilder,
    AsgiServer,
    BaseApplication,
    ConfigurationHandler,
)
from genro_asgi_core.middleware.base import BaseMiddleware
from genro_asgi_core.types import Message, Receive, Scope, Send


class ShopApp(BaseApplication):
    """Default primary app: answers ``shop``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"shop"})


class ErpApp(BaseApplication):
    """Grouped app hosted by the worker/batch roles: answers ``erp``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"erp"})


class SiteConfig(AsgiConfigBuilder):
    """The whole site: two apps (shop default, erp with groups), cors, basic auth."""

    def main(self, root: Any) -> None:
        root.server(host="0.0.0.0", port=9200)
        root.middleware(cors=True)
        root.auth(basic={"admin": {"password": "secret", "tags": "admin"}})
        apps = root.applications(default="shop")
        apps.application(code="shop", app_class=ShopApp)
        erp = apps.application(code="erp", app_class=ErpApp)
        groups = erp.groups(default="stable")
        groups.group(code="stable", workers=2)


@pytest.fixture
def handler() -> ConfigurationHandler:
    """One handler over ONE built site config, materialized per-role by the tests."""
    return ConfigurationHandler(SiteConfig(name="site"))


def basic_header(username: str, password: str) -> list[tuple[bytes, bytes]]:
    """An ``Authorization: Basic`` header list for the given credentials."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return [(b"authorization", f"Basic {token}".encode())]


def chain_types(server: AsgiServer) -> list[str]:
    """The class names of the middlewares in the server's chain, outermost first."""
    names: list[str] = []
    node: object = server.middleware_chain
    while isinstance(node, BaseMiddleware):
        names.append(type(node).__name__)
        node = node.app
    return names


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


class TestRootRole:
    def test_root_mounts_both_apps_arms_chain_and_auth(self, handler: ConfigurationHandler):
        server = handler.materialize(role="root")
        assert isinstance(server.primary, ShopApp)
        assert set(server.mounts) == {"erp"}
        types = chain_types(server)
        assert "CORSMiddleware" in types
        assert "ErrorMiddleware" in types
        avatar = server.authenticate({"headers": basic_header("admin", "secret")})
        assert avatar is not None
        assert avatar.identity == "admin"
        assert server.config_host == "0.0.0.0"
        assert server.config_port == 9200

    def test_root_with_app_raises_typeerror(self, handler: ConfigurationHandler):
        with pytest.raises(TypeError):
            handler.materialize(role="root", app="erp")


class TestWorkerRole:
    def test_worker_hosts_only_its_app_as_primary(self, handler: ConfigurationHandler):
        server = handler.materialize(role="worker", app="erp")
        assert isinstance(server, AsgiServer)
        assert isinstance(server.primary, ErpApp)
        assert server.primary.mount_name == ""
        assert server.mounts == {}

    def test_worker_has_no_chain_no_auth_no_listener_address(
        self, handler: ConfigurationHandler
    ):
        server = handler.materialize(role="worker", app="erp")
        assert chain_types(server) == []
        assert server.authenticate({"headers": []}) is None
        assert server.config_host is None
        assert server.config_port is None

    async def test_worker_still_serves_its_app(self, handler: ConfigurationHandler):
        server = handler.materialize(role="worker", app="erp")
        assert await http_get(server, "/") == b"erp"

    async def test_worker_attaches_no_session(self, handler: ConfigurationHandler):
        server = handler.materialize(role="worker", app="erp")
        scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request"}

        async def send(message: Message) -> None:
            sent.append(message)

        await server(scope, receive, send)
        assert scope.get("session") is None
        assert server.session(scope) is None

    def test_worker_without_app_raises_typeerror(self, handler: ConfigurationHandler):
        with pytest.raises(TypeError):
            handler.materialize(role="worker")

    def test_worker_with_undeclared_app_raises_valueerror(self, handler: ConfigurationHandler):
        with pytest.raises(ValueError, match="crm"):
            handler.materialize(role="worker", app="crm")


class TestBatchRole:
    def test_batch_same_section_cut_as_worker(self, handler: ConfigurationHandler):
        server = handler.materialize(role="batch", app="erp")
        assert isinstance(server, AsgiServer)
        assert isinstance(server.primary, ErpApp)
        assert server.mounts == {}
        assert chain_types(server) == []
        assert server.authenticate({"headers": []}) is None
        assert server.config_host is None
        assert server.config_port is None

    def test_batch_without_app_raises_typeerror(self, handler: ConfigurationHandler):
        with pytest.raises(TypeError):
            handler.materialize(role="batch")


class TestUnknownRole:
    def test_unknown_role_raises_valueerror_naming_it(self, handler: ConfigurationHandler):
        with pytest.raises(ValueError, match="manager"):
            handler.materialize(role="manager")


class TestSameConfigEveryRole:
    def test_one_config_object_serves_every_role(self, handler: ConfigurationHandler):
        root = handler.materialize(role="root")
        worker = handler.materialize(role="worker", app="erp")
        batch = handler.materialize(role="batch", app="shop")
        assert isinstance(root.primary, ShopApp) and set(root.mounts) == {"erp"}
        assert isinstance(worker.primary, ErpApp) and worker.mounts == {}
        assert isinstance(batch.primary, ShopApp) and batch.mounts == {}
