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

"""Tests for ``ServerApplication`` and the automatic ``_server`` mount (D4)."""

from __future__ import annotations

import json

import pytest
from genro_routes import RoutingClass, route

from genro_asgi_core import AsgiServer, BaseApplication, ServerApplication


class MinimalProfileServer(AsgiServer):
    """Test-only composition exercising the MINIMAL profile seam (D4/D6)."""

    server_app_profile = "minimal"


class DemoSection(RoutingClass):
    """A tiny system section to exercise ``attach_section``."""

    def __init__(self, application: ServerApplication) -> None:
        self.application = application

    @route()
    def ping(self) -> dict[str, bool]:
        return {"pong": True}


class TestAutoMount:
    def test_hand_built_server_mounts_server_app(self) -> None:
        server = AsgiServer(primary=BaseApplication())
        assert "_server" in server.mounts
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.mount_name == "_server"
        assert app.profile == "full"
        assert app.server is server

    def test_mount_hook_is_idempotent(self) -> None:
        server = AsgiServer(primary=BaseApplication())
        app = server.mounts["_server"]
        server._mount_server_app()
        assert server.mounts["_server"] is app


class TestServerEndpoints:
    async def test_index_answers_at_server_root(
        self, http_request, response_status, response_body
    ) -> None:
        server = AsgiServer(primary=BaseApplication())
        sent = await http_request(server, "/_server/")
        assert response_status(sent) == 200
        data = json.loads(response_body(sent))
        assert data["profile"] == "full"
        assert data["sections"] == ["auth"]

    async def test_meta_schema_json_is_exposed(
        self, http_request, response_status, response_body
    ) -> None:
        server = AsgiServer(primary=BaseApplication())
        sent = await http_request(server, "/_server/_meta/schema_json")
        assert response_status(sent) == 200
        doc = json.loads(response_body(sent))
        assert doc["openapi"] == "3.1.0"
        assert doc["info"]["title"] == "genro-asgi-core server endpoints"


class TestProfiles:
    def test_unknown_profile_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown _server profile"):
            ServerApplication(profile="bogus")

    async def test_full_profile_serves_docs(self, http_request, response_status) -> None:
        server = AsgiServer(primary=BaseApplication())
        sent = await http_request(server, "/_server/_meta/docs")
        assert response_status(sent) == 200

    async def test_minimal_profile_exposes_only_the_minimal_surface(
        self, http_request, response_status
    ) -> None:
        server = MinimalProfileServer(primary=BaseApplication())
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.profile == "minimal"
        assert app.docs_style == "off"
        sent = await http_request(server, "/_server/_meta/docs")
        assert response_status(sent) == 404
        sent = await http_request(server, "/_server/")
        assert response_status(sent) == 200


class TestSections:
    async def test_attach_section_registers_and_routes(
        self, http_request, response_status, response_body
    ) -> None:
        server = AsgiServer(primary=BaseApplication())
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        app.attach_section(DemoSection(app), name="demo")
        assert app.sections["demo"] is not None
        sent = await http_request(server, "/_server/demo/ping")
        assert response_status(sent) == 200
        assert json.loads(response_body(sent)) == {"pong": True}
        sent = await http_request(server, "/_server/")
        data = json.loads(response_body(sent))
        assert data["sections"] == ["auth", "demo"]
