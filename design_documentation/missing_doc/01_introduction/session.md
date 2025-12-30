## Source: plan_2025_12_29/4-session.md

**Stato**: ❌ NON IMPLEMENTATO
**Priorità**: P2 (Nice to have)
**Data**: 2025-12-29

Il documento originale proponeva un sistema di sessioni lato server per utenti browser:

1. **SessionMiddleware** - Middleware per gestire cookie session ID
2. **SessionStore** (Protocol) - Interface per storage sessioni
3. **MemorySessionStore** - Implementazione in-memory
4. **RedisSessionStore** - Implementazione con Redis
5. **Session** - Oggetto sessione con API dict-like

```python
# Accesso dalla request
session = request.session
session["user_id"] = 123
session["cart"] = ["item1", "item2"]

# O dall'app (via context)
session = self.session
```

```yaml
middleware:
  session: on

session_middleware:
  store: memory  # o redis
  cookie_name: "session_id"
  max_age: 3600
  secret: "your-secret-key"
```

**Non implementato**. Nessun codice presente.

1. **API stateless** - Il caso d'uso principale di genro-asgi sono API M2M stateless
2. **Token auth** - L'autenticazione è gestita via token, non sessioni
3. **Priorità** - Focus su core functionality prima di sessioni

```python
class SessionMiddleware(BaseMiddleware):
    """Session middleware - manages server-side sessions via cookies."""

middleware_name = "session"
    middleware_order = 450  # Dopo auth
    middleware_default = False

__slots__ = ("_store", "_cookie_name", "_max_age", "_secret")

def __init__(
        self,
        app: ASGIApp,
        store: str = "memory",
        cookie_name: str = "session_id",
        max_age: int = 3600,
        secret: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(app)
        self._cookie_name = cookie_name
        self._max_age = max_age
        self._secret = secret
        self._store = self._create_store(store, **kwargs)

def _create_store(self, store_type: str, **kwargs) -> SessionStore:
        if store_type == "memory":
            return MemorySessionStore(**kwargs)
        elif store_type == "redis":
            return RedisSessionStore(**kwargs)
        raise ValueError(f"Unknown session store: {store_type}")

async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

# Extract session ID from cookie
        session_id = self._get_session_id(scope)

# Load or create session
        if session_id:
            session = await self._store.load(session_id)
        else:
            session_id = self._generate_session_id()
            session = Session(session_id)

# Inject session into scope
        scope["session"] = session

# Wrap send to set cookie
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                if session.modified:
                    await self._store.save(session)
                    # Add Set-Cookie header
                    headers = list(message.get("headers", []))
                    cookie = self._make_session_cookie(session_id)
                    headers.append((b"set-cookie", cookie.encode()))
                    message["headers"] = headers
            await send(message)

await self.app(scope, receive, send_wrapper)
```

```python
from typing import Protocol

class SessionStore(Protocol):
    """Protocol for session storage backends."""

async def load(self, session_id: str) -> Session | None:
        """Load session by ID. Returns None if not found or expired."""
        ...

async def save(self, session: Session) -> None:
        """Save session to store."""
        ...

async def delete(self, session_id: str) -> None:
        """Delete session from store."""
        ...

async def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        ...
```

```python
class MemorySessionStore:
    """In-memory session store. For development only."""

def __init__(self, max_age: int = 3600) -> None:
        self._sessions: dict[str, tuple[Session, float]] = {}
        self._max_age = max_age

async def load(self, session_id: str) -> Session | None:
        if session_id not in self._sessions:
            return None
        session, created_at = self._sessions[session_id]
        if time.time() - created_at > self._max_age:
            del self._sessions[session_id]
            return None
        return session

async def save(self, session: Session) -> None:
        self._sessions[session.session_id] = (session, time.time())

async def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

async def exists(self, session_id: str) -> bool:
        return session_id in self._sessions
```

```python
class Session:
    """Server-side session with dict-like API."""

__slots__ = ("session_id", "_data", "_modified")

def __init__(self, session_id: str, data: dict | None = None) -> None:
        self.session_id = session_id
        self._data = data or {}
        self._modified = False

@property
    def modified(self) -> bool:
        return self._modified

def __getitem__(self, key: str) -> Any:
        return self._data[key]

def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._modified = True

def __delitem__(self, key: str) -> None:
        del self._data[key]
        self._modified = True

def __contains__(self, key: str) -> bool:
        return key in self._data

def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

def pop(self, key: str, default: Any = None) -> Any:
        self._modified = True
        return self._data.pop(key, default)

def clear(self) -> None:
        self._data.clear()
        self._modified = True

def keys(self):
        return self._data.keys()

def values(self):
        return self._data.values()

def items(self):
        return self._data.items()
```

```python
class HttpRequest(BaseRequest):
    @property
    def session(self) -> Session | None:
        """Server-side session (requires SessionMiddleware)."""
        return self._scope.get("session")
```

1. **SessionMiddleware** - Core middleware
2. **SessionStore implementations** - Memory, Redis
3. **Cookie handling** - Firma, expiry
4. **Request.session property** - Accesso lazy

Session è utile per:
- **PageApplication** - App web con browser
- **Login form** - Mantenere stato login
- **Wizard/multi-step** - Stato tra pagine
- **Flash messages** - Messaggi one-time

NON necessario per:
- **API REST** - Stateless by design
- **M2M auth** - Usa token
- **SPA** - Gestisce stato client-side

- **SessionMiddleware**: 4h
- **MemorySessionStore**: 2h
- **RedisSessionStore**: 4h
- **Cookie handling**: 2h
- **Tests**: 4h
- **Totale**: ~2 giorni

**Ultimo aggiornamento**: 2025-12-29

