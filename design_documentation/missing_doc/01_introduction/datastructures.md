## Source: initial_implementation_plan/archive/02-datastructures.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types
**Commit message**: `feat(datastructures): add Headers, QueryParams, URL, State, Address`

Reusable data structures for request/response handling. Each is usable standalone.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Data structures for ASGI applications."""

from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

class Address:
    """Client or server address."""

def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

def __repr__(self) -> str:
        return f"Address(host={self.host!r}, port={self.port})"

def __eq__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.host == other.host and self.port == other.port
        if isinstance(other, tuple) and len(other) == 2:
            return self.host == other[0] and self.port == other[1]
        return False

class URL:
    """URL parsing and components."""

__slots__ = ("_url", "_parsed")

def __init__(self, url: str) -> None:
        self._url = url
        self._parsed = urlparse(url)

@property
    def scheme(self) -> str:
        return self._parsed.scheme

@property
    def netloc(self) -> str:
        return self._parsed.netloc

@property
    def path(self) -> str:
        return unquote(self._parsed.path) or "/"

@property
    def query(self) -> str:
        return self._parsed.query

@property
    def fragment(self) -> str:
        return self._parsed.fragment

@property
    def hostname(self) -> str | None:
        return self._parsed.hostname

@property
    def port(self) -> int | None:
        return self._parsed.port

def __str__(self) -> str:
        return self._url

def __repr__(self) -> str:
        return f"URL({self._url!r})"

def __eq__(self, other: object) -> bool:
        if isinstance(other, URL):
            return self._url == other._url
        if isinstance(other, str):
            return self._url == other
        return False

class Headers:
    """
    Case-insensitive HTTP headers.

Supports multiple values per key (as per HTTP spec).
    """

def __init__(
        self,
        raw_headers: list[tuple[bytes, bytes]] | None = None,
        scope: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize headers.

Args:
            raw_headers: List of (name, value) byte tuples from ASGI scope
            scope: ASGI scope dict (will extract 'headers' key)
        """
        if scope is not None:
            raw_headers = scope.get("headers", [])
        self._headers: list[tuple[str, str]] = []
        if raw_headers:
            for name, value in raw_headers:
                self._headers.append((
                    name.decode("latin-1").lower(),
                    value.decode("latin-1")
                ))

def get(self, key: str, default: str | None = None) -> str | None:
        """Get first value for key (case-insensitive)."""
        key_lower = key.lower()
        for name, value in self._headers:
            if name == key_lower:
                return value
        return default

def getlist(self, key: str) -> list[str]:
        """Get all values for key (case-insensitive)."""
        key_lower = key.lower()
        return [value for name, value in self._headers if name == key_lower]

def keys(self) -> list[str]:
        """Return all header names."""
        seen: set[str] = set()
        result: list[str] = []
        for name, _ in self._headers:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

def values(self) -> list[str]:
        """Return all header values."""
        return [value for _, value in self._headers]

def items(self) -> list[tuple[str, str]]:
        """Return all (name, value) pairs."""
        return list(self._headers)

def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

def __len__(self) -> int:
        return len(self._headers)

def __repr__(self) -> str:
        return f"Headers({self._headers!r})"

class QueryParams:
    """
    Query string parameters.

Supports multiple values per key.
    """

def __init__(
        self,
        query_string: bytes | str | None = None,
        scope: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize query params.

Args:
            query_string: Raw query string (bytes or str)
            scope: ASGI scope dict (will extract 'query_string' key)
        """
        if scope is not None:
            query_string = scope.get("query_string", b"")

if query_string is None:
            query_string = b""

if isinstance(query_string, bytes):
            query_string = query_string.decode("latin-1")

self._params = parse_qs(query_string, keep_blank_values=True)

def get(self, key: str, default: str | None = None) -> str | None:
        """Get first value for key."""
        values = self._params.get(key)
        if values:
            return values[0]
        return default

def getlist(self, key: str) -> list[str]:
        """Get all values for key."""
        return self._params.get(key, [])

def keys(self) -> list[str]:
        """Return all parameter names."""
        return list(self._params.keys())

def values(self) -> list[str]:
        """Return first value for each parameter."""
        return [v[0] for v in self._params.values() if v]

def items(self) -> list[tuple[str, str]]:
        """Return (name, first_value) pairs."""
        return [(k, v[0]) for k, v in self._params.items() if v]

def multi_items(self) -> list[tuple[str, str]]:
        """Return all (name, value) pairs including duplicates."""
        result: list[tuple[str, str]] = []
        for key, values in self._params.items():
            for value in values:
                result.append((key, value))
        return result

def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

def __contains__(self, key: str) -> bool:
        return key in self._params

def __iter__(self) -> Iterator[str]:
        return iter(self._params)

def __len__(self) -> int:
        return len(self._params)

def __bool__(self) -> bool:
        return bool(self._params)

def __repr__(self) -> str:
        return f"QueryParams({self._params!r})"

class State:
    """
    Request/application state container.

Allows arbitrary attribute access for storing request-scoped data.
    """

def __init__(self) -> None:
        object.__setattr__(self, "_state", {})

def __setattr__(self, name: str, value: Any) -> None:
        self._state[name] = value

def __getattr__(self, name: str) -> Any:
        try:
            return self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'")

def __delattr__(self, name: str) -> None:
        try:
            del self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'")

def __contains__(self, name: str) -> bool:
        return name in self._state

def __repr__(self) -> str:
        return f"State({self._state!r})"
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for data structures."""

import pytest
from genro_asgi.datastructures import Address, Headers, QueryParams, State, URL

class TestAddress:
    def test_create(self):
        addr = Address("127.0.0.1", 8000)
        assert addr.host == "127.0.0.1"
        assert addr.port == 8000

def test_equality_with_address(self):
        a1 = Address("localhost", 80)
        a2 = Address("localhost", 80)
        assert a1 == a2

def test_equality_with_tuple(self):
        addr = Address("localhost", 80)
        assert addr == ("localhost", 80)

def test_repr(self):
        addr = Address("localhost", 80)
        assert "localhost" in repr(addr)

class TestURL:
    def test_parse_full_url(self):
        url = URL("https://example.com:8080/path?query=1#frag")
        assert url.scheme == "https"
        assert url.hostname == "example.com"
        assert url.port == 8080
        assert url.path == "/path"
        assert url.query == "query=1"
        assert url.fragment == "frag"

def test_parse_simple_path(self):
        url = URL("/users/123")
        assert url.path == "/users/123"
        assert url.scheme == ""

def test_str(self):
        url = URL("http://test.com")
        assert str(url) == "http://test.com"

def test_equality(self):
        url = URL("http://test.com")
        assert url == URL("http://test.com")
        assert url == "http://test.com"

def test_unquote_path(self):
        url = URL("/path%20with%20spaces")
        assert url.path == "/path with spaces"

class TestHeaders:
    def test_from_raw_headers(self):
        raw = [(b"content-type", b"application/json"), (b"x-custom", b"value")]
        headers = Headers(raw_headers=raw)
        assert headers.get("content-type") == "application/json"
        assert headers.get("x-custom") == "value"

def test_case_insensitive(self):
        raw = [(b"Content-Type", b"text/html")]
        headers = Headers(raw_headers=raw)
        assert headers.get("content-type") == "text/html"
        assert headers.get("CONTENT-TYPE") == "text/html"

def test_getlist(self):
        raw = [(b"set-cookie", b"a=1"), (b"set-cookie", b"b=2")]
        headers = Headers(raw_headers=raw)
        assert headers.getlist("set-cookie") == ["a=1", "b=2"]

def test_getitem_raises(self):
        headers = Headers(raw_headers=[])
        with pytest.raises(KeyError):
            _ = headers["missing"]

def test_contains(self):
        raw = [(b"x-test", b"yes")]
        headers = Headers(raw_headers=raw)
        assert "x-test" in headers
        assert "missing" not in headers

def test_from_scope(self):
        scope = {"headers": [(b"host", b"localhost")]}
        headers = Headers(scope=scope)
        assert headers.get("host") == "localhost"

def test_len(self):
        raw = [(b"a", b"1"), (b"b", b"2")]
        headers = Headers(raw_headers=raw)
        assert len(headers) == 2

class TestQueryParams:
    def test_parse_query_string(self):
        params = QueryParams(query_string=b"name=john&age=30")
        assert params.get("name") == "john"
        assert params.get("age") == "30"

def test_parse_string(self):
        params = QueryParams(query_string="foo=bar")
        assert params.get("foo") == "bar"

def test_multi_values(self):
        params = QueryParams(query_string=b"tag=a&tag=b&tag=c")
        assert params.get("tag") == "a"
        assert params.getlist("tag") == ["a", "b", "c"]

def test_missing_key(self):
        params = QueryParams(query_string=b"")
        assert params.get("missing") is None
        assert params.get("missing", "default") == "default"

def test_getitem_raises(self):
        params = QueryParams(query_string=b"")
        with pytest.raises(KeyError):
            _ = params["missing"]

def test_contains(self):
        params = QueryParams(query_string=b"key=value")
        assert "key" in params
        assert "other" not in params

def test_from_scope(self):
        scope = {"query_string": b"x=1"}
        params = QueryParams(scope=scope)
        assert params.get("x") == "1"

def test_bool_empty(self):
        params = QueryParams(query_string=b"")
        assert not params

def test_bool_non_empty(self):
        params = QueryParams(query_string=b"a=1")
        assert params

def test_multi_items(self):
        params = QueryParams(query_string=b"a=1&a=2&b=3")
        items = params.multi_items()
        assert ("a", "1") in items
        assert ("a", "2") in items
        assert ("b", "3") in items

class TestState:
    def test_set_get(self):
        state = State()
        state.user_id = 123
        assert state.user_id == 123

def test_missing_attribute(self):
        state = State()
        with pytest.raises(AttributeError):
            _ = state.missing

def test_delete(self):
        state = State()
        state.temp = "value"
        del state.temp
        with pytest.raises(AttributeError):
            _ = state.temp

def test_contains(self):
        state = State()
        state.exists = True
        assert "exists" in state
        assert "missing" not in state

def test_repr(self):
        state = State()
        state.key = "value"
        assert "key" in repr(state)
```

```python
from .datastructures import Address, Headers, QueryParams, State, URL
```

- [ ] Create `src/genro_asgi/datastructures.py`
- [ ] Create `tests/test_datastructures.py`
- [ ] Run `pytest tests/test_datastructures.py`
- [ ] Run `mypy src/genro_asgi/datastructures.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

