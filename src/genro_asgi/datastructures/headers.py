# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Case-insensitive HTTP headers with multi-value support.

Purpose
=======
HTTP header names are case-insensitive per RFC 7230. The same header can
appear multiple times (e.g., Set-Cookie, Accept). ASGI provides headers as
``list[tuple[bytes, bytes]]`` with Latin-1 encoding.

This module provides:
- ``Headers``: Immutable, case-insensitive header collection
- ``headers_from_scope()``: Factory to create Headers from ASGI scope

ASGI Mapping::

    scope["headers"] = [(b"...", b"...")]  →  Headers (case-insensitive)

Processing Schema::

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

Definition::

    class Headers:
        __slots__ = ("_headers",)

        def __init__(self, raw_headers: list[tuple[bytes, bytes]]) -> None
        def get(self, key: str, default: str | None = None) -> str | None
        def getlist(self, key: str) -> list[str]
        def keys(self) -> list[str]
        def values(self) -> list[str]
        def items(self) -> list[tuple[str, str]]
        def __getitem__(self, key: str) -> str
        def __contains__(self, key: object) -> bool
        def __iter__(self) -> Iterator[str]
        def __len__(self) -> int
        def __repr__(self) -> str

    def headers_from_scope(scope: Mapping[str, Any]) -> Headers

Example::

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

Design Notes
============
- Uses ``__slots__`` for memory efficiency
- Headers is immutable (read-only) - no mutation methods
- For response headers, use ``list[tuple[bytes, bytes]]`` directly
- Names normalized to lowercase, values preserved as-is

References
==========
- HTTP Headers (RFC 7230): https://tools.ietf.org/html/rfc7230#section-3.2
- ASGI Specification: https://asgi.readthedocs.io/en/latest/specs/main.html
"""

from collections.abc import Mapping
from typing import Any, Iterator

__all__ = ["Headers", "headers_from_scope"]


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
