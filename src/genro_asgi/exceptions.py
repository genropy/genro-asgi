# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Exception classes for genro-asgi HTTP and WebSocket error handling.

This module provides typed exceptions for signaling errors in the HTTP
request/response cycle and WebSocket connections. These exceptions are
designed to be caught by the framework and converted to appropriate
HTTP responses or WebSocket close frames.

Module Structure
----------------
Three exception classes, all inheriting directly from Exception:

1. HTTPException - For HTTP error responses (4xx, 5xx)
2. WebSocketException - For closing WebSocket with error code
3. WebSocketDisconnect - Signal that client disconnected (not an error)

Design Decisions
----------------
- No validation: status_code and code are not validated. Users are expected
  to use appropriate values (4xx/5xx for HTTP, 1000-4999 for WebSocket).
- No __slots__: Exceptions are short-lived and don't benefit significantly
  from __slots__. This also maintains compatibility with Exception base class.
- No common base: Each exception inherits directly from Exception for simplicity.
  Use tuple syntax for catching multiple: `except (HTTPException, WebSocketException)`
- headers: Accepts both dict[str, str] for simple headers and list[tuple[str, str]]
  for headers that may have duplicate names (e.g., multiple Set-Cookie headers).

HTTPException
-------------
Raise in handlers to return an HTTP error response.

Attributes:
    status_code (int): HTTP status code (expected 4xx or 5xx)
    detail (str): Error detail message (default: "")
    headers (list[tuple[str, str]] | None): Optional response headers as list of
        tuples. Supports duplicate header names (e.g., multiple Set-Cookie).
        Input can be dict[str, str] or list[tuple[str, str]], stored as list.

Example:
    >>> raise HTTPException(404, detail="User not found")
    >>> raise HTTPException(401, detail="Auth required", headers={"WWW-Authenticate": "Bearer"})
    >>> raise HTTPException(400, headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])

WebSocketException
------------------
Raise to close a WebSocket connection with an error code.

WebSocket close codes (RFC 6455):
    1000 - Normal closure
    1001 - Going away
    1002 - Protocol error
    1003 - Unsupported data
    1007 - Invalid payload
    1008 - Policy violation
    1009 - Message too big
    1011 - Internal error
    4000-4999 - Application-specific (free to use)

Attributes:
    code (int): WebSocket close code (default: 1000)
    reason (str): Close reason message (default: "")

Example:
    >>> raise WebSocketException(code=4000, reason="Invalid message format")
    >>> raise WebSocketException(code=1008, reason="Rate limit exceeded")

WebSocketDisconnect
-------------------
Raised by the framework when a WebSocket client disconnects.
This is NOT an error - it's a signal for cleanup.

Attributes:
    code (int): WebSocket close code sent by client (default: 1000)
    reason (str): Close reason from client (default: "")

Example:
    >>> try:
    ...     data = await websocket.receive_text()
    ... except WebSocketDisconnect:
    ...     logger.info("Client disconnected normally")

Difference between WebSocketException and WebSocketDisconnect:

    WebSocketException:
        - Raised BY the server code (explicit raise)
        - Semantics: "I want to close this connection with an error"
        - Typical handling: Log error, cleanup

    WebSocketDisconnect:
        - Raised BY the framework (when receive fails)
        - Semantics: "The client has disconnected"
        - Typical handling: Normal cleanup, no error logging

Usage Pattern:
    >>> async def websocket_handler(websocket):
    ...     try:
    ...         while True:
    ...             msg = await websocket.receive_json()
    ...             if not validate(msg):
    ...                 raise WebSocketException(4000, "Invalid format")
    ...             await process(msg)
    ...     except WebSocketDisconnect:
    ...         logger.info("Client left")
    ...     except WebSocketException as e:
    ...         logger.error(f"WebSocket error: {e.code} - {e.reason}")
"""


class HTTPException(Exception):
    """
    HTTP exception with status code and detail.

    Raise this in handlers to return an HTTP error response.
    The framework will catch this and convert it to an appropriate
    HTTP response with the given status code, detail, and headers.

    Attributes:
        status_code: HTTP status code (expected 4xx or 5xx, not validated)
        detail: Error detail message
        headers: Response headers as list of tuples (supports duplicate names)

    Example:
        >>> raise HTTPException(404, detail="User not found")
        >>> raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})
        >>> raise HTTPException(400, headers=[("Set-Cookie", "a=1"), ("Set-Cookie", "b=2")])
    """

    def __init__(
        self,
        status_code: int,
        detail: str = "",
        headers: dict[str, str] | list[tuple[str, str]] | None = None,
    ) -> None:
        """
        Initialize HTTP exception.

        Args:
            status_code: HTTP status code (4xx, 5xx expected)
            detail: Error detail message (default: "")
            headers: Response headers as dict or list of tuples (default: None).
                     Dict is converted to list internally to support duplicate names.
        """
        self.status_code = status_code
        self.detail = detail
        # Normalize headers to list[tuple[str, str]] for consistent internal format
        if headers is None:
            self.headers: list[tuple[str, str]] | None = None
        elif isinstance(headers, dict):
            self.headers = list(headers.items())
        else:
            self.headers = list(headers)
        super().__init__(detail)

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return f"HTTPException(status_code={self.status_code}, detail={self.detail!r})"


class WebSocketException(Exception):
    """
    WebSocket exception with close code and reason.

    Raise this to close a WebSocket connection with an error code.
    The framework will catch this and send a close frame with the
    given code and reason.

    Attributes:
        code: WebSocket close code (1000-4999, not validated)
        reason: Close reason message

    Example:
        >>> raise WebSocketException(code=4000, reason="Invalid message")
    """

    def __init__(
        self,
        code: int = 1000,
        reason: str = "",
    ) -> None:
        """
        Initialize WebSocket exception.

        Args:
            code: WebSocket close code (default: 1000)
            reason: Close reason message (default: "")
        """
        self.code = code
        self.reason = reason
        super().__init__(reason)

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return f"WebSocketException(code={self.code}, reason={self.reason!r})"


class WebSocketDisconnect(Exception):
    """
    Raised when a WebSocket is disconnected by the client.

    This is not an error, just a signal that the connection was closed.
    The framework raises this when a receive operation fails because
    the client has disconnected.

    Attributes:
        code: WebSocket close code from client
        reason: Close reason from client (if any)

    Example:
        >>> try:
        ...     data = await websocket.receive_text()
        ... except WebSocketDisconnect as e:
        ...     print(f"Client disconnected: {e.code}")
    """

    def __init__(
        self,
        code: int = 1000,
        reason: str = "",
    ) -> None:
        """
        Initialize disconnect exception.

        Args:
            code: WebSocket close code (default: 1000)
            reason: Close reason (default: "")
        """
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected with code {code}")

    def __repr__(self) -> str:
        """Return detailed string representation."""
        return f"WebSocketDisconnect(code={self.code}, reason={self.reason!r})"


class Redirect(HTTPException):
    """HTTP redirect exception. Raises 302 redirect by default."""

    def __init__(self, url: str, status_code: int = 302) -> None:
        super().__init__(status_code, headers={"Location": url})
        self.url = url

    def __repr__(self) -> str:
        return f"Redirect(url={self.url!r}, status_code={self.status_code})"


class HTTPNotFound(HTTPException):
    """HTTP 404 Not Found exception."""

    def __init__(self, detail: str = "Not found") -> None:
        super().__init__(404, detail=detail)


class HTTPUnauthorized(HTTPException):
    """HTTP 401 Unauthorized exception."""

    def __init__(self, detail: str = "Unauthorized") -> None:
        super().__init__(401, detail=detail)


class HTTPForbidden(HTTPException):
    """HTTP 403 Forbidden exception."""

    def __init__(self, detail: str = "Forbidden") -> None:
        super().__init__(403, detail=detail)


class HTTPBadRequest(HTTPException):
    """HTTP 400 Bad Request exception."""

    def __init__(self, detail: str = "Bad request") -> None:
        super().__init__(400, detail=detail)


class HTTPServiceUnavailable(HTTPException):
    """HTTP 503 Service Unavailable exception."""

    def __init__(self, detail: str = "Service unavailable") -> None:
        super().__init__(503, detail=detail)
