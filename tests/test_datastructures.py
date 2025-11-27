# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for data structures.

These tests verify the datastructure classes defined in genro_asgi.datastructures.
Tests cover:
- Address: client/server address wrapper
- URL: URL parsing and components
- Headers: case-insensitive HTTP headers
- QueryParams: query string parameters
- State: request-scoped state container
- Helper functions: headers_from_scope, query_params_from_scope
"""

import pytest

from genro_asgi.datastructures import (
    Address,
    Headers,
    QueryParams,
    State,
    URL,
    headers_from_scope,
    query_params_from_scope,
)


class TestAddress:
    """Test Address class."""

    def test_create(self):
        """Address should store host and port."""
        addr = Address("127.0.0.1", 8000)
        assert addr.host == "127.0.0.1"
        assert addr.port == 8000

    def test_equality_with_address(self):
        """Address should equal another Address with same values."""
        a1 = Address("localhost", 80)
        a2 = Address("localhost", 80)
        a3 = Address("localhost", 8080)
        assert a1 == a2
        assert a1 != a3

    def test_equality_with_tuple(self):
        """Address should equal tuple (host, port) for ASGI compatibility."""
        addr = Address("localhost", 80)
        assert addr == ("localhost", 80)
        assert addr != ("localhost", 8080)
        assert addr != ("other", 80)

    def test_equality_with_wrong_type(self):
        """Address should not equal incompatible types."""
        addr = Address("localhost", 80)
        assert addr != "localhost:80"
        assert addr != 80
        assert addr != ["localhost", 80]
        assert addr != ("localhost", 80, "extra")

    def test_repr(self):
        """Address repr should show host and port."""
        addr = Address("localhost", 80)
        r = repr(addr)
        assert "Address" in r
        assert "localhost" in r
        assert "80" in r


class TestURL:
    """Test URL class."""

    def test_parse_full_url(self):
        """URL should parse all components."""
        url = URL("https://example.com:8080/path?query=1#frag")
        assert url.scheme == "https"
        assert url.netloc == "example.com:8080"
        assert url.hostname == "example.com"
        assert url.port == 8080
        assert url.path == "/path"
        assert url.query == "query=1"
        assert url.fragment == "frag"

    def test_parse_simple_path(self):
        """URL should handle path-only URLs."""
        url = URL("/users/123")
        assert url.path == "/users/123"
        assert url.scheme == ""
        assert url.hostname is None
        assert url.port is None

    def test_parse_url_without_port(self):
        """URL should handle URLs without explicit port."""
        url = URL("https://example.com/path")
        assert url.hostname == "example.com"
        assert url.port is None

    def test_path_default_slash(self):
        """URL path should default to '/' when empty."""
        url = URL("https://example.com")
        assert url.path == "/"

    def test_unquote_path(self):
        """URL should unquote percent-encoded path."""
        url = URL("/path%20with%20spaces")
        assert url.path == "/path with spaces"

    def test_str(self):
        """str(URL) should return original URL."""
        original = "http://test.com/path"
        url = URL(original)
        assert str(url) == original

    def test_repr(self):
        """repr(URL) should show the URL."""
        url = URL("http://test.com")
        r = repr(url)
        assert "URL" in r
        assert "http://test.com" in r

    def test_equality_with_url(self):
        """URL should equal another URL with same value."""
        url1 = URL("http://test.com")
        url2 = URL("http://test.com")
        url3 = URL("http://other.com")
        assert url1 == url2
        assert url1 != url3

    def test_equality_with_string(self):
        """URL should equal string with same value."""
        url = URL("http://test.com")
        assert url == "http://test.com"
        assert url != "http://other.com"

    def test_equality_with_wrong_type(self):
        """URL should not equal incompatible types."""
        url = URL("http://test.com")
        assert url != 123
        assert url != ["http://test.com"]


class TestHeaders:
    """Test Headers class."""

    def test_from_raw_headers(self):
        """Headers should parse raw byte headers."""
        raw = [(b"content-type", b"application/json"), (b"x-custom", b"value")]
        headers = Headers(raw)
        assert headers.get("content-type") == "application/json"
        assert headers.get("x-custom") == "value"

    def test_case_insensitive_get(self):
        """Headers.get should be case-insensitive."""
        raw = [(b"Content-Type", b"text/html")]
        headers = Headers(raw)
        assert headers.get("content-type") == "text/html"
        assert headers.get("CONTENT-TYPE") == "text/html"
        assert headers.get("Content-Type") == "text/html"

    def test_get_default(self):
        """Headers.get should return default for missing key."""
        headers = Headers([])
        assert headers.get("missing") is None
        assert headers.get("missing", "default") == "default"

    def test_getlist(self):
        """Headers.getlist should return all values for key."""
        raw = [(b"set-cookie", b"a=1"), (b"set-cookie", b"b=2")]
        headers = Headers(raw)
        assert headers.getlist("set-cookie") == ["a=1", "b=2"]

    def test_getlist_empty(self):
        """Headers.getlist should return empty list for missing key."""
        headers = Headers([])
        assert headers.getlist("missing") == []

    def test_getitem(self):
        """Headers[key] should return first value."""
        raw = [(b"x-test", b"value")]
        headers = Headers(raw)
        assert headers["x-test"] == "value"

    def test_getitem_raises_keyerror(self):
        """Headers[key] should raise KeyError for missing key."""
        headers = Headers([])
        with pytest.raises(KeyError):
            _ = headers["missing"]

    def test_contains(self):
        """'key in headers' should check case-insensitively."""
        raw = [(b"X-Test", b"yes")]
        headers = Headers(raw)
        assert "x-test" in headers
        assert "X-TEST" in headers
        assert "missing" not in headers

    def test_iter(self):
        """Iterating headers should yield unique keys."""
        raw = [(b"a", b"1"), (b"b", b"2"), (b"a", b"3")]
        headers = Headers(raw)
        keys = list(headers)
        assert keys == ["a", "b"]

    def test_len(self):
        """len(headers) should return total header count."""
        raw = [(b"a", b"1"), (b"b", b"2"), (b"a", b"3")]
        headers = Headers(raw)
        assert len(headers) == 3

    def test_keys(self):
        """Headers.keys should return unique keys in order."""
        raw = [(b"a", b"1"), (b"b", b"2"), (b"a", b"3")]
        headers = Headers(raw)
        assert headers.keys() == ["a", "b"]

    def test_values(self):
        """Headers.values should return all values."""
        raw = [(b"a", b"1"), (b"b", b"2")]
        headers = Headers(raw)
        assert headers.values() == ["1", "2"]

    def test_items(self):
        """Headers.items should return all (name, value) pairs."""
        raw = [(b"a", b"1"), (b"b", b"2")]
        headers = Headers(raw)
        assert headers.items() == [("a", "1"), ("b", "2")]

    def test_repr(self):
        """repr(Headers) should show internal list."""
        raw = [(b"a", b"1")]
        headers = Headers(raw)
        r = repr(headers)
        assert "Headers" in r

    def test_empty_headers(self):
        """Headers should handle empty list."""
        headers = Headers([])
        assert len(headers) == 0
        assert headers.keys() == []
        assert headers.get("any") is None


class TestQueryParams:
    """Test QueryParams class."""

    def test_parse_bytes(self):
        """QueryParams should parse bytes query string."""
        params = QueryParams(b"name=john&age=30")
        assert params.get("name") == "john"
        assert params.get("age") == "30"

    def test_parse_string(self):
        """QueryParams should parse string query string."""
        params = QueryParams("foo=bar")
        assert params.get("foo") == "bar"

    def test_get_default(self):
        """QueryParams.get should return default for missing key."""
        params = QueryParams(b"")
        assert params.get("missing") is None
        assert params.get("missing", "default") == "default"

    def test_multi_values(self):
        """QueryParams should handle multiple values per key."""
        params = QueryParams(b"tag=a&tag=b&tag=c")
        assert params.get("tag") == "a"
        assert params.getlist("tag") == ["a", "b", "c"]

    def test_getlist_empty(self):
        """QueryParams.getlist should return empty list for missing key."""
        params = QueryParams(b"")
        assert params.getlist("missing") == []

    def test_getitem(self):
        """QueryParams[key] should return first value."""
        params = QueryParams(b"key=value")
        assert params["key"] == "value"

    def test_getitem_raises_keyerror(self):
        """QueryParams[key] should raise KeyError for missing key."""
        params = QueryParams(b"")
        with pytest.raises(KeyError):
            _ = params["missing"]

    def test_contains(self):
        """'key in params' should check key existence."""
        params = QueryParams(b"key=value")
        assert "key" in params
        assert "other" not in params

    def test_case_sensitive(self):
        """QueryParams should be case-sensitive (unlike headers)."""
        params = QueryParams(b"Key=value")
        assert params.get("Key") == "value"
        assert params.get("key") is None

    def test_iter(self):
        """Iterating params should yield keys."""
        params = QueryParams(b"a=1&b=2")
        keys = list(params)
        assert set(keys) == {"a", "b"}

    def test_len(self):
        """len(params) should return unique key count."""
        params = QueryParams(b"a=1&b=2&a=3")
        assert len(params) == 2

    def test_bool_empty(self):
        """bool(params) should be False when empty."""
        params = QueryParams(b"")
        assert not params

    def test_bool_non_empty(self):
        """bool(params) should be True when non-empty."""
        params = QueryParams(b"a=1")
        assert params

    def test_keys(self):
        """QueryParams.keys should return all keys."""
        params = QueryParams(b"a=1&b=2")
        assert set(params.keys()) == {"a", "b"}

    def test_values(self):
        """QueryParams.values should return first value per key."""
        params = QueryParams(b"a=1&b=2&a=3")
        values = params.values()
        assert "1" in values
        assert "2" in values

    def test_items(self):
        """QueryParams.items should return (key, first_value) pairs."""
        params = QueryParams(b"a=1&b=2")
        items = params.items()
        assert ("a", "1") in items
        assert ("b", "2") in items

    def test_multi_items(self):
        """QueryParams.multi_items should return all (key, value) pairs."""
        params = QueryParams(b"a=1&a=2&b=3")
        items = params.multi_items()
        assert ("a", "1") in items
        assert ("a", "2") in items
        assert ("b", "3") in items

    def test_empty_value(self):
        """QueryParams should handle empty values."""
        params = QueryParams(b"empty=")
        assert params.get("empty") == ""

    def test_url_decoding(self):
        """QueryParams should URL-decode values."""
        params = QueryParams(b"name=hello%20world")
        assert params.get("name") == "hello world"

    def test_repr(self):
        """repr(QueryParams) should show internal dict."""
        params = QueryParams(b"a=1")
        r = repr(params)
        assert "QueryParams" in r


class TestState:
    """Test State class."""

    def test_set_get(self):
        """State should allow setting and getting attributes."""
        state = State()
        state.user_id = 123
        assert state.user_id == 123

    def test_multiple_attributes(self):
        """State should handle multiple attributes."""
        state = State()
        state.user_id = 123
        state.is_authenticated = True
        state.roles = ["admin", "user"]
        assert state.user_id == 123
        assert state.is_authenticated is True
        assert state.roles == ["admin", "user"]

    def test_overwrite_attribute(self):
        """State should allow overwriting attributes."""
        state = State()
        state.value = "old"
        state.value = "new"
        assert state.value == "new"

    def test_missing_attribute_raises(self):
        """Accessing missing attribute should raise AttributeError."""
        state = State()
        with pytest.raises(AttributeError) as exc_info:
            _ = state.missing
        assert "missing" in str(exc_info.value)

    def test_delete_attribute(self):
        """del state.attr should remove the attribute."""
        state = State()
        state.temp = "value"
        del state.temp
        with pytest.raises(AttributeError):
            _ = state.temp

    def test_delete_missing_attribute_raises(self):
        """Deleting missing attribute should raise AttributeError."""
        state = State()
        with pytest.raises(AttributeError):
            del state.missing

    def test_contains(self):
        """'name in state' should check attribute existence."""
        state = State()
        state.exists = True
        assert "exists" in state
        assert "missing" not in state

    def test_repr(self):
        """repr(State) should show internal dict."""
        state = State()
        state.key = "value"
        r = repr(state)
        assert "State" in r
        assert "key" in r


class TestHeadersFromScope:
    """Test headers_from_scope helper function."""

    def test_from_scope_with_headers(self):
        """headers_from_scope should extract headers from scope."""
        scope = {"headers": [(b"host", b"localhost"), (b"accept", b"*/*")]}
        headers = headers_from_scope(scope)
        assert headers.get("host") == "localhost"
        assert headers.get("accept") == "*/*"

    def test_from_scope_without_headers(self):
        """headers_from_scope should handle scope without headers."""
        scope = {}
        headers = headers_from_scope(scope)
        assert len(headers) == 0

    def test_from_scope_empty_headers(self):
        """headers_from_scope should handle empty headers list."""
        scope = {"headers": []}
        headers = headers_from_scope(scope)
        assert len(headers) == 0


class TestQueryParamsFromScope:
    """Test query_params_from_scope helper function."""

    def test_from_scope_with_query_string(self):
        """query_params_from_scope should extract query_string from scope."""
        scope = {"query_string": b"page=1&limit=10"}
        params = query_params_from_scope(scope)
        assert params.get("page") == "1"
        assert params.get("limit") == "10"

    def test_from_scope_without_query_string(self):
        """query_params_from_scope should handle scope without query_string."""
        scope = {}
        params = query_params_from_scope(scope)
        assert len(params) == 0

    def test_from_scope_empty_query_string(self):
        """query_params_from_scope should handle empty query_string."""
        scope = {"query_string": b""}
        params = query_params_from_scope(scope)
        assert len(params) == 0


class TestExports:
    """Test module exports."""

    def test_all_exports(self):
        """Verify __all__ contains expected exports."""
        from genro_asgi import datastructures

        expected = {
            "Address",
            "URL",
            "Headers",
            "QueryParams",
            "State",
            "headers_from_scope",
            "query_params_from_scope",
        }
        assert set(datastructures.__all__) == expected

    def test_importable_from_module(self):
        """Verify all exports are importable."""
        from genro_asgi.datastructures import (
            Address,
            Headers,
            QueryParams,
            State,
            URL,
            headers_from_scope,
            query_params_from_scope,
        )

        assert Address is not None
        assert URL is not None
        assert Headers is not None
        assert QueryParams is not None
        assert State is not None
        assert headers_from_scope is not None
        assert query_params_from_scope is not None
