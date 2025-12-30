# Session Management

Sistema di sessioni lato server per utenti browser.

## Stato

❌ **NON IMPLEMENTATO** - Priorità P2 (Nice to have)

## Motivazione

- API stateless è il caso d'uso principale di genro-asgi
- Autenticazione gestita via token, non sessioni
- Focus su core functionality prima di sessioni

## Design Proposto

### SessionMiddleware

```python
class SessionMiddleware(BaseMiddleware):
    middleware_name = "session"
    middleware_order = 450  # Dopo auth
    middleware_default = False

    def __init__(
        self,
        app: ASGIApp,
        store: str = "memory",
        cookie_name: str = "session_id",
        max_age: int = 3600,
        secret: str = "",
        **kwargs,
    ): ...
```

### SessionStore Protocol

```python
class SessionStore(Protocol):
    async def load(self, session_id: str) -> Session | None: ...
    async def save(self, session: Session) -> None: ...
    async def delete(self, session_id: str) -> None: ...
    async def exists(self, session_id: str) -> bool: ...
```

### Implementazioni

- `MemorySessionStore` - In-memory (development only)
- `RedisSessionStore` - Redis backend (production)

### Session Class

```python
class Session:
    session_id: str
    modified: bool

    def __getitem__(self, key): ...
    def __setitem__(self, key, value): ...
    def get(self, key, default=None): ...
    def pop(self, key, default=None): ...
    def clear(self): ...
```

## Config YAML

```yaml
middleware:
  session: on

session_middleware:
  store: memory  # o redis
  cookie_name: "session_id"
  max_age: 3600
  secret: "your-secret-key"
```

## Accesso dalla Request

```python
session = request.session
session["user_id"] = 123
session["cart"] = ["item1", "item2"]
```

## Quando Implementare

**Utile per**:
- PageApplication (app web con browser)
- Login form (mantenere stato login)
- Wizard multi-step (stato tra pagine)
- Flash messages (messaggi one-time)

**Non necessario per**:
- API REST (stateless by design)
- M2M auth (usa token)
- SPA (gestisce stato client-side)

## Effort Stimato

~2 giorni totali
