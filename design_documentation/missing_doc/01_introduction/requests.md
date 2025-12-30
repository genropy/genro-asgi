## Source: initial_implementation_plan/archive/04-requests.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types, 02-datastructures
**Commit message**: `feat(requests): add Request class with body/json/form support`

HTTP Request class wrapping ASGI scope and receive callable.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import json
from typing import Any, AsyncIterator

from .datastructures import Address, Headers, QueryParams, State, URL
from .types import Message, Receive, Scope

# Optional fast JSON
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

class Request:
    """
    HTTP Request wrapper.

Provides convenient access to ASGI scope and body reading.

Example:
        async def handler(request: Request):
            name = request.query_params.get("name", "World")
            data = await request.json()
            return JSONResponse({"hello": name, "data": data})
    """

__slots__ = (
        "_scope",
        "_receive",
        "_body",
        "_json",
        "_headers",
        "_query_params",
        "_url",
        "_state",
    )

def __init__(self, scope: Scope, receive: Receive) -> None:
        """
        Initialize request from ASGI scope and receive.

Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
        """
        self._scope = scope
        self._receive = receive
        self._body: bytes | None = None
        self._json: Any = None
        self._headers: Headers | None = None
        self._query_params: QueryParams | None = None
        self._url: URL | None = None
        self._state: State | None = None

@property
    def scope(self) -> Scope:
        """Raw ASGI scope."""
        return self._scope

@property
    def method(self) -> str:
        """HTTP method (GET, POST, etc.)."""
        return self._scope.get("method", "GET")

@property
    def path(self) -> str:
        """Request path."""
        return self._scope.get("path", "/")

@property
    def scheme(self) -> str:
        """URL scheme (http or https)."""
        return self._scope.get("scheme", "http")

@property
    def url(self) -> URL:
        """Full URL object."""
        if self._url is None:
            scheme = self.scheme
            server = self._scope.get("server")
            path = self._scope.get("root_path", "") + self.path
            query_string = self._scope.get("query_string", b"")

if server:
                host, port = server
                if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
                    netloc = host
                else:
                    netloc = f"{host}:{port}"
            else:
                netloc = self.headers.get("host", "localhost")

url_str = f"{scheme}://{netloc}{path}"
            if query_string:
                url_str += f"?{query_string.decode('latin-1')}"

self._url = URL(url_str)
        return self._url

@property
    def headers(self) -> Headers:
        """Request headers (case-insensitive)."""
        if self._headers is None:
            self._headers = Headers(scope=self._scope)
        return self._headers

@property
    def query_params(self) -> QueryParams:
        """Query string parameters."""
        if self._query_params is None:
            self._query_params = QueryParams(scope=self._scope)
        return self._query_params

@property
    def client(self) -> Address | None:
        """Client address (host, port) if available."""
        client = self._scope.get("client")
        if client:
            return Address(client[0], client[1])
        return None

@property
    def state(self) -> State:
        """Request state for storing custom data."""
        if self._state is None:
            self._state = State()
        return self._state

@property
    def content_type(self) -> str | None:
        """Content-Type header value."""
        return self.headers.get("content-type")

async def body(self) -> bytes:
        """
        Read and return the request body.

The body is cached after first read.
        """
        if self._body is None:
            chunks: list[bytes] = []
            async for chunk in self.stream():
                chunks.append(chunk)
            self._body = b"".join(chunks)
        return self._body

async def stream(self) -> AsyncIterator[bytes]:
        """
        Stream the request body in chunks.

Use this for large request bodies to avoid loading
        everything into memory at once.
        """
        if self._body is not None:
            yield self._body
            return

while True:
            message: Message = await self._receive()
            body = message.get("body", b"")
            if body:
                yield body
            if not message.get("more_body", False):
                break

async def json(self) -> Any:
        """
        Parse request body as JSON.

Uses orjson if available, falls back to stdlib json.
        Result is cached after first parse.

Raises:
            ValueError: If body is not valid JSON
        """
        if self._json is None:
            body = await self.body()
            if HAS_ORJSON:
                self._json = orjson.loads(body)
            else:
                self._json = json.loads(body.decode("utf-8"))
        return self._json

async def form(self) -> dict[str, Any]:
        """
        Parse request body as form data.

Supports application/x-www-form-urlencoded.
        For multipart, use a dedicated parser (future).

Returns:
            Dict of form field values
        """
        from urllib.parse import parse_qs

body = await self.body()
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        # Return single values instead of lists for convenience
        return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}

def __repr__(self) -> str:
        return f"Request(method={self.method!r}, path={self.path!r})"
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import pytest
from genro_asgi.requests import Request

def make_receive(body: bytes = b"", more_body: bool = False):
    """Create a mock receive callable."""
    messages = [{"type": "http.request", "body": body, "more_body": more_body}]
    if more_body:
        messages.append({"type": "http.request", "body": b"", "more_body": False})

async def receive():
        return messages.pop(0)

def make_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    scheme: str = "http",
    server: tuple[str, int] | None = ("localhost", 8000),
    client: tuple[str, int] | None = ("127.0.0.1", 50000),
) -> dict:
    """Create a mock ASGI scope."""
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "scheme": scheme,
        "server": server,
        "client": client,
        "root_path": "",
    }

class TestRequestBasic:
    def test_method(self):
        scope = make_scope(method="POST")
        request = Request(scope, make_receive())
        assert request.method == "POST"

def test_path(self):
        scope = make_scope(path="/users/123")
        request = Request(scope, make_receive())
        assert request.path == "/users/123"

def test_scheme(self):
        scope = make_scope(scheme="https")
        request = Request(scope, make_receive())
        assert request.scheme == "https"

def test_client(self):
        scope = make_scope(client=("192.168.1.1", 12345))
        request = Request(scope, make_receive())
        assert request.client is not None
        assert request.client.host == "192.168.1.1"
        assert request.client.port == 12345

def test_client_none(self):
        scope = make_scope(client=None)
        request = Request(scope, make_receive())
        assert request.client is None

class TestRequestHeaders:
    def test_headers(self):
        headers = [(b"content-type", b"application/json"), (b"x-custom", b"value")]
        scope = make_scope(headers=headers)
        request = Request(scope, make_receive())
        assert request.headers.get("content-type") == "application/json"
        assert request.headers.get("x-custom") == "value"

def test_content_type(self):
        headers = [(b"content-type", b"text/html")]
        scope = make_scope(headers=headers)
        request = Request(scope, make_receive())
        assert request.content_type == "text/html"

class TestRequestQueryParams:
    def test_query_params(self):
        scope = make_scope(query_string=b"name=john&age=30")
        request = Request(scope, make_receive())
        assert request.query_params.get("name") == "john"
        assert request.query_params.get("age") == "30"

def test_query_params_empty(self):
        scope = make_scope(query_string=b"")
        request = Request(scope, make_receive())
        assert request.query_params.get("missing") is None

class TestRequestURL:
    def test_url_basic(self):
        scope = make_scope(path="/test", query_string=b"foo=bar")
        request = Request(scope, make_receive())
        assert request.url.path == "/test"
        assert request.url.query == "foo=bar"

def test_url_with_port(self):
        scope = make_scope(server=("example.com", 8080))
        request = Request(scope, make_receive())
        assert "8080" in str(request.url)

def test_url_default_port_http(self):
        scope = make_scope(scheme="http", server=("example.com", 80))
        request = Request(scope, make_receive())
        assert ":80" not in str(request.url)

class TestRequestBody:
    @pytest.mark.asyncio
    async def test_body(self):
        scope = make_scope(method="POST")
        receive = make_receive(body=b"hello world")
        request = Request(scope, receive)
        body = await request.body()
        assert body == b"hello world"

@pytest.mark.asyncio
    async def test_body_cached(self):
        scope = make_scope(method="POST")
        receive = make_receive(body=b"data")
        request = Request(scope, receive)
        body1 = await request.body()
        body2 = await request.body()
        assert body1 == body2 == b"data"

@pytest.mark.asyncio
    async def test_json(self):
        scope = make_scope(method="POST")
        receive = make_receive(body=b'{"key": "value"}')
        request = Request(scope, receive)
        data = await request.json()
        assert data == {"key": "value"}

@pytest.mark.asyncio
    async def test_json_cached(self):
        scope = make_scope(method="POST")
        receive = make_receive(body=b'{"a": 1}')
        request = Request(scope, receive)
        data1 = await request.json()
        data2 = await request.json()
        assert data1 == data2

@pytest.mark.asyncio
    async def test_json_invalid(self):
        scope = make_scope(method="POST")
        receive = make_receive(body=b"not json")
        request = Request(scope, receive)
        with pytest.raises(Exception):  # json.JSONDecodeError or orjson.JSONDecodeError
            await request.json()

@pytest.mark.asyncio
    async def test_form(self):
        scope = make_scope(method="POST")
        receive = make_receive(body=b"name=john&email=john%40example.com")
        request = Request(scope, receive)
        form = await request.form()
        assert form["name"] == "john"
        assert form["email"] == "john@example.com"

class TestRequestStream:
    @pytest.mark.asyncio
    async def test_stream(self):
        scope = make_scope(method="POST")

chunks = [
            {"type": "http.request", "body": b"chunk1", "more_body": True},
            {"type": "http.request", "body": b"chunk2", "more_body": True},
            {"type": "http.request", "body": b"chunk3", "more_body": False},
        ]

async def receive():
            return chunks.pop(0)

request = Request(scope, receive)
        received = []
        async for chunk in request.stream():
            received.append(chunk)

assert received == [b"chunk1", b"chunk2", b"chunk3"]

class TestRequestState:
    def test_state(self):
        scope = make_scope()
        request = Request(scope, make_receive())
        request.state.user_id = 123
        assert request.state.user_id == 123

def test_state_isolated(self):
        scope = make_scope()
        r1 = Request(scope, make_receive())
        r2 = Request(scope, make_receive())
        r1.state.value = "a"
        with pytest.raises(AttributeError):
            _ = r2.state.value

class TestRequestRepr:
    def test_repr(self):
        scope = make_scope(method="POST", path="/api/users")
        request = Request(scope, make_receive())
        r = repr(request)
        assert "POST" in r
        assert "/api/users" in r
```

```python
from .requests import Request
```

- [ ] Create `src/genro_asgi/requests.py`
- [ ] Create `tests/test_requests.py`
- [ ] Run `pytest tests/test_requests.py`
- [ ] Run `mypy src/genro_asgi/requests.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

