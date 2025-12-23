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

"""Tests for authentication middleware and backends."""

import base64

import pytest

from genro_asgi.authentication import BearerBackend, BasicBackend
from genro_asgi.exceptions import HTTPException
from genro_asgi.middleware.authentication import AuthMiddleware


class TestBearerBackend:
    """Tests for BearerBackend."""

    def test_valid_token(self) -> None:
        """Valid token returns auth dict with tags."""
        backend = BearerBackend()
        config = {
            "type": "bearer",
            "tokens": {
                "reader_token": {"token": "tk_abc123", "tags": "read,write"},
                "readonly_token": {"token": "tk_readonly", "tags": "read"},
            },
        }
        result = backend.try_auth("tk_abc123", config)

        assert result is not None
        assert result["identity"] == "reader_token"
        assert result["tags"] == ["read", "write"]
        assert result["backend"] == "bearer"

    def test_readonly_token(self) -> None:
        """Readonly token returns correct tags."""
        backend = BearerBackend()
        config = {
            "type": "bearer",
            "tokens": {
                "reader_token": {"token": "tk_abc123", "tags": "read,write"},
                "readonly_token": {"token": "tk_readonly", "tags": "read"},
            },
        }
        result = backend.try_auth("tk_readonly", config)

        assert result is not None
        assert result["identity"] == "readonly_token"
        assert result["tags"] == ["read"]

    def test_invalid_token(self) -> None:
        """Invalid token returns None."""
        backend = BearerBackend()
        config = {
            "type": "bearer",
            "tokens": {
                "reader_token": {"token": "tk_abc123", "tags": "read"},
            },
        }
        result = backend.try_auth("invalid_token", config)

        assert result is None

    def test_empty_tokens(self) -> None:
        """Empty tokens config returns None."""
        backend = BearerBackend()
        config = {"type": "bearer", "tokens": {}}
        result = backend.try_auth("tk_abc123", config)

        assert result is None

    def test_token_without_tags(self) -> None:
        """Token without tags gets empty list."""
        backend = BearerBackend()
        config = {
            "type": "bearer",
            "tokens": {
                "notags_token": {"token": "tk_notags"},
            },
        }
        result = backend.try_auth("tk_notags", config)

        assert result is not None
        assert result["tags"] == []

    def test_tags_as_list(self) -> None:
        """Tags can be specified as list."""
        backend = BearerBackend()
        config = {
            "type": "bearer",
            "tokens": {
                "admin_token": {"token": "tk_admin", "tags": ["read", "write", "admin"]},
            },
        }
        result = backend.try_auth("tk_admin", config)

        assert result is not None
        assert result["tags"] == ["read", "write", "admin"]


class TestBasicBackend:
    """Tests for BasicBackend."""

    def _encode_basic(self, username: str, password: str) -> str:
        """Helper to encode basic auth credentials."""
        return base64.b64encode(f"{username}:{password}".encode()).decode()

    def test_valid_credentials(self) -> None:
        """Valid credentials return auth dict with tags."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "mrossi": {"password": "secret123", "tags": "read,write"},
                "admin": {"password": "supersecret", "tags": "admin"},
            },
        }
        credentials = self._encode_basic("mrossi", "secret123")
        result = backend.try_auth(credentials, config)

        assert result is not None
        assert result["identity"] == "mrossi"
        assert result["tags"] == ["read", "write"]
        assert result["backend"] == "basic"

    def test_admin_user(self) -> None:
        """Admin user returns admin tags."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "mrossi": {"password": "secret123", "tags": "read,write"},
                "admin": {"password": "supersecret", "tags": "admin"},
            },
        }
        credentials = self._encode_basic("admin", "supersecret")
        result = backend.try_auth(credentials, config)

        assert result is not None
        assert result["identity"] == "admin"
        assert result["tags"] == ["admin"]

    def test_invalid_password(self) -> None:
        """Invalid password returns None."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "mrossi": {"password": "secret123", "tags": "read"},
            },
        }
        credentials = self._encode_basic("mrossi", "wrongpassword")
        result = backend.try_auth(credentials, config)

        assert result is None

    def test_unknown_user(self) -> None:
        """Unknown user returns None."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "mrossi": {"password": "secret123", "tags": "read"},
            },
        }
        credentials = self._encode_basic("unknown", "anypassword")
        result = backend.try_auth(credentials, config)

        assert result is None

    def test_invalid_base64(self) -> None:
        """Invalid base64 returns None."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "mrossi": {"password": "secret123", "tags": "read"},
            },
        }
        result = backend.try_auth("not-valid-base64!!!", config)

        assert result is None

    def test_missing_colon(self) -> None:
        """Credentials without colon returns None."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "mrossi": {"password": "secret123", "tags": "read"},
            },
        }
        # Encode "nocolon" without colon separator
        credentials = base64.b64encode(b"nocolon").decode()
        result = backend.try_auth(credentials, config)

        assert result is None

    def test_user_without_tags(self) -> None:
        """User without tags gets empty list."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "users": {
                "notags": {"password": "pass123"},
            },
        }
        credentials = self._encode_basic("notags", "pass123")
        result = backend.try_auth(credentials, config)

        assert result is not None
        assert result["tags"] == []

    def test_usertable_returns_none(self) -> None:
        """Config with usertable returns None (not implemented yet)."""
        backend = BasicBackend()
        config = {
            "type": "basic",
            "usertable": "users",
            "username_column": "username",
            "password_column": "password_hash",
        }
        credentials = self._encode_basic("anyuser", "anypass")
        result = backend.try_auth(credentials, config)

        assert result is None


class TestAuthMiddleware:
    """Tests for AuthMiddleware."""

    @pytest.fixture
    def captured_scope(self) -> dict:
        """Fixture to capture scope passed to app."""
        return {}

    @pytest.fixture
    def dummy_app(self, captured_scope: dict):
        """Dummy ASGI app that captures scope."""

        async def app(scope, receive, send):
            captured_scope.update(scope)

        return app

    @pytest.mark.asyncio
    async def test_bearer_auth(self, dummy_app, captured_scope) -> None:
        """Middleware authenticates bearer token."""
        middleware = AuthMiddleware(
            dummy_app,
            bearer={
                "test_token": {"token": "tk_test", "tags": "read"},
            },
        )
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer tk_test")],
        }
        await middleware(scope, None, None)

        assert "auth" in captured_scope
        assert captured_scope["auth"]["identity"] == "test_token"
        assert captured_scope["auth"]["tags"] == ["read"]
        assert captured_scope["auth"]["backend"] == "bearer"

    @pytest.mark.asyncio
    async def test_basic_auth(self, dummy_app, captured_scope) -> None:
        """Middleware authenticates basic credentials."""
        credentials = base64.b64encode(b"mrossi:secret123").decode()
        middleware = AuthMiddleware(
            dummy_app,
            basic={
                "mrossi": {"password": "secret123", "tags": "read,write"},
            },
        )
        scope = {
            "type": "http",
            "headers": [(b"authorization", f"Basic {credentials}".encode())],
        }
        await middleware(scope, None, None)

        assert "auth" in captured_scope
        assert captured_scope["auth"]["identity"] == "mrossi"
        assert captured_scope["auth"]["tags"] == ["read", "write"]
        assert captured_scope["auth"]["backend"] == "basic"

    @pytest.mark.asyncio
    async def test_no_auth_header(self, dummy_app, captured_scope) -> None:
        """Middleware sets auth to None when no header present."""
        middleware = AuthMiddleware(
            dummy_app,
            bearer={
                "test_token": {"token": "tk_test", "tags": "read"},
            },
        )
        scope = {"type": "http", "headers": []}
        await middleware(scope, None, None)

        assert "auth" in captured_scope
        assert captured_scope["auth"] is None

    @pytest.mark.asyncio
    async def test_invalid_token(self, dummy_app, captured_scope) -> None:
        """Middleware raises 401 when token is invalid."""
        middleware = AuthMiddleware(
            dummy_app,
            bearer={
                "test_token": {"token": "tk_test", "tags": "read"},
            },
        )
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer invalid_token")],
        }
        with pytest.raises(HTTPException) as exc_info:
            await middleware(scope, None, None)

        assert exc_info.value.status_code == 401
        assert "Invalid or expired credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_multiple_entries(self, dummy_app, captured_scope) -> None:
        """Middleware tries all entries until one matches."""
        credentials = base64.b64encode(b"admin:supersecret").decode()
        middleware = AuthMiddleware(
            dummy_app,
            bearer={
                "api_token": {"token": "tk_api", "tags": "api"},
            },
            basic={
                "admin": {"password": "supersecret", "tags": "admin"},
            },
        )
        scope = {
            "type": "http",
            "headers": [(b"authorization", f"Basic {credentials}".encode())],
        }
        await middleware(scope, None, None)

        assert captured_scope["auth"]["identity"] == "admin"
        assert captured_scope["auth"]["tags"] == ["admin"]
        assert captured_scope["auth"]["backend"] == "basic"

    @pytest.mark.asyncio
    async def test_bearer_over_basic(self, dummy_app, captured_scope) -> None:
        """Bearer token is matched when header uses Bearer scheme."""
        middleware = AuthMiddleware(
            dummy_app,
            bearer={
                "api_token": {"token": "tk_api", "tags": "api"},
            },
            basic={
                "admin": {"password": "supersecret", "tags": "admin"},
            },
        )
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer tk_api")],
        }
        await middleware(scope, None, None)

        assert captured_scope["auth"]["identity"] == "api_token"
        assert captured_scope["auth"]["backend"] == "bearer"

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self, dummy_app, captured_scope) -> None:
        """Non-HTTP scopes pass through without auth."""
        middleware = AuthMiddleware(
            dummy_app,
            tokens={
                "type": "bearer",
                "test_token": {"token": "tk_test", "tags": "read"},
            },
        )
        scope = {"type": "websocket", "headers": []}
        await middleware(scope, None, None)

        assert "auth" not in captured_scope

    @pytest.mark.asyncio
    async def test_no_entries(self, dummy_app, captured_scope) -> None:
        """Middleware with no entries raises 401 when credentials provided."""
        middleware = AuthMiddleware(dummy_app)
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer tk_test")],
        }
        with pytest.raises(HTTPException) as exc_info:
            await middleware(scope, None, None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_scheme(self, dummy_app, captured_scope) -> None:
        """Unknown auth scheme raises 401."""
        middleware = AuthMiddleware(
            dummy_app,
            tokens={
                "type": "bearer",
                "test_token": {"token": "tk_test", "tags": "read"},
            },
        )
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Digest somecredentials")],
        }
        with pytest.raises(HTTPException) as exc_info:
            await middleware(scope, None, None)

        assert exc_info.value.status_code == 401
