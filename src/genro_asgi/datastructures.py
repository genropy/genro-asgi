# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Data structures for ASGI applications.

Purpose
=======
This module provides Pythonic wrapper classes around raw ASGI data structures.
ASGI uses primitive types (bytes, tuples, dicts) for efficiency. These classes
add ergonomic APIs without sacrificing performance.

Mapping from ASGI to genro-asgi classes::

    ASGI Raw Data                        genro-asgi Classes
    ─────────────────                    ──────────────────
    scope["client"] = ("1.2.3.4", 80)    →  Address(host, port)
    scope["server"] = ("example.com", 443) →  Address(host, port)
    scope["headers"] = [(b"...", b"...")]  →  Headers (case-insensitive)
    scope["query_string"] = b"a=1&b=2"   →  QueryParams (parsed)
    "https://example.com/path?q=1"       →  URL (parsed)
    scope["state"] = {}                  →  State (attribute access)

Imports Required
================
::

    from typing import Any, Iterator
    from urllib.parse import parse_qs, unquote, urlparse

Classes
=======

Address
-------
Wrapper for client/server address tuple ``(host: str, port: int)``.

Definition::

    class Address:
        __slots__ = ("host", "port")

        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port

        def __repr__(self) -> str:
            return f"Address(host={self.host!r}, port={self.port})"

        def __eq__(self, other: object) -> bool:
            # Compares with Address or tuple (for ASGI compatibility)
            if isinstance(other, Address):
                return self.host == other.host and self.port == other.port
            if isinstance(other, tuple) and len(other) == 2:
                return self.host == other[0] and self.port == other[1]
            return False

URL
---
URL parsing and component access. Wraps ``urllib.parse.urlparse``.

Definition::

    class URL:
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
            # Returns unquoted path, defaults to "/" if empty
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

URL parsing schema::

    https://user:pass@example.com:8080/path/to/resource?query=1&b=2#section
    ─────   ─────────────────────────────────────────────────────────────
    scheme          netloc                path           query    fragment
            ──────────────────────────────
            user:pass@example.com:8080
                      ───────────  ────
                      hostname     port

Headers
-------
Case-insensitive HTTP headers with multi-value support.

HTTP header names are case-insensitive per RFC 7230. The same header can
appear multiple times (e.g., Set-Cookie, Accept). ASGI provides headers as
``list[tuple[bytes, bytes]]`` with Latin-1 encoding.

Definition::

    class Headers:
        __slots__ = ("_headers",)

        def __init__(self, raw_headers: list[tuple[bytes, bytes]]) -> None:
            # Normalize: decode bytes to str, lowercase names
            self._headers: list[tuple[str, str]] = []
            for name, value in raw_headers:
                self._headers.append((
                    name.decode("latin-1").lower(),
                    value.decode("latin-1")
                ))

        def get(self, key: str, default: str | None = None) -> str | None:
            # Returns first value for key (case-insensitive)
            key_lower = key.lower()
            for name, value in self._headers:
                if name == key_lower:
                    return value
            return default

        def getlist(self, key: str) -> list[str]:
            # Returns all values for key (case-insensitive)
            key_lower = key.lower()
            return [value for name, value in self._headers if name == key_lower]

        def keys(self) -> list[str]:
            # Returns unique header names (preserves first occurrence order)
            seen: set[str] = set()
            result: list[str] = []
            for name, _ in self._headers:
                if name not in seen:
                    seen.add(name)
                    result.append(name)
            return result

        def values(self) -> list[str]:
            # Returns all header values
            return [value for _, value in self._headers]

        def items(self) -> list[tuple[str, str]]:
            # Returns all (name, value) pairs
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

Headers processing schema::

    Input ASGI (bytes, case-preserving):
    [(b"Content-Type", b"application/json"), (b"X-Custom", b"value")]
                        ↓
                Normalization
                        ↓
    Internal storage (str, lowercase names):
    [("content-type", "application/json"), ("x-custom", "value")]
                        ↓
                Case-insensitive lookup
                        ↓
    headers.get("CONTENT-TYPE") → "application/json"

QueryParams
-----------
Parsed query string parameters with multi-value support.

Query parameters are case-sensitive (unlike headers). Uses ``urllib.parse.parse_qs``
for parsing, which handles URL decoding automatically.

Definition::

    class QueryParams:
        __slots__ = ("_params",)

        def __init__(self, query_string: bytes | str) -> None:
            if isinstance(query_string, bytes):
                query_string = query_string.decode("latin-1")
            self._params = parse_qs(query_string, keep_blank_values=True)

        def get(self, key: str, default: str | None = None) -> str | None:
            # Returns first value for key
            values = self._params.get(key)
            if values:
                return values[0]
            return default

        def getlist(self, key: str) -> list[str]:
            # Returns all values for key
            return self._params.get(key, [])

        def keys(self) -> list[str]:
            return list(self._params.keys())

        def values(self) -> list[str]:
            # Returns first value for each key
            return [v[0] for v in self._params.values() if v]

        def items(self) -> list[tuple[str, str]]:
            # Returns (key, first_value) pairs
            return [(k, v[0]) for k, v in self._params.items() if v]

        def multi_items(self) -> list[tuple[str, str]]:
            # Returns all (key, value) pairs including duplicates
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

QueryParams parsing schema::

    Query string: "name=john&tags=python&tags=web&empty="
                        ↓
                urllib.parse.parse_qs
                        ↓
    Internal dict: {
        "name": ["john"],
        "tags": ["python", "web"],
        "empty": [""]
    }
                        ↓
    params.get("name") → "john"
    params.getlist("tags") → ["python", "web"]
    params.get("missing") → None

Differences between Headers and QueryParams:

    +-----------------+------------------+------------------+
    | Aspect          | Headers          | QueryParams      |
    +-----------------+------------------+------------------+
    | Case            | Case-insensitive | Case-sensitive   |
    | Storage         | list[tuple]      | dict[str, list]  |
    | Empty values    | N/A              | Supported (?k=)  |
    | URL encoding    | No (raw bytes)   | Yes (automatic)  |
    +-----------------+------------------+------------------+

State
-----
Request-scoped data container with attribute access.

Uses magic attribute methods (``__getattr__``/``__setattr__``) to provide
ergonomic attribute-style access while storing data in an internal dict.
This is a standard pattern used by Starlette, Flask, and other frameworks.

Definition::

    class State:
        __slots__ = ("_state",)

        def __init__(self) -> None:
            # Must use object.__setattr__ to bypass our override
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

Helper Functions
================

headers_from_scope
------------------
Creates Headers instance from ASGI scope.

Definition::

    def headers_from_scope(scope: dict[str, Any]) -> Headers:
        return Headers(scope.get("headers", []))

query_params_from_scope
-----------------------
Creates QueryParams instance from ASGI scope.

Definition::

    def query_params_from_scope(scope: dict[str, Any]) -> QueryParams:
        return QueryParams(scope.get("query_string", b""))

Public Exports
==============
The module exports (via __all__)::

    __all__ = [
        "Address",
        "URL",
        "Headers",
        "QueryParams",
        "State",
        "headers_from_scope",
        "query_params_from_scope",
    ]

Examples
========
Address usage::

    from genro_asgi.datastructures import Address

    client = Address("192.168.1.1", 54321)
    print(client.host)  # "192.168.1.1"
    print(client.port)  # 54321

    # Comparison with ASGI tuple
    assert client == ("192.168.1.1", 54321)

URL usage::

    from genro_asgi.datastructures import URL

    url = URL("https://example.com:8080/path?query=1#section")
    print(url.scheme)    # "https"
    print(url.hostname)  # "example.com"
    print(url.port)      # 8080
    print(url.path)      # "/path"
    print(url.query)     # "query=1"
    print(url.fragment)  # "section"

Headers usage::

    from genro_asgi.datastructures import Headers, headers_from_scope

    # From raw headers
    raw = [(b"Content-Type", b"application/json"), (b"Accept", b"text/html")]
    headers = Headers(raw)
    print(headers.get("content-type"))  # "application/json" (case-insensitive)
    print(headers["accept"])            # "text/html"

    # From ASGI scope
    scope = {"headers": [(b"Host", b"example.com")]}
    headers = headers_from_scope(scope)
    print(headers.get("host"))  # "example.com"

    # Multi-value headers
    raw = [(b"Set-Cookie", b"a=1"), (b"Set-Cookie", b"b=2")]
    headers = Headers(raw)
    print(headers.getlist("set-cookie"))  # ["a=1", "b=2"]

QueryParams usage::

    from genro_asgi.datastructures import QueryParams, query_params_from_scope

    # From query string
    params = QueryParams(b"name=john&tags=python&tags=web")
    print(params.get("name"))       # "john"
    print(params.getlist("tags"))   # ["python", "web"]

    # From ASGI scope
    scope = {"query_string": b"page=1&limit=10"}
    params = query_params_from_scope(scope)
    print(params.get("page"))   # "1"
    print(params.get("limit"))  # "10"

State usage::

    from genro_asgi.datastructures import State

    state = State()
    state.user_id = 123
    state.is_authenticated = True

    print(state.user_id)          # 123
    print("user_id" in state)     # True
    print("missing" in state)     # False

    del state.user_id
    # state.user_id  # Raises AttributeError

Design Decisions
================
1. **All classes use __slots__**:
   Memory efficiency (~40% less per instance), faster attribute access,
   and prevention of attribute typos. All datastructure classes benefit
   from these optimizations since many instances may be created.

2. **Single-argument constructors with helper functions**:
   Headers and QueryParams accept only their raw data (raw_headers, query_string).
   To create from ASGI scope, use the helper functions ``headers_from_scope()``
   and ``query_params_from_scope()``. This design was chosen over dual-parameter
   constructors because:
   - API is more explicit and unambiguous
   - No confusion about parameter priority
   - Type hints are cleaner (no Optional parameters)
   - Consistent pattern with URL (string-only constructor)
   - Better separation of concerns (class handles data, function handles extraction)

3. **Headers is immutable (read-only)**:
   Headers class does not provide mutation methods. For response headers,
   either use ``list[tuple[bytes, bytes]]`` directly or a future MutableHeaders
   class if needed. Immutability prevents accidental modification of request
   headers.

4. **Address compares equal to tuple**:
   For backward compatibility with code expecting ASGI tuples, Address
   implements ``__eq__`` to compare with ``tuple[str, int]``. No ``__hash__``
   is provided (can be added if dict key usage is needed).

5. **State uses magic attributes pattern**:
   The ``__getattr__``/``__setattr__`` override pattern is standard in web
   frameworks (Starlette, Flask, Werkzeug). It provides ergonomic attribute
   access (``state.user``) instead of dict access (``state["user"]``).

6. **No entry point for utility module**:
   This module contains multiple utility classes with no single "primary" class.
   The ``if __name__ == '__main__'`` pattern applies to modules with a main
   class (Application, Request, etc.), not pure utility modules.

What This Module Does NOT Include
=================================
- **MutableHeaders**: Will be added in response module (Block 05) if needed.
  Current Headers is read-only for request headers.

- **URL.replace()**: Method to create modified URLs can be added later if needed
  for redirect/link building use cases.

- **Address.__hash__**: Can be added if Address needs to be used as dict key.
  Currently not hashable.

- **Address.__iter__**: Tuple unpacking (``host, port = address``) not supported.
  Use explicit ``address.host, address.port`` access.

- **url_from_scope()**: Factory to build URL from ASGI scope components.
  Can be added when URL construction from scope is needed.

References
==========
- ASGI Specification: https://asgi.readthedocs.io/en/latest/specs/main.html
- HTTP Headers (RFC 7230): https://tools.ietf.org/html/rfc7230#section-3.2
- URL Syntax (RFC 3986): https://tools.ietf.org/html/rfc3986
- urllib.parse: https://docs.python.org/3/library/urllib.parse.html
"""

from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

__all__ = [
    "Address",
    "URL",
    "Headers",
    "QueryParams",
    "State",
    "headers_from_scope",
    "query_params_from_scope",
]


class Address:
    """Client or server address."""

    __slots__ = ("host", "port")

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    def __repr__(self) -> str:
        return f"Address(host={self.host!r}, port={self.port})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.host == other.host and self.port == other.port
        if isinstance(other, tuple) and len(other) == 2:
            return bool(self.host == other[0] and self.port == other[1])
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
    """Case-insensitive HTTP headers with multi-value support."""

    __slots__ = ("_headers",)

    def __init__(self, raw_headers: list[tuple[bytes, bytes]]) -> None:
        self._headers: list[tuple[str, str]] = []
        for name, value in raw_headers:
            self._headers.append(
                (name.decode("latin-1").lower(), value.decode("latin-1"))
            )

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
        """Return unique header names."""
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

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return self.get(key) is not None

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def __len__(self) -> int:
        return len(self._headers)

    def __repr__(self) -> str:
        return f"Headers({self._headers!r})"


class QueryParams:
    """Query string parameters with multi-value support."""

    __slots__ = ("_params",)

    def __init__(self, query_string: bytes | str) -> None:
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

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
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
    """Request/application state container with attribute access."""

    __slots__ = ("_state",)

    def __init__(self) -> None:
        object.__setattr__(self, "_state", {})

    def __setattr__(self, name: str, value: Any) -> None:
        self._state[name] = value

    def __getattr__(self, name: str) -> Any:
        try:
            return self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'") from None

    def __delattr__(self, name: str) -> None:
        try:
            del self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'") from None

    def __contains__(self, name: object) -> bool:
        if not isinstance(name, str):
            return False
        return name in self._state

    def __repr__(self) -> str:
        return f"State({self._state!r})"


def headers_from_scope(scope: dict[str, Any]) -> Headers:
    """Create Headers from ASGI scope."""
    return Headers(scope.get("headers", []))


def query_params_from_scope(scope: dict[str, Any]) -> QueryParams:
    """Create QueryParams from ASGI scope."""
    return QueryParams(scope.get("query_string", b""))
