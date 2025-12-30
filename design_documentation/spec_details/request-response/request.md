# Request

Wrapper HTTP request per ASGI scope.

## Classe

```python
class HttpRequest(BaseRequest):
    __slots__ = ("_scope", "_receive", "_body", "_json",
                 "_headers", "_query_params", "_url", "_state")

    def __init__(self, scope: Scope, receive: Receive): ...
```

## Properties Sincrone

| Property | Tipo | Descrizione |
|----------|------|-------------|
| `scope` | Scope | ASGI scope dict |
| `method` | str | HTTP method |
| `path` | str | Request path |
| `scheme` | str | http/https |
| `url` | URL | URL completa |
| `headers` | Headers | Headers (lazy) |
| `query_params` | QueryParams | Query params (lazy) |
| `client` | Address \| None | Client IP:port |
| `state` | State | Request-scoped data |
| `content_type` | str \| None | Content-Type header |

## Metodi Async

```python
async def body() -> bytes:
    """Legge e cache il body completo."""

async def stream() -> AsyncIterator[bytes]:
    """Itera chunks body (mutually exclusive con body())."""

async def json() -> Any:
    """Parse body come JSON (orjson se disponibile)."""

async def form() -> dict[str, Any]:
    """Parse application/x-www-form-urlencoded."""
```

## Lazy Loading

Headers e query_params sono creati al primo accesso:

```python
@property
def headers(self) -> Headers:
    if self._headers is None:
        self._headers = headers_from_scope(self._scope)
    return self._headers
```

## Decisioni

- **Lazy loading** - Headers/query_params creati on-demand
- **Body una volta** - `body()` e `stream()` mutualmente esclusivi
- **UTF-8 implicito** - Per `json()` e `form()`
- **orjson fallback** - Usa orjson se disponibile
- **Solo urlencoded** - `form()` non supporta multipart
- **File `request.py`** - Singolare, coerente con Starlette
