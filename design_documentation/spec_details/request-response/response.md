# Response

Classi Response per invio risposte HTTP via ASGI.

## Gerarchia

| Classe | Uso | Media Type |
|--------|-----|------------|
| Response | Base, content bytes/str | None (custom) |
| JSONResponse | Serializza dict → JSON | application/json |
| HTMLResponse | HTML content | text/html |
| PlainTextResponse | Plain text | text/plain |
| RedirectResponse | HTTP redirect | - |
| StreamingResponse | Async iterator | custom |
| FileResponse | Download file | auto-detect |

## Response Base

```python
class Response:
    __slots__ = ("_body", "_status_code", "_headers", "_media_type", "_charset")

    def __init__(
        self,
        content: bytes | str = b"",
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        charset: str = "utf-8",
    ): ...

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """ASGI interface."""
```

## Decisioni Chiave

| Aspetto | Decisione |
|---------|-----------|
| API | `__call__(scope, receive, send)` - standard ASGI |
| Parametro status | `status_code` (esplicito) |
| Headers input | `Mapping[str, str]` (flessibile) |
| Media type default | `None` (nessuno automatico) |
| Charset | Auto-append per `text/*` |
| Header encoding | latin-1 (standard HTTP) |
| Content-Length | Auto per non-streaming |

## StreamingResponse

```python
class StreamingResponse(Response):
    def __init__(
        self,
        content: AsyncIterator[bytes],
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ): ...
```

- Solo async iterator (no sync)
- No Content-Length (chunked transfer)

## FileResponse

```python
class FileResponse(Response):
    def __init__(
        self,
        path: str | Path,
        filename: str | None = None,
        media_type: str | None = None,
        chunk_size: int = 65536,
    ): ...
```

- Content-Length da file.stat() se esiste
- Content-Disposition per download
- I/O sincrono (v1, async futuro)

## Decisioni

- **`__slots__`** - Su tutte le classi Response
- **Sync FileResponse** - Accettabile per v1, async futuro
- **No redirect validation** - Libertà utente su status code
- **File missing** - FileNotFoundError naturale da open()
