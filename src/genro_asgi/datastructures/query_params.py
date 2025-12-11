# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
Parsed query string parameters with multi-value support.

Purpose
=======
Query parameters are case-sensitive (unlike headers). Uses ``urllib.parse.parse_qs``
for parsing, which handles URL decoding automatically.

This module provides:
- ``QueryParams``: Parsed query string with multi-value support
- ``query_params_from_scope()``: Factory to create QueryParams from ASGI scope

ASGI Mapping::

    scope["query_string"] = b"a=1&b=2"  →  QueryParams (parsed)

Parsing Schema::

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

Differences from Headers::

    +-----------------+------------------+------------------+
    | Aspect          | Headers          | QueryParams      |
    +-----------------+------------------+------------------+
    | Case            | Case-insensitive | Case-sensitive   |
    | Storage         | list[tuple]      | dict[str, list]  |
    | Empty values    | N/A              | Supported (?k=)  |
    | URL encoding    | No (raw bytes)   | Yes (automatic)  |
    +-----------------+------------------+------------------+

Definition::

    class QueryParams:
        __slots__ = ("_params",)

        def __init__(self, query_string: bytes | str) -> None
        def get(self, key: str, default: str | None = None) -> str | None
        def getlist(self, key: str) -> list[str]
        def keys(self) -> list[str]
        def values(self) -> list[str]
        def items(self) -> list[tuple[str, str]]
        def multi_items(self) -> list[tuple[str, str]]
        def __getitem__(self, key: str) -> str
        def __contains__(self, key: object) -> bool
        def __iter__(self) -> Iterator[str]
        def __len__(self) -> int
        def __bool__(self) -> bool
        def __repr__(self) -> str

    def query_params_from_scope(scope: Mapping[str, Any]) -> QueryParams

Example::

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

Design Notes
============
- Uses ``__slots__`` for memory efficiency
- Case-sensitive (unlike Headers)
- Empty values are preserved (``?key=`` → ``""``  not ``None``)
- ``__bool__`` returns False for empty params
"""

from collections.abc import Mapping
from typing import Any, Iterator
from urllib.parse import parse_qs

__all__ = ["QueryParams", "query_params_from_scope"]


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
