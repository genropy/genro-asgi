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

"""
HTTP Request wrapper for ASGI applications.

This module provides the Request class, a high-level wrapper around the raw ASGI
scope and receive callable. It offers an ergonomic API for accessing request
metadata (method, path, headers, query parameters) and reading the request body
in various formats (raw bytes, JSON, form data).

Design Philosophy
=================
The Request class follows these principles:

1. **Lazy evaluation**: Headers, query parameters, URL, and state are created
   only when first accessed, avoiding unnecessary object creation.

2. **Single read**: The request body can only be read ONCE from the ASGI receive
   callable. Once read, it is cached internally for subsequent access.

3. **Immutable view**: The Request provides a read-only view of the incoming
   request data. Modifications should be made through middleware or State.

4. **Zero dependencies**: Uses only Python stdlib, with optional orjson support
   for faster JSON parsing.

ASGI Scope Mapping
==================
The Request class wraps the following ASGI HTTP scope fields::

    ASGI scope field          Request property/method
    ================          =======================
    scope["method"]           request.method -> str
    scope["path"]             request.path -> str
    scope["scheme"]           request.scheme -> str
    scope["query_string"]     request.query_params -> QueryParams
    scope["headers"]          request.headers -> Headers
    scope["server"]           (used in url construction)
    scope["client"]           request.client -> Address | None
    scope["root_path"]        (used in url construction)
    (computed)                request.url -> URL
    (internal)                request.state -> State

Body Reading (IMPORTANT)
========================
The request body is received through the ASGI receive callable as a sequence
of ``http.request`` messages. Key constraints:

1. **Single consumption**: The receive callable can only be consumed ONCE.
   After reading, the body is cached in ``_body`` for subsequent access.

2. **stream() vs body()**: These methods are MUTUALLY EXCLUSIVE.

   - Use ``stream()`` when you need to process large bodies in chunks
     without loading everything into memory.
   - Use ``body()`` when you need the complete body as bytes.
   - Calling ``body()`` (or ``json()``/``form()``) after ``stream()`` has
     started consuming raises ``RuntimeError``.

3. **Caching behavior**:

   - ``body()`` caches the complete body, subsequent calls return cached value
   - ``json()`` caches the parsed JSON, subsequent calls return cached value
   - ``form()`` does NOT cache - parses body each time (body itself is cached)

JSON Parsing
============
The ``json()`` method supports two backends:

1. **orjson** (if installed): Faster, accepts bytes directly, assumes UTF-8
2. **stdlib json**: Fallback, decodes body as UTF-8 before parsing

Charset handling:
- JSON is **always decoded as UTF-8** (RFC 8259 standard)
- Content-Type charset parameter is ignored for JSON parsing
- Invalid UTF-8 sequences will raise an exception

Form Parsing
============
The ``form()`` method supports only ``application/x-www-form-urlencoded``:

- Decodes body as UTF-8
- Uses stdlib ``urllib.parse.parse_qs``
- Returns single values (not lists) when field appears once
- Returns lists when field appears multiple times

**NOT SUPPORTED**: multipart/form-data (file uploads). For multipart support,
use a dedicated library or middleware (future consideration).

Charset handling:
- Form data is **always decoded as UTF-8** (modern standard)
- Content-Type charset parameter is ignored

Class: Request
==============
Main class providing the request wrapper.

Constructor
-----------
``__init__(self, scope: Scope, receive: Receive) -> None``

Args:
    scope: ASGI HTTP connection scope dict. Must contain at minimum:
           - type: "http"
           - method: HTTP method string
           - path: Request path string
    receive: ASGI receive callable for reading body messages

The constructor initializes lazy attributes to None. No I/O is performed.

Slots
-----
The class uses ``__slots__`` for memory efficiency::

    __slots__ = (
        "_scope",            # Scope: raw ASGI scope dict
        "_receive",          # Receive: ASGI receive callable
        "_body",             # bytes | None: cached body after read
        "_json",             # Any: cached parsed JSON
        "_headers",          # Headers | None: lazy headers object
        "_query_params",     # QueryParams | None: lazy query params
        "_url",              # URL | None: lazy URL object
        "_state",            # State | None: lazy state object
        "_stream_consumed",  # bool: True if stream() started consuming
    )

Properties (Synchronous)
------------------------
These properties access scope data synchronously:

``scope -> Scope``
    Raw ASGI scope dict. Provides access to any scope field not exposed
    through dedicated properties.

``method -> str``
    HTTP method: "GET", "POST", "PUT", "DELETE", etc.
    Default: "GET" if not in scope.

``path -> str``
    Request path without query string: "/users/123", "/api/items".
    Default: "/" if not in scope.

``scheme -> str``
    URL scheme: "http" or "https".
    Default: "http" if not in scope.

``url -> URL``
    Full request URL as URL object. Constructed lazily from:
    - scheme (from scope)
    - server host:port (from scope, or Host header fallback)
    - root_path + path (for mounted applications)
    - query_string (if present)

    URL construction rules:
    - Default ports (80 for http, 443 for https) are omitted from netloc
    - If server is None, uses Host header or "localhost" fallback
    - Query string is decoded as latin-1 (HTTP standard)

``headers -> Headers``
    Request headers as case-insensitive Headers object.
    Created lazily using headers_from_scope() helper.

``query_params -> QueryParams``
    Query string parameters as QueryParams object.
    Created lazily using query_params_from_scope() helper.

``client -> Address | None``
    Client address (host, port) if available.
    Returns None when client info is not available (e.g., Unix sockets, tests).

``state -> State``
    Request-scoped state container for storing custom data.
    Each Request instance has its own isolated State.
    Use for passing data between middleware and handlers.

``content_type -> str | None``
    Shortcut for headers.get("content-type").
    Returns None if Content-Type header is not present.

Methods (Asynchronous)
----------------------
These methods perform I/O and must be awaited:

``async def body(self) -> bytes``
    Read and return the complete request body as bytes.

    - First call reads from receive() and caches result
    - Subsequent calls return cached value
    - Empty body returns b""

    Returns:
        Complete request body as bytes

    Raises:
        RuntimeError: If stream() has already started consuming the body.

``async def stream(self) -> AsyncIterator[bytes]``
    Yield request body chunks as they arrive.

    Use for large request bodies to avoid memory issues.
    Each chunk is raw bytes from receive() messages.

    - If body was already read (cached), yields the cached body as single chunk
    - Empty chunks from receive() are skipped
    - Iteration ends when more_body is False
    - Once iteration starts, body()/json()/form() will raise RuntimeError

    Yields:
        Body chunks as bytes

    Note:
        Mutually exclusive with body(). Once stream() starts consuming,
        body()/json()/form() cannot be used.

``async def json(self) -> Any``
    Parse request body as JSON and return the result.

    - First call parses and caches result
    - Subsequent calls return cached value
    - Uses orjson if available, else stdlib json
    - Body is decoded as UTF-8

    Returns:
        Parsed JSON (dict, list, str, int, float, bool, or None)

    Raises:
        json.JSONDecodeError: If body is not valid JSON (stdlib)
        orjson.JSONDecodeError: If body is not valid JSON (orjson)

``async def form(self) -> dict[str, Any]``
    Parse request body as URL-encoded form data.

    Only supports application/x-www-form-urlencoded.
    For multipart/form-data, use dedicated middleware.

    - Body is decoded as UTF-8
    - Single-value fields return string
    - Multi-value fields return list of strings
    - URL-encoded values are decoded (e.g., %40 -> @)

    Returns:
        Dict mapping field names to values (str or list[str])

Special Methods
---------------
``__repr__(self) -> str``
    Returns string representation: "Request(method='GET', path='/users')"

Usage Examples
==============
Basic request handling::

    async def handler(scope, receive, send):
        request = Request(scope, receive)

        # Access metadata
        print(f"{request.method} {request.path}")
        print(f"Client: {request.client}")

        # Access headers
        auth = request.headers.get("authorization")
        content_type = request.content_type

        # Access query params
        page = request.query_params.get("page", "1")
        limit = request.query_params.get("limit", "10")

        # Read body
        if request.method == "POST":
            if content_type == "application/json":
                data = await request.json()
            elif content_type == "application/x-www-form-urlencoded":
                data = await request.form()
            else:
                data = await request.body()

Streaming large uploads::

    async def upload_handler(scope, receive, send):
        request = Request(scope, receive)

        with open("upload.bin", "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)

Using request state::

    # In middleware
    async def auth_middleware(scope, receive, send):
        request = Request(scope, receive)
        token = request.headers.get("authorization")
        request.state.user = validate_token(token)
        # ... pass to next handler

    # In handler
    async def handler(scope, receive, send):
        request = Request(scope, receive)
        user = request.state.user  # Set by middleware

Dependencies
============
Internal imports from genro_asgi:

- ``.types``: Scope, Receive, Message type aliases
- ``.datastructures``: Address, URL, Headers, QueryParams, State,
                       headers_from_scope, query_params_from_scope

Optional external:

- ``orjson``: Fast JSON parsing (falls back to stdlib if not installed)

Module-Level Constants
======================
``HAS_ORJSON: bool``
    True if orjson is available for fast JSON parsing.

Public Exports
==============
The module exports (via __all__)::

    __all__ = ["Request"]

Entry Point
===========
When run as main module, demonstrates basic Request usage::

    if __name__ == "__main__":
        # Create mock scope and receive for demonstration
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "query_string": b"name=world",
            "headers": [(b"host", b"localhost:8000")],
            "scheme": "http",
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 50000),
            "root_path": "",
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        import asyncio

        async def demo():
            request = Request(scope, receive)
            print(f"Request: {request}")
            print(f"Method: {request.method}")
            print(f"Path: {request.path}")
            print(f"URL: {request.url}")
            print(f"Query params: {list(request.query_params.items())}")
            print(f"Headers: {list(request.headers.items())}")
            print(f"Client: {request.client}")

        asyncio.run(demo())
"""

from __future__ import annotations

import json as stdlib_json
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs

from .datastructures import (
    Address,
    Headers,
    QueryParams,
    State,
    URL,
    headers_from_scope,
    query_params_from_scope,
)
from .types import Message, Receive, Scope

if TYPE_CHECKING:
    pass

__all__ = ["Request"]

# Optional fast JSON parsing
try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    orjson = None  # type: ignore[assignment]
    HAS_ORJSON = False


class Request:
    """
    HTTP Request wrapper for ASGI applications.

    Provides convenient access to ASGI scope data and request body reading
    with support for JSON and form parsing.

    The Request uses lazy initialization for headers, query_params, url, and
    state to avoid creating objects that may not be used.

    Attributes:
        scope: The raw ASGI scope dict.

    Example:
        >>> async def handler(scope, receive, send):
        ...     request = Request(scope, receive)
        ...     print(f"{request.method} {request.path}")
        ...     if request.method == "POST":
        ...         data = await request.json()
    """

    __slots__ = (
        "_scope",
        "_receive",
        "_body",
        "_json",
        "_headers",
        "_query_params",
        "_url",
        "_state",
        "_stream_consumed",
    )

    def __init__(self, scope: Scope, receive: Receive) -> None:
        """
        Initialize request from ASGI scope and receive callable.

        Args:
            scope: ASGI HTTP connection scope dict containing request metadata.
            receive: ASGI receive callable for reading request body messages.

        Note:
            No I/O is performed during construction. All body reading is
            deferred until body(), stream(), json(), or form() is called.
        """
        self._scope = scope
        self._receive = receive
        self._body: bytes | None = None
        self._json: Any = None
        self._headers: Headers | None = None
        self._query_params: QueryParams | None = None
        self._url: URL | None = None
        self._state: State | None = None
        self._stream_consumed: bool = False

    @property
    def scope(self) -> Scope:
        """
        Raw ASGI scope dict.

        Provides access to any scope field not exposed through dedicated
        properties, such as custom fields added by middleware.

        Returns:
            The ASGI scope dict passed to the constructor.
        """
        return self._scope

    @property
    def method(self) -> str:
        """
        HTTP request method.

        Returns:
            The HTTP method string (GET, POST, PUT, DELETE, etc.).
            Defaults to "GET" if not present in scope.
        """
        return str(self._scope.get("method", "GET"))

    @property
    def path(self) -> str:
        """
        Request path without query string.

        Returns:
            The URL path component (e.g., "/users/123").
            Defaults to "/" if not present in scope.
        """
        return str(self._scope.get("path", "/"))

    @property
    def scheme(self) -> str:
        """
        URL scheme.

        Returns:
            The URL scheme ("http" or "https").
            Defaults to "http" if not present in scope.
        """
        return str(self._scope.get("scheme", "http"))

    @property
    def url(self) -> URL:
        """
        Full request URL.

        Constructed lazily from scope fields: scheme, server, root_path,
        path, and query_string.

        Returns:
            URL object representing the complete request URL.

        Note:
            Default ports (80 for HTTP, 443 for HTTPS) are omitted from
            the URL string. If server is not available, the Host header
            is used as fallback.
        """
        if self._url is None:
            scheme = self.scheme
            server = self._scope.get("server")
            path = self._scope.get("root_path", "") + self.path
            query_string = self._scope.get("query_string", b"")

            if server:
                host, port = server
                if (scheme == "http" and port == 80) or (
                    scheme == "https" and port == 443
                ):
                    netloc = host
                else:
                    netloc = f"{host}:{port}"
            else:
                netloc = self.headers.get("host", "localhost")

            url_str = f"{scheme}://{netloc}{path}"
            if query_string:
                url_str += f"?{query_string.decode('latin-1')}"

            self._url = URL(url_str)
        return self._url

    @property
    def headers(self) -> Headers:
        """
        Request headers.

        Returns:
            Case-insensitive Headers object containing all request headers.

        Note:
            Created lazily on first access using headers_from_scope().
        """
        if self._headers is None:
            self._headers = headers_from_scope(self._scope)
        return self._headers

    @property
    def query_params(self) -> QueryParams:
        """
        Query string parameters.

        Returns:
            QueryParams object for accessing URL query parameters.

        Note:
            Created lazily on first access using query_params_from_scope().
        """
        if self._query_params is None:
            self._query_params = query_params_from_scope(self._scope)
        return self._query_params

    @property
    def client(self) -> Address | None:
        """
        Client address.

        Returns:
            Address object with host and port if available, None otherwise.
            May be None for Unix sockets, during testing, or when client
            info is not provided by the server.
        """
        client = self._scope.get("client")
        if client:
            return Address(host=client[0], port=client[1])
        return None

    @property
    def state(self) -> State:
        """
        Request-scoped state container.

        Use to store custom data that needs to be passed between middleware
        and request handlers.

        Returns:
            State object for storing arbitrary attributes.

        Note:
            Each Request instance has its own isolated State. Creating
            multiple Request objects from the same scope will have
            separate State instances.
        """
        if self._state is None:
            self._state = State()
        return self._state

    @property
    def content_type(self) -> str | None:
        """
        Content-Type header value.

        Returns:
            The Content-Type header value if present, None otherwise.
            Includes any parameters like charset if present in the header.
        """
        return self.headers.get("content-type")

    async def body(self) -> bytes:
        """
        Read and return the complete request body.

        The body is read from the ASGI receive callable and cached for
        subsequent calls.

        Returns:
            The complete request body as bytes.

        Raises:
            RuntimeError: If stream() has already started consuming the body.
        """
        if self._body is not None:
            return self._body
        if self._stream_consumed:
            raise RuntimeError(
                "Cannot call body() after stream() has started consuming. "
                "Use either stream() OR body(), not both."
            )
        chunks: list[bytes] = []
        async for chunk in self.stream():
            chunks.append(chunk)
        self._body = b"".join(chunks)
        return self._body

    async def stream(self) -> AsyncIterator[bytes]:
        """
        Stream the request body in chunks.

        Use for large request bodies to avoid loading everything into
        memory at once.

        Yields:
            Body chunks as bytes.

        Note:
            If body() was previously called, yields the cached body as
            a single chunk. Empty chunks from receive() are skipped.
            Once iteration starts, body()/json()/form() will raise RuntimeError.
        """
        if self._body is not None:
            yield self._body
            return

        self._stream_consumed = True
        while True:
            message: Message = await self._receive()
            body = message.get("body", b"")
            if body:
                yield body
            if not message.get("more_body", False):
                break

    async def json(self) -> Any:
        """
        Parse request body as JSON.

        Uses orjson if available for better performance, falls back to
        stdlib json otherwise. The result is cached for subsequent calls.

        Returns:
            The parsed JSON value (dict, list, str, int, float, bool, or None).

        Raises:
            json.JSONDecodeError: If body is not valid JSON (stdlib backend).
            orjson.JSONDecodeError: If body is not valid JSON (orjson backend).

        Note:
            Body is always decoded as UTF-8 per RFC 8259.
        """
        if self._json is None:
            body = await self.body()
            if HAS_ORJSON:
                self._json = orjson.loads(body)
            else:
                self._json = stdlib_json.loads(body.decode("utf-8"))
        return self._json

    async def form(self) -> dict[str, Any]:
        """
        Parse request body as URL-encoded form data.

        Only supports application/x-www-form-urlencoded format.
        For multipart/form-data (file uploads), use a dedicated library.

        Returns:
            Dict mapping field names to values. Single-value fields return
            a string, multi-value fields return a list of strings.

        Note:
            Body is decoded as UTF-8. The result is NOT cached - each call
            parses the body again (though the body bytes are cached).
        """
        body = await self.body()
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

    def __repr__(self) -> str:
        """Return string representation of the request."""
        return f"Request(method={self.method!r}, path={self.path!r})"


if __name__ == "__main__":
    import asyncio

    # Create mock scope and receive for demonstration
    demo_scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "query_string": b"name=world",
        "headers": [(b"host", b"localhost:8000")],
        "scheme": "http",
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
    }

    async def demo_receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def demo() -> None:
        request = Request(demo_scope, demo_receive)
        print(f"Request: {request}")
        print(f"Method: {request.method}")
        print(f"Path: {request.path}")
        print(f"URL: {request.url}")
        print(f"Query params: {list(request.query_params.items())}")
        print(f"Headers: {list(request.headers.items())}")
        print(f"Client: {request.client}")

    asyncio.run(demo())
