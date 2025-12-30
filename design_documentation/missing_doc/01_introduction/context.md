## Source: plan_2025_12_29/3-context.md

**Stato**: ⚠️ ARCHITETTURA SEMPLIFICATA
**Data**: 2025-12-29

Il documento originale proponeva un sistema di context injection con:
- Classe `AsgiContext` separata
- Property su `AsgiApplication`: `request`, `response`, `auth`, `session`, `avatar`
- Context passato via scope ASGI
- Lazy evaluation delle property
- Supporto per testing con context mock

**Problema identificato**: Troppa complessità per il caso d'uso attuale.

Invece di un oggetto `AsgiContext` separato, l'informazione di contesto è distribuita su:

1. **Request properties** - `auth_tags`, `env_capabilities`
2. **ASGI scope** - `scope["auth"]`, `scope["auth_tags"]`
3. **ContextVar** - `get_current_request()` per accesso globale

```python
# middleware/authentication.py
class AuthMiddleware:
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            scope["auth"] = self._authenticate(scope)
            # auth contiene: {"tags": [...], "identity": "...", "backend": "..."}
        await self.app(scope, receive, send)
```

```python
# dispatcher.py
class Dispatcher:
    async def __call__(self, scope, receive, send):
        request = await self.request_registry.create(scope, receive, send)
        set_current_request(request)
        # ...
```

```python
# request.py
class HttpRequest(BaseRequest):
    async def init(self, scope, receive, send, **kwargs):
        # ...
        # Set auth_tags and env_capabilities from scope (set by middleware)
        self._auth_tags = list(scope.get("auth_tags", []))
        self._env_capabilities = list(scope.get("env_capabilities", []))
```

```python
# dispatcher.py
node = self.router.node(
    request.path,
    auth_tags=request.auth_tags,           # ← dal middleware via scope
    env_capabilities=request.env_capabilities,  # ← dal middleware via scope
    errors=ROUTER_ERRORS,
)
```

```python
@route()
def my_handler(self):
    request = self.server.request
    tags = request.auth_tags          # ['read', 'write']
    caps = request.env_capabilities   # ['has_jwt']
    # ...
```

```python
from genro_asgi.request import get_current_request

def utility_function():
    request = get_current_request()
    if request:
        print(request.path)
        print(request.auth_tags)
```

```python
class MyApp(AsgiApplication):
    @route()
    def handler(self):
        # Via server
        request = self.server.request
        response = self.server.response
        # ...
```

Quando AuthMiddleware autentica con successo:

```python
scope["auth"] = {
    "tags": ["read", "write"],      # Lista tag autorizzazione
    "identity": "user123",          # Identificativo utente/token
    "backend": "bearer"             # Tipo auth: bearer, basic, jwt:config_name
}
```

```python
scope["auth"] = None
```

```python
class BaseRequest(ABC):
    __slots__ = (
        "_auth_tags",
        "_env_capabilities",
        # ...
    )

@property
    def auth_tags(self) -> list[str]:
        """Auth tags (set from scope during init by AuthMiddleware)."""
        return self._auth_tags

@property
    def env_capabilities(self) -> list[str]:
        """Environment capabilities (set from scope during init)."""
        return self._env_capabilities
```

```python
class HttpRequest(BaseRequest):
    async def init(self, scope, receive, send, **kwargs):
        # ...
        self._auth_tags = list(scope.get("auth_tags", []))
        self._env_capabilities = list(scope.get("env_capabilities", []))
```

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Context object | `AsgiContext` classe | Non esiste |
| Auth access | `app.auth.tags` | `request.auth_tags` |
| Request access | `app.request` | `server.request` |
| Response access | `app.response` | `server.response` |
| Session | `app.session` | ❌ Non implementato |
| Avatar | `app.avatar` | ❌ Non implementato |

```python
# PIANO (non implementato)
class AsgiContext:
    def __init__(self, scope, receive, send):
        self._scope = scope
        # ...

@property
    def auth(self):
        return self._scope.get("auth")

class AsgiApplication:
    @property
    def request(self):
        return self._context.request
```

L'implementazione semplificata evita un livello di indirezione:

```python
# IMPLEMENTAZIONE
# auth_tags e env_capabilities direttamente sulla request
request.auth_tags
request.env_capabilities

# Accesso via server per retrocompatibilità
server.request
server.response
```

**Vantaggi**:
- Meno oggetti da gestire
- Path più diretto ai dati
- Più facile da capire
- Session/Avatar possono essere aggiunti in futuro se necessari

Tags automatici basati sull'ambiente/capabilities del server, non sull'utente.

```python
@route("root", auth_tags="superadmin&has_jwt")
def _create_jwt(self, ...):
    """Richiede tag superadmin E capability has_jwt."""
    pass
```

- `env_capabilities` è passato al router ✅
- Middleware può settare `scope["env_capabilities"]` ✅
- **NON c'è** un middleware che setta automaticamente `has_jwt` ⚠️

```python
# middleware/capabilities.py (DA IMPLEMENTARE)
class CapabilitiesMiddleware(BaseMiddleware):
    middleware_name = "capabilities"
    middleware_order = 150  # Prima di auth
    middleware_default = True

async def __call__(self, scope, receive, send):
        capabilities = []
        if HAS_JWT:
            capabilities.append("has_jwt")
        # Future: has_redis, has_celery, etc.
        scope["env_capabilities"] = capabilities
        await self.app(scope, receive, send)
```

```python
# request.py
_current_request: ContextVar["BaseRequest | None"] = ContextVar(
    "current_request", default=None
)

def get_current_request() -> "BaseRequest | None":
    """Get the current request from context. Returns None if not in request context."""
    return _current_request.get()

def set_current_request(request: "BaseRequest | None") -> Any:
    """Set the current request in context. Returns token for reset."""
    return _current_request.set(request)
```

```python
# dispatcher.py
async def __call__(self, scope, receive, send):
    request = await self.request_registry.create(scope, receive, send)
    set_current_request(request)      # ← setta ContextVar

try:
        # ... handle request
    finally:
        set_current_request(None)     # ← pulisce
        self.request_registry.unregister()
```

1. **Mockare scope** con auth_tags/env_capabilities
2. **Settare ContextVar** manualmente
3. **Creare request mock** con valori predefiniti

```python
# Esempio test
def test_with_auth():
    scope = {
        "type": "http",
        "auth_tags": ["admin"],
        "env_capabilities": ["has_jwt"],
        # ...
    }
    request = HttpRequest()
    await request.init(scope, receive, send)
    assert request.auth_tags == ["admin"]
```

**Ultimo aggiornamento**: 2025-12-29

