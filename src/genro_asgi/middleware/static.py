# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Static Files Middleware."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class StaticFilesMiddleware(BaseMiddleware):
    """Static files middleware - serves files from a directory.

    Config options:
        directory: Directory containing static files. Required.
        prefix: URL prefix for static files. Default: "/static"
        html: Serve index.html for directories. Default: True
    """

    __slots__ = ("directory", "prefix", "html")

    def __init__(
        self,
        app: ASGIApp,
        directory: str | Path,
        prefix: str = "/static",
        html: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.directory = Path(directory).resolve()
        self.prefix = prefix.rstrip("/")
        self.html = html

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - serve static files or pass through."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")

        # Check if path matches prefix
        if not path.startswith(self.prefix):
            await self.app(scope, receive, send)
            return

        # Get file path
        relative_path = path[len(self.prefix):].lstrip("/")
        file_path = (self.directory / relative_path).resolve()

        # Security: ensure path is within directory
        try:
            file_path.relative_to(self.directory)
        except ValueError:
            await self._send_404(send)
            return

        # Check if it's a directory and serve index.html
        if file_path.is_dir() and self.html:
            file_path = file_path / "index.html"

        # Check if file exists
        if not file_path.is_file():
            await self._send_404(send)
            return

        await self._send_file(send, file_path)

    async def _send_file(self, send: Send, file_path: Path) -> None:
        """Send file content."""
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        content = file_path.read_bytes()

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", content_type.encode()),
                (b"content-length", str(len(content)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": content,
        })

    async def _send_404(self, send: Send) -> None:
        """Send 404 response."""
        body = b"Not Found"
        await send({
            "type": "http.response.start",
            "status": 404,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })


if __name__ == "__main__":
    pass
