"""ASGI Response utilities.

Copyright 2025 Softwell S.r.l.
Licensed under the Apache License, Version 2.0
"""

import json
from typing import Any, Callable

try:
    import orjson  # type: ignore
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False


class Response:
    """Base ASGI Response.

    Provides methods to send HTTP responses through ASGI send callable.
    """

    def __init__(
        self,
        content: bytes = b"",
        status: int = 200,
        headers: dict[str, str] | None = None,
        media_type: str = "text/plain"
    ) -> None:
        """Initialize response.

        Args:
            content: Response body
            status: HTTP status code
            headers: Response headers
            media_type: Content-Type header value
        """
        self.content = content
        self.status = status
        self.headers = headers or {}
        self.media_type = media_type

    async def send(self, send: Callable) -> None:
        """Send response through ASGI send callable.

        Args:
            send: ASGI send callable
        """
        headers_list = [
            [b"content-type", self.media_type.encode("latin1")]
        ]
        for name, value in self.headers.items():
            headers_list.append([
                name.encode("latin1"),
                value.encode("latin1")
            ])

        await send({
            "type": "http.response.start",
            "status": self.status,
            "headers": headers_list,
        })
        await send({
            "type": "http.response.body",
            "body": self.content,
        })


class JSONResponse(Response):
    """JSON Response.

    Uses orjson if available, falls back to standard library json.
    """

    def __init__(
        self,
        content: Any,
        status: int = 200,
        headers: dict[str, str] | None = None
    ) -> None:
        """Initialize JSON response.

        Args:
            content: Python object to serialize as JSON
            status: HTTP status code
            headers: Response headers
        """
        if HAS_ORJSON:
            body = orjson.dumps(content)
        else:
            body = json.dumps(content).encode("utf-8")

        super().__init__(
            content=body,
            status=status,
            headers=headers,
            media_type="application/json"
        )


class HTMLResponse(Response):
    """HTML Response."""

    def __init__(
        self,
        content: str | bytes,
        status: int = 200,
        headers: dict[str, str] | None = None
    ) -> None:
        """Initialize HTML response.

        Args:
            content: HTML content
            status: HTTP status code
            headers: Response headers
        """
        body = content.encode("utf-8") if isinstance(content, str) else content
        super().__init__(
            content=body,
            status=status,
            headers=headers,
            media_type="text/html; charset=utf-8"
        )


class PlainTextResponse(Response):
    """Plain Text Response."""

    def __init__(
        self,
        content: str | bytes,
        status: int = 200,
        headers: dict[str, str] | None = None
    ) -> None:
        """Initialize plain text response.

        Args:
            content: Text content
            status: HTTP status code
            headers: Response headers
        """
        body = content.encode("utf-8") if isinstance(content, str) else content
        super().__init__(
            content=body,
            status=status,
            headers=headers,
            media_type="text/plain; charset=utf-8"
        )
