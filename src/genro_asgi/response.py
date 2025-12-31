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

Response is created by Request and linked to it. The dispatcher calls handler,
then uses response.set_result() to set the body with auto-detection of content type.

Main Pattern
============
Response is created empty by Request and configured via set_result()::

    # In dispatcher after calling handler:
    result = await handler(**args)
    request.response.set_result(result, mime_type=node.get("mime_type"))
    await request.response(scope, receive, send)

TYTX Support
============
If request has X-TYTX-Transport header, set_result() automatically:
- Serializes dict/list using genro_tytx.to_tytx()
- Uses the same transport (json/msgpack) as the request
- Sets Content-Type to application/vnd.tytx+{transport}

Classes
=======
Response
    Single response class. Has request reference, set_result(), set_header(), set_error().

Response Methods
================
set_result(result, mime_type=None)
    Set body from result. Auto-detects content type:
    - dict/list: JSON (or TYTX if request.tytx_mode)
    - Path: file bytes with guessed media type
    - bytes: application/octet-stream
    - str: text/plain
    - None: empty body
    - other: str() as text/plain

set_header(name, value)
    Add a response header.

set_error(error)
    Set error response from exception. Maps error type to HTTP status.

Helper Functions
================
make_cookie(key, value, **options)
    Creates Set-Cookie header tuple for use with headers parameter.
"""

from __future__ import annotations

import json as stdlib_json
import mimetypes
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .types import Receive, Scope, Send

if TYPE_CHECKING:
    pass

__all__ = [
    "Response",
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

    Can be created empty and configured via set_header/set_result before sending.

    Attributes:
        body: Encoded response body as bytes.
        status_code: HTTP status code.
        media_type: Content-Type media type (may include charset).

    Example:
        >>> response = Response(content="Hello", media_type="text/plain")
        >>> await response(scope, receive, send)

        # Or create empty and configure:
        >>> response = Response()
        >>> response.set_header("X-Custom", "value")
        >>> response.set_result({"data": 123})  # auto-detects JSON
        >>> await response(scope, receive, send)
    """

    __slots__ = ("body", "status_code", "_media_type", "_headers", "request")

    media_type: str | None = None
    charset: str = "utf-8"

    def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: HeadersInput = None,
        media_type: str | None = None,
        request: Any = None,
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
        self.request = request
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
        """Encode response content to bytes.

        Args:
            content: Content to encode. Accepts bytes, str, or None.

        Returns:
            Encoded content as bytes.

        Note:
            - None: Returns empty bytes (b"")
            - bytes: Returns as-is, no encoding
            - str: Encoded using self.charset (default: utf-8)
        """
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

    def set_header(self, name: str, value: str) -> None:
        """Set a response header. Can be called before set_result."""
        self._headers.append((name, value))

    def _guess_mime_type(self, result: Any, metadata: dict[str, Any] | None) -> str | None:
        """Guess MIME type from metadata or result type.

        Priority:
        1. self._media_type if already set (by handler)
        2. metadata["mime_type"] if present
        3. For Path: guess from file extension
        4. None (let set_result use type-based defaults)
        """
        # Handler may have set _media_type directly (e.g., _resource endpoint)
        if self._media_type is not None:
            return self._media_type
        if metadata and "mime_type" in metadata:
            mime: str = metadata["mime_type"]
            return mime
        if isinstance(result, Path):
            guessed, _ = mimetypes.guess_type(str(result))
            return guessed
        return None

    def set_result(self, result: Any, metadata: dict[str, Any] | None = None) -> None:
        """Set response body from result.

        Uses _guess_mime_type() to determine content type. Falls back to
        type-based defaults:
        - dict/list: application/json (or TYTX if request.tytx_mode)
        - Path: from extension
        - bytes: application/octet-stream
        - str: text/plain
        - None: text/plain (empty body)
        - other: text/plain (str conversion)

        Args:
            result: The handler result to set as response body.
            metadata: Route metadata dict. Uses mime_type if present.
        """
        mime_type = self._guess_mime_type(result, metadata)
        if isinstance(result, (dict, list)):
            # Use TYTX serialization if request is in TYTX mode
            if self.request and self.request.tytx_mode:
                from genro_tytx import to_tytx
                from typing import cast, Literal
                transport = cast(
                    Literal["json", "xml", "msgpack"],
                    self.request.tytx_transport or "json"
                )
                encoded = to_tytx(result, transport)
                self.body = encoded if isinstance(encoded, bytes) else encoded.encode("utf-8")
                self._media_type = mime_type or f"application/vnd.tytx+{transport}"
            else:
                if HAS_ORJSON:
                    self.body = orjson.dumps(result)
                else:
                    self.body = stdlib_json.dumps(result, ensure_ascii=False).encode("utf-8")
                self._media_type = mime_type or "application/json"
        elif isinstance(result, Path):
            self.body = result.read_bytes()
            self._media_type = mime_type or "application/octet-stream"
        elif isinstance(result, bytes):
            self.body = result
            self._media_type = mime_type or "application/octet-stream"
        elif isinstance(result, str):
            self.body = result.encode(self.charset)
            self._media_type = mime_type or "text/plain"
        elif result is None:
            self.body = b""
            self._media_type = mime_type or "text/plain"
        else:
            self.body = str(result).encode(self.charset)
            self._media_type = mime_type or "text/plain"

        # Update content-type and content-length headers
        self._update_content_headers()

    def _update_content_headers(self) -> None:
        """Update content-type and content-length headers after set_result."""
        # Remove existing content-type and content-length
        self._headers = [
            (name, value) for name, value in self._headers
            if name.lower() not in ("content-type", "content-length")
        ]
        # Add new ones
        content_type = self._get_content_type()
        if content_type:
            self._headers.append(("content-type", content_type))
        self._headers.append(("content-length", str(len(self.body))))

    # Error type to HTTP status code mapping
    ERROR_MAP: dict[str, int] = {
        "NotFound": 404,
        "NotAuthorized": 403,
        "ValueError": 400,
        "TypeError": 400,
        "PermissionError": 403,
        "FileNotFoundError": 404,
    }

    def set_error(self, error: Exception) -> None:
        """Set response as error from exception.

        Maps exception type to HTTP status code using ERROR_MAP.
        Unknown exceptions default to 500 and are logged.

        Args:
            error: The exception to convert to error response.
        """
        import logging

        error_name = type(error).__name__
        self.status_code = self.ERROR_MAP.get(error_name, 500)
        if self.status_code == 500:
            logging.getLogger("genro_asgi").exception(f"Handler error: {error}")
        self.set_result({"error": str(error)})


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
