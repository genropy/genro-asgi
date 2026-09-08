# Requests and errors

> **Status:** Draft; implementation checked against the development source on 2026-09-08.

`RoutedApplication` creates a `Request` and awaits `init()` before resolving and
calling a handler. It drains the entire ASGI body and decodes it by content type.
It uses genro-tytx for serialization, not for reading the ASGI protocol.

## Body arguments

| Content type | Handler arguments |
|---|---|
| JSON, XML, msgpack (including TYTX media types) | Hydrated value in `body_data` |
| `application/x-www-form-urlencoded` | Individual field kwargs |
| `multipart/form-data` | Individual field kwargs; file parts are `UploadedFile` |
| Other or missing content type | Bytes in `body_raw` |
| Empty body | No body argument |

Query parameters form the initial kwargs. Repeated query keys become lists;
form fields override query fields with the same name. Repeated multipart names
also become lists. A file has `name` (form field name), `filename` (client-supplied),
`content_type` and `data` (complete bytes). Uploaded files are not spooled to disk.

Save this as `bodies.py`, then run `python bodies.py`:

```python
from genro_asgi import AsgiServer, RoutedApplication
from genro_routes import route


class Bodies(RoutedApplication):
    mount = ""

    @route()
    def document(self, body_data):
        return {"received": body_data}

    @route()
    def upload(self, title, document):
        return {"title": title, "filename": document.filename,
                "bytes": len(document.data)}

    @route()
    def raw(self, body_raw):
        return {"bytes": len(body_raw)}


if __name__ == "__main__":
    AsgiServer(applications=[Bodies()]).serve(host="127.0.0.1", port=8000)
```

```console
$ curl -H 'Content-Type: application/json' -d '{"name":"Ada"}' http://127.0.0.1:8000/document
{"received":{"name":"Ada"}}
$ curl -F title=Example -F document=@bodies.py http://127.0.0.1:8000/upload
{"title":"Example","filename":"bodies.py","bytes":...}
$ curl -H 'Content-Type: application/octet-stream' --data-binary abc http://127.0.0.1:8000/raw
{"bytes":3}
```

Stop the process with Ctrl-C. There is no configurable total body-size limit in
`Request.read_body()`: memory grows with the body, including multipart uploads.
Use an ingress limit or an application that controls `receive` directly when
unbounded uploads are unacceptable. Direct HTTP response streaming does not
change this request buffering; see [Streaming](streaming.md).

## Validation and status codes

`AsgiServer` automatically arms `pydantic` and `openapi` on its routed
applications. Neither can be disabled; explicit entries configure their
options. A composition without `PluginMixin` does not supply this pair.

Pydantic coerces and validates annotated parameters. A JSON dictionary is
spread over declared scalar parameters
unless the handler declares `body_data` or accepts `**kwargs`. Extra JSON keys
are dropped in that spreading case. Forms and query kwargs still bind normally.

| Condition | Status |
|---|---|
| Unknown route | 404 |
| Missing required argument or unexpected kwarg | 400 |
| Signature fits, but configured pydantic validation rejects values | 422 |
| Exception raised inside the handler body | 500, unless it is an HTTP exception |
| Handler raises an `HTTPException` subclass | That exception's status |

Malformed payload decoding is separate from signature validation: do not assume
that every parse error becomes 400 or 422. See the error middleware and
[request API](../api/core.rst) for the current mappings.

A handler that declares an **unannotated** `_request` parameter can receive the
live request when parameter metadata is available. `AsgiServer` supplies that
metadata through its automatically armed pydantic plugin.
It exposes the session and `avatar()`, and its `response` can be given cookies or
headers before the handler returns its result. This is explicit parameter
injection, not a thread-local current request.
