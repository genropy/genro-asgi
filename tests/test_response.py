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

"""Tests for HTTP Response classes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path


# =============================================================================
# Test Fixtures
# =============================================================================


class MockSend:
    """Capture ASGI send messages for testing."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def __call__(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    @property
    def start_message(self) -> dict[str, Any]:
        """Get the http.response.start message."""
        return self.messages[0]

    @property
    def body_messages(self) -> list[dict[str, Any]]:
        """Get all http.response.body messages."""
        return [m for m in self.messages if m["type"] == "http.response.body"]

    @property
    def status(self) -> int:
        """Get response status code."""
        return self.start_message["status"]

    @property
    def headers(self) -> dict[bytes, bytes]:
        """Get headers as dict."""
        return dict(self.start_message["headers"])

    @property
    def body(self) -> bytes:
        """Get complete body (concatenated from all body messages)."""
        return b"".join(m.get("body", b"") for m in self.body_messages)


@pytest.fixture
def send() -> MockSend:
    """Create a mock send callable."""
    return MockSend()


@pytest.fixture
def scope() -> dict[str, Any]:
    """Create a minimal HTTP scope."""
    return {"type": "http"}


async def mock_receive() -> dict[str, Any]:
    """Mock receive callable (not used by responses)."""
    return {"type": "http.request", "body": b""}


# =============================================================================
# Test Response (base class)
# =============================================================================


class TestResponse:
    """Tests for base Response class."""

    @pytest.mark.asyncio
    async def test_basic_bytes_content(self, scope: dict, send: MockSend) -> None:
        """Response with bytes content sends correct messages."""
        from genro_asgi.response import Response

        response = Response(content=b"Hello, World!")
        await response(scope, mock_receive, send)

        assert len(send.messages) == 2
        assert send.start_message["type"] == "http.response.start"
        assert send.status == 200
        assert send.body_messages[0]["type"] == "http.response.body"
        assert send.body == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_string_content_encoded_utf8(
        self, scope: dict, send: MockSend
    ) -> None:
        """String content is encoded as UTF-8."""
        from genro_asgi.response import Response

        response = Response(content="Ciao, Mondo! 🌍")
        await response(scope, mock_receive, send)

        assert send.body == "Ciao, Mondo! 🌍".encode("utf-8")

    @pytest.mark.asyncio
    async def test_none_content_becomes_empty(
        self, scope: dict, send: MockSend
    ) -> None:
        """None content becomes empty bytes."""
        from genro_asgi.response import Response

        response = Response(content=None)
        await response(scope, mock_receive, send)

        assert send.body == b""

    @pytest.mark.asyncio
    async def test_custom_status_code(self, scope: dict, send: MockSend) -> None:
        """Custom status code is sent."""
        from genro_asgi.response import Response

        response = Response(content=b"", status_code=404)
        await response(scope, mock_receive, send)

        assert send.status == 404

    @pytest.mark.asyncio
    async def test_custom_headers(self, scope: dict, send: MockSend) -> None:
        """Custom headers are sent (lowercased, latin-1 encoded)."""
        from genro_asgi.response import Response

        response = Response(
            content=b"",
            headers={"X-Custom-Header": "custom-value", "X-Another": "another"},
        )
        await response(scope, mock_receive, send)

        headers = send.headers
        assert headers[b"x-custom-header"] == b"custom-value"
        assert headers[b"x-another"] == b"another"

    @pytest.mark.asyncio
    async def test_media_type_sets_content_type(
        self, scope: dict, send: MockSend
    ) -> None:
        """Media type sets Content-Type header."""
        from genro_asgi.response import Response

        response = Response(content=b"<xml/>", media_type="application/xml")
        await response(scope, mock_receive, send)

        assert send.headers[b"content-type"] == b"application/xml"

    @pytest.mark.asyncio
    async def test_text_media_type_appends_charset(
        self, scope: dict, send: MockSend
    ) -> None:
        """Text media types get charset appended."""
        from genro_asgi.response import Response

        response = Response(content="Hello", media_type="text/plain")
        await response(scope, mock_receive, send)

        assert send.headers[b"content-type"] == b"text/plain; charset=utf-8"

    @pytest.mark.asyncio
    async def test_text_media_type_with_existing_charset(
        self, scope: dict, send: MockSend
    ) -> None:
        """Text media type with existing charset is not modified."""
        from genro_asgi.response import Response

        response = Response(
            content="Hello", media_type="text/plain; charset=iso-8859-1"
        )
        await response(scope, mock_receive, send)

        assert send.headers[b"content-type"] == b"text/plain; charset=iso-8859-1"

    @pytest.mark.asyncio
    async def test_content_length_added_automatically(
        self, scope: dict, send: MockSend
    ) -> None:
        """Content-Length header is added automatically."""
        from genro_asgi.response import Response

        response = Response(content=b"12345")
        await response(scope, mock_receive, send)

        assert send.headers[b"content-length"] == b"5"

    @pytest.mark.asyncio
    async def test_content_length_not_overwritten(
        self, scope: dict, send: MockSend
    ) -> None:
        """Explicit Content-Length is not overwritten."""
        from genro_asgi.response import Response

        response = Response(content=b"12345", headers={"Content-Length": "100"})
        await response(scope, mock_receive, send)

        assert send.headers[b"content-length"] == b"100"

    @pytest.mark.asyncio
    async def test_empty_body_has_content_length_zero(
        self, scope: dict, send: MockSend
    ) -> None:
        """Empty body has Content-Length: 0."""
        from genro_asgi.response import Response

        response = Response(content=b"")
        await response(scope, mock_receive, send)

        assert send.headers[b"content-length"] == b"0"

    @pytest.mark.asyncio
    async def test_no_media_type_no_content_type_header(
        self, scope: dict, send: MockSend
    ) -> None:
        """No media type means no Content-Type header."""
        from genro_asgi.response import Response

        response = Response(content=b"data")
        await response(scope, mock_receive, send)

        assert b"content-type" not in send.headers

    @pytest.mark.asyncio
    async def test_headers_accepts_mapping(self, scope: dict, send: MockSend) -> None:
        """Headers parameter accepts any Mapping."""
        from genro_asgi.datastructures import Headers
        from genro_asgi.response import Response

        # Test with Headers object
        headers_obj = Headers([(b"x-test", b"value")])
        response = Response(content=b"", headers=headers_obj)
        await response(scope, mock_receive, send)

        assert send.headers[b"x-test"] == b"value"

    @pytest.mark.asyncio
    async def test_headers_accepts_list_of_tuples(
        self, scope: dict, send: MockSend
    ) -> None:
        """Headers parameter accepts list of tuples."""
        from genro_asgi.response import Response

        headers_list = [("X-First", "one"), ("X-Second", "two")]
        response = Response(content=b"", headers=headers_list)
        await response(scope, mock_receive, send)

        assert send.headers[b"x-first"] == b"one"
        assert send.headers[b"x-second"] == b"two"

    @pytest.mark.asyncio
    async def test_duplicate_headers_preserved(
        self, scope: dict, send: MockSend
    ) -> None:
        """Multiple headers with same name are preserved."""
        from genro_asgi.response import Response

        headers_list = [
            ("Set-Cookie", "session=abc"),
            ("Set-Cookie", "prefs=dark"),
            ("Set-Cookie", "lang=en"),
        ]
        response = Response(content=b"", headers=headers_list)
        await response(scope, mock_receive, send)

        # Get all Set-Cookie headers
        set_cookie_headers = [
            value for name, value in send.start_message["headers"]
            if name == b"set-cookie"
        ]
        assert len(set_cookie_headers) == 3
        assert b"session=abc" in set_cookie_headers
        assert b"prefs=dark" in set_cookie_headers
        assert b"lang=en" in set_cookie_headers

    def test_response_has_slots(self) -> None:
        """Response class uses __slots__ for efficiency."""
        from genro_asgi.response import Response

        assert hasattr(Response, "__slots__")
        response = Response(content=b"")
        with pytest.raises(AttributeError):
            response.undefined_attribute = "test"  # type: ignore[attr-defined]


# =============================================================================
# Test Module-Level
# =============================================================================


class TestModuleLevel:
    """Tests for module-level attributes and exports."""

    def test_has_orjson_constant(self) -> None:
        """HAS_ORJSON constant is defined."""
        from genro_asgi.response import HAS_ORJSON

        assert isinstance(HAS_ORJSON, bool)

    def test_all_exports(self) -> None:
        """All expected classes are exported."""
        from genro_asgi.response import Response

        assert Response is not None

    def test_exports_from_package(self) -> None:
        """Response classes are exported from main package."""
        from genro_asgi import Response, make_cookie

        assert Response is not None
        assert make_cookie is not None


# =============================================================================
# Test make_cookie Function
# =============================================================================


class TestMakeCookie:
    """Tests for make_cookie helper function."""

    def test_basic_cookie(self) -> None:
        """Basic cookie with key and value."""
        from genro_asgi.response import make_cookie

        name, value = make_cookie("session", "abc123")
        assert name == "set-cookie"
        assert "session=abc123" in value

    def test_value_url_encoded(self) -> None:
        """Cookie value is URL-encoded."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("data", "hello world")
        assert "hello%20world" in value

    def test_special_chars_encoded(self) -> None:
        """Special characters in value are encoded."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("data", "a=b&c=d")
        assert "=" not in value.split("=", 1)[1].split(";")[0] or "%3D" in value

    def test_max_age(self) -> None:
        """Max-Age attribute is set."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", max_age=3600)
        assert "Max-Age=3600" in value

    def test_path_default(self) -> None:
        """Default path is '/'."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc")
        assert "Path=/" in value

    def test_path_custom(self) -> None:
        """Custom path is set."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", path="/api")
        assert "Path=/api" in value

    def test_domain(self) -> None:
        """Domain attribute is set."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", domain="example.com")
        assert "Domain=example.com" in value

    def test_secure(self) -> None:
        """Secure flag is set."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", secure=True)
        assert "; Secure" in value

    def test_httponly(self) -> None:
        """HttpOnly flag is set."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", httponly=True)
        assert "; HttpOnly" in value

    def test_samesite_default_lax(self) -> None:
        """Default SameSite is Lax."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc")
        assert "SameSite=Lax" in value

    def test_samesite_strict(self) -> None:
        """SameSite=Strict is set."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", samesite="strict")
        assert "SameSite=Strict" in value

    def test_samesite_none(self) -> None:
        """SameSite=None is set (requires Secure)."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", samesite="none", secure=True)
        assert "SameSite=None" in value
        assert "Secure" in value

    def test_samesite_omitted(self) -> None:
        """SameSite can be omitted."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "abc", samesite=None)
        assert "SameSite" not in value

    def test_all_attributes(self) -> None:
        """All attributes together."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie(
            "session",
            "abc123",
            max_age=86400,
            path="/app",
            domain=".example.com",
            secure=True,
            httponly=True,
            samesite="strict",
        )
        assert "session=abc123" in value
        assert "Max-Age=86400" in value
        assert "Path=/app" in value
        assert "Domain=.example.com" in value
        assert "Secure" in value
        assert "HttpOnly" in value
        assert "SameSite=Strict" in value

    def test_empty_value(self) -> None:
        """Empty value for deleting cookie."""
        from genro_asgi.response import make_cookie

        _, value = make_cookie("session", "", max_age=0)
        assert "session=" in value
        assert "Max-Age=0" in value

    def test_use_with_response(self) -> None:
        """Cookie can be used with Response."""
        from genro_asgi.response import Response, make_cookie

        cookie1 = make_cookie("session", "abc", httponly=True)
        cookie2 = make_cookie("prefs", "dark", max_age=31536000)

        response = Response(content="OK", headers=[cookie1, cookie2])
        assert len(response._headers) >= 2


