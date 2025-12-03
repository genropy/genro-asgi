# Response System

**Version**: 1.0.0
**Status**: SOURCE OF TRUTH
**Last Updated**: 2025-12-03

---

## Overview

Response classes for HTTP output. All classes live in `response.py`:

- `Response` - Base response class
- `JSONResponse` - JSON serialization
- `HTMLResponse` - HTML content
- `PlainTextResponse` - Plain text
- `RedirectResponse` - HTTP redirects
- `StreamingResponse` - Async streaming
- `FileResponse` - File downloads

Plus helper function:
- `make_cookie()` - Create Set-Cookie header

---

## Response (Base Class)

```python
class Response:
    """Base HTTP response."""

    def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.body = self._encode_content(content)
        self.status_code = status_code
        self._headers: list[tuple[str, str]] = []
        self.media_type = media_type

        if headers:
            for name, value in headers.items():
                self.append_header(name, value)

    def append_header(self, name: str, value: str) -> None:
        """Add header (allows multiple with same name)."""
        self._headers.append((name, value))

    def set_header(self, name: str, value: str) -> None:
        """Set header (replaces existing)."""
        name_lower = name.lower()
        self._headers = [(n, v) for n, v in self._headers if n.lower() != name_lower]
        self._headers.append((name, value))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })
        await send({
            "type": "http.response.body",
            "body": self.body,
        })
```

---

## JSONResponse

```python
class JSONResponse(Response):
    """JSON response with auto-serialization."""

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        body = self._serialize(content)
        super().__init__(
            content=body,
            status_code=status_code,
            headers=headers,
            media_type="application/json",
        )

    def _serialize(self, content: Any) -> bytes:
        """Serialize to JSON bytes."""
        if HAS_ORJSON:
            return orjson.dumps(content)
        return json.dumps(content, ensure_ascii=False).encode("utf-8")
```

---

## HTMLResponse

```python
class HTMLResponse(Response):
    """HTML response."""

    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type="text/html; charset=utf-8",
        )
```

---

## PlainTextResponse

```python
class PlainTextResponse(Response):
    """Plain text response."""

    def __init__(
        self,
        content: str,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            media_type="text/plain; charset=utf-8",
        )
```

---

## RedirectResponse

```python
class RedirectResponse(Response):
    """HTTP redirect response."""

    def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(
            content=None,
            status_code=status_code,
            headers=headers,
        )
        self.set_header("location", url)
```

Status codes:
- `301` - Permanent redirect (cacheable)
- `302` - Found (legacy, avoid)
- `303` - See Other (always GET)
- `307` - Temporary redirect (preserves method)
- `308` - Permanent redirect (preserves method)

---

## StreamingResponse

```python
class StreamingResponse(Response):
    """Streaming response from async generator."""

    def __init__(
        self,
        content: AsyncIterable[bytes | str],
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        self.body_iterator = content
        self.status_code = status_code
        self._headers = []
        self.media_type = media_type
        if headers:
            for name, value in headers.items():
                self.append_header(name, value)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })

        async for chunk in self.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
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
```

Usage:
```python
async def generate():
    for i in range(10):
        yield f"chunk {i}\n"
        await asyncio.sleep(0.1)

response = StreamingResponse(generate(), media_type="text/plain")
```

---

## FileResponse

```python
class FileResponse(Response):
    """File download response."""

    def __init__(
        self,
        path: str | Path,
        filename: str | None = None,
        media_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.path = Path(path)
        self.filename = filename or self.path.name
        self.media_type = media_type or self._guess_media_type()
        self._headers = []
        if headers:
            for name, value in headers.items():
                self.append_header(name, value)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        stat = await aiofiles.os.stat(self.path)

        headers = self._build_headers()
        headers.append((b"content-length", str(stat.st_size).encode()))
        headers.append((
            b"content-disposition",
            f'attachment; filename="{self.filename}"'.encode()
        ))

        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": headers,
        })

        async with aiofiles.open(self.path, "rb") as f:
            while chunk := await f.read(65536):
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
```

---

## make_cookie Helper

```python
def make_cookie(
    name: str,
    value: str,
    *,
    max_age: int | None = None,
    expires: datetime | None = None,
    path: str = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    samesite: str = "lax",
) -> tuple[str, str]:
    """
    Create Set-Cookie header tuple.

    Returns:
        Tuple of ("set-cookie", cookie_string)

    Usage:
        response.append_header(*make_cookie("session", "abc123", httponly=True))
    """
    parts = [f"{name}={value}"]

    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    if expires is not None:
        parts.append(f"Expires={expires.strftime('%a, %d %b %Y %H:%M:%S GMT')}")
    if path:
        parts.append(f"Path={path}")
    if domain:
        parts.append(f"Domain={domain}")
    if secure:
        parts.append("Secure")
    if httponly:
        parts.append("HttpOnly")
    if samesite:
        parts.append(f"SameSite={samesite.capitalize()}")

    return ("set-cookie", "; ".join(parts))
```

---

## Handler Result Conversion

In router mode, `AsgiServer._result_to_response()` converts handler returns:

```python
def _result_to_response(self, result: Any) -> Response:
    # Already a Response
    if isinstance(result, Response):
        return result

    # Dict/List -> JSON
    if isinstance(result, (dict, list)):
        return JSONResponse(result)

    # String -> PlainText
    if isinstance(result, str):
        return PlainTextResponse(result)

    # Callable ASGI app
    if callable(result):
        return CallableWrapper(result)

    # Fallback
    return PlainTextResponse(str(result))
```

---

## Multi-Header Support

Response supports multiple headers with same name (e.g., Set-Cookie):

```python
response = Response(content="OK")
response.append_header(*make_cookie("session", "abc"))
response.append_header(*make_cookie("user", "mario"))
# Both Set-Cookie headers will be sent
```

---

## Class Hierarchy

```
Response
    │
    ├── JSONResponse
    ├── HTMLResponse
    ├── PlainTextResponse
    ├── RedirectResponse
    ├── StreamingResponse
    └── FileResponse
```

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
