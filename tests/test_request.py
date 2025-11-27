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

"""Tests for Request class.

Test coverage based on request.py module docstring (source of truth).
"""

from __future__ import annotations

from typing import Any

import pytest

from genro_asgi.request import Request
from genro_asgi.datastructures import Address, Headers, QueryParams, State, URL


# =============================================================================
# Test Fixtures / Helpers
# =============================================================================


def make_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    scheme: str = "http",
    server: tuple[str, int] | None = ("localhost", 8000),
    client: tuple[str, int] | None = ("127.0.0.1", 50000),
    root_path: str = "",
) -> dict[str, Any]:
    """Create a mock ASGI HTTP scope."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "scheme": scheme,
        "server": server,
        "client": client,
        "root_path": root_path,
    }


def make_receive(body: bytes = b"", chunked: bool = False) -> Any:
    """Create a mock receive callable.

    Args:
        body: The body content to return
        chunked: If True, split body into multiple chunks
    """
    if chunked and body:
        # Split into 3 chunks
        chunk_size = len(body) // 3 or 1
        chunks = []
        for i in range(0, len(body), chunk_size):
            chunk = body[i : i + chunk_size]
            more = i + chunk_size < len(body)
            chunks.append({"type": "http.request", "body": chunk, "more_body": more})
        # Ensure last chunk has more_body=False
        if chunks:
            chunks[-1]["more_body"] = False
    else:
        chunks = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive() -> dict[str, Any]:
        if chunks:
            return chunks.pop(0)
        return {"type": "http.request", "body": b"", "more_body": False}

    return receive


# =============================================================================
# Test: Constructor
# =============================================================================


class TestRequestConstructor:
    """Tests for Request.__init__."""

    def test_constructor_accepts_scope_and_receive(self) -> None:
        """Request can be constructed with scope and receive."""
        scope = make_scope()
        receive = make_receive()
        request = Request(scope, receive)
        assert request is not None

    def test_constructor_stores_scope(self) -> None:
        """Constructor stores scope accessible via property."""
        scope = make_scope(method="POST", path="/test")
        request = Request(scope, make_receive())
        assert request.scope is scope

    def test_constructor_no_io(self) -> None:
        """Constructor does not perform any I/O (lazy initialization)."""
        # If constructor called receive, this would fail
        call_count = 0

        async def counting_receive() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = make_scope()
        Request(scope, counting_receive)
        assert call_count == 0, "Constructor should not call receive"


# =============================================================================
# Test: Synchronous Properties (from scope)
# =============================================================================


class TestRequestMethod:
    """Tests for Request.method property."""

    def test_method_get(self) -> None:
        """Method property returns GET."""
        request = Request(make_scope(method="GET"), make_receive())
        assert request.method == "GET"

    def test_method_post(self) -> None:
        """Method property returns POST."""
        request = Request(make_scope(method="POST"), make_receive())
        assert request.method == "POST"

    def test_method_put(self) -> None:
        """Method property returns PUT."""
        request = Request(make_scope(method="PUT"), make_receive())
        assert request.method == "PUT"

    def test_method_delete(self) -> None:
        """Method property returns DELETE."""
        request = Request(make_scope(method="DELETE"), make_receive())
        assert request.method == "DELETE"

    def test_method_default(self) -> None:
        """Method defaults to GET if not in scope."""
        scope = make_scope()
        del scope["method"]
        request = Request(scope, make_receive())
        assert request.method == "GET"


class TestRequestPath:
    """Tests for Request.path property."""

    def test_path_root(self) -> None:
        """Path property returns root path."""
        request = Request(make_scope(path="/"), make_receive())
        assert request.path == "/"

    def test_path_simple(self) -> None:
        """Path property returns simple path."""
        request = Request(make_scope(path="/users"), make_receive())
        assert request.path == "/users"

    def test_path_nested(self) -> None:
        """Path property returns nested path."""
        request = Request(make_scope(path="/api/v1/users/123"), make_receive())
        assert request.path == "/api/v1/users/123"

    def test_path_default(self) -> None:
        """Path defaults to / if not in scope."""
        scope = make_scope()
        del scope["path"]
        request = Request(scope, make_receive())
        assert request.path == "/"


class TestRequestScheme:
    """Tests for Request.scheme property."""

    def test_scheme_http(self) -> None:
        """Scheme property returns http."""
        request = Request(make_scope(scheme="http"), make_receive())
        assert request.scheme == "http"

    def test_scheme_https(self) -> None:
        """Scheme property returns https."""
        request = Request(make_scope(scheme="https"), make_receive())
        assert request.scheme == "https"

    def test_scheme_default(self) -> None:
        """Scheme defaults to http if not in scope."""
        scope = make_scope()
        del scope["scheme"]
        request = Request(scope, make_receive())
        assert request.scheme == "http"


class TestRequestClient:
    """Tests for Request.client property."""

    def test_client_present(self) -> None:
        """Client property returns Address when present."""
        request = Request(make_scope(client=("192.168.1.1", 12345)), make_receive())
        client = request.client
        assert client is not None
        assert isinstance(client, Address)
        assert client.host == "192.168.1.1"
        assert client.port == 12345

    def test_client_none(self) -> None:
        """Client property returns None when not present."""
        request = Request(make_scope(client=None), make_receive())
        assert request.client is None

    def test_client_localhost(self) -> None:
        """Client property handles localhost."""
        request = Request(make_scope(client=("127.0.0.1", 50000)), make_receive())
        client = request.client
        assert client is not None
        assert client.host == "127.0.0.1"


class TestRequestContentType:
    """Tests for Request.content_type property."""

    def test_content_type_json(self) -> None:
        """Content-type property returns JSON type."""
        headers = [(b"content-type", b"application/json")]
        request = Request(make_scope(headers=headers), make_receive())
        assert request.content_type == "application/json"

    def test_content_type_form(self) -> None:
        """Content-type property returns form type."""
        headers = [(b"content-type", b"application/x-www-form-urlencoded")]
        request = Request(make_scope(headers=headers), make_receive())
        assert request.content_type == "application/x-www-form-urlencoded"

    def test_content_type_with_charset(self) -> None:
        """Content-type includes charset if present."""
        headers = [(b"content-type", b"text/html; charset=utf-8")]
        request = Request(make_scope(headers=headers), make_receive())
        assert request.content_type == "text/html; charset=utf-8"

    def test_content_type_none(self) -> None:
        """Content-type returns None if header not present."""
        request = Request(make_scope(headers=[]), make_receive())
        assert request.content_type is None


# =============================================================================
# Test: Lazy Properties (Headers, QueryParams, URL, State)
# =============================================================================


class TestRequestHeaders:
    """Tests for Request.headers property."""

    def test_headers_returns_headers_object(self) -> None:
        """Headers property returns Headers instance."""
        headers = [(b"content-type", b"application/json")]
        request = Request(make_scope(headers=headers), make_receive())
        assert isinstance(request.headers, Headers)

    def test_headers_case_insensitive(self) -> None:
        """Headers are case-insensitive."""
        headers = [(b"Content-Type", b"application/json")]
        request = Request(make_scope(headers=headers), make_receive())
        assert request.headers.get("content-type") == "application/json"
        assert request.headers.get("CONTENT-TYPE") == "application/json"

    def test_headers_multiple(self) -> None:
        """Multiple headers are accessible."""
        headers = [
            (b"content-type", b"application/json"),
            (b"authorization", b"Bearer token123"),
            (b"x-custom", b"value"),
        ]
        request = Request(make_scope(headers=headers), make_receive())
        assert request.headers.get("content-type") == "application/json"
        assert request.headers.get("authorization") == "Bearer token123"
        assert request.headers.get("x-custom") == "value"

    def test_headers_empty(self) -> None:
        """Empty headers returns empty Headers object."""
        request = Request(make_scope(headers=[]), make_receive())
        assert len(request.headers) == 0

    def test_headers_lazy(self) -> None:
        """Headers are created lazily (same instance on repeated access)."""
        request = Request(make_scope(headers=[(b"x-test", b"value")]), make_receive())
        headers1 = request.headers
        headers2 = request.headers
        assert headers1 is headers2


class TestRequestQueryParams:
    """Tests for Request.query_params property."""

    def test_query_params_returns_queryparams_object(self) -> None:
        """Query params property returns QueryParams instance."""
        request = Request(make_scope(query_string=b"name=john"), make_receive())
        assert isinstance(request.query_params, QueryParams)

    def test_query_params_single(self) -> None:
        """Single query parameter is accessible."""
        request = Request(make_scope(query_string=b"name=john"), make_receive())
        assert request.query_params.get("name") == "john"

    def test_query_params_multiple(self) -> None:
        """Multiple query parameters are accessible."""
        request = Request(make_scope(query_string=b"name=john&age=30"), make_receive())
        assert request.query_params.get("name") == "john"
        assert request.query_params.get("age") == "30"

    def test_query_params_url_encoded(self) -> None:
        """URL-encoded values are decoded."""
        request = Request(
            make_scope(query_string=b"email=john%40example.com"), make_receive()
        )
        assert request.query_params.get("email") == "john@example.com"

    def test_query_params_empty(self) -> None:
        """Empty query string returns empty QueryParams."""
        request = Request(make_scope(query_string=b""), make_receive())
        assert len(request.query_params) == 0
        assert request.query_params.get("missing") is None

    def test_query_params_lazy(self) -> None:
        """Query params are created lazily."""
        request = Request(make_scope(query_string=b"x=1"), make_receive())
        qp1 = request.query_params
        qp2 = request.query_params
        assert qp1 is qp2


class TestRequestURL:
    """Tests for Request.url property."""

    def test_url_returns_url_object(self) -> None:
        """URL property returns URL instance."""
        request = Request(make_scope(), make_receive())
        assert isinstance(request.url, URL)

    def test_url_basic(self) -> None:
        """URL contains scheme, host, and path."""
        request = Request(
            make_scope(scheme="http", server=("example.com", 8000), path="/test"),
            make_receive(),
        )
        url = request.url
        assert url.scheme == "http"
        assert url.path == "/test"

    def test_url_with_query(self) -> None:
        """URL includes query string."""
        request = Request(
            make_scope(path="/search", query_string=b"q=hello"), make_receive()
        )
        assert request.url.query == "q=hello"

    def test_url_default_port_http_omitted(self) -> None:
        """Default HTTP port (80) is omitted from URL."""
        request = Request(
            make_scope(scheme="http", server=("example.com", 80)), make_receive()
        )
        url_str = str(request.url)
        assert ":80" not in url_str
        assert "example.com" in url_str

    def test_url_default_port_https_omitted(self) -> None:
        """Default HTTPS port (443) is omitted from URL."""
        request = Request(
            make_scope(scheme="https", server=("example.com", 443)), make_receive()
        )
        url_str = str(request.url)
        assert ":443" not in url_str

    def test_url_non_default_port_included(self) -> None:
        """Non-default port is included in URL."""
        request = Request(
            make_scope(scheme="http", server=("example.com", 8080)), make_receive()
        )
        url_str = str(request.url)
        assert ":8080" in url_str

    def test_url_with_root_path(self) -> None:
        """URL includes root_path for mounted apps."""
        request = Request(
            make_scope(root_path="/api/v1", path="/users"), make_receive()
        )
        assert "/api/v1/users" in str(request.url)

    def test_url_fallback_to_host_header(self) -> None:
        """URL uses Host header when server is None."""
        headers = [(b"host", b"myhost.com:9000")]
        request = Request(
            make_scope(server=None, headers=headers), make_receive()
        )
        url_str = str(request.url)
        assert "myhost.com" in url_str

    def test_url_lazy(self) -> None:
        """URL is created lazily."""
        request = Request(make_scope(), make_receive())
        url1 = request.url
        url2 = request.url
        assert url1 is url2


class TestRequestState:
    """Tests for Request.state property."""

    def test_state_returns_state_object(self) -> None:
        """State property returns State instance."""
        request = Request(make_scope(), make_receive())
        assert isinstance(request.state, State)

    def test_state_set_and_get(self) -> None:
        """State allows setting and getting attributes."""
        request = Request(make_scope(), make_receive())
        request.state.user_id = 123
        request.state.username = "john"
        assert request.state.user_id == 123
        assert request.state.username == "john"

    def test_state_missing_attribute_raises(self) -> None:
        """Accessing missing state attribute raises AttributeError."""
        request = Request(make_scope(), make_receive())
        with pytest.raises(AttributeError):
            _ = request.state.nonexistent

    def test_state_isolated_per_request(self) -> None:
        """Each request has its own isolated state."""
        scope = make_scope()
        r1 = Request(scope, make_receive())
        r2 = Request(scope, make_receive())
        r1.state.value = "from_r1"
        with pytest.raises(AttributeError):
            _ = r2.state.value

    def test_state_lazy(self) -> None:
        """State is created lazily."""
        request = Request(make_scope(), make_receive())
        s1 = request.state
        s2 = request.state
        assert s1 is s2


# =============================================================================
# Test: Async Methods (Body Reading)
# =============================================================================


class TestRequestBody:
    """Tests for Request.body() async method."""

    async def test_body_empty(self) -> None:
        """Empty body returns empty bytes."""
        request = Request(make_scope(), make_receive(body=b""))
        body = await request.body()
        assert body == b""

    async def test_body_simple(self) -> None:
        """Body returns request content."""
        request = Request(make_scope(method="POST"), make_receive(body=b"hello world"))
        body = await request.body()
        assert body == b"hello world"

    async def test_body_binary(self) -> None:
        """Body handles binary content."""
        binary_data = bytes(range(256))
        request = Request(make_scope(method="POST"), make_receive(body=binary_data))
        body = await request.body()
        assert body == binary_data

    async def test_body_cached(self) -> None:
        """Body is cached after first read."""
        request = Request(make_scope(method="POST"), make_receive(body=b"data"))
        body1 = await request.body()
        body2 = await request.body()
        assert body1 == body2 == b"data"
        assert body1 is body2  # Same object

    async def test_body_large(self) -> None:
        """Body handles large content."""
        large_data = b"x" * 100000
        request = Request(make_scope(method="POST"), make_receive(body=large_data))
        body = await request.body()
        assert body == large_data
        assert len(body) == 100000


class TestRequestStream:
    """Tests for Request.stream() async method."""

    async def test_stream_empty(self) -> None:
        """Streaming empty body yields nothing."""
        request = Request(make_scope(), make_receive(body=b""))
        chunks = [chunk async for chunk in request.stream()]
        # Empty body may yield empty list or single empty chunk
        assert b"".join(chunks) == b""

    async def test_stream_single_chunk(self) -> None:
        """Streaming single chunk body."""
        request = Request(make_scope(method="POST"), make_receive(body=b"hello"))
        chunks = [chunk async for chunk in request.stream()]
        assert b"".join(chunks) == b"hello"

    async def test_stream_multiple_chunks(self) -> None:
        """Streaming multiple chunks."""
        request = Request(
            make_scope(method="POST"), make_receive(body=b"hello world!", chunked=True)
        )
        chunks = [chunk async for chunk in request.stream()]
        assert len(chunks) >= 1
        assert b"".join(chunks) == b"hello world!"

    async def test_stream_after_body_cached(self) -> None:
        """Streaming after body() returns cached body."""
        request = Request(make_scope(method="POST"), make_receive(body=b"cached"))
        # First read with body()
        await request.body()
        # Now stream should yield the cached body
        chunks = [chunk async for chunk in request.stream()]
        assert b"".join(chunks) == b"cached"

    async def test_body_after_partial_stream_raises(self) -> None:
        """Calling body() after stream() started raises RuntimeError."""
        request = Request(
            make_scope(method="POST"), make_receive(body=b"hello world!", chunked=True)
        )
        # Partially consume stream
        stream = request.stream()
        await stream.__anext__()  # Read first chunk

        # Now body() should raise
        with pytest.raises(RuntimeError, match="stream.*consuming"):
            await request.body()

    async def test_json_after_partial_stream_raises(self) -> None:
        """Calling json() after stream() started raises RuntimeError."""
        request = Request(
            make_scope(method="POST"), make_receive(body=b'{"key": "value"}', chunked=True)
        )
        # Partially consume stream
        stream = request.stream()
        await stream.__anext__()

        # Now json() should raise (it calls body() internally)
        with pytest.raises(RuntimeError, match="stream.*consuming"):
            await request.json()

    async def test_form_after_partial_stream_raises(self) -> None:
        """Calling form() after stream() started raises RuntimeError."""
        request = Request(
            make_scope(method="POST"), make_receive(body=b"name=value", chunked=True)
        )
        # Partially consume stream
        stream = request.stream()
        await stream.__anext__()

        # Now form() should raise (it calls body() internally)
        with pytest.raises(RuntimeError, match="stream.*consuming"):
            await request.form()


class TestRequestJson:
    """Tests for Request.json() async method."""

    async def test_json_object(self) -> None:
        """JSON parsing returns dict for object."""
        body = b'{"name": "john", "age": 30}'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data == {"name": "john", "age": 30}

    async def test_json_array(self) -> None:
        """JSON parsing returns list for array."""
        body = b'[1, 2, 3]'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data == [1, 2, 3]

    async def test_json_string(self) -> None:
        """JSON parsing returns str for string."""
        body = b'"hello"'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data == "hello"

    async def test_json_number(self) -> None:
        """JSON parsing returns number."""
        body = b"42"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data == 42

    async def test_json_null(self) -> None:
        """JSON parsing returns None for null."""
        body = b"null"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data is None

    async def test_json_boolean(self) -> None:
        """JSON parsing returns bool."""
        request = Request(make_scope(method="POST"), make_receive(body=b"true"))
        assert await request.json() is True

    async def test_json_nested(self) -> None:
        """JSON parsing handles nested structures."""
        body = b'{"user": {"name": "john", "roles": ["admin", "user"]}}'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data["user"]["name"] == "john"
        assert data["user"]["roles"] == ["admin", "user"]

    async def test_json_cached(self) -> None:
        """JSON is cached after first parse."""
        body = b'{"key": "value"}'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data1 = await request.json()
        data2 = await request.json()
        assert data1 == data2
        assert data1 is data2  # Same object

    async def test_json_invalid_raises(self) -> None:
        """Invalid JSON raises exception."""
        request = Request(make_scope(method="POST"), make_receive(body=b"not json"))
        with pytest.raises(Exception):  # json.JSONDecodeError or orjson.JSONDecodeError
            await request.json()

    async def test_json_empty_raises(self) -> None:
        """Empty body raises exception."""
        request = Request(make_scope(method="POST"), make_receive(body=b""))
        with pytest.raises(Exception):
            await request.json()

    async def test_json_utf8(self) -> None:
        """JSON handles UTF-8 content."""
        body = '{"message": "こんにちは"}'.encode("utf-8")
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data["message"] == "こんにちは"


class TestRequestForm:
    """Tests for Request.form() async method."""

    async def test_form_single_field(self) -> None:
        """Form parsing handles single field."""
        body = b"name=john"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["name"] == "john"

    async def test_form_multiple_fields(self) -> None:
        """Form parsing handles multiple fields."""
        body = b"name=john&age=30&city=rome"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["name"] == "john"
        assert form["age"] == "30"
        assert form["city"] == "rome"

    async def test_form_url_encoded(self) -> None:
        """Form parsing decodes URL-encoded values."""
        body = b"email=john%40example.com&message=hello%20world"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["email"] == "john@example.com"
        assert form["message"] == "hello world"

    async def test_form_multi_value_single(self) -> None:
        """Form with single occurrence returns string."""
        body = b"color=red"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["color"] == "red"
        assert isinstance(form["color"], str)

    async def test_form_multi_value_list(self) -> None:
        """Form with multiple occurrences returns list."""
        body = b"color=red&color=blue&color=green"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["color"] == ["red", "blue", "green"]

    async def test_form_empty(self) -> None:
        """Empty form returns empty dict."""
        request = Request(make_scope(method="POST"), make_receive(body=b""))
        form = await request.form()
        assert form == {}

    async def test_form_blank_value(self) -> None:
        """Form keeps blank values."""
        body = b"name=&other=value"
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["name"] == ""
        assert form["other"] == "value"

    async def test_form_utf8(self) -> None:
        """Form handles UTF-8 content."""
        # UTF-8 encoded form data
        body = "name=日本語".encode("utf-8")
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["name"] == "日本語"

    async def test_form_special_chars(self) -> None:
        """Form handles special characters."""
        body = b"data=%26%3D%3F"  # &=?
        request = Request(make_scope(method="POST"), make_receive(body=body))
        form = await request.form()
        assert form["data"] == "&=?"


# =============================================================================
# Test: Special Methods
# =============================================================================


class TestRequestRepr:
    """Tests for Request.__repr__."""

    def test_repr_get(self) -> None:
        """Repr shows method and path for GET."""
        request = Request(make_scope(method="GET", path="/users"), make_receive())
        r = repr(request)
        assert "GET" in r
        assert "/users" in r

    def test_repr_post(self) -> None:
        """Repr shows method and path for POST."""
        request = Request(make_scope(method="POST", path="/api/data"), make_receive())
        r = repr(request)
        assert "POST" in r
        assert "/api/data" in r

    def test_repr_format(self) -> None:
        """Repr follows expected format."""
        request = Request(make_scope(method="DELETE", path="/item/1"), make_receive())
        r = repr(request)
        assert r.startswith("Request(")
        assert r.endswith(")")


# =============================================================================
# Test: Edge Cases and Integration
# =============================================================================


class TestRequestEdgeCases:
    """Edge cases and integration tests."""

    def test_scope_accessible(self) -> None:
        """Raw scope is accessible for custom fields."""
        scope = make_scope()
        scope["custom_field"] = "custom_value"
        request = Request(scope, make_receive())
        assert request.scope["custom_field"] == "custom_value"

    async def test_body_then_json(self) -> None:
        """Can call body() then json() (uses cached body)."""
        body = b'{"key": "value"}'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        raw = await request.body()
        assert raw == body
        data = await request.json()
        assert data == {"key": "value"}

    async def test_json_then_body(self) -> None:
        """Can call json() then body() (body is cached during json)."""
        body = b'{"key": "value"}'
        request = Request(make_scope(method="POST"), make_receive(body=body))
        data = await request.json()
        assert data == {"key": "value"}
        raw = await request.body()
        assert raw == body

    def test_all_properties_accessible(self) -> None:
        """All properties are accessible on a single request."""
        headers = [(b"content-type", b"application/json"), (b"host", b"example.com")]
        scope = make_scope(
            method="POST",
            path="/api/users",
            query_string=b"page=1",
            headers=headers,
            scheme="https",
            server=("example.com", 443),
            client=("192.168.1.100", 54321),
        )
        request = Request(scope, make_receive())

        # All sync properties
        assert request.method == "POST"
        assert request.path == "/api/users"
        assert request.scheme == "https"
        assert request.content_type == "application/json"
        assert request.client is not None
        assert request.client.host == "192.168.1.100"
        assert request.headers.get("host") == "example.com"
        assert request.query_params.get("page") == "1"
        assert request.url is not None
        assert request.state is not None
