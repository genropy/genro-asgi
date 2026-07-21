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

"""Password login surface tests (core 1d wave 1, Phase 4).

The flow is driven through a full hand-built ``AsgiServer`` at the ASGI level
(no uvicorn), the same driving style as ``test_session.py``: JSON POST to
``/_server/login`` verifies against a seeded in-memory ``UserStore``, promotes
the session (``promote_session``) and the ``Set-Cookie`` for the change rides
the response via ``SessionMiddleware`` (option A) — handlers never touch
cookies. The HTML page, the public ``login_methods``, ``logout``, the
``AuthMethod``/``AuthSection`` contract and the ``safe_next_path`` guard are
covered alongside.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from genro_asgi_core import (
    AsgiServer,
    AuthSection,
    BaseApplication,
    PasswordMethod,
    ServerApplication,
    UserStore,
)
from genro_asgi_core.auth.auth_method import safe_next_path
from genro_asgi_core.types import Message, Scope


class MemoryUserStore(UserStore):
    """In-memory ``UserStore`` backend: the contract suite over a plain dict."""

    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def load_all(self) -> list[dict[str, Any]]:
        return list(self._records.values())

    def get(self, identity: str) -> dict[str, Any] | None:
        return self._records.get(identity)

    def save(self, record: dict[str, Any]) -> None:
        self._records[record["identity"]] = record

    def delete(self, identity: str) -> bool:
        return self._records.pop(identity, None) is not None


class MinimalProfileServer(AsgiServer):
    """Test-only composition exercising the MINIMAL profile seam (D4/D6)."""

    server_app_profile = "minimal"


def make_server(with_users: bool = True) -> AsgiServer:
    """A full hand-built server; ``with_users`` seeds alice/wonder on a user store."""
    server = AsgiServer(primary=BaseApplication())
    if with_users:
        store = MemoryUserStore()
        store.save(
            {
                "identity": "alice",
                "password_hash": store.hash_password("wonder"),
                "tags": ["admin"],
                "enabled": True,
            }
        )
        store.save(
            {
                "identity": "mallory",
                "password_hash": store.hash_password("evil"),
                "tags": [],
                "enabled": False,
            }
        )
        server.user_store = store
    return server


async def drive(
    server: AsgiServer,
    path: str,
    method: str = "GET",
    cookie: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[Scope, list[Message]]:
    """Drive one request through ``server`` at the ASGI level (JSON body when given)."""
    headers: list[tuple[bytes, bytes]] = []
    raw = b""
    if body is not None:
        headers.append((b"content-type", b"application/json"))
        raw = json.dumps(body).encode()
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    path, _, query = path.partition("?")
    scope: Scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query.encode(),
        "headers": headers,
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": raw, "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    return scope, sent


def response_status(sent: list[Message]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def response_headers(sent: list[Message]) -> dict[bytes, bytes]:
    start = next(m for m in sent if m["type"] == "http.response.start")
    return {name: value for name, value in start["headers"] if name != b"set-cookie"}


def response_body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def json_body(sent: list[Message]) -> Any:
    return json.loads(response_body(sent))


def set_cookie_value(sent: list[Message]) -> str | None:
    start = next(m for m in sent if m["type"] == "http.response.start")
    for name, value in start["headers"]:
        if name == b"set-cookie":
            return value.decode()
    return None


def cookie_token(sent: list[Message]) -> str:
    cookie = set_cookie_value(sent)
    assert cookie is not None
    return cookie.split(";")[0].split("=", 1)[1]


class TestLoginHappyPath:
    async def test_login_promotes_the_session_and_sets_the_cookie(self) -> None:
        server = make_server()
        anonymous = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/login",
            "POST",
            cookie=f"session_id={anonymous.id}",
            body={"identity": "alice", "password": "wonder"},
        )
        assert response_status(sent) == 200
        payload = json_body(sent)
        assert payload["identity"] == "alice"
        assert payload["tags"] == ["admin"]
        assert payload["session_id"] != anonymous.id
        assert cookie_token(sent) == payload["session_id"]
        promoted = server.session_store.get(payload["session_id"])
        assert promoted is not None
        assert promoted.avatar is not None
        assert promoted.avatar.identity == "alice"
        assert promoted.avatar.tags == ["admin"]

    async def test_login_accepts_the_pages_form_encoded_post(self) -> None:
        server = make_server()
        anonymous = server.session_store.create()
        raw = b"identity=alice&password=wonder"
        headers = [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"cookie", f"session_id={anonymous.id}".encode()),
        ]
        scope: Scope = {
            "type": "http",
            "method": "POST",
            "path": "/_server/login",
            "query_string": b"",
            "headers": headers,
        }
        sent: list[Message] = []

        async def receive() -> Message:
            return {"type": "http.request", "body": raw, "more_body": False}

        async def send(message: Message) -> None:
            sent.append(message)

        await server(scope, receive, send)
        payload = json_body(sent)
        assert payload["identity"] == "alice"
        assert cookie_token(sent) == payload["session_id"]

    async def test_login_on_first_contact_issues_the_promoted_cookie(self) -> None:
        server = make_server()
        _, sent = await drive(
            server,
            "/_server/login",
            "POST",
            body={"identity": "alice", "password": "wonder"},
        )
        payload = json_body(sent)
        assert cookie_token(sent) == payload["session_id"]
        promoted = server.session_store.get(payload["session_id"])
        assert promoted is not None and promoted.avatar is not None


class TestLoginFailures:
    async def test_invalid_credentials_answer_the_error_and_no_cookie(self) -> None:
        server = make_server()
        anonymous = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/login",
            "POST",
            cookie=f"session_id={anonymous.id}",
            body={"identity": "alice", "password": "nope"},
        )
        assert response_status(sent) == 200
        assert json_body(sent) == {"error": "Invalid credentials"}
        assert set_cookie_value(sent) is None

    async def test_disabled_user_never_authenticates(self) -> None:
        server = make_server()
        anonymous = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/login",
            "POST",
            cookie=f"session_id={anonymous.id}",
            body={"identity": "mallory", "password": "evil"},
        )
        assert json_body(sent) == {"error": "Invalid credentials"}
        assert set_cookie_value(sent) is None

    async def test_missing_credentials_answer_the_error(self) -> None:
        server = make_server()
        anonymous = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/login",
            "POST",
            cookie=f"session_id={anonymous.id}",
            body={"identity": "alice"},
        )
        assert json_body(sent) == {"error": "Identity and password are required"}
        assert set_cookie_value(sent) is None

    async def test_server_without_a_user_store_answers_the_error(self) -> None:
        server = make_server(with_users=False)
        anonymous = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/login",
            "POST",
            cookie=f"session_id={anonymous.id}",
            body={"identity": "alice", "password": "wonder"},
        )
        assert json_body(sent) == {"error": "Login is not available"}
        assert set_cookie_value(sent) is None


class TestLoginPage:
    async def test_login_page_serves_the_descriptor_driven_html(self) -> None:
        server = make_server()
        _, sent = await drive(server, "/_server/login_page")
        assert response_status(sent) == 200
        assert response_headers(sent)[b"content-type"].startswith(b"text/html")
        page = response_body(sent).decode()
        assert "<title>Sign in</title>" in page
        assert "/_server/login_methods" in page

    async def test_login_page_binds_the_next_query_param(self) -> None:
        server = make_server()
        _, sent = await drive(server, "/_server/login_page?next=/app/page")
        assert response_status(sent) == 200


class TestLoginMethods:
    async def test_login_methods_is_public_and_lists_the_password_descriptor(self) -> None:
        server = make_server(with_users=False)
        _, sent = await drive(server, "/_server/login_methods")
        assert response_status(sent) == 200
        assert json_body(sent) == {
            "methods": [
                {
                    "id": "password",
                    "kind": "form",
                    "label": "Sign in",
                    "action": "/_server/login",
                }
            ]
        }

    async def test_minimal_profile_has_no_login_methods(self) -> None:
        server = MinimalProfileServer(primary=BaseApplication())
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.auth_section is None
        _, sent = await drive(server, "/_server/login_methods")
        assert json_body(sent) == {"methods": []}


class TestLogout:
    async def test_logout_deletes_the_session(self) -> None:
        server = make_server(with_users=False)
        session = server.session_store.create()
        _, sent = await drive(
            server, "/_server/logout", "POST", body={"session_id": session.id}
        )
        assert json_body(sent) == {"status": "ok"}
        assert server.session_store.get(session.id) is None

    async def test_logout_without_a_session_id_still_answers_ok(self) -> None:
        server = make_server(with_users=False)
        _, sent = await drive(server, "/_server/logout", "POST", body={})
        assert json_body(sent) == {"status": "ok"}


class TestAuthMethodContract:
    def test_password_method_owns_zero_routes(self) -> None:
        server = make_server(with_users=False)
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.auth_section is not None
        method = app.auth_section.methods["password"]
        assert isinstance(method, PasswordMethod)
        assert method.route.nodes() == {}

    def test_password_method_is_registered_under_the_auth_section(self) -> None:
        server = make_server(with_users=False)
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert isinstance(app.auth_section, AuthSection)
        assert app.sections["auth"] is app.auth_section
        assert list(app.auth_section.methods) == ["password"]
        method = app.auth_section.methods["password"]
        assert method.application is app
        assert method.server is server

    def test_duplicate_method_id_is_rejected(self) -> None:
        server = make_server(with_users=False)
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        with pytest.raises(ValueError, match="already registered"):
            app.register_auth_method(PasswordMethod(app, "password"))


class TestSafeNextPath:
    @pytest.mark.parametrize(
        "value",
        ["/app/page", "/", "/a?b=c"],
    )
    def test_same_origin_relative_paths_pass(self, value: str) -> None:
        assert safe_next_path(value) == value

    @pytest.mark.parametrize(
        "value",
        [None, "", "app/page", "//evil.example", "https://evil.example", "/a\\b", "javascript:x"],
    )
    def test_unsafe_values_collapse_to_the_default(self, value: str | None) -> None:
        assert safe_next_path(value) == "/"
        assert safe_next_path(value, default="/home") == "/home"
