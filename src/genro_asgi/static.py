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
Static file serving ASGI application.

Source of truth - rebuild from this description:

StaticFiles is an ASGI application that serves static files from a directory.
It handles GET and HEAD requests, serves index files for directories, and
returns appropriate content types based on file extensions.

Features:
- Serves files from a specified directory
- Configurable index file (default: index.html)
- SPA fallback support (serve index.html for missing paths)
- Content-Type detection via mimetypes
- ETag generation for caching
- HEAD request support
- Security: prevents directory traversal attacks

Constructor:
    StaticFiles(directory, index="index.html", fallback=None)

    - directory: Path to serve files from (str or Path)
    - index: Default file for directory requests
    - fallback: File to serve for 404s (SPA mode)

ASGI interface:
    __call__(scope, receive, send)

    - Only handles HTTP requests (type="http")
    - Returns 404 for missing files (or fallback if configured)
    - Returns 405 for non-GET/HEAD methods
"""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from .types import Receive, Scope, Send

__all__ = ["StaticFiles"]

# Ensure common types are registered
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("text/html", ".html")
mimetypes.add_type("text/html", ".htm")


class StaticFiles:
    """
    ASGI application for serving static files.

    Serves files from a directory with support for index files,
    content-type detection, and SPA fallback mode.

    Example:
        # Basic usage
        app = StaticFiles(directory="./public")

        # With custom index
        app = StaticFiles(directory="./docs", index="readme.html")

        # SPA mode - serve index.html for all 404s
        app = StaticFiles(
            directory="./webapp/dist",
            index="index.html",
            fallback="index.html"
        )

        # Mount in AsgiServer
        server = AsgiServer()
        server.mount("/static", StaticFiles(directory="./assets"))
    """

    def __init__(
        self,
        directory: str | Path,
        index: str = "index.html",
        fallback: str | None = None,
    ) -> None:
        """
        Initialize static file server.

        Args:
            directory: Root directory to serve files from.
            index: Default file to serve for directory requests.
            fallback: File to serve when requested path not found (SPA mode).
                     If None, returns 404 for missing files.
        """
        self.directory = Path(directory).resolve()
        self.index = index
        self.fallback = fallback

        if not self.directory.is_dir():
            raise ValueError(f"Directory does not exist: {self.directory}")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Handle ASGI request.

        Args:
            scope: ASGI scope dict.
            receive: ASGI receive callable.
            send: ASGI send callable.
        """
        if scope["type"] != "http":
            return

        method = scope.get("method", "GET")
        if method not in ("GET", "HEAD"):
            await self._send_error(send, 405, "Method Not Allowed")
            return

        path = scope.get("path", "/")
        file_path = self._resolve_path(path)

        if file_path is None:
            if self.fallback:
                file_path = self.directory / self.fallback
                if not file_path.is_file():
                    await self._send_error(send, 404, "Not Found")
                    return
            else:
                await self._send_error(send, 404, "Not Found")
                return

        await self._send_file(send, file_path, include_body=(method == "GET"))

    def _resolve_path(self, url_path: str) -> Path | None:
        """
        Resolve URL path to filesystem path.

        Prevents directory traversal attacks by ensuring resolved path
        is within the configured directory.

        Args:
            url_path: URL path from request.

        Returns:
            Resolved Path or None if not found/invalid.
        """
        # Remove leading slash and normalize
        clean_path = url_path.lstrip("/")
        if not clean_path:
            clean_path = self.index

        # Resolve the full path
        try:
            file_path = (self.directory / clean_path).resolve()
        except (ValueError, OSError):
            return None

        # Security: ensure path is within directory
        try:
            file_path.relative_to(self.directory)
        except ValueError:
            return None

        # If directory, look for index file
        if file_path.is_dir():
            file_path = file_path / self.index

        # Check file exists
        if not file_path.is_file():
            return None

        return file_path

    async def _send_file(
        self,
        send: Send,
        file_path: Path,
        include_body: bool = True,
    ) -> None:
        """
        Send file as HTTP response.

        Args:
            send: ASGI send callable.
            file_path: Path to file.
            include_body: Include body (False for HEAD requests).
        """
        # Get content type
        content_type = self._get_content_type(file_path)

        # Read file
        content = file_path.read_bytes()

        # Generate ETag
        etag = self._generate_etag(content)

        # Build headers
        headers: list[tuple[bytes, bytes]] = [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(content)).encode()),
            (b"etag", f'"{etag}"'.encode()),
            (b"cache-control", b"public, max-age=3600"),
        ]

        # Send response
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })

        if include_body:
            await send({
                "type": "http.response.body",
                "body": content,
            })
        else:
            await send({
                "type": "http.response.body",
                "body": b"",
            })

    async def _send_error(
        self,
        send: Send,
        status: int,
        message: str,
    ) -> None:
        """
        Send error response.

        Args:
            send: ASGI send callable.
            status: HTTP status code.
            message: Error message.
        """
        body = f"{status} {message}".encode()

        await send({
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        })

        await send({
            "type": "http.response.body",
            "body": body,
        })

    def _get_content_type(self, file_path: Path) -> str:
        """
        Get content type for file.

        Args:
            file_path: Path to file.

        Returns:
            MIME type string.
        """
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        # Add charset for text types
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type = f"{content_type}; charset=utf-8"

        return content_type

    def _generate_etag(self, content: bytes) -> str:
        """
        Generate ETag for content.

        Args:
            content: File content.

        Returns:
            ETag string (MD5 hash).
        """
        return hashlib.md5(content).hexdigest()

    def __repr__(self) -> str:
        """Return string representation."""
        return f"StaticFiles(directory={self.directory!r}, index={self.index!r})"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Serve static files")
    parser.add_argument("directory", help="Directory to serve")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    parser.add_argument("--index", default="index.html", help="Index file")
    args = parser.parse_args()

    app = StaticFiles(directory=args.directory, index=args.index)

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port)
