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

from genro_asgi import AsgiServer, BaseApplication, ServerApplication
from genro_asgi.applications.server_sections import INSPECTOR_ENV_VAR


@pytest.fixture(autouse=True)
def _inspector_unmounted(monkeypatch):
    """The section list these tests photograph is the default one.

    The inspector is opt-in and read from the environment at construction, so a
    developer who exported ``GNR_ASGI_INSPECTOR`` to open the page would
    otherwise see two contract tests fail for a reason unrelated to his work.
    """
    monkeypatch.delenv(INSPECTOR_ENV_VAR, raising=False)


class DemoSection(RoutingClass):
    """A tiny system section to exercise ``attach_section``."""

    def __init__(self, application: ServerApplication) -> None:
        self.application = application

    @route()
    def ping(self) -> dict[str, bool]:
        return {"pong": True}


class TestAutoMount:
    def test_hand_built_server_registers_the_server_app(self) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        assert "_server" in server.applications
        app = server.applications["_server"]
        assert isinstance(app, ServerApplication)
        assert app.mount == "_server"
        assert app.server is server

    def test_registration_hook_is_idempotent(self) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        app = server.applications["_server"]
        server._register_server_app()
        assert server.applications["_server"] is app

    def test_identity_is_declared_on_the_class(self) -> None:
        # D4: the system code and mount are declared, not configured — three
        # cross-file references hardcode /_server/..., so moving the app would
        # 404 them silently.
        app = ServerApplication()
        assert (app.code, app.mount) == ("_server", "_server")


class TestServerEndpoints:
    async def test_index_answers_at_server_root(
        self, http_request, response_status, response_body
    ) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        sent = await http_request(server, "/_server/")
        assert response_status(sent) == 200
        data = json.loads(response_body(sent))
        assert data["sections"] == ["auth", "monitor", "tasks", "tokens", "users"]

    async def test_meta_schema_json_is_exposed(
        self, http_request, response_status, response_body
    ) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        sent = await http_request(server, "/_server/_meta/schema_json")
        assert response_status(sent) == 200
        doc = json.loads(response_body(sent))
        assert doc["openapi"] == "3.1.0"
        assert doc["info"]["title"] == "genro-asgi server endpoints"

    async def test_login_schema_hides_the_injected_request_and_is_post(
        self, http_request, response_body
    ) -> None:
        # REVIEW #6: the injected ``_request`` must NOT surface in the public
        # request body, and the route is POST by declaration (openapi_method).
        server = AsgiServer(applications=[BaseApplication(mount="")])
        sent = await http_request(server, "/_server/_meta/schema_json")
        doc = json.loads(response_body(sent))
        login = doc["paths"]["/login"]
        assert set(login) == {"post"}
        props = login["post"]["requestBody"]["content"]["application/json"]["schema"][
            "properties"
        ]
        assert set(props) == {"identity", "password"}
        assert "_request" not in props and "request" not in props


class TestDocs:
    async def test_server_serves_the_docs_page(self, http_request, response_status) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        sent = await http_request(server, "/_server/_meta/docs")
        assert response_status(sent) == 200


class TestSections:
    async def test_attach_section_registers_and_routes(
        self, http_request, response_status, response_body
    ) -> None:
        server = AsgiServer(applications=[BaseApplication(mount="")])
        app = server.applications["_server"]
        assert isinstance(app, ServerApplication)
        app.attach_section(DemoSection(app), name="demo")
        assert app.sections["demo"] is not None
        sent = await http_request(server, "/_server/demo/ping")
        assert response_status(sent) == 200
        assert json.loads(response_body(sent)) == {"pong": True}
        sent = await http_request(server, "/_server/")
        data = json.loads(response_body(sent))
        assert data["sections"] == ["auth", "demo", "monitor", "tasks", "tokens", "users"]
