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
HTTP Response classes for ASGI applications.

This module provides Response classes for constructing and sending HTTP responses
through the ASGI interface. Each Response is an ASGI application callable that
sends the appropriate ``http.response.start`` and ``http.response.body`` messages.

Design Philosophy
=================
The Response classes follow these principles:

1. **ASGI-native**: Each Response implements ``__call__(scope, receive, send)``
   making it directly usable as an ASGI application or return value.

2. **Immutable after construction**: Response content and headers are set at
   construction time. The Response object is then "frozen" and can be sent.

3. **Automatic Content-Length**: For non-streaming responses where body size
   is known, Content-Length header is added automatically.

4. **Zero dependencies**: Uses only Python stdlib, with optional orjson support
   for faster JSON serialization.

5. **Multiple headers support**: Headers can be provided as dict[str, str] for
   simple cases, or list[tuple[str, str]] for headers with duplicate names
   (e.g., multiple Set-Cookie headers).

ASGI Response Protocol
======================
Responses send two types of ASGI messages::

    # First: response start with status and headers
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
    })

    # Then: response body (one or more messages)
    await send({
        "type": "http.response.body",
        "body": b"Hello, World!",
        "more_body": False,  # True for streaming
    })

For streaming responses, multiple ``http.response.body`` messages are sent with
``more_body=True`` until the final chunk which has ``more_body=False``.

Class Hierarchy
===============
::

    Response (base)
    ├── JSONResponse      - Serializes Python objects to JSON
    ├── HTMLResponse      - HTML content with text/html media type
    ├── PlainTextResponse - Plain text with text/plain media type
    ├── RedirectResponse  - HTTP redirect with Location header
    ├── StreamingResponse - Body from async iterator (chunked)
    └── FileResponse      - Stream file from disk

Class: Response
===============
Base HTTP response class. Sends bytes or string content with headers.

Constructor
-----------
``__init__(self, content: bytes | str | None = None, status_code: int = 200,
           headers: Mapping[str, str] | list[tuple[str, str]] | None = None,
           media_type: str | None = None) -> None``

Args:
    content: Response body as bytes or string. Strings are encoded using
             the charset (default UTF-8). None becomes empty bytes.
    status_code: HTTP status code (default 200).
    headers: Response headers. Accepts dict[str, str] for simple headers or
             list[tuple[str, str]] for headers with duplicate names (e.g.,
             multiple Set-Cookie). Stored internally as list of tuples.
    media_type: Content-Type media type. Overrides class default if provided.
                For text/* types, charset is appended automatically.

Class Attributes:
    media_type (str | None): Default media type for this response class.
                             None for base Response, set by subclasses.
    charset (str): Character encoding for string content. Default "utf-8".

Instance Attributes:
    body (bytes): Encoded response body.
    status_code (int): HTTP status code.
    media_type (str | None): Content-Type media type (may include charset).

Slots
-----
::

    __slots__ = ("body", "status_code", "media_type", "_headers")

Methods
-------
``async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None``
    ASGI application interface. Sends the response through the send callable.

    Sends:
    1. ``http.response.start`` with status and headers
    2. ``http.response.body`` with body content

``def _build_headers(self) -> list[tuple[bytes, bytes]]``
    Build ASGI headers list from internal headers.
    Header names are lowercased and encoded as latin-1 (HTTP standard).

Content-Length Behavior
-----------------------
Content-Length header is added automatically if:
- Not already present in headers
- Body is not empty OR status allows body

This applies to Response, JSONResponse, HTMLResponse, PlainTextResponse,
and RedirectResponse. StreamingResponse does NOT add Content-Length.

Charset Handling
----------------
For text/* media types without explicit charset, "; charset=utf-8" is appended::

    media_type="text/plain"  -> "text/plain; charset=utf-8"
    media_type="text/html"   -> "text/html; charset=utf-8"
    media_type="text/plain; charset=latin-1"  -> unchanged

Class: JSONResponse
===================
Response that serializes Python objects to JSON.

Uses orjson if available for better performance, falls back to stdlib json.

Constructor
-----------
``__init__(self, content: Any = None, status_code: int = 200,
           headers: Mapping[str, str] | list[tuple[str, str]] | None = None) -> None``

Args:
    content: Python object to serialize (dict, list, str, int, etc.)
    status_code: HTTP status code (default 200).
    headers: Additional response headers.

Class Attributes:
    media_type = "application/json"

JSON Serialization
------------------
- orjson (if available): Fast, outputs bytes directly
- stdlib json: Uses ensure_ascii=False, encodes to UTF-8

Class: HTMLResponse
===================
Response for HTML content.

Constructor
-----------
Inherits from Response. Accepts bytes or string content.

Class Attributes:
    media_type = "text/html"

Class: PlainTextResponse
========================
Response for plain text content.

Constructor
-----------
Inherits from Response. Accepts bytes or string content.

Class Attributes:
    media_type = "text/plain"

Class: RedirectResponse
=======================
HTTP redirect response with Location header.

Constructor
-----------
``__init__(self, url: str, status_code: int = 307,
           headers: Mapping[str, str] | list[tuple[str, str]] | None = None) -> None``

Args:
    url: Redirect target URL (absolute or relative).
    status_code: HTTP redirect status code. Default 307 (Temporary Redirect).
                 Common values: 301, 302, 303, 307, 308.
    headers: Additional response headers.

Behavior:
- Sets Location header to the provided URL
- Body is empty (Content-Length: 0)
- No media_type is set

Class: StreamingResponse
========================
Response that streams body from an async iterator.

Use for large responses or server-sent events where body size is unknown
or content is generated dynamically.

Constructor
-----------
``__init__(self, content: AsyncIterator[bytes], status_code: int = 200,
           headers: Mapping[str, str] | list[tuple[str, str]] | None = None,
           media_type: str | None = None) -> None``

Args:
    content: Async iterator yielding bytes chunks.
    status_code: HTTP status code (default 200).
    headers: Response headers.
    media_type: Content-Type media type.

Instance Attributes:
    body_iterator: The async iterator providing body chunks.

Slots
-----
::

    __slots__ = ("body_iterator", "status_code", "media_type", "_headers")

Streaming Behavior
------------------
1. Sends ``http.response.start`` with status and headers
2. For each chunk from iterator: sends ``http.response.body`` with ``more_body=True``
3. After iterator exhausted: sends final ``http.response.body`` with empty body
   and ``more_body=False``

Content-Length is NOT added (size unknown).

Class: FileResponse
===================
Response that streams a file from disk.

Constructor
-----------
``__init__(self, path: str | Path, status_code: int = 200,
           headers: Mapping[str, str] | list[tuple[str, str]] | None = None,
           media_type: str | None = None, filename: str | None = None,
           chunk_size: int = 64 * 1024) -> None``

Args:
    path: Path to file on disk (string or Path object).
    status_code: HTTP status code (default 200).
    headers: Response headers.
    media_type: Content-Type. Auto-detected from filename if None.
    filename: Download filename for Content-Disposition header.
              If provided, sets "attachment; filename=..." header.
    chunk_size: Size of chunks to read (default 64KB).

Instance Attributes:
    path (Path): Path object for the file.
    chunk_size (int): Chunk size for reading.

Slots
-----
::

    __slots__ = ("path", "chunk_size", "status_code", "media_type", "_headers")

File Handling
-------------
- Media type auto-detection uses mimetypes.guess_type()
- Falls back to "application/octet-stream" if unknown
- Content-Length is set if file exists at construction time
- File is read synchronously in chunks (blocking I/O)
- FileNotFoundError raised at send time if file doesn't exist

Content-Disposition
-------------------
If filename is provided::

    Content-Disposition: attachment; filename="document.pdf"

Module-Level Constants
======================
``HAS_ORJSON: bool``
    True if orjson is available for fast JSON serialization.

Dependencies
============
Internal imports from genro_asgi:
- ``.types``: Scope, Receive, Send type aliases

Optional external:
- ``orjson``: Fast JSON serialization (falls back to stdlib if not installed)

Standard library:
- ``json``: JSON serialization fallback
- ``mimetypes``: Media type detection for FileResponse
- ``pathlib``: Path handling for FileResponse

Public Exports
==============
The module exports (via __all__)::

    __all__ = [
        "Response",
        "JSONResponse",
        "HTMLResponse",
        "PlainTextResponse",
        "RedirectResponse",
        "StreamingResponse",
        "FileResponse",
        "make_cookie",
    ]

Helper Functions
================
``make_cookie(key, value, **options) -> tuple[str, str]``
    Creates a Set-Cookie header tuple for use with Response headers.
    This is a module-level function (not a method) to preserve Response
    immutability - cookies must be defined at Response construction time.

Usage Examples
==============
Basic response::

    from genro_asgi import Response

    async def handler(scope, receive, send):
        response = Response(
            content="Hello, World!",
            status_code=200,
            media_type="text/plain"
        )
        await response(scope, receive, send)

JSON response::

    from genro_asgi import JSONResponse

    async def api_handler(scope, receive, send):
        data = {"status": "ok", "items": [1, 2, 3]}
        response = JSONResponse(data, status_code=200)
        await response(scope, receive, send)

Redirect::

    from genro_asgi import RedirectResponse

    async def redirect_handler(scope, receive, send):
        response = RedirectResponse("/new-location", status_code=303)
        await response(scope, receive, send)

Streaming response::

    from genro_asgi import StreamingResponse

    async def stream_handler(scope, receive, send):
        async def generate():
            for i in range(10):
                yield f"chunk {i}\\n".encode()

        response = StreamingResponse(generate(), media_type="text/plain")
        await response(scope, receive, send)

File download::

    from genro_asgi import FileResponse

    async def download_handler(scope, receive, send):
        response = FileResponse(
            "/path/to/document.pdf",
            filename="download.pdf"
        )
        await response(scope, receive, send)

Setting cookies with make_cookie::

    from genro_asgi import Response, make_cookie

    async def handler(scope, receive, send):
        response = Response(
            content="OK",
            headers=[
                make_cookie("session", "abc123", httponly=True, secure=True),
                make_cookie("prefs", "dark", max_age=31536000),
            ]
        )
        await response(scope, receive, send)

Entry Point
===========
When run as main module, demonstrates basic Response usage with mock send::

    if __name__ == "__main__":
        import asyncio

        messages = []

        async def mock_send(message):
            messages.append(message)
            print(f"Sent: {message['type']}")

        async def demo():
            # Test basic response
            response = Response(content="Hello!", media_type="text/plain")
            await response({}, lambda: None, mock_send)

            print(f"Status: {messages[0]['status']}")
            print(f"Body: {messages[1]['body']}")

        asyncio.run(demo())
"""

from __future__ import annotations

import json as stdlib_json
import mimetypes
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .types import Receive, Scope, Send

if TYPE_CHECKING:
    pass

__all__ = [
    "Response",
    "JSONResponse",
    "HTMLResponse",
    "PlainTextResponse",
    "RedirectResponse",
    "StreamingResponse",
    "FileResponse",
    "make_cookie",
]

# Optional fast JSON serialization
try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    orjson = None  # type: ignore[assignment]
    HAS_ORJSON = False


# Type alias for headers input
HeadersInput = Mapping[str, str] | list[tuple[str, str]] | None


def _normalize_headers(
    headers: HeadersInput,
) -> list[tuple[str, str]]:
    """
    Normalize headers input to list of tuples.

    Args:
        headers: Headers as dict, list of tuples, or None.

    Returns:
        List of (name, value) tuples. Empty list if headers is None.
    """
    if headers is None:
        return []
    if isinstance(headers, list):
        return list(headers)
    return list(headers.items())


class Response:
    """
    Base HTTP response class.

    Sends bytes or string content with headers through the ASGI interface.
    Implements ``__call__`` to be usable as an ASGI application.

    Attributes:
        body: Encoded response body as bytes.
        status_code: HTTP status code.
        media_type: Content-Type media type (may include charset).

    Example:
        >>> response = Response(content="Hello", media_type="text/plain")
        >>> await response(scope, receive, send)
    """

    __slots__ = ("body", "status_code", "_media_type", "_headers")

    media_type: str | None = None
    charset: str = "utf-8"

    def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: HeadersInput = None,
        media_type: str | None = None,
    ) -> None:
        """
        Initialize response.

        Args:
            content: Response body (bytes, string, or None).
            status_code: HTTP status code (default 200).
            headers: Response headers as dict or list of tuples.
            media_type: Content-Type media type (overrides class default).

        Note:
            HTTP status codes 204 (No Content) and 304 (Not Modified) must not
            have body content per RFC 7230. If you provide content with these
            status codes, the ASGI server may reject or truncate the response.
        """
        self.status_code = status_code
        self._headers: list[tuple[str, str]] = _normalize_headers(headers)

        # Use instance media_type if provided, else class default
        self._media_type = media_type

        # Encode content
        self.body = self._encode_content(content)

        # Set content-type header if media_type is set and not already present
        effective_media_type = self._media_type if self._media_type is not None else self.media_type
        if effective_media_type is not None:
            header_names = {name.lower() for name, _ in self._headers}
            if "content-type" not in header_names:
                content_type = self._get_content_type()
                if content_type:
                    self._headers.append(("content-type", content_type))

        # Add content-length if not present
        self._add_content_length()

    def _encode_content(self, content: bytes | str | None) -> bytes:
        """Encode content to bytes."""
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        return content.encode(self.charset)

    def _get_content_type(self) -> str | None:
        """Get content-type header value with charset for text types."""
        effective_media_type = self._media_type if self._media_type is not None else self.media_type
        if effective_media_type is None:
            return None
        if effective_media_type.startswith("text/") and "charset" not in effective_media_type:
            return f"{effective_media_type}; charset={self.charset}"
        return effective_media_type

    def _add_content_length(self) -> None:
        """Add Content-Length header if not present."""
        header_names = {name.lower() for name, _ in self._headers}
        if "content-length" not in header_names:
            self._headers.append(("content-length", str(len(self.body))))

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        """
        Build ASGI headers list.

        Header names are lowercased and encoded as latin-1 (HTTP standard).

        Returns:
            List of (name, value) tuples as bytes.
        """
        return [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in self._headers
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI application interface.

        Sends http.response.start and http.response.body messages.

        Args:
            scope: ASGI scope dict (unused but required by interface).
            receive: ASGI receive callable (unused but required by interface).
            send: ASGI send callable for sending response messages.
        """
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": self.body,
            }
        )


class JSONResponse(Response):
    """
    JSON response that serializes Python objects.

    Uses orjson if available for better performance, falls back to stdlib json.

    Attributes:
        media_type: Always "application/json".

    Example:
        >>> response = JSONResponse({"status": "ok"})
        >>> await response(scope, receive, send)
    """

    media_type = "application/json"

    def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: HeadersInput = None,
    ) -> None:
        """
        Initialize JSON response.

        Args:
            content: Python object to serialize as JSON.
            status_code: HTTP status code (default 200).
            headers: Response headers.
        """
        # Serialize to JSON bytes
        if HAS_ORJSON:
            body = orjson.dumps(content)
        else:
            body = stdlib_json.dumps(content, ensure_ascii=False).encode("utf-8")

        super().__init__(
            content=body,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )


class HTMLResponse(Response):
    """
    HTML response with text/html content type.

    Example:
        >>> response = HTMLResponse("<h1>Hello</h1>")
        >>> await response(scope, receive, send)
    """

    media_type = "text/html"


class PlainTextResponse(Response):
    """
    Plain text response with text/plain content type.

    Example:
        >>> response = PlainTextResponse("Hello, World!")
        >>> await response(scope, receive, send)
    """

    media_type = "text/plain"


class RedirectResponse(Response):
    """
    HTTP redirect response with Location header.

    Example:
        >>> response = RedirectResponse("/new-location")
        >>> await response(scope, receive, send)
    """

    def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: HeadersInput = None,
    ) -> None:
        """
        Initialize redirect response.

        Args:
            url: Redirect target URL (absolute or relative).
            status_code: HTTP status code (default 307 Temporary Redirect).
            headers: Additional response headers.
        """
        # Normalize headers and add Location
        headers_list = _normalize_headers(headers)
        headers_list.append(("location", url))

        super().__init__(
            content=b"",
            status_code=status_code,
            headers=headers_list,
        )


class StreamingResponse:
    """
    Streaming response from an async iterator.

    Use for large responses or server-sent events where body size is unknown.
    Content-Length is NOT added since size is unknown.

    Attributes:
        body_iterator: Async iterator yielding bytes chunks.
        status_code: HTTP status code.
        media_type: Content-Type media type.

    Example:
        >>> async def generate():
        ...     yield b"chunk1"
        ...     yield b"chunk2"
        >>> response = StreamingResponse(generate())
        >>> await response(scope, receive, send)
    """

    __slots__ = ("body_iterator", "status_code", "media_type", "_headers")

    charset: str = "utf-8"

    def __init__(
        self,
        content: AsyncIterator[bytes],
        status_code: int = 200,
        headers: HeadersInput = None,
        media_type: str | None = None,
    ) -> None:
        """
        Initialize streaming response.

        Args:
            content: Async iterator yielding bytes chunks.
            status_code: HTTP status code (default 200).
            headers: Response headers.
            media_type: Content-Type media type.
        """
        self.body_iterator = content
        self.status_code = status_code
        self.media_type = media_type
        self._headers: list[tuple[str, str]] = _normalize_headers(headers)

        # Add content-type if media_type provided and not already set
        if self.media_type is not None:
            header_names = {name.lower() for name, _ in self._headers}
            if "content-type" not in header_names:
                content_type = self.media_type
                # Auto-append charset for text/* types (same behavior as Response)
                if content_type.startswith("text/") and "charset" not in content_type:
                    content_type = f"{content_type}; charset={self.charset}"
                self._headers.append(("content-type", content_type))

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        """Build ASGI headers list."""
        return [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in self._headers
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI application interface.

        Streams body chunks with more_body=True until exhausted.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )

        async for chunk in self.body_iterator:
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                }
            )

        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )


class FileResponse:
    """
    Response that streams a file from disk.

    Supports automatic media type detection and Content-Disposition for downloads.
    File reading is performed in a thread pool to avoid blocking the event loop.

    Attributes:
        path: Path object for the file.
        chunk_size: Size of chunks to read.
        status_code: HTTP status code.
        media_type: Content-Type media type.

    Example:
        >>> response = FileResponse("/path/to/file.pdf", filename="doc.pdf")
        >>> await response(scope, receive, send)
    """

    __slots__ = ("path", "chunk_size", "status_code", "media_type", "_headers")

    def __init__(
        self,
        path: str | Path,
        status_code: int = 200,
        headers: HeadersInput = None,
        media_type: str | None = None,
        filename: str | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        """
        Initialize file response.

        Args:
            path: Path to file on disk.
            status_code: HTTP status code (default 200).
            headers: Response headers.
            media_type: Content-Type (auto-detected if None).
            filename: Download filename for Content-Disposition.
            chunk_size: Size of chunks to read (default 64KB).
        """
        self.path = Path(path)
        self.chunk_size = chunk_size
        self.status_code = status_code
        self._headers: list[tuple[str, str]] = _normalize_headers(headers)

        # Auto-detect media type if not provided
        if media_type is None:
            media_type, _ = mimetypes.guess_type(str(self.path))
        self.media_type = media_type or "application/octet-stream"

        # Add content-type if not already set
        header_names = {name.lower() for name, _ in self._headers}
        if "content-type" not in header_names:
            self._headers.append(("content-type", self.media_type))

        # Add content-disposition for download
        if filename:
            self._headers.append(
                ("content-disposition", f'attachment; filename="{filename}"')
            )

        # Add content-length if file exists
        if self.path.exists():
            self._headers.append(("content-length", str(self.path.stat().st_size)))

    def _build_headers(self) -> list[tuple[bytes, bytes]]:
        """Build ASGI headers list."""
        return [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in self._headers
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI application interface.

        Streams file content in chunks using thread pool for non-blocking I/O.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Raises:
            FileNotFoundError: If file does not exist.
        """
        import asyncio

        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self._build_headers(),
            }
        )

        loop = asyncio.get_running_loop()

        # Stream file in chunks using thread pool to avoid blocking event loop
        with open(self.path, "rb") as f:
            while True:
                chunk = await loop.run_in_executor(None, f.read, self.chunk_size)
                more_body = len(chunk) == self.chunk_size
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": more_body,
                    }
                )
                if not more_body:
                    break


def make_cookie(
    key: str,
    value: str = "",
    *,
    max_age: int | None = None,
    path: str = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    samesite: str | None = "lax",
) -> tuple[str, str]:
    """
    Create a Set-Cookie header tuple.

    This is a helper function for creating cookie headers without modifying
    the immutable Response object. The returned tuple can be passed directly
    to Response headers.

    .. note:: Design Decision - Module-level function vs method

        This is a **module-level function** (not a Response method) to preserve
        Response immutability. Response objects are "frozen" after construction
        - all headers must be provided at creation time. A ``response.set_cookie()``
        method would violate this principle by modifying headers after construction.

        Using ``make_cookie()`` the user creates cookie tuples BEFORE constructing
        the Response, keeping the Response immutable and predictable.

    Args:
        key: Cookie name.
        value: Cookie value (will be URL-encoded).
        max_age: Max age in seconds. None means session cookie.
        path: Cookie path (default "/").
        domain: Cookie domain. None means current domain only.
        secure: If True, cookie only sent over HTTPS.
        httponly: If True, cookie not accessible via JavaScript.
        samesite: SameSite policy ("strict", "lax", "none", or None to omit).

    Returns:
        Tuple of ("set-cookie", cookie_string) for use in Response headers.

    Example:
        >>> from genro_asgi import Response, make_cookie
        >>> response = Response(
        ...     content="OK",
        ...     headers=[
        ...         make_cookie("session", "abc123", httponly=True, secure=True),
        ...         make_cookie("prefs", "dark", max_age=31536000),
        ...     ]
        ... )
    """
    from urllib.parse import quote

    cookie = f"{key}={quote(value, safe='')}"

    if max_age is not None:
        cookie += f"; Max-Age={max_age}"
    if path:
        cookie += f"; Path={path}"
    if domain:
        cookie += f"; Domain={domain}"
    if secure:
        cookie += "; Secure"
    if httponly:
        cookie += "; HttpOnly"
    if samesite:
        cookie += f"; SameSite={samesite.capitalize()}"

    return ("set-cookie", cookie)


if __name__ == "__main__":
    import asyncio
    from collections.abc import MutableMapping

    messages: list[MutableMapping[str, Any]] = []

    async def mock_send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)
        print(f"Sent: {message['type']}")

    async def mock_receive() -> MutableMapping[str, Any]:
        return {"type": "http.request", "body": b""}

    async def demo() -> None:
        # Test basic response
        response = Response(content="Hello!", media_type="text/plain")
        await response({}, mock_receive, mock_send)

        print(f"Status: {messages[0]['status']}")
        print(f"Headers: {messages[0]['headers']}")
        print(f"Body: {messages[1]['body']}")

    asyncio.run(demo())
