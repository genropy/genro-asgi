## Source: initial_implementation_plan/archive/05-responses.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types, 02-datastructures
**Commit message**: `feat(responses): add Response classes (JSON, HTML, Streaming, Redirect)`

HTTP Response classes for sending data back to clients.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import json
from typing import Any, AsyncIterator, Mapping

from .types import Receive, Scope, Send

# Optional fast JSON
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

class Response:
    """
    Base HTTP Response.

Sends bytes content with headers and status code.

Example:
        response = Response(content=b"Hello", status_code=200)
        await response(scope, receive, send)
    """

media_type: str | None = None
    charset: str = "utf-8"

def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        """
        Initialize response.

Args:
            content: Response body (bytes or str)
            status_code: HTTP status code
            headers: Response headers
            media_type: Content-Type (overrides class default)
        """
        self.status_code = status_code
        self._headers: dict[str, str] = dict(headers) if headers else {}

if media_type is not None:
            self.media_type = media_type

self.body = self._encode_content(content)

# Set content-type if not already set
        if "content-type" not in {k.lower() for k in self._headers}:
            content_type = self._get_content_type()
            if content_type:
                self._headers["content-type"] = content_type

def _encode_content(self, content: bytes | str | None) -> bytes:
        """Encode content to bytes."""
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        return content.encode(self.charset)

def _get_content_type(self) -> str | None:
        """Get content-type header value."""
        if self.media_type is None:
            return None
        if self.media_type.startswith("text/") and "charset" not in self.media_type:
            return f"{self.media_type}; charset={self.charset}"
        return self.media_type

def _build_headers(self) -> list[tuple[bytes, bytes]]:
        """Build ASGI header list."""
        return [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in self._headers.items()
        ]

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - send the response."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })
        await send({
            "type": "http.response.body",
            "body": self.body,
        })

class JSONResponse(Response):
    """
    JSON Response.

Serializes Python objects to JSON.
    Uses orjson if available for better performance.

Example:
        return JSONResponse({"status": "ok", "data": [1, 2, 3]})
    """

media_type = "application/json"

def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """
        Initialize JSON response.

Args:
            content: Python object to serialize as JSON
            status_code: HTTP status code
            headers: Response headers
        """
        # Serialize to JSON bytes
        if HAS_ORJSON:
            body = orjson.dumps(content)
        else:
            body = json.dumps(content, ensure_ascii=False).encode("utf-8")

super().__init__(
            content=body,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )

class HTMLResponse(Response):
    """
    HTML Response.

Example:
        return HTMLResponse("<h1>Hello World</h1>")
    """

class PlainTextResponse(Response):
    """
    Plain Text Response.

Example:
        return PlainTextResponse("Hello, World!")
    """

class RedirectResponse(Response):
    """
    HTTP Redirect Response.

Example:
        return RedirectResponse("/new-location")
        return RedirectResponse("/login", status_code=303)
    """

def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """
        Initialize redirect response.

Args:
            url: Redirect target URL
            status_code: HTTP status code (301, 302, 303, 307, 308)
            headers: Additional response headers
        """
        _headers = dict(headers) if headers else {}
        _headers["location"] = url
        super().__init__(
            content=b"",
            status_code=status_code,
            headers=_headers,
        )

class StreamingResponse(Response):
    """
    Streaming Response.

Sends response body from an async iterator.

Example:
        async def generate():
            for i in range(10):
                yield f"chunk {i}\n".encode()

return StreamingResponse(generate())
    """

def __init__(
        self,
        content: AsyncIterator[bytes],
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        """
        Initialize streaming response.

Args:
            content: Async iterator yielding bytes chunks
            status_code: HTTP status code
            headers: Response headers
            media_type: Content-Type header
        """
        self.body_iterator = content
        self.status_code = status_code
        self._headers = dict(headers) if headers else {}

if media_type is not None:
            self.media_type = media_type

if self.media_type and "content-type" not in {k.lower() for k in self._headers}:
            self._headers["content-type"] = self.media_type

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - stream the response."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })

async for chunk in self.body_iterator:
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": True,
            })

await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })

class FileResponse(Response):
    """
    File Download Response.

Example:
        return FileResponse("/path/to/file.pdf")
        return FileResponse("/path/to/file.pdf", filename="document.pdf")
    """

def __init__(
        self,
        path: str,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        filename: str | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        """
        Initialize file response.

Args:
            path: Path to file on disk
            status_code: HTTP status code
            headers: Response headers
            media_type: Content-Type (auto-detected if None)
            filename: Download filename (for Content-Disposition)
            chunk_size: Size of chunks to read (default 64KB)
        """
        import mimetypes
        from pathlib import Path

self.path = Path(path)
        self.chunk_size = chunk_size
        self.status_code = status_code
        self._headers = dict(headers) if headers else {}

# Auto-detect media type
        if media_type is None:
            media_type, _ = mimetypes.guess_type(str(self.path))
        self.media_type = media_type or "application/octet-stream"

if "content-type" not in {k.lower() for k in self._headers}:
            self._headers["content-type"] = self.media_type

# Set content-disposition for download
        if filename:
            self._headers["content-disposition"] = f'attachment; filename="{filename}"'

# Set content-length if file exists
        if self.path.exists():
            self._headers["content-length"] = str(self.path.stat().st_size)

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - stream the file."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })

# Stream file in chunks
        with open(self.path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                more_body = len(chunk) == self.chunk_size
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": more_body,
                })
                if not more_body:
                    break
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for Response classes."""

import pytest
from genro_asgi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

class MockSend:
    """Capture sent messages."""

def __init__(self):
        self.messages = []

async def __call__(self, message):
        self.messages.append(message)

@pytest.fixture
def send():
    return MockSend()

@pytest.fixture
def scope():
    return {"type": "http"}

async def receive():
    return {"type": "http.request", "body": b""}

class TestResponse:
    @pytest.mark.asyncio
    async def test_basic(self, scope, send):
        response = Response(content=b"Hello", status_code=200)
        await response(scope, receive, send)

assert len(send.messages) == 2
        assert send.messages[0]["type"] == "http.response.start"
        assert send.messages[0]["status"] == 200
        assert send.messages[1]["type"] == "http.response.body"
        assert send.messages[1]["body"] == b"Hello"

@pytest.mark.asyncio
    async def test_string_content(self, scope, send):
        response = Response(content="Hello", status_code=200)
        await response(scope, receive, send)
        assert send.messages[1]["body"] == b"Hello"

@pytest.mark.asyncio
    async def test_custom_headers(self, scope, send):
        response = Response(
            content=b"",
            headers={"X-Custom": "value"},
        )
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"x-custom"] == b"value"

@pytest.mark.asyncio
    async def test_media_type(self, scope, send):
        response = Response(content=b"", media_type="application/xml")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"application/xml"

class TestJSONResponse:
    @pytest.mark.asyncio
    async def test_dict(self, scope, send):
        response = JSONResponse({"key": "value"})
        await response(scope, receive, send)

body = send.messages[1]["body"]
        assert b"key" in body
        assert b"value" in body

@pytest.mark.asyncio
    async def test_list(self, scope, send):
        response = JSONResponse([1, 2, 3])
        await response(scope, receive, send)

body = send.messages[1]["body"]
        assert body in (b"[1,2,3]", b"[1, 2, 3]")

@pytest.mark.asyncio
    async def test_content_type(self, scope, send):
        response = JSONResponse({})
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"application/json"

@pytest.mark.asyncio
    async def test_status_code(self, scope, send):
        response = JSONResponse({"error": "not found"}, status_code=404)
        await response(scope, receive, send)
        assert send.messages[0]["status"] == 404

class TestHTMLResponse:
    @pytest.mark.asyncio
    async def test_basic(self, scope, send):
        response = HTMLResponse("<h1>Hello</h1>")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert b"text/html" in headers[b"content-type"]
        assert send.messages[1]["body"] == b"<h1>Hello</h1>"

class TestPlainTextResponse:
    @pytest.mark.asyncio
    async def test_basic(self, scope, send):
        response = PlainTextResponse("Hello, World!")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert b"text/plain" in headers[b"content-type"]

class TestRedirectResponse:
    @pytest.mark.asyncio
    async def test_redirect(self, scope, send):
        response = RedirectResponse("/new-location")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"location"] == b"/new-location"
        assert send.messages[0]["status"] == 307

@pytest.mark.asyncio
    async def test_redirect_303(self, scope, send):
        response = RedirectResponse("/login", status_code=303)
        await response(scope, receive, send)
        assert send.messages[0]["status"] == 303

class TestStreamingResponse:
    @pytest.mark.asyncio
    async def test_streaming(self, scope, send):
        async def generate():
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

response = StreamingResponse(generate())
        await response(scope, receive, send)

# Start + 3 chunks + final empty
        assert send.messages[0]["type"] == "http.response.start"
        assert send.messages[1]["body"] == b"chunk1"
        assert send.messages[2]["body"] == b"chunk2"
        assert send.messages[3]["body"] == b"chunk3"
        assert send.messages[4]["body"] == b""
        assert send.messages[4]["more_body"] is False

@pytest.mark.asyncio
    async def test_media_type(self, scope, send):
        async def generate():
            yield b"data"

response = StreamingResponse(generate(), media_type="text/event-stream")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"text/event-stream"

class TestFileResponse:
    @pytest.mark.asyncio
    async def test_file(self, scope, send, tmp_path):
        # Create temp file
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello from file")

response = FileResponse(str(file_path))
        await response(scope, receive, send)

# Collect body chunks
        body = b"".join(
            msg["body"] for msg in send.messages if msg["type"] == "http.response.body"
        )
        assert body == b"Hello from file"

@pytest.mark.asyncio
    async def test_filename(self, scope, send, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

response = FileResponse(str(file_path), filename="download.txt")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert b"attachment" in headers[b"content-disposition"]
        assert b"download.txt" in headers[b"content-disposition"]

@pytest.mark.asyncio
    async def test_content_length(self, scope, send, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("12345")

response = FileResponse(str(file_path))
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-length"] == b"5"
```

```python
from .responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
```

- [ ] Create `src/genro_asgi/responses.py`
- [ ] Create `tests/test_responses.py`
- [ ] Run `pytest tests/test_responses.py`
- [ ] Run `mypy src/genro_asgi/responses.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

