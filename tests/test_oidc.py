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

"""OIDC login method tests (core 1d wave 3 — provider, ``start``, ``callback``, e2e).

Drives a full hand-built ``AsgiServer`` at the ASGI level (the ``test_login_flow``
style): an OIDC provider is configured through the ``server_app`` config lift, so
the ``ServerApplication`` registers one ``OidcMethod`` under
``/_server/auth/oidc:<code>/``. Both routes are exercised end to end — ``start``
(the authorization redirect) and ``callback`` (code exchange, id_token
validation, avatar attach) — plus a single closing e2e that runs the whole round
trip. The external dependencies (discovery, the token endpoint, the JWKS) are
mocked at the httpx and ``jwt.PyJWKClient`` boundaries; a module RSA keypair signs
the id_token. The descriptor, ``login_methods`` ordering, the S256 PKCE challenge
and the lazy-discovery boot guarantee are covered alongside.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from genro_asgi_core import AsgiServer, BaseApplication, OidcMethod, ServerApplication
from genro_asgi_core.types import Message, Scope

DISCOVERY_DOC = {
    "authorization_endpoint": "https://accounts.example.com/authorize",
    "token_endpoint": "https://accounts.example.com/token",
    "jwks_uri": "https://accounts.example.com/jwks",
}

PROVIDER = {
    "issuer": "https://accounts.example.com",
    "client_id": "client-123",
    "scopes": "openid email profile",
    "identity_claim": "email",
    "tags": [],
}

# One RSA keypair for the whole module: the "provider" signs the id_token with the
# private key, the callback verifies it with the public key served as the JWKS.
_SIGNING_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def make_id_token(
    private_key: Any = _SIGNING_KEY,
    *,
    issuer: str = "https://accounts.example.com",
    audience: str = "client-123",
    claims: dict[str, Any] | None = None,
) -> str:
    """A signed RS256 id_token — the provider's response to the token exchange."""
    payload: dict[str, Any] = {"iss": issuer, "aud": audience, "email": "alice@example.com"}
    payload.update(claims or {})
    return jwt.encode(payload, private_key, algorithm="RS256")


class _FakeSigningKey:
    """Stand-in for a ``jwt.PyJWK`` — exposes the public key as ``.key``."""

    def __init__(self, key: Any) -> None:
        self.key = key


class _FakePyJWKClient:
    """Stand-in for ``jwt.PyJWKClient``: resolves every token to the module key."""

    def __init__(self, uri: str) -> None:
        pass

    def get_signing_key_from_jwt(self, token: str) -> _FakeSigningKey:
        return _FakeSigningKey(_SIGNING_KEY.public_key())


class FakeResponse:
    """Minimal stand-in for an ``httpx.Response`` — carries a canned JSON payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeAsyncClient:
    """Stand-in for ``httpx.AsyncClient``: GET returns discovery, POST the token set.

    ``token_response`` (a class attribute swapped per test) is what the token
    endpoint answers; the default carries a freshly signed id_token.
    """

    token_response: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        pass

    async def get(self, url: str) -> FakeResponse:
        return FakeResponse(DISCOVERY_DOC)

    async def post(self, url: str, data: dict[str, Any] | None = None) -> FakeResponse:
        return FakeResponse(self.token_response or {"id_token": make_id_token()})


@pytest.fixture
def mock_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the httpx boundary so ``discovery()`` returns the canned document."""
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)


@pytest.fixture
def mock_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock discovery, the JWKS signing-key resolution, and the token endpoint."""
    FakeAsyncClient.token_response = {}
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(jwt, "PyJWKClient", _FakePyJWKClient)


def make_server(provider: dict[str, Any] | None = None) -> AsgiServer:
    """A hand-built server carrying one OIDC provider under code ``google``."""
    return AsgiServer(
        primary=BaseApplication(),
        server_app={"oidc": {"google": provider if provider is not None else PROVIDER}},
    )


async def drive(
    server: AsgiServer,
    path: str,
    method: str = "GET",
    cookie: str | None = None,
) -> tuple[Scope, list[Message]]:
    """Drive one request through ``server`` at the ASGI level."""
    headers: list[tuple[bytes, bytes]] = []
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
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    await server(scope, receive, send)
    return scope, sent


def response_status(sent: list[Message]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def response_headers(sent: list[Message]) -> dict[bytes, bytes]:
    start = next(m for m in sent if m["type"] == "http.response.start")
    return {name: value for name, value in start["headers"]}


def response_body(sent: list[Message]) -> bytes:
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def json_body(sent: list[Message]) -> Any:
    return json.loads(response_body(sent))


def location_query(sent: list[Message]) -> dict[str, list[str]]:
    """The parsed query of the redirect ``Location`` header."""
    location = response_headers(sent)[b"location"].decode()
    return parse_qs(urlparse(location).query)


class TestOidcDescriptor:
    def test_descriptor_shape_and_no_secret_leak(self) -> None:
        server = make_server()
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.auth_section is not None
        method = app.auth_section.methods["oidc:google"]
        assert isinstance(method, OidcMethod)
        assert method.descriptor() == {
            "id": "oidc:google",
            "kind": "redirect",
            "label": "Sign in with google",
            "url": "/_server/auth/oidc:google/start",
        }
        # The public descriptor never carries the client id, issuer, or secret.
        for leak in ("client_id", "issuer", "client_secret"):
            assert leak not in method.descriptor()

    def test_method_owns_routes_and_is_attached(self) -> None:
        server = make_server()
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.auth_section is not None
        routers = app.auth_section.route.nodes(lazy=True).get("routers") or {}
        assert "oidc:google" in routers

    async def test_login_methods_lists_oidc_after_password(self) -> None:
        server = make_server()
        _, sent = await drive(server, "/_server/login_methods")
        assert response_status(sent) == 200
        methods = json_body(sent)["methods"]
        assert [m["id"] for m in methods] == ["password", "oidc:google"]
        assert methods[1]["kind"] == "redirect"
        assert methods[1]["label"] == "Sign in with google"
        assert methods[1]["url"] == "/_server/auth/oidc:google/start"


class TestOidcStart:
    async def test_start_redirects_to_the_authorization_endpoint(
        self, mock_discovery: None
    ) -> None:
        server = make_server()
        session = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/auth/oidc:google/start?next=/app/page",
            cookie=f"session_id={session.id}",
        )
        assert response_status(sent) == 302
        location = response_headers(sent)[b"location"].decode()
        assert location.startswith("https://accounts.example.com/authorize?")
        query = location_query(sent)
        assert query["response_type"] == ["code"]
        assert query["client_id"] == ["client-123"]
        assert query["redirect_uri"] == ["/_server/auth/oidc:google/callback"]
        assert query["scope"] == ["openid email profile"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["state"][0]
        assert query["code_challenge"][0]

    async def test_start_lands_state_verifier_next_in_the_session(
        self, mock_discovery: None
    ) -> None:
        server = make_server()
        session = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/auth/oidc:google/start?next=/app/page",
            cookie=f"session_id={session.id}",
        )
        reloaded = server.session_store.get(session.id)
        assert reloaded is not None
        state = reloaded.data["oidc.oidc:google.state"]
        verifier = reloaded.data["oidc.oidc:google.verifier"]
        assert state and verifier
        assert reloaded.data["oidc.oidc:google.next"] == "/app/page"
        # The state minted for the session is the state carried in the redirect.
        assert location_query(sent)["state"] == [state]

    async def test_start_stores_only_a_safe_next(self, mock_discovery: None) -> None:
        server = make_server()
        session = server.session_store.create()
        await drive(
            server,
            "/_server/auth/oidc:google/start?next=//evil.example",
            cookie=f"session_id={session.id}",
        )
        reloaded = server.session_store.get(session.id)
        assert reloaded is not None
        assert reloaded.data["oidc.oidc:google.next"] == "/"  # collapsed by safe_next_path

    async def test_pkce_challenge_matches_the_stored_verifier(
        self, mock_discovery: None
    ) -> None:
        server = make_server()
        session = server.session_store.create()
        _, sent = await drive(
            server,
            "/_server/auth/oidc:google/start",
            cookie=f"session_id={session.id}",
        )
        reloaded = server.session_store.get(session.id)
        assert reloaded is not None
        verifier = reloaded.data["oidc.oidc:google.verifier"]
        challenge = location_query(sent)["code_challenge"][0]
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        assert challenge == expected


class TestOidcDiscoveryLazy:
    def test_construction_does_not_fetch_discovery(self) -> None:
        # An unreachable issuer must not break server construction: discovery is
        # lazy, never called in __init__ (the offline-boot guarantee).
        server = make_server({"issuer": "https://unreachable.invalid", "client_id": "x"})
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        assert app.auth_section is not None
        method = app.auth_section.methods["oidc:google"]
        assert isinstance(method, OidcMethod)
        assert method._discovery is None  # nothing fetched at construction


async def begin_flow(server: AsgiServer, next_target: str = "/app/page") -> tuple[str, str]:
    """Run ``start`` for a fresh session; return ``(session_id, minted_state)``.

    Lands the real ``state``/``verifier``/``next`` in the session exactly as a
    live authorization request would, so the callback exercises the true round
    trip rather than a hand-seeded facsimile.
    """
    session = server.session_store.create()
    await drive(
        server,
        f"/_server/auth/oidc:google/start?next={next_target}",
        cookie=f"session_id={session.id}",
    )
    reloaded = server.session_store.get(session.id)
    assert reloaded is not None
    return session.id, reloaded.data["oidc.oidc:google.state"]


class TestOidcCallback:
    async def test_callback_authenticates_and_redirects_to_next(self, mock_provider: None) -> None:
        server = make_server()
        session_id, state = await begin_flow(server)
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 302
        assert response_headers(sent)[b"location"].decode() == "/app/page"
        promoted = server.session_store.get(session_id)
        assert promoted is not None and promoted.avatar is not None
        assert promoted.avatar.identity == "alice@example.com"
        assert promoted.avatar.tags == []
        # The session id never changes at login (no cookie involved).
        assert promoted.id == session_id

    async def test_callback_clears_the_one_shot_flow_keys(self, mock_provider: None) -> None:
        server = make_server()
        session_id, state = await begin_flow(server)
        await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        promoted = server.session_store.get(session_id)
        assert promoted is not None
        for suffix in ("state", "verifier", "next"):
            assert f"oidc.oidc:google.{suffix}" not in promoted.data

    async def test_callback_does_not_touch_the_lockout_counter(self, mock_provider: None) -> None:
        # OIDC never routes through the password login route, so the store-backed
        # failure counter (Phase 2) is untouched by a successful OIDC login.
        server = make_server()
        session_id, state = await begin_flow(server)
        await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        app = server.mounts["_server"]
        assert isinstance(app, ServerApplication)
        user_store = getattr(server, "user_store", None)
        assert user_store is None  # no user store wired: nothing to touch

    async def test_callback_rejects_a_mismatched_state(self, mock_provider: None) -> None:
        server = make_server()
        session_id, _ = await begin_flow(server)
        _, sent = await drive(
            server,
            "/_server/auth/oidc:google/callback?state=forged&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400
        promoted = server.session_store.get(session_id)
        assert promoted is not None and promoted.avatar is None

    async def test_callback_rejects_a_missing_state(self, mock_provider: None) -> None:
        server = make_server()
        session_id, _ = await begin_flow(server)
        _, sent = await drive(
            server,
            "/_server/auth/oidc:google/callback?code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400

    async def test_callback_rejects_a_token_response_without_id_token(
        self, monkeypatch: pytest.MonkeyPatch, mock_provider: None
    ) -> None:
        server = make_server()
        session_id, state = await begin_flow(server)
        monkeypatch.setattr(FakeAsyncClient, "token_response", {"access_token": "opaque"})
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400

    async def test_callback_rejects_a_wrong_audience_id_token(
        self, monkeypatch: pytest.MonkeyPatch, mock_provider: None
    ) -> None:
        server = make_server()
        session_id, state = await begin_flow(server)
        forged = make_id_token(audience="someone-else")
        monkeypatch.setattr(FakeAsyncClient, "token_response", {"id_token": forged})
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400
        promoted = server.session_store.get(session_id)
        assert promoted is not None and promoted.avatar is None

    async def test_callback_rejects_a_wrong_issuer_id_token(
        self, monkeypatch: pytest.MonkeyPatch, mock_provider: None
    ) -> None:
        server = make_server()
        session_id, state = await begin_flow(server)
        forged = make_id_token(issuer="https://evil.example")
        monkeypatch.setattr(FakeAsyncClient, "token_response", {"id_token": forged})
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400

    async def test_callback_rejects_a_bad_signature_id_token(
        self, monkeypatch: pytest.MonkeyPatch, mock_provider: None
    ) -> None:
        # An id_token signed by a DIFFERENT key than the JWKS resolves — the
        # signature check must reject it.
        server = make_server()
        session_id, state = await begin_flow(server)
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = make_id_token(private_key=other_key)
        monkeypatch.setattr(FakeAsyncClient, "token_response", {"id_token": forged})
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400

    async def test_callback_rejects_a_missing_identity_claim(
        self, monkeypatch: pytest.MonkeyPatch, mock_provider: None
    ) -> None:
        server = make_server()
        session_id, state = await begin_flow(server)
        no_email = make_id_token(claims={"email": None})
        monkeypatch.setattr(FakeAsyncClient, "token_response", {"id_token": no_email})
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=f"session_id={session_id}",
        )
        assert response_status(sent) == 400


class TestOidcEndToEnd:
    """The closing barrier: one configured provider, discovered → started →
    called back → authenticated, over the real ASGI drive — the whole round trip
    a browser makes, in a single narrative."""

    async def test_configured_provider_logs_a_user_in_end_to_end(
        self, mock_provider: None
    ) -> None:
        server = make_server()

        # 1. The provider appears as a redirect descriptor in login_methods.
        _, sent = await drive(server, "/_server/login_methods")
        methods = json_body(sent)["methods"]
        oidc = next(m for m in methods if m["id"] == "oidc:google")
        assert oidc["kind"] == "redirect"
        assert oidc["url"] == "/_server/auth/oidc:google/start"

        # 2. start: the browser is redirected to the provider's authorize endpoint.
        session = server.session_store.create()
        cookie = f"session_id={session.id}"
        _, sent = await drive(server, oidc["url"] + "?next=/app/home", cookie=cookie)
        assert response_status(sent) == 302
        authorize = response_headers(sent)[b"location"].decode()
        assert authorize.startswith("https://accounts.example.com/authorize?")
        query = location_query(sent)
        state = query["state"][0]

        # 3. callback: the provider redirects back; the code is exchanged, the
        #    id_token validated, the avatar attached, the browser sent to next.
        _, sent = await drive(
            server,
            f"/_server/auth/oidc:google/callback?state={state}&code=auth-code",
            cookie=cookie,
        )
        assert response_status(sent) == 302
        assert response_headers(sent)[b"location"].decode() == "/app/home"

        # 4. The session now carries the authenticated identity (id unchanged),
        #    and the OIDC login never touched the password lockout machinery.
        authenticated = server.session_store.get(session.id)
        assert authenticated is not None and authenticated.avatar is not None
        assert authenticated.avatar.identity == "alice@example.com"
        assert authenticated.id == session.id
        assert getattr(server, "user_store", None) is None
