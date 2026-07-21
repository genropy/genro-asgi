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

"""Auth tests (Macro 2 Phases 5+9): AuthCore verification + §5.5 identity precedence.

Header verification (basic/bearer/jwt, wrong credentials → 401) is driven at
the ASGI level through an ``AuthMixin/MiddlewareMixin/BaseServer`` composition,
the same driving style as ``test_session.py``. The §5.5 precedence — header
identity wins over the session, an invalid header is a 401 with no fallback —
is exercised both by calling ``server.authenticate(scope)`` at app-dispatch
time and END-TO-END through the REAL combined chain (session middleware order
400 OUTSIDE auth 450) on the full
``AuthMixin/SessionMixin/MiddlewareMixin/BaseServer`` composition.
"""

from __future__ import annotations

import base64

import jwt
import pytest

from genro_asgi_core import (
    AuthCore,
    AuthMixin,
    Avatar,
    BaseApplication,
    BaseServer,
    Session,
    SessionMixin,
)
from genro_asgi_core.exceptions import HTTPUnauthorized
from genro_asgi_core.middleware import MiddlewareMixin
from genro_asgi_core.types import Message, Receive, Scope, Send


def basic_header(username: str, password: str) -> str:
    """The value of a Basic ``Authorization`` header for these credentials."""
    raw = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Basic {raw}"


AUTH_CONFIG = {
    "basic": {"alice": {"password": "wonderland", "tags": "admin,ops"}},
    "bearer": {"svc": {"token": "sk_live_xyz", "tags": "api"}},
    "jwt": [{"secret": "topsecret", "algorithm": "HS256"}],
}


# --- AuthCore unit ---


class TestAuthCore:
    def test_no_header_returns_none(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        assert core.authenticate({"headers": []}) is None

    def test_basic_ok_returns_avatar(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        scope: Scope = {"headers": [(b"authorization", basic_header("alice", "wonderland").encode())]}
        avatar = core.authenticate(scope)
        assert avatar is not None
        assert avatar.identity == "alice"
        assert avatar.tags == ["admin", "ops"]

    def test_bearer_ok_returns_avatar(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        scope: Scope = {"headers": [(b"authorization", b"Bearer sk_live_xyz")]}
        avatar = core.authenticate(scope)
        assert avatar is not None and avatar.identity == "svc"

    def test_jwt_ok_returns_avatar(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        token = jwt.encode({"sub": "carol", "tags": ["reader"]}, "topsecret", algorithm="HS256")
        scope: Scope = {"headers": [(b"authorization", f"Bearer {token}".encode())]}
        avatar = core.authenticate(scope)
        assert avatar is not None
        assert avatar.identity == "carol"
        assert avatar.tags == ["reader"]

    def test_wrong_password_raises_401(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        scope: Scope = {"headers": [(b"authorization", basic_header("alice", "nope").encode())]}
        with pytest.raises(HTTPUnauthorized) as excinfo:
            core.authenticate(scope)
        assert excinfo.value.status == 401
        assert (b"www-authenticate", b"Bearer") in excinfo.value.headers

    def test_malformed_header_raises_401_with_challenge(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        scope: Scope = {"headers": [(b"authorization", b"Basicabc123")]}
        with pytest.raises(HTTPUnauthorized) as excinfo:
            core.authenticate(scope)
        assert (b"www-authenticate", b"Bearer") in excinfo.value.headers

    def test_unknown_scheme_raises_401(self) -> None:
        core = AuthCore(**AUTH_CONFIG)
        scope: Scope = {"headers": [(b"authorization", b"Weird abc")]}
        with pytest.raises(HTTPUnauthorized):
            core.authenticate(scope)

    def test_missing_basic_password_config_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'password'"):
            AuthCore(basic={"bob": {"tags": "user"}})

    def test_missing_bearer_token_config_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'token'"):
            AuthCore(bearer={"svc": {"tags": "api"}})


# --- ASGI-level header authentication ---


class HeaderAuthServer(AuthMixin, MiddlewareMixin, BaseServer):
    """Header-only auth composition: no session capability."""


class EchoAuthApp(BaseApplication):
    """Echoes the identity of the avatar published on ``scope["auth"]``."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        auth = scope.get("auth")
        body = auth.identity.encode() if auth is not None else b"anonymous"
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": body})


async def http_get(
    server: BaseServer, authorization: str | None = None, cookie: str | None = None
) -> tuple[Scope, list[Message]]:
    """Drive one GET through ``server`` at the ASGI level; return the scope and what it sent."""
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    if cookie is not None:
        headers.append((b"cookie", cookie.encode()))
    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request"}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    return scope, sent


def response_status(sent: list[Message]) -> int:
    start = next(m for m in sent if m["type"] == "http.response.start")
    return start["status"]


def response_body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def set_cookie_value(sent: list[Message]) -> str | None:
    start = next(m for m in sent if m["type"] == "http.response.start")
    for name, value in start["headers"]:
        if name == b"set-cookie":
            return value.decode()
    return None


def header_value(sent: list[Message], header: bytes) -> bytes | None:
    start = next(m for m in sent if m["type"] == "http.response.start")
    for name, value in start["headers"]:
        if name == header:
            return value
    return None


class TestHeaderAuthFlow:
    async def test_basic_ok(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        scope, sent = await http_get(server, basic_header("alice", "wonderland"))
        assert response_status(sent) == 200
        assert response_body(sent) == b"alice"
        assert scope["auth"].identity == "alice"

    async def test_bearer_ok(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        _, sent = await http_get(server, "Bearer sk_live_xyz")
        assert response_body(sent) == b"svc"

    async def test_jwt_ok(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        token = jwt.encode({"sub": "carol"}, "topsecret", algorithm="HS256")
        _, sent = await http_get(server, f"Bearer {token}")
        assert response_body(sent) == b"carol"

    async def test_wrong_password_yields_401(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        _, sent = await http_get(server, basic_header("alice", "nope"))
        assert response_status(sent) == 401

    async def test_invalid_credentials_401_carries_www_authenticate(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        _, sent = await http_get(server, basic_header("alice", "nope"))
        assert response_status(sent) == 401
        assert header_value(sent, b"www-authenticate") == b"Bearer"

    async def test_malformed_credentials_401_carries_www_authenticate(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        _, sent = await http_get(server, "Basicabc123")
        assert response_status(sent) == 401
        assert header_value(sent, b"www-authenticate") == b"Bearer"

    async def test_no_header_is_anonymous(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        scope, sent = await http_get(server)
        assert scope["auth"] is None
        assert response_body(sent) == b"anonymous"

    async def test_explicit_auth_false_disarms_the_middleware(self) -> None:
        server = HeaderAuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG, middleware={"auth": False})
        scope, _ = await http_get(server, basic_header("alice", "wonderland"))
        assert "auth" not in scope


# --- §5.5 identity precedence (server.authenticate at app-dispatch time) ---


class AuthServer(AuthMixin, SessionMixin, MiddlewareMixin, BaseServer):
    """The shipped-shape composition: header auth over sessions and the chain."""


def scope_with(session: Session | None, authorization: str | None) -> Scope:
    """A scope carrying an attached session and/or an Authorization header."""
    headers = [(b"authorization", authorization.encode())] if authorization is not None else []
    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": headers}
    if session is not None:
        scope["session"] = session
    return scope


class TestIdentityPrecedence:
    def test_header_wins_over_session(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        session = Session("sid", avatar=Avatar("sessionuser"), ttl=3600)
        scope = scope_with(session, basic_header("alice", "wonderland"))
        avatar = server.authenticate(scope)
        assert avatar.identity == "alice"

    def test_invalid_header_is_401_no_session_fallback(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        session = Session("sid", avatar=Avatar("sessionuser"), ttl=3600)
        scope = scope_with(session, basic_header("alice", "nope"))
        with pytest.raises(HTTPUnauthorized):
            server.authenticate(scope)

    def test_no_header_falls_back_to_session(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        session = Session("sid", avatar=Avatar("sessionuser", ["member"]), ttl=3600)
        scope = scope_with(session, None)
        avatar = server.authenticate(scope)
        assert avatar.identity == "sessionuser"
        assert avatar.tags == ["member"]

    def test_no_header_anonymous_session_is_none(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        session = Session("sid", avatar=None, ttl=3600)
        assert server.authenticate(scope_with(session, None)) is None

    def test_no_header_no_session_is_none(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        assert server.authenticate(scope_with(None, None)) is None


# --- end-to-end through the REAL combined chain (Phase 9: B1/B2/B3) ---


class TestCombinedChainFlow:
    async def test_header_auth_without_cookie_gets_anonymous_session(self) -> None:
        # B1: header identity on the scope, anonymous session, Set-Cookie, no 500.
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        scope, sent = await http_get(server, basic_header("alice", "wonderland"))
        assert response_status(sent) == 200
        assert scope["auth"].identity == "alice"
        assert set_cookie_value(sent) is not None
        assert scope["session"].avatar is None

    async def test_session_identity_flows_through_the_chain(self) -> None:
        # B2: cookie only — the §5.5 session fallback works through the chain.
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        session = server.session_store.create(avatar=Avatar("sessionuser", ["member"]))
        scope, sent = await http_get(server, cookie=f"session_id={session.id}")
        assert response_status(sent) == 200
        assert response_body(sent) == b"sessionuser"
        assert scope["auth"].identity == "sessionuser"

    async def test_header_wins_over_session_through_the_chain(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        session = server.session_store.create(avatar=Avatar("sessionuser"))
        _, sent = await http_get(
            server, basic_header("alice", "wonderland"), cookie=f"session_id={session.id}"
        )
        assert response_body(sent) == b"alice"

    async def test_jwt_null_tags_claim_yields_empty_tags(self) -> None:
        # B3: a validly signed token with "tags": null normalizes to empty tags.
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        token = jwt.encode({"sub": "carol", "tags": None}, "topsecret", algorithm="HS256")
        scope, sent = await http_get(server, f"Bearer {token}")
        assert response_status(sent) == 200
        assert scope["auth"].tags == []

    async def test_malformed_header_is_401(self) -> None:
        server = AuthServer(primary=EchoAuthApp(), auth=AUTH_CONFIG)
        _, sent = await http_get(server, "Basicabc123")
        assert response_status(sent) == 401


# --- composition without the auth capability ---


class TestWithoutAuthMixin:
    def test_base_server_authenticate_is_none(self) -> None:
        server = BaseServer(primary=EchoAuthApp())
        assert server.authenticate({"headers": []}) is None

    def test_session_only_composition_authenticate_is_none(self) -> None:
        class SessionOnly(SessionMixin, MiddlewareMixin, BaseServer):
            pass

        server = SessionOnly(primary=EchoAuthApp())
        assert server.authenticate({"headers": []}) is None
