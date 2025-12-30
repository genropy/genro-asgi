# Datastructures

Strutture dati per request/response.

## Headers

```python
class Headers(Mapping[str, str]):
    """Immutable, case-insensitive headers mapping."""

    def __init__(self, raw_headers: list[tuple[bytes, bytes]] | None = None): ...

    def __getitem__(self, key: str) -> str: ...
    def __iter__(self) -> Iterator[str]: ...
    def __len__(self) -> int: ...
    def get(self, key: str, default: str | None = None) -> str | None: ...
    def getlist(self, key: str) -> list[str]: ...
```

Helper:
```python
def headers_from_scope(scope: Scope) -> Headers:
    return Headers(scope.get("headers", []))
```

## QueryParams

```python
class QueryParams(Mapping[str, str]):
    """Query string parameters (immutable)."""

    def __init__(self, query_string: bytes = b""): ...

    def __getitem__(self, key: str) -> str: ...  # First value
    def getlist(self, key: str) -> list[str]: ...  # All values
```

Helper:
```python
def query_params_from_scope(scope: Scope) -> QueryParams:
    return QueryParams(scope.get("query_string", b""))
```

## URL

```python
class URL:
    """Parsed URL with components."""

    scheme: str
    netloc: str
    path: str
    query: str
    fragment: str

    @property
    def hostname(self) -> str | None: ...
    @property
    def port(self) -> int | None: ...
```

## Address

```python
class Address(NamedTuple):
    """Client or server address."""
    host: str
    port: int
```

## State

```python
class State:
    """Mutable state container for request-scoped data."""

    def __setattr__(self, name: str, value: Any): ...
    def __getattr__(self, name: str) -> Any: ...
    def __delattr__(self, name: str): ...
```

## Decisioni

- **Headers case-insensitive** - Lookup con `.lower()`
- **Headers immutable** - Solo lettura dopo creazione
- **QueryParams first value** - `__getitem__` ritorna primo, `getlist` tutti
- **Helper functions** - `headers_from_scope()` invece di costruttore duale
- **State mutable** - Unico container mutabile, request-scoped
