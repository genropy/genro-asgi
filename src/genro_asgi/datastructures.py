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

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import time
from typing import TYPE_CHECKING, Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse
from uuid import uuid4

if TYPE_CHECKING:
    from .request import Request

__all__ = [
    "Address",
    "URL",
    "Headers",
    "QueryParams",
    "State",
    "RequestEnvelope",
    "ResponseEnvelope",
    "headers_from_scope",
    "query_params_from_scope",
]


class Address:
    """
    Client or server address wrapper.

    Wraps the ``(host, port)`` tuple used in ASGI scope for ``client`` and
    ``server`` fields. Provides named attribute access instead of tuple indexing.

    Attributes:
        host: The hostname or IP address.
        port: The port number.

    Example:
        >>> addr = Address("192.168.1.1", 8080)
        >>> addr.host
        '192.168.1.1'
        >>> addr.port
        8080
        >>> addr == ("192.168.1.1", 8080)  # Compare with ASGI tuple
        True
    """

    __slots__ = ("host", "port")

    def __init__(self, host: str, port: int) -> None:
        """
        Initialize an Address.

        Args:
            host: The hostname or IP address.
            port: The port number.
        """
        self.host = host
        self.port = port

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"Address(host={self.host!r}, port={self.port})"

    def __eq__(self, other: object) -> bool:
        """
        Compare with another Address or tuple.

        Supports comparison with ASGI-style tuples for backward compatibility.

        Args:
            other: An Address instance or a ``(host, port)`` tuple.

        Returns:
            True if host and port match, False otherwise.
        """
        if isinstance(other, Address):
            return self.host == other.host and self.port == other.port
        if isinstance(other, tuple) and len(other) == 2:
            return bool(self.host == other[0] and self.port == other[1])
        return False


class URL:
    """
    URL parser with component access.

    Parses a URL string and provides access to its components (scheme, host,
    path, query, etc.). Wraps ``urllib.parse.urlparse`` internally.

    Attributes:
        scheme: The URL scheme (e.g., "https", "http").
        netloc: Network location including host and optional port.
        path: URL path, automatically unquoted. Defaults to "/" if empty.
        query: Query string without the leading "?".
        fragment: Fragment identifier without the leading "#".
        hostname: Hostname extracted from netloc (None if not present).
        port: Port number extracted from netloc (None if not present).

    Example:
        >>> url = URL("https://example.com:8080/path?q=1#section")
        >>> url.scheme
        'https'
        >>> url.hostname
        'example.com'
        >>> url.port
        8080
        >>> url.path
        '/path'
        >>> str(url)
        'https://example.com:8080/path?q=1#section'
    """

    __slots__ = ("_url", "_parsed")

    def __init__(self, url: str) -> None:
        """
        Initialize URL from a URL string.

        Args:
            url: The URL string to parse.
        """
        self._url = url
        self._parsed = urlparse(url)

    @property
    def scheme(self) -> str:
        """The URL scheme (e.g., 'https', 'http', 'ws')."""
        return self._parsed.scheme

    @property
    def netloc(self) -> str:
        """Network location (e.g., 'user:pass@host:port')."""
        return self._parsed.netloc

    @property
    def path(self) -> str:
        """URL path, unquoted. Returns '/' if path is empty."""
        return unquote(self._parsed.path) or "/"

    @property
    def query(self) -> str:
        """Query string without leading '?'."""
        return self._parsed.query

    @property
    def fragment(self) -> str:
        """Fragment identifier without leading '#'."""
        return self._parsed.fragment

    @property
    def hostname(self) -> str | None:
        """Hostname from netloc, or None if not present."""
        return self._parsed.hostname

    @property
    def port(self) -> int | None:
        """Port number from netloc, or None if not specified."""
        return self._parsed.port

    def __str__(self) -> str:
        """Return the original URL string."""
        return self._url

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"URL({self._url!r})"

    def __eq__(self, other: object) -> bool:
        """
        Compare with another URL or string.

        Args:
            other: A URL instance or URL string.

        Returns:
            True if URLs match, False otherwise.
        """
        if isinstance(other, URL):
            return self._url == other._url
        if isinstance(other, str):
            return self._url == other
        return False


class Headers:
    """
    Immutable, case-insensitive HTTP headers with multi-value support.

    HTTP header names are case-insensitive per RFC 7230. This class normalizes
    header names to lowercase internally while preserving values. The same
    header can appear multiple times (e.g., Set-Cookie).

    ASGI provides headers as ``list[tuple[bytes, bytes]]`` with Latin-1 encoding.
    This class decodes them to strings automatically.

    This class is read-only. For mutable headers (response building), use
    ``list[tuple[bytes, bytes]]`` directly or a future MutableHeaders class.

    Example:
        >>> raw = [(b"Content-Type", b"application/json"), (b"Accept", b"text/html")]
        >>> headers = Headers(raw)
        >>> headers.get("content-type")  # Case-insensitive
        'application/json'
        >>> headers["ACCEPT"]  # Also case-insensitive
        'text/html'
        >>> "content-type" in headers
        True

        # Multi-value headers
        >>> raw = [(b"Set-Cookie", b"a=1"), (b"Set-Cookie", b"b=2")]
        >>> headers = Headers(raw)
        >>> headers.getlist("set-cookie")
        ['a=1', 'b=2']
    """

    __slots__ = ("_headers",)

    def __init__(self, raw_headers: list[tuple[bytes, bytes]]) -> None:
        """
        Initialize Headers from raw ASGI headers.

        Args:
            raw_headers: List of (name, value) byte tuples from ASGI scope.
                         Both name and value are decoded as Latin-1.
                         Names are normalized to lowercase.
        """
        self._headers: list[tuple[str, str]] = []
        for name, value in raw_headers:
            self._headers.append(
                (name.decode("latin-1").lower(), value.decode("latin-1"))
            )

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Get the first value for a header (case-insensitive).

        Args:
            key: Header name (case-insensitive).
            default: Value to return if header not found.

        Returns:
            The first value for the header, or default if not found.
        """
        key_lower = key.lower()
        for name, value in self._headers:
            if name == key_lower:
                return value
        return default

    def getlist(self, key: str) -> list[str]:
        """
        Get all values for a header (case-insensitive).

        Useful for headers that can appear multiple times like Set-Cookie.

        Args:
            key: Header name (case-insensitive).

        Returns:
            List of all values for the header, empty list if not found.
        """
        key_lower = key.lower()
        return [value for name, value in self._headers if name == key_lower]

    def keys(self) -> list[str]:
        """
        Return unique header names (lowercase).

        Returns:
            List of unique header names in order of first occurrence.
        """
        seen: set[str] = set()
        result: list[str] = []
        for name, _ in self._headers:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

    def values(self) -> list[str]:
        """
        Return all header values.

        Returns:
            List of all values in order, including duplicates.
        """
        return [value for _, value in self._headers]

    def items(self) -> list[tuple[str, str]]:
        """
        Return all (name, value) pairs.

        Returns:
            List of tuples with lowercase names, including duplicates.
        """
        return list(self._headers)

    def __getitem__(self, key: str) -> str:
        """
        Get header value by name, raising KeyError if not found.

        Args:
            key: Header name (case-insensitive).

        Returns:
            The first value for the header.

        Raises:
            KeyError: If header is not present.
        """
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key: object) -> bool:
        """Check if header exists (case-insensitive)."""
        if not isinstance(key, str):
            return False
        return self.get(key) is not None

    def __iter__(self) -> Iterator[str]:
        """Iterate over unique header names."""
        return iter(self.keys())

    def __len__(self) -> int:
        """Return total number of header entries (including duplicates)."""
        return len(self._headers)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"Headers({self._headers!r})"


class QueryParams:
    """
    Parsed query string parameters with multi-value support.

    Parses URL query strings (e.g., "name=john&tags=a&tags=b") into an
    accessible structure. Unlike Headers, parameter names are case-sensitive.

    Uses ``urllib.parse.parse_qs`` internally, which handles URL decoding
    (e.g., ``%20`` becomes space) automatically.

    Example:
        >>> params = QueryParams(b"name=john&tags=python&tags=web")
        >>> params.get("name")
        'john'
        >>> params.getlist("tags")
        ['python', 'web']
        >>> params["name"]
        'john'
        >>> "tags" in params
        True

        # Empty values are preserved
        >>> params = QueryParams("key=&other=value")
        >>> params.get("key")
        ''
    """

    __slots__ = ("_params",)

    def __init__(self, query_string: bytes | str) -> None:
        """
        Initialize QueryParams from a query string.

        Args:
            query_string: The query string to parse (bytes or str).
                          Bytes are decoded as Latin-1. URL encoding
                          (e.g., %20) is decoded automatically.
        """
        if isinstance(query_string, bytes):
            query_string = query_string.decode("latin-1")
        self._params = parse_qs(query_string, keep_blank_values=True)

    def get(self, key: str, default: str | None = None) -> str | None:
        """
        Get the first value for a parameter.

        Args:
            key: Parameter name (case-sensitive).
            default: Value to return if parameter not found.

        Returns:
            The first value for the parameter, or default if not found.
        """
        values = self._params.get(key)
        if values:
            return values[0]
        return default

    def getlist(self, key: str) -> list[str]:
        """
        Get all values for a parameter.

        Useful for parameters that appear multiple times (e.g., "?tag=a&tag=b").

        Args:
            key: Parameter name (case-sensitive).

        Returns:
            List of all values, empty list if parameter not found.
        """
        return self._params.get(key, [])

    def keys(self) -> list[str]:
        """
        Return all parameter names.

        Returns:
            List of unique parameter names.
        """
        return list(self._params.keys())

    def values(self) -> list[str]:
        """
        Return the first value for each parameter.

        Returns:
            List of first values in parameter order.
        """
        return [v[0] for v in self._params.values() if v]

    def items(self) -> list[tuple[str, str]]:
        """
        Return (name, first_value) pairs.

        Returns:
            List of tuples with first value for each parameter.
        """
        return [(k, v[0]) for k, v in self._params.items() if v]

    def multi_items(self) -> list[tuple[str, str]]:
        """
        Return all (name, value) pairs including duplicates.

        Useful for iterating all values when parameters have multiple values.

        Returns:
            List of all (name, value) tuples.

        Example:
            >>> params = QueryParams("a=1&a=2&b=3")
            >>> params.multi_items()
            [('a', '1'), ('a', '2'), ('b', '3')]
        """
        result: list[tuple[str, str]] = []
        for key, values in self._params.items():
            for value in values:
                result.append((key, value))
        return result

    def __getitem__(self, key: str) -> str:
        """
        Get parameter value by name, raising KeyError if not found.

        Args:
            key: Parameter name (case-sensitive).

        Returns:
            The first value for the parameter.

        Raises:
            KeyError: If parameter is not present.
        """
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key: object) -> bool:
        """Check if parameter exists (case-sensitive)."""
        if not isinstance(key, str):
            return False
        return key in self._params

    def __iter__(self) -> Iterator[str]:
        """Iterate over parameter names."""
        return iter(self._params)

    def __len__(self) -> int:
        """Return number of unique parameters."""
        return len(self._params)

    def __bool__(self) -> bool:
        """Return True if there are any parameters."""
        return bool(self._params)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"QueryParams({self._params!r})"


class State:
    """
    Request-scoped state container with attribute access.

    Provides ergonomic attribute-style access to request state, commonly used
    by middleware to attach data (e.g., authenticated user, request ID).

    Uses Python's magic attribute methods (``__getattr__``/``__setattr__``) to
    store data in an internal dictionary while providing ``state.attr`` syntax.
    This is a standard pattern used by Starlette, Flask, and other frameworks.

    Example:
        >>> state = State()
        >>> state.user_id = 123
        >>> state.is_authenticated = True
        >>> state.user_id
        123
        >>> "user_id" in state
        True
        >>> del state.user_id
        >>> "user_id" in state
        False

        # Missing attributes raise AttributeError
        >>> state.missing  # doctest: +IGNORE_EXCEPTION_DETAIL
        Traceback (most recent call last):
            ...
        AttributeError: State has no attribute 'missing'
    """

    __slots__ = ("_state",)

    def __init__(self) -> None:
        """
        Initialize an empty State container.

        Uses ``object.__setattr__`` to initialize the internal dict without
        triggering our custom ``__setattr__`` override.
        """
        object.__setattr__(self, "_state", {})

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Set a state attribute.

        Args:
            name: Attribute name.
            value: Value to store.
        """
        self._state[name] = value

    def __getattr__(self, name: str) -> Any:
        """
        Get a state attribute.

        Args:
            name: Attribute name.

        Returns:
            The stored value.

        Raises:
            AttributeError: If attribute does not exist.
        """
        try:
            return self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'") from None

    def __delattr__(self, name: str) -> None:
        """
        Delete a state attribute.

        Args:
            name: Attribute name to delete.

        Raises:
            AttributeError: If attribute does not exist.
        """
        try:
            del self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'") from None

    def __contains__(self, name: object) -> bool:
        """Check if attribute exists in state."""
        if not isinstance(name, str):
            return False
        return name in self._state

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return f"State({self._state!r})"


@dataclass
class RequestEnvelope:
    """
    Unified request wrapper for HTTP and WebSocket transports.

    Provides a transport-agnostic abstraction for request handling. Every incoming
    request (HTTP or WebSocket message) is wrapped in an envelope that provides:

    - Unique internal ID for tracking
    - External ID preservation for client correlation
    - TYTX mode detection and propagation
    - Unified parameter access (already hydrated if TYTX)
    - Metadata storage for middleware

    The envelope pattern enables:
    - Unified handler API regardless of transport
    - Request/response correlation
    - Automatic TYTX symmetry (receive TYTX → respond TYTX)
    - Request lifecycle tracking

    Attributes:
        internal_id: Server-generated unique ID (UUID). Always present.
        external_id: Client-provided ID (e.g., WSX message id). Optional, echoed back.
        tytx_mode: True if request had ::TYTX marker. Response will also use TYTX.
        params: Request parameters, already hydrated if TYTX mode.
        metadata: Additional context for middleware/handlers.
        created_at: Timestamp when envelope was created.
        _http_request: Reference to original HTTP Request (if HTTP transport).
        _wsx_message: Reference to original WSX message dict (if WebSocket transport).

    Example:
        >>> # HTTP request
        >>> envelope = RequestEnvelope.from_http(request)
        >>> print(envelope.internal_id)  # "550e8400-e29b-41d4-a716-446655440000"
        >>> print(envelope.params)  # {"user_id": 123}  (hydrated if TYTX)

        >>> # WebSocket message
        >>> envelope = RequestEnvelope.from_wsx(message, tytx_mode=True)
        >>> print(envelope.external_id)  # "client-req-42"
        >>> print(envelope.tytx_mode)  # True
    """

    internal_id: str = field(default_factory=lambda: str(uuid4()))
    external_id: str | None = None
    tytx_mode: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time)
    _http_request: "Request | None" = field(default=None, repr=False)
    _wsx_message: dict[str, Any] | None = field(default=None, repr=False)

    @property
    def is_http(self) -> bool:
        """True if this envelope wraps an HTTP request."""
        return self._http_request is not None

    @property
    def is_websocket(self) -> bool:
        """True if this envelope wraps a WebSocket message."""
        return self._wsx_message is not None

    @property
    def http_request(self) -> "Request":
        """
        Get the underlying HTTP request.

        Returns:
            The original HTTP Request object.

        Raises:
            RuntimeError: If this envelope is not from HTTP transport.
        """
        if self._http_request is None:
            raise RuntimeError("This envelope is not from HTTP transport")
        return self._http_request

    @property
    def wsx_message(self) -> dict[str, Any]:
        """
        Get the underlying WSX message.

        Returns:
            The original WSX message dict.

        Raises:
            RuntimeError: If this envelope is not from WebSocket transport.
        """
        if self._wsx_message is None:
            raise RuntimeError("This envelope is not from WebSocket transport")
        return self._wsx_message


@dataclass
class ResponseEnvelope:
    """
    Unified response wrapper for HTTP and WebSocket transports.

    Pairs with RequestEnvelope to complete the request/response cycle.
    Automatically inherits TYTX mode from the request envelope.

    Attributes:
        request_id: Reference to RequestEnvelope.internal_id.
        external_id: Echoed from request for client correlation.
        tytx_mode: Inherited from request. If True, response uses TYTX serialization.
        data: Response payload (will be serialized with TYTX if tytx_mode=True).
        metadata: Additional response metadata.

    Example:
        >>> # Create response from request envelope
        >>> response = ResponseEnvelope.from_request(
        ...     request_envelope,
        ...     data={"status": "ok", "user": user_data}
        ... )
        >>> print(response.tytx_mode)  # Same as request_envelope.tytx_mode
    """

    request_id: str
    external_id: str | None = None
    tytx_mode: bool = False
    data: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_request(
        cls,
        request: RequestEnvelope,
        data: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ResponseEnvelope":
        """
        Create a response envelope from a request envelope.

        Automatically copies request_id, external_id, and tytx_mode.

        Args:
            request: The request envelope to respond to.
            data: Response payload.
            metadata: Optional response metadata.

        Returns:
            A new ResponseEnvelope linked to the request.
        """
        return cls(
            request_id=request.internal_id,
            external_id=request.external_id,
            tytx_mode=request.tytx_mode,
            data=data,
            metadata=metadata or {},
        )


def headers_from_scope(scope: Mapping[str, Any]) -> Headers:
    """
    Create Headers instance from ASGI scope.

    Convenience function to extract and parse headers from an ASGI scope dict.

    Args:
        scope: ASGI scope mapping containing "headers" key.

    Returns:
        Headers instance. Returns empty Headers if "headers" not in scope.

    Example:
        >>> scope = {"type": "http", "headers": [(b"host", b"example.com")]}
        >>> headers = headers_from_scope(scope)
        >>> headers.get("host")
        'example.com'
    """
    return Headers(scope.get("headers", []))


def query_params_from_scope(scope: Mapping[str, Any]) -> QueryParams:
    """
    Create QueryParams instance from ASGI scope.

    Convenience function to extract and parse query string from an ASGI scope mapping.

    Args:
        scope: ASGI scope mapping containing "query_string" key.

    Returns:
        QueryParams instance. Returns empty QueryParams if "query_string" not in scope.

    Example:
        >>> scope = {"type": "http", "query_string": b"page=1&limit=10"}
        >>> params = query_params_from_scope(scope)
        >>> params.get("page")
        '1'
    """
    return QueryParams(scope.get("query_string", b""))
