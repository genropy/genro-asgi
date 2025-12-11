# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""
URL parser with component access.

Purpose
=======
Parses a URL string and provides access to its components (scheme, host,
path, query, etc.). Wraps ``urllib.parse.urlparse`` internally.

URL Parsing Schema::

    https://user:pass@example.com:8080/path/to/resource?query=1&b=2#section
    ─────   ─────────────────────────────────────────────────────────────
    scheme          netloc                path           query    fragment
            ──────────────────────────────
            user:pass@example.com:8080
                      ───────────  ────
                      hostname     port

Definition::

    class URL:
        __slots__ = ("_url", "_parsed")

        def __init__(self, url: str) -> None
        @property scheme -> str
        @property netloc -> str
        @property path -> str  # Unquoted, defaults to "/"
        @property query -> str
        @property fragment -> str
        @property hostname -> str | None
        @property port -> int | None
        def __str__(self) -> str
        def __repr__(self) -> str
        def __eq__(self, other: object) -> bool

Example::

    from genro_asgi.datastructures import URL

    url = URL("https://example.com:8080/path?query=1#section")
    print(url.scheme)    # "https"
    print(url.hostname)  # "example.com"
    print(url.port)      # 8080
    print(url.path)      # "/path"
    print(url.query)     # "query=1"
    print(url.fragment)  # "section"

Design Notes
============
- Uses ``__slots__`` for memory efficiency
- Compares equal to ``str`` for convenience
- Path is automatically unquoted and defaults to "/" if empty
- No ``replace()`` method (can be added for redirect/link building)

References
==========
- URL Syntax (RFC 3986): https://tools.ietf.org/html/rfc3986
- urllib.parse: https://docs.python.org/3/library/urllib.parse.html
"""

from urllib.parse import unquote, urlparse

__all__ = ["URL"]


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
