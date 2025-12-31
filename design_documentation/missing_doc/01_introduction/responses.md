# Responses

**Status**: ✅ IMPLEMENTATO
**Source**: `src/genro_asgi/response.py`

## Implementation Status

genro-asgi implements a **single Response class** with dynamic content type
detection via `set_result()`, rather than specialized subclasses.

| Feature | Status | Notes |
| ------- | ------ | ----- |
| Response base class | ✅ Done | Full implementation |
| set_result() auto-detection | ✅ Done | dict, str, bytes, Path, None |
| set_header() | ✅ Done | Add headers post-construction |
| set_error() | ✅ Done | Exception to HTTP status mapping |
| make_cookie() | ✅ Done | Helper function for cookies |
| TYTX support | ✅ Done | Auto-serialization if request.tytx_mode |
| orjson support | ✅ Done | Optional fast JSON |

## Design Decision

The original plan included specialized subclasses (JSONResponse, HTMLResponse,
StreamingResponse, FileResponse, etc.) following the Starlette pattern.

**Implemented instead**: Single Response class with `set_result()` that auto-detects
content type from result type. This integrates better with the dispatcher flow
where Response is created by Request and configured after handler execution.

## Not Implemented (By Design)

The following subclasses from the original plan are **not implemented**:

- `JSONResponse` - Use `response.set_result({"data": ...})`
- `HTMLResponse` - Use `response.set_result(html_string)` with `mime_type="text/html"`
- `PlainTextResponse` - Use `response.set_result("text")`
- `RedirectResponse` - Use `raise Redirect(url)` exception
- `StreamingResponse` - Not yet needed, can be added if required
- `FileResponse` - Use `response.set_result(Path("file.pdf"))`

## Documentation

See `spec_details/request-response/response.md` for full API documentation.
