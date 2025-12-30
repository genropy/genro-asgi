# Missing Documentation - 01_introduction

Paragraphs present in source documents but not in specifications.

## Source: initial_specifications/dependencies/genro-routes.md

**Status**: 🟢 Verificato da README ufficiale
**Versione**: 0.9.0 (Beta)
**Documentazione**: https://genro-routes.readthedocs.io

**Instance-scoped routing engine** - espone metodi Python come "endpoint" senza blueprint globali o registri condivisi. Ogni istanza crea i propri router con stato isolato.

1. **Instance-scoped routers** - `Router(self, ...)` crea router con stato isolato per istanza
2. **@route decorator** - Registra metodi con nomi espliciti e metadata
3. **Gerarchie semplici** - `attach_instance(child, name="alias")` connette RoutingClass
4. **Plugin pipeline** - `BasePlugin` con hook `on_decore`/`wrap_handler`, ereditati dai parent
5. **Configurazione runtime** - `routedclass.configure()` per override globali o per-handler
6. **Extra opzionali** - Plugin logging, pydantic; core con dipendenze minime

| Concetto | Descrizione |
|----------|-------------|
| **Router** | Runtime router bound a un oggetto: `Router(self, name="api")` |
| **@route("name")** | Decorator che marca metodi per un router specifico |
| **RoutingClass** | Mixin che traccia router per istanza |
| **BasePlugin** | Base per plugin con hook `on_decore` e `wrap_handler` |
| **routedclass** | Proxy per gestire router/plugin senza inquinare il namespace |

```python
from genro_routes import RoutingClass, Router, route

class OrdersAPI(RoutingClass):
    def __init__(self, label: str):
        self.label = label
        self.api = Router(self, name="orders")

@route("orders")
    def list(self):
        return ["order-1", "order-2"]

@route("orders")
    def retrieve(self, ident: str):
        return f"{self.label}:{ident}"

orders = OrdersAPI("acme")
orders.api.get("list")()          # ["order-1", "order-2"]
orders.api.get("retrieve")("42")  # "acme:42"
```

```python
class UsersAPI(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")

@route("api")
    def list(self):
        return ["alice", "bob"]

class Application(RoutingClass):
    def __init__(self):
        self.api = Router(self, name="api")
        self.users = UsersAPI()
        self.api.attach_instance(self.users, name="users")

app = Application()
app.api.get("users/list")()  # ["alice", "bob"]
```

Plugin = middleware a livello di singolo metodo, configurabili a runtime.

- **Per-instance state**: ogni router ha istanze plugin indipendenti (no stato globale)
- **Due hook principali**: `on_decore()` (registrazione), `wrap_handler()` (esecuzione)
- **Ereditarietà**: plugin dei parent si applicano ai child router
- **Composizione**: più plugin lavorano insieme automaticamente

- **LoggingPlugin** (`"logging"`) - logging chiamate
- **PydanticPlugin** (`"pydantic"`) - validazione input/output con modelli Pydantic

```python
# Fluent API
self.api = Router(self, name="api").plug("logging").plug("pydantic")

# Con configurazione iniziale
self.api = Router(self, name="api").plug("logging", level="debug")
```

| Hook | Quando | Scopo |
|------|--------|-------|
| `configure()` | Init e runtime | Schema configurazione |
| `on_decore()` | Registrazione handler | Metadata, validazione signature |
| `wrap_handler()` | Invocazione handler | Middleware (logging, auth, cache) |
| `allow_entry()` | `members()` | Filtra handler visibili |
| `entry_metadata()` | `members()` | Aggiunge metadata plugin |

```python
from genro_routes.plugins._base_plugin import BasePlugin

class MyPlugin(BasePlugin):
    plugin_code = "my_plugin"           # Identificatore unico
    plugin_description = "Description"  # Descrizione

def __init__(self, router, **config):
        self.my_state = []              # Stato per-istanza
        super().__init__(router, **config)

def configure(self, enabled: bool = True, level: str = "info"):
        """Schema configurazione (body può essere vuoto)."""
        pass

def wrap_handler(self, router, entry, call_next):
        def wrapper(*args, **kwargs):
            # Before
            result = call_next(*args, **kwargs)
            # After
            return result
        return wrapper

# Registrazione globale
Router.register_plugin(MyPlugin)
```

Sintassi: `<router>:<plugin>/<selector>`

```python
# Globale - tutti gli handler
svc.routedclass.configure("api:logging/_all_", threshold=10)

# Per handler specifico
svc.routedclass.configure("api:logging/foo", enabled=False)

# Glob pattern
svc.routedclass.configure("api:logging/admin_*", level="debug")

# Batch update (JSON-friendly)
svc.routedclass.configure([
    {"target": "api:logging/_all_", "enabled": True},
    {"target": "api:logging/foo", "limit": 5},
])

# Introspection
info = svc.routedclass.configure("?")  # Albero completo
```

```python
# Via attributo router
svc.api.logging.configure(level="debug")
cfg = svc.api.logging.configuration("handler_name")
```

- **Solo metodi di istanza** - no static/class method, no funzioni libere
- **Plugin system minimale** - intenzionalmente semplice

```python
class AsgiServer(RoutingClass):
    def __init__(self):
        self.router = Router(self, name="root")

@route("root")
    def index(self):
        return HTMLResponse(...)

# Il Dispatcher converte path HTTP in selettore:
# /shop/products → selector = "shop/products" → router.get("shop/products")
```

Le app montate con `attach_instance(app, name="shop")` diventano sotto-alberi del router.

```
genro-routes/
├── src/genro_routes/
│   ├── core/               # Router, decorators, RoutingClass
│   │   ├── router.py
│   │   ├── decorators.py
│   │   └── routed.py
│   └── plugins/            # LoggingPlugin, PydanticPlugin
├── tests/                  # 99% coverage, 100 tests
├── docs/                   # Sphinx documentation
└── examples/
```

- `genro-toolbox>=0.1.0`
- `pydantic>=2.0.0`

- **Documentazione**: https://genro-routes.readthedocs.io
- **Repository**: https://github.com/genropy/genro-routes
- **Quick Start**: docs/quickstart.md
- **FAQ**: docs/FAQ.md

## Source: initial_specifications/guides/applications.md

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2025-12-13

Questa guida spiega come creare applicazioni per genro-asgi. Un'app è un modulo autocontenuto che può essere montato su `AsgiServer`.

```python
# myapp/app.py
from genro_asgi import AsgiApplication
from genro_routes import route

class MyApp(AsgiApplication):
    @route("index")
    def index(self):
        return {"message": "Hello from MyApp!"}

@route("hello/:name")
    def hello(self, name: str):
        return {"message": f"Hello, {name}!"}
```

```yaml
# config.yaml
apps:
  myapp:
    module: "myapp.app:MyApp"
```

L'app risponde a:
- `GET /myapp/index` → `{"message": "Hello from MyApp!"}`
- `GET /myapp/hello/world` → `{"message": "Hello, world!"}`

```
myapp/
├── __init__.py
├── app.py
└── config.yaml
```

```
myapp/
├── __init__.py
├── app.py
├── config.yaml
├── middleware/
│   └── auth.py
└── plugins/
    └── cache.py
```

Ogni app può avere un proprio `config.yaml`:

# Settings passed to app constructor
setting1: "value1"
setting2: 42

# App-specific middleware
middleware:
  - type: "compression"
    level: 6

# App-specific plugins
plugins:
  - "myapp.plugins.cache:CachePlugin"
```

```python
class MyApp(AsgiApplication):
    def __init__(self, setting1: str, setting2: int = 10):
        self.setting1 = setting1
        self.setting2 = setting2
```

I valori da `config.yaml` vengono passati automaticamente al costruttore.

```yaml
apps:
  api:
    module: "myapp.app:MyApp"
    setting1: "inline_value"
```

```yaml
apps:
  api:
    path: "./myapp"
```

Con path reference, genro-asgi:
1. Cerca `./myapp/config.yaml`
2. Importa l'app da `./myapp/__init__.py` o `./myapp/app.py`
3. Passa i parametri dal config.yaml

Le app possono avere middleware propri che si applicano solo alle richieste per quell'app.

```yaml
# myapp/config.yaml
middleware:
  - type: "compression"
    level: 6
  - type: "cache"
    max_age: 3600
```

```python
# myapp/middleware/auth.py
class AuthMiddleware:
    def __init__(self, app, secret_key: str):
        self.app = app
        self.secret_key = secret_key

async def __call__(self, scope, receive, send):
        # Check auth...
        await self.app(scope, receive, send)
```

```yaml
# myapp/config.yaml
middleware:
  - module: "myapp.middleware.auth:AuthMiddleware"
    secret_key: "my-secret"
```

I plugin estendono le funzionalità dell'app.

```python
# myapp/plugins/cache.py
class CachePlugin:
    def __init__(self, app, ttl: int = 300):
        self.app = app
        self.ttl = ttl
        self.cache = {}

def get(self, key):
        return self.cache.get(key)

def set(self, key, value):
        self.cache[key] = value
```

```yaml
# myapp/config.yaml
plugins:
  - module: "myapp.plugins.cache:CachePlugin"
    ttl: 600
```

Usa l'app built-in `StaticSite`:

```yaml
apps:
  docs:
    module: "genro_asgi:StaticSite"
    directory: "./public"
    name: "docs"
```

```python
# api/app.py
from genro_asgi import AsgiApplication
from genro_routes import route

class ApiApp(AsgiApplication):
    def __init__(self, db_url: str):
        self.db_url = db_url

@route("users")
    async def list_users(self):
        # ...
        return {"users": [...]}

@route("users/:id")
    async def get_user(self, id: int):
        # ...
        return {"user": {...}}
```

```yaml
apps:
  api:
    module: "api.app:ApiApp"
    db_url: "postgresql://localhost/mydb"
```

```python
# shop/app.py
from genro_asgi import AsgiApplication
from genro_routes import route

class ShopApp(AsgiApplication):
    def __init__(self, stripe_key: str):
        self.stripe_key = stripe_key
        self.stripe = None  # Initialized on startup

async def on_startup(self):
        """Called when server starts."""
        import stripe
        stripe.api_key = self.stripe_key
        self.stripe = stripe

async def on_shutdown(self):
        """Called when server stops."""
        # Cleanup...
        pass
```

Ogni app dovrebbe avere una singola responsabilità.

```yaml
# Good: separate apps
apps:
  api: "api:ApiApp"
  admin: "admin:AdminApp"
  docs: "genro_asgi:StaticSite"

# Bad: monolithic app
apps:
  everything: "monolith:EverythingApp"
```

Non hardcodare valori nell'app.

```python
# Good
class MyApp(AsgiApplication):
    def __init__(self, api_key: str):
        self.api_key = api_key

# Bad
class MyApp(AsgiApplication):
    def __init__(self):
        self.api_key = "hardcoded-key"
```

```yaml
# myapp/config.yaml
middleware:
  - type: "auth"  # Only for this app
```

Il prefix dell'app (nome nel config) è automatico. I tuoi routes sono relativi.

```python
@route("users")  # Becomes /myapp/users
def list_users(self):
    pass
```

- [Architecture: Applications](../architecture/applications.md) - Dettagli tecnici
- [Configuration](../interview/answers/E-configuration.md) - Sistema di configurazione
- [Routing](../interview/answers/D-routing.md) - Come funziona il routing

## Source: initial_specifications/interview/answers/M-resources.md

**A:** Framework internal resources go in `src/genro_asgi/resources/` with subfolders by type. User application static files are separate.

```
src/genro_asgi/
├── resources/           # Framework internal assets
│   ├── html/           # HTML templates
│   │   └── default_index.html
│   ├── css/            # Stylesheets
│   └── js/             # JavaScript
└── ...
```

| Resource Type | Location | Example |
|---------------|----------|---------|
| Framework default pages | `resources/html/` | `default_index.html` |
| Framework CSS | `resources/css/` | Error page styles |
| Framework JS | `resources/js/` | Client utilities |
| Framework logos/images | `resources/images/` | Logo for default page |
| **User app static files** | User's `app_dir` | Served via `StaticSite` |

**Framework resources** (`resources/`):

- Internal to genro-asgi package
- Default pages (welcome, error pages)
- Loaded via `Path(__file__).parent / "resources"`
- NOT served directly to users (embedded in responses)

**User static files** (`StaticSite`):

- External to package
- User's HTML, CSS, JS, images
- Served via HTTP from user's directory
- Configured in `config.yaml`

```python
# In server.py - reading framework resource
from pathlib import Path

@route("root")
def index(self) -> Response:
    html_path = Path(__file__).parent / "resources" / "html" / "default_index.html"
    return HTMLResponse(content=html_path.read_text())
```

- `resources/` is for framework internal assets only
- Subfolders: `html/`, `css/`, `js/`, `images/` as needed
- Resources are read from disk, not served via HTTP
- User static files use `StaticSite` application
- Clean separation: framework resources vs user content

## Source: initial_specifications/interview/answers/N-cli.md

**Come si avvia genro-asgi da riga di comando?**

- C'è un comando CLI?
- Come funziona `python -m genro_asgi`?

genro-asgi offre due modi per avviare il server da CLI:

1. **Comando installato** (definito in pyproject.toml):
   ```bash
   genro-asgi serve ./myapp --port 9000
   ```

2. **Via python -m**:
   ```bash
   python -m genro_asgi serve ./myapp --port 9000
   ```

Il file `__main__.py` è un file speciale Python che permette di eseguire un package come script.
Quando esegui `python -m <package>`, Python cerca ed esegue `<package>/__main__.py`.

```bash
# Avvia server
genro-asgi serve <app_dir> [options]

# Mostra versione
genro-asgi --version
genro-asgi -v

# Mostra help
genro-asgi --help
genro-asgi -h
```

| Opzione | Default | Descrizione |
|---------|---------|-------------|
| `--host HOST` | 127.0.0.1 | Host del server |
| `--port PORT` | 8000 | Porta del server |
| `--reload` | false | Abilita auto-reload (development) |

```bash
# Avvia in development mode con auto-reload
genro-asgi serve ./my_app --port 8080 --reload

# Output:
# genro-asgi starting...
# App dir: ./my_app
# Server: http://127.0.0.1:8080
# Mode: development (auto-reload enabled)
```

```toml
[project.scripts]
genro-asgi = "genro_asgi.__main__:main"
```

La directory app deve contenere un file di configurazione:
- `config.yaml` oppure
- `genro-asgi.yaml`

- [\_\_main\_\_.py](../../../src/genro_asgi/__main__.py) - Entry point CLI
- [pyproject.toml](../../../pyproject.toml) - Definizione script

## Source: initial_specifications/interview/answers/C-request-lifecycle.md

**Date**: 2025-12-13
**Status**: Verified

There is a **logical request** (`BaseRequest`) that materializes into:

- `HttpRequest` - native HTTP request (ASGI scope)
- `WsxRequest` - pseudo-request from WSX message (WebSocket/NATS)

The handler always sees `BaseRequest` with a uniform interface.

```text
1. Request arrives (HTTP/WS/NATS)
   │
2. Request creation (HttpRequest or WsxRequest)
   │  - Server generates internal ID (UUID)
   │  - request.server = reference to server (dual relationship)
   │
3. Registration in RequestRegistry
   │  - registry[request.id] = request
   │
4. Dispatch to handler (via Router)
   │
5. Handler processes, produces Response
   │
6. Send Response
   │  - For WS/NATS: response carries the same correlation ID from client (if present in data)
   │
7. De-registration from RequestRegistry
   │  - del registry[request.id]
```

- **`request.id`**: Internal ID generated by server (UUID), used by registry
- **Client ID** (optional): if client sends a correlation ID, it travels in request data, not as registry ID

- In registry → in progress
- Out of registry → completed

Additional info (timestamp, duration, etc.) obtained by querying the request itself.

1. **Load snapshot**: know what the server is processing in real time
2. **Request ID as global identifier**: key for correlating logging, cache, metrics
3. **WS/NATS correlation**: associate response with pending request
4. **Lifecycle**: manage timeout, cancellation

## Source: initial_specifications/interview/answers/F-transport.md

**genro-tytx** handles all data serialization between client and server.

It solves the fundamental problem: JSON loses types (Decimal becomes string, Date becomes string).

| Python | JavaScript | Wire Format |
|--------|------------|-------------|
| `Decimal` | `Big` (big.js) | `"99.99::N"` |
| `date` | `Date` (midnight UTC) | `"2025-01-15::D"` |
| `datetime` | `Date` | `"2025-01-15T10:30:00.000Z::DHZ"` |
| `time` | `Date` (epoch date) | `"10:30:00.000::H"` |

Native JSON types pass through unchanged.

| Transport | Content-Type | Use Case |
|-----------|--------------|----------|
| JSON | `application/vnd.tytx+json` | Default, debugging |
| MessagePack | `application/vnd.tytx+msgpack` | Performance |
| XML | `application/vnd.tytx+xml` | Legacy systems |

**Auto-detection from Content-Type header.**

Client chooses transport:
```javascript
// JSON (default)
await fetchTytx('/api/order', { body: data });

// MessagePack
await fetchTytx('/api/order', { body: data, transport: 'msgpack' });
```

Server auto-detects and responds with same transport.
**No code changes needed in handlers.**

Dispatcher uses `asgi_data()` to extract typed parameters:

```python
async def dispatch(self, scope, receive, send):
    # Auto-detects transport, decodes to Python types
    data = await asgi_data(scope, receive)

# params are Decimal, date, etc. - NOT strings
    result = await handler(**data['body'])

# Response uses same transport
    await self.send_response(result, data['transport'], send)
```

Response uses `to_tytx()` to encode typed results:

```python
async def send_response(self, result, transport, send):
    body = to_tytx(result, transport)
    content_type = f'application/vnd.tytx+{transport}'
    # ... send ASGI response
```

For high-frequency operations (live grids, real-time updates):

1. **Smaller payload**: ~30-50% smaller than JSON
2. **Faster parsing**: binary, no string parsing
3. **Same API**: just change `transport` parameter
4. **Transparent**: handlers don't know or care

**Without TYTX** (20 manual conversions):

```python
# Receive: string → Decimal
unit_price = Decimal(json_data['unit_price'])

# Send: Decimal → string
return {'total': str(result['total'])}
```

```javascript
// Send: Big → string
body: { unit_price: orderData.unit_price.toString() }

// Receive: string → Big
const total = new Big(json.total);
```

```python
# Receive: already Decimal
data = await asgi_data(scope, receive)
unit_price = data['body']['unit_price']  # Decimal

# Send: just return
return {'total': total}  # Decimal preserved
```

```javascript
// Send: just pass types
await fetchTytx('/api', { body: { unit_price: new Big('99.99') } });

// Receive: already Big
result.total  // Big, ready to use
```

| Function | Input | Output | Used by |
|----------|-------|--------|---------|
| `asgi_data(scope, receive)` | ASGI request | `{body: dict, transport: str}` | Dispatcher |
| `to_tytx(data, transport)` | Python dict | Wire format (str/bytes) | Response |

- **genro-tytx** (Python): `pip install genro-tytx`
- **genro-tytx** (JavaScript): `npm install genro-tytx`
- **big.js** (JavaScript): recommended for Decimal

## Source: initial_implementation_plan/archive/12-wsx-subscriptions.md

**Status**: DA REVISIONARE
**Dependencies**: 10-wsx-core, 11-wsx-handler
**Commit message**: `feat(wsx): add SubscriptionManager for channel-based pub/sub`

Subscription manager for channel-based pub/sub over WSX.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX subscription manager for channel-based pub/sub."""

import asyncio
from typing import Any, Callable, Awaitable
from weakref import WeakSet

# Type for send function
SendFunc = Callable[[dict[str, Any]], Awaitable[None]]

class Subscription:
    """
    A single subscription to a channel.

Tracks the subscriber's send function and any filter parameters.
    """

__slots__ = ("channel", "send_func", "params", "id")

def __init__(
        self,
        channel: str,
        send_func: SendFunc,
        params: dict[str, Any] | None = None,
        subscription_id: str | None = None,
    ) -> None:
        """
        Initialize subscription.

Args:
            channel: Channel name
            send_func: Async function to send messages to subscriber
            params: Filter parameters for the subscription
            subscription_id: Unique ID for this subscription
        """
        self.channel = channel
        self.send_func = send_func
        self.params = params or {}
        self.id = subscription_id

async def send(self, payload: Any, meta: dict[str, Any] | None = None) -> bool:
        """
        Send event to subscriber.

Args:
            payload: Event payload
            meta: Optional metadata

Returns:
            True if sent successfully, False otherwise
        """
        event = WSXEvent(
            channel=self.channel,
            payload=payload,
            meta=meta or {},
        )
        if self.id:
            event.meta["sub_id"] = self.id

try:
            await self.send_func(event.to_dict())
            return True
        except Exception:
            return False

class SubscriptionManager:
    """
    Manages channel subscriptions for pub/sub.

Thread-safe subscription management with support for:
    - Multiple subscribers per channel
    - Wildcard channel patterns (future)
    - Subscription parameters/filters
    - Automatic cleanup on disconnect

Example:
        manager = SubscriptionManager()

# Subscribe a client
        sub_id = manager.subscribe(
            channel="user.updates",
            send_func=websocket.send_json,
            params={"user_id": 123},
        )

# Publish to channel
        await manager.publish("user.updates", {"status": "online"})

# Unsubscribe
        manager.unsubscribe(sub_id)
    """

def __init__(self) -> None:
        """Initialize subscription manager."""
        self._subscriptions: dict[str, list[Subscription]] = {}
        self._by_id: dict[str, Subscription] = {}
        self._counter = 0
        self._lock = asyncio.Lock()

def subscribe(
        self,
        channel: str,
        send_func: SendFunc,
        params: dict[str, Any] | None = None,
        subscription_id: str | None = None,
    ) -> str:
        """
        Subscribe to a channel.

Args:
            channel: Channel name to subscribe to
            send_func: Async function to send messages
            params: Optional filter parameters
            subscription_id: Optional custom ID (auto-generated if None)

Returns:
            Subscription ID
        """
        if subscription_id is None:
            self._counter += 1
            subscription_id = f"sub-{self._counter}"

sub = Subscription(
            channel=channel,
            send_func=send_func,
            params=params,
            subscription_id=subscription_id,
        )

if channel not in self._subscriptions:
            self._subscriptions[channel] = []

self._subscriptions[channel].append(sub)
        self._by_id[subscription_id] = sub

def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe by subscription ID.

Args:
            subscription_id: ID returned from subscribe()

Returns:
            True if unsubscribed, False if not found
        """
        sub = self._by_id.pop(subscription_id, None)
        if sub is None:
            return False

channel_subs = self._subscriptions.get(sub.channel, [])
        try:
            channel_subs.remove(sub)
        except ValueError:
            pass

# Clean up empty channel
        if not channel_subs and sub.channel in self._subscriptions:
            del self._subscriptions[sub.channel]

def unsubscribe_all(self, send_func: SendFunc) -> int:
        """
        Unsubscribe all subscriptions for a send function.

Useful for cleanup when a WebSocket disconnects.

Args:
            send_func: The send function to remove

Returns:
            Number of subscriptions removed
        """
        removed = 0
        to_remove: list[str] = []

for sub_id, sub in self._by_id.items():
            if sub.send_func is send_func:
                to_remove.append(sub_id)

for sub_id in to_remove:
            if self.unsubscribe(sub_id):
                removed += 1

async def publish(
        self,
        channel: str,
        payload: Any,
        meta: dict[str, Any] | None = None,
        filter_func: Callable[[Subscription, Any], bool] | None = None,
    ) -> int:
        """
        Publish event to all subscribers of a channel.

Args:
            channel: Channel to publish to
            payload: Event payload
            meta: Optional metadata
            filter_func: Optional function to filter subscribers

Returns:
            Number of subscribers notified
        """
        subs = self._subscriptions.get(channel, [])
        if not subs:
            return 0

sent = 0
        failed: list[Subscription] = []

for sub in subs:
            # Apply filter if provided
            if filter_func and not filter_func(sub, payload):
                continue

success = await sub.send(payload, meta)
            if success:
                sent += 1
            else:
                failed.append(sub)

# Clean up failed subscriptions
        for sub in failed:
            if sub.id:
                self.unsubscribe(sub.id)

async def broadcast(
        self,
        payload: Any,
        meta: dict[str, Any] | None = None,
        channels: list[str] | None = None,
    ) -> int:
        """
        Broadcast event to multiple channels.

Args:
            payload: Event payload
            meta: Optional metadata
            channels: Channels to broadcast to (all if None)

Returns:
            Total number of subscribers notified
        """
        target_channels = channels or list(self._subscriptions.keys())
        total = 0

for channel in target_channels:
            count = await self.publish(channel, payload, meta)
            total += count

def get_subscribers(self, channel: str) -> list[Subscription]:
        """
        Get all subscribers for a channel.

Args:
            channel: Channel name

Returns:
            List of subscriptions
        """
        return list(self._subscriptions.get(channel, []))

def get_channels(self) -> list[str]:
        """
        Get all active channels.

Returns:
            List of channel names with subscribers
        """
        return list(self._subscriptions.keys())

def count(self, channel: str | None = None) -> int:
        """
        Count subscriptions.

Args:
            channel: Specific channel (all if None)

Returns:
            Number of subscriptions
        """
        if channel:
            return len(self._subscriptions.get(channel, []))
        return len(self._by_id)

def clear(self) -> None:
        """Remove all subscriptions."""
        self._subscriptions.clear()
        self._by_id.clear()

class ChannelDispatcher(SubscriptionManager):
    """
    Extended subscription manager with dispatcher integration.

Integrates with WSXDispatcher to handle subscribe/unsubscribe messages.

Example:
        channels = ChannelDispatcher()
        dispatcher = WSXDispatcher()

# Register channel handlers
        channels.register_with_dispatcher(dispatcher)

# In handler
        async def ws_handler(websocket: WebSocket):
            handler = WSXHandler(websocket, dispatcher)
            handler.on_disconnect = lambda: channels.unsubscribe_all(websocket.send_json)
            await handler.run()
    """

def __init__(self) -> None:
        super().__init__()
        self._channel_validators: dict[str, Callable[[dict], bool]] = {}

def validate_channel(
        self, channel: str
    ) -> Callable[[Callable[[dict], bool]], Callable[[dict], bool]]:
        """
        Decorator to register a channel validator.

The validator receives subscription params and returns True if valid.

Example:
            @channels.validate_channel("user.updates")
            def validate_user_sub(params: dict) -> bool:
                return "user_id" in params
        """
        def decorator(func: Callable[[dict], bool]) -> Callable[[dict], bool]:
            self._channel_validators[channel] = func
            return func
        return decorator

def can_subscribe(self, channel: str, params: dict[str, Any]) -> bool:
        """
        Check if subscription is allowed.

Args:
            channel: Channel name
            params: Subscription parameters

Returns:
            True if subscription is allowed
        """
        validator = self._channel_validators.get(channel)
        if validator:
            return validator(params)
        return True  # Allow by default

def register_with_dispatcher(self, dispatcher: "WSXDispatcher") -> None:
        """
        Register handlers with a WSX dispatcher.

Args:
            dispatcher: WSX dispatcher instance
        """
        from .dispatcher import WSXDispatcher

# Override dispatcher's subscribe/unsubscribe handlers
        original_subscribe = dispatcher._handle_subscribe
        original_unsubscribe = dispatcher._handle_unsubscribe

async def handle_subscribe(subscribe):
            if not self.can_subscribe(subscribe.channel, subscribe.params):
                from .types import WSXError
                return WSXError(
                    id=subscribe.id,
                    code="SUBSCRIPTION_DENIED",
                    message=f"Cannot subscribe to channel: {subscribe.channel}",
                )

# The send_func will be set by the handler
            # For now, just validate
            return await original_subscribe(subscribe)

dispatcher._handle_subscribe = handle_subscribe
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for WSX subscriptions."""

import pytest
from genro_asgi.wsx.subscriptions import (
    ChannelDispatcher,
    Subscription,
    SubscriptionManager,
)

class TestSubscription:
    @pytest.mark.asyncio
    async def test_send(self):
        sent = []

async def send_func(data):
            sent.append(data)

sub = Subscription(
            channel="test",
            send_func=send_func,
            subscription_id="sub-1",
        )

result = await sub.send({"key": "value"})

assert result is True
        assert len(sent) == 1
        assert sent[0]["type"] == "rpc.event"
        assert sent[0]["channel"] == "test"
        assert sent[0]["payload"] == {"key": "value"}
        assert sent[0]["meta"]["sub_id"] == "sub-1"

@pytest.mark.asyncio
    async def test_send_failure(self):
        async def failing_send(data):
            raise Exception("Send failed")

sub = Subscription(
            channel="test",
            send_func=failing_send,
        )

result = await sub.send({"data": 1})

class TestSubscriptionManager:
    def test_subscribe(self):
        manager = SubscriptionManager()

async def send(data):
            pass

sub_id = manager.subscribe("channel1", send)

assert sub_id.startswith("sub-")
        assert manager.count("channel1") == 1

def test_subscribe_custom_id(self):
        manager = SubscriptionManager()

async def send(data):
            pass

sub_id = manager.subscribe("channel1", send, subscription_id="custom-id")

def test_unsubscribe(self):
        manager = SubscriptionManager()

async def send(data):
            pass

sub_id = manager.subscribe("channel1", send)
        result = manager.unsubscribe(sub_id)

assert result is True
        assert manager.count("channel1") == 0

def test_unsubscribe_not_found(self):
        manager = SubscriptionManager()

result = manager.unsubscribe("nonexistent")

def test_unsubscribe_all(self):
        manager = SubscriptionManager()

async def send1(data):
            pass

async def send2(data):
            pass

manager.subscribe("channel1", send1)
        manager.subscribe("channel2", send1)
        manager.subscribe("channel1", send2)

removed = manager.unsubscribe_all(send1)

assert removed == 2
        assert manager.count() == 1

@pytest.mark.asyncio
    async def test_publish(self):
        manager = SubscriptionManager()
        received = []

async def send(data):
            received.append(data)

manager.subscribe("updates", send)
        manager.subscribe("updates", send)

count = await manager.publish("updates", {"msg": "hello"})

assert count == 2
        assert len(received) == 2

@pytest.mark.asyncio
    async def test_publish_empty_channel(self):
        manager = SubscriptionManager()

count = await manager.publish("empty", {"data": 1})

@pytest.mark.asyncio
    async def test_publish_with_filter(self):
        manager = SubscriptionManager()
        received = []

async def send(data):
            received.append(data)

manager.subscribe("users", send, params={"user_id": 1})
        manager.subscribe("users", send, params={"user_id": 2})

def filter_user(sub, payload):
            return sub.params.get("user_id") == payload.get("target_user")

count = await manager.publish(
            "users",
            {"target_user": 1, "msg": "hello"},
            filter_func=filter_user,
        )

assert count == 1
        assert len(received) == 1

@pytest.mark.asyncio
    async def test_broadcast(self):
        manager = SubscriptionManager()
        received = []

async def send(data):
            received.append(data)

manager.subscribe("channel1", send)
        manager.subscribe("channel2", send)
        manager.subscribe("channel3", send)

count = await manager.broadcast({"msg": "broadcast"})

assert count == 3
        assert len(received) == 3

@pytest.mark.asyncio
    async def test_broadcast_specific_channels(self):
        manager = SubscriptionManager()
        received = []

async def send(data):
            received.append(data)

manager.subscribe("channel1", send)
        manager.subscribe("channel2", send)
        manager.subscribe("channel3", send)

count = await manager.broadcast(
            {"msg": "partial"},
            channels=["channel1", "channel2"],
        )

def test_get_subscribers(self):
        manager = SubscriptionManager()

async def send(data):
            pass

manager.subscribe("test", send, params={"a": 1})
        manager.subscribe("test", send, params={"b": 2})

subs = manager.get_subscribers("test")

def test_get_channels(self):
        manager = SubscriptionManager()

async def send(data):
            pass

manager.subscribe("channel1", send)
        manager.subscribe("channel2", send)
        manager.subscribe("channel1", send)

channels = manager.get_channels()

assert set(channels) == {"channel1", "channel2"}

def test_count(self):
        manager = SubscriptionManager()

async def send(data):
            pass

manager.subscribe("a", send)
        manager.subscribe("a", send)
        manager.subscribe("b", send)

assert manager.count() == 3
        assert manager.count("a") == 2
        assert manager.count("b") == 1
        assert manager.count("c") == 0

def test_clear(self):
        manager = SubscriptionManager()

async def send(data):
            pass

manager.subscribe("a", send)
        manager.subscribe("b", send)

assert manager.count() == 0
        assert manager.get_channels() == []

class TestChannelDispatcher:
    def test_validate_channel_decorator(self):
        channels = ChannelDispatcher()

@channels.validate_channel("private")
        def validate(params):
            return "token" in params

assert channels.can_subscribe("private", {"token": "abc"}) is True
        assert channels.can_subscribe("private", {}) is False

def test_can_subscribe_default(self):
        channels = ChannelDispatcher()

# No validator = allow all
        assert channels.can_subscribe("any", {}) is True
```

Add to exports:
```python
from .subscriptions import ChannelDispatcher, Subscription, SubscriptionManager
```

- [ ] Create `src/genro_asgi/wsx/subscriptions.py`
- [ ] Create `tests/test_wsx_subscriptions.py`
- [ ] Run `pytest tests/test_wsx_subscriptions.py`
- [ ] Run `mypy src/genro_asgi/wsx/subscriptions.py`
- [ ] Update `wsx/__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/05-responses.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types, 02-datastructures
**Commit message**: `feat(responses): add Response classes (JSON, HTML, Streaming, Redirect)`

HTTP Response classes for sending data back to clients.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import json
from typing import Any, AsyncIterator, Mapping

from .types import Receive, Scope, Send

# Optional fast JSON
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

class Response:
    """
    Base HTTP Response.

Sends bytes content with headers and status code.

Example:
        response = Response(content=b"Hello", status_code=200)
        await response(scope, receive, send)
    """

media_type: str | None = None
    charset: str = "utf-8"

def __init__(
        self,
        content: bytes | str | None = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        """
        Initialize response.

Args:
            content: Response body (bytes or str)
            status_code: HTTP status code
            headers: Response headers
            media_type: Content-Type (overrides class default)
        """
        self.status_code = status_code
        self._headers: dict[str, str] = dict(headers) if headers else {}

if media_type is not None:
            self.media_type = media_type

self.body = self._encode_content(content)

# Set content-type if not already set
        if "content-type" not in {k.lower() for k in self._headers}:
            content_type = self._get_content_type()
            if content_type:
                self._headers["content-type"] = content_type

def _encode_content(self, content: bytes | str | None) -> bytes:
        """Encode content to bytes."""
        if content is None:
            return b""
        if isinstance(content, bytes):
            return content
        return content.encode(self.charset)

def _get_content_type(self) -> str | None:
        """Get content-type header value."""
        if self.media_type is None:
            return None
        if self.media_type.startswith("text/") and "charset" not in self.media_type:
            return f"{self.media_type}; charset={self.charset}"
        return self.media_type

def _build_headers(self) -> list[tuple[bytes, bytes]]:
        """Build ASGI header list."""
        return [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in self._headers.items()
        ]

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - send the response."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })
        await send({
            "type": "http.response.body",
            "body": self.body,
        })

class JSONResponse(Response):
    """
    JSON Response.

Serializes Python objects to JSON.
    Uses orjson if available for better performance.

Example:
        return JSONResponse({"status": "ok", "data": [1, 2, 3]})
    """

media_type = "application/json"

def __init__(
        self,
        content: Any = None,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """
        Initialize JSON response.

Args:
            content: Python object to serialize as JSON
            status_code: HTTP status code
            headers: Response headers
        """
        # Serialize to JSON bytes
        if HAS_ORJSON:
            body = orjson.dumps(content)
        else:
            body = json.dumps(content, ensure_ascii=False).encode("utf-8")

super().__init__(
            content=body,
            status_code=status_code,
            headers=headers,
            media_type=self.media_type,
        )

class HTMLResponse(Response):
    """
    HTML Response.

Example:
        return HTMLResponse("<h1>Hello World</h1>")
    """

class PlainTextResponse(Response):
    """
    Plain Text Response.

Example:
        return PlainTextResponse("Hello, World!")
    """

class RedirectResponse(Response):
    """
    HTTP Redirect Response.

Example:
        return RedirectResponse("/new-location")
        return RedirectResponse("/login", status_code=303)
    """

def __init__(
        self,
        url: str,
        status_code: int = 307,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """
        Initialize redirect response.

Args:
            url: Redirect target URL
            status_code: HTTP status code (301, 302, 303, 307, 308)
            headers: Additional response headers
        """
        _headers = dict(headers) if headers else {}
        _headers["location"] = url
        super().__init__(
            content=b"",
            status_code=status_code,
            headers=_headers,
        )

class StreamingResponse(Response):
    """
    Streaming Response.

Sends response body from an async iterator.

Example:
        async def generate():
            for i in range(10):
                yield f"chunk {i}\n".encode()

return StreamingResponse(generate())
    """

def __init__(
        self,
        content: AsyncIterator[bytes],
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
    ) -> None:
        """
        Initialize streaming response.

Args:
            content: Async iterator yielding bytes chunks
            status_code: HTTP status code
            headers: Response headers
            media_type: Content-Type header
        """
        self.body_iterator = content
        self.status_code = status_code
        self._headers = dict(headers) if headers else {}

if media_type is not None:
            self.media_type = media_type

if self.media_type and "content-type" not in {k.lower() for k in self._headers}:
            self._headers["content-type"] = self.media_type

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - stream the response."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })

async for chunk in self.body_iterator:
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

class FileResponse(Response):
    """
    File Download Response.

Example:
        return FileResponse("/path/to/file.pdf")
        return FileResponse("/path/to/file.pdf", filename="document.pdf")
    """

def __init__(
        self,
        path: str,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
        media_type: str | None = None,
        filename: str | None = None,
        chunk_size: int = 64 * 1024,
    ) -> None:
        """
        Initialize file response.

Args:
            path: Path to file on disk
            status_code: HTTP status code
            headers: Response headers
            media_type: Content-Type (auto-detected if None)
            filename: Download filename (for Content-Disposition)
            chunk_size: Size of chunks to read (default 64KB)
        """
        import mimetypes
        from pathlib import Path

self.path = Path(path)
        self.chunk_size = chunk_size
        self.status_code = status_code
        self._headers = dict(headers) if headers else {}

# Auto-detect media type
        if media_type is None:
            media_type, _ = mimetypes.guess_type(str(self.path))
        self.media_type = media_type or "application/octet-stream"

if "content-type" not in {k.lower() for k in self._headers}:
            self._headers["content-type"] = self.media_type

# Set content-disposition for download
        if filename:
            self._headers["content-disposition"] = f'attachment; filename="{filename}"'

# Set content-length if file exists
        if self.path.exists():
            self._headers["content-length"] = str(self.path.stat().st_size)

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface - stream the file."""
        await send({
            "type": "http.response.start",
            "status": self.status_code,
            "headers": self._build_headers(),
        })

# Stream file in chunks
        with open(self.path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                more_body = len(chunk) == self.chunk_size
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": more_body,
                })
                if not more_body:
                    break
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for Response classes."""

import pytest
from genro_asgi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

class MockSend:
    """Capture sent messages."""

def __init__(self):
        self.messages = []

async def __call__(self, message):
        self.messages.append(message)

@pytest.fixture
def send():
    return MockSend()

@pytest.fixture
def scope():
    return {"type": "http"}

async def receive():
    return {"type": "http.request", "body": b""}

class TestResponse:
    @pytest.mark.asyncio
    async def test_basic(self, scope, send):
        response = Response(content=b"Hello", status_code=200)
        await response(scope, receive, send)

assert len(send.messages) == 2
        assert send.messages[0]["type"] == "http.response.start"
        assert send.messages[0]["status"] == 200
        assert send.messages[1]["type"] == "http.response.body"
        assert send.messages[1]["body"] == b"Hello"

@pytest.mark.asyncio
    async def test_string_content(self, scope, send):
        response = Response(content="Hello", status_code=200)
        await response(scope, receive, send)
        assert send.messages[1]["body"] == b"Hello"

@pytest.mark.asyncio
    async def test_custom_headers(self, scope, send):
        response = Response(
            content=b"",
            headers={"X-Custom": "value"},
        )
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"x-custom"] == b"value"

@pytest.mark.asyncio
    async def test_media_type(self, scope, send):
        response = Response(content=b"", media_type="application/xml")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"application/xml"

class TestJSONResponse:
    @pytest.mark.asyncio
    async def test_dict(self, scope, send):
        response = JSONResponse({"key": "value"})
        await response(scope, receive, send)

body = send.messages[1]["body"]
        assert b"key" in body
        assert b"value" in body

@pytest.mark.asyncio
    async def test_list(self, scope, send):
        response = JSONResponse([1, 2, 3])
        await response(scope, receive, send)

body = send.messages[1]["body"]
        assert body in (b"[1,2,3]", b"[1, 2, 3]")

@pytest.mark.asyncio
    async def test_content_type(self, scope, send):
        response = JSONResponse({})
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"application/json"

@pytest.mark.asyncio
    async def test_status_code(self, scope, send):
        response = JSONResponse({"error": "not found"}, status_code=404)
        await response(scope, receive, send)
        assert send.messages[0]["status"] == 404

class TestHTMLResponse:
    @pytest.mark.asyncio
    async def test_basic(self, scope, send):
        response = HTMLResponse("<h1>Hello</h1>")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert b"text/html" in headers[b"content-type"]
        assert send.messages[1]["body"] == b"<h1>Hello</h1>"

class TestPlainTextResponse:
    @pytest.mark.asyncio
    async def test_basic(self, scope, send):
        response = PlainTextResponse("Hello, World!")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert b"text/plain" in headers[b"content-type"]

class TestRedirectResponse:
    @pytest.mark.asyncio
    async def test_redirect(self, scope, send):
        response = RedirectResponse("/new-location")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"location"] == b"/new-location"
        assert send.messages[0]["status"] == 307

@pytest.mark.asyncio
    async def test_redirect_303(self, scope, send):
        response = RedirectResponse("/login", status_code=303)
        await response(scope, receive, send)
        assert send.messages[0]["status"] == 303

class TestStreamingResponse:
    @pytest.mark.asyncio
    async def test_streaming(self, scope, send):
        async def generate():
            yield b"chunk1"
            yield b"chunk2"
            yield b"chunk3"

response = StreamingResponse(generate())
        await response(scope, receive, send)

# Start + 3 chunks + final empty
        assert send.messages[0]["type"] == "http.response.start"
        assert send.messages[1]["body"] == b"chunk1"
        assert send.messages[2]["body"] == b"chunk2"
        assert send.messages[3]["body"] == b"chunk3"
        assert send.messages[4]["body"] == b""
        assert send.messages[4]["more_body"] is False

@pytest.mark.asyncio
    async def test_media_type(self, scope, send):
        async def generate():
            yield b"data"

response = StreamingResponse(generate(), media_type="text/event-stream")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-type"] == b"text/event-stream"

class TestFileResponse:
    @pytest.mark.asyncio
    async def test_file(self, scope, send, tmp_path):
        # Create temp file
        file_path = tmp_path / "test.txt"
        file_path.write_text("Hello from file")

response = FileResponse(str(file_path))
        await response(scope, receive, send)

# Collect body chunks
        body = b"".join(
            msg["body"] for msg in send.messages if msg["type"] == "http.response.body"
        )
        assert body == b"Hello from file"

@pytest.mark.asyncio
    async def test_filename(self, scope, send, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

response = FileResponse(str(file_path), filename="download.txt")
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert b"attachment" in headers[b"content-disposition"]
        assert b"download.txt" in headers[b"content-disposition"]

@pytest.mark.asyncio
    async def test_content_length(self, scope, send, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.write_text("12345")

response = FileResponse(str(file_path))
        await response(scope, receive, send)

headers = dict(send.messages[0]["headers"])
        assert headers[b"content-length"] == b"5"
```

```python
from .responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
```

- [ ] Create `src/genro_asgi/responses.py`
- [ ] Create `tests/test_responses.py`
- [ ] Run `pytest tests/test_responses.py`
- [ ] Run `mypy src/genro_asgi/responses.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/07-lifespan.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types
**Commit message**: `feat(lifespan): add Lifespan event handler`

ASGI Lifespan event handling for startup/shutdown hooks.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ASGI Lifespan event handling."""

from typing import Awaitable, Callable

from .types import Receive, Scope, Send

# Type aliases for handlers
LifespanHandler = Callable[[], Awaitable[None]]

class Lifespan:
    """
    ASGI Lifespan event manager.

Manages application startup and shutdown events.

Example:
        lifespan = Lifespan()

@lifespan.on_startup
        async def startup():
            print("Starting up...")
            app.state.db = await create_db_pool()

@lifespan.on_shutdown
        async def shutdown():
            print("Shutting down...")
            await app.state.db.close()

app = App(handler=my_handler, lifespan=lifespan)
    """

__slots__ = ("_startup_handlers", "_shutdown_handlers")

def __init__(self) -> None:
        """Initialize lifespan manager."""
        self._startup_handlers: list[LifespanHandler] = []
        self._shutdown_handlers: list[LifespanHandler] = []

def on_startup(self, func: LifespanHandler) -> LifespanHandler:
        """
        Register a startup handler.

Args:
            func: Async function to call on startup

Returns:
            The registered function (for use as decorator)
        """
        self._startup_handlers.append(func)
        return func

def on_shutdown(self, func: LifespanHandler) -> LifespanHandler:
        """
        Register a shutdown handler.

Args:
            func: Async function to call on shutdown

Returns:
            The registered function (for use as decorator)
        """
        self._shutdown_handlers.append(func)
        return func

def add_startup_handler(self, func: LifespanHandler) -> None:
        """
        Add a startup handler (non-decorator form).

Args:
            func: Async function to call on startup
        """
        self._startup_handlers.append(func)

def add_shutdown_handler(self, func: LifespanHandler) -> None:
        """
        Add a shutdown handler (non-decorator form).

Args:
            func: Async function to call on shutdown
        """
        self._shutdown_handlers.append(func)

async def run_startup(self) -> None:
        """
        Run all startup handlers in registration order.

Raises:
            Exception: Re-raises any exception from handlers
        """
        for handler in self._startup_handlers:
            await handler()

async def run_shutdown(self) -> None:
        """
        Run all shutdown handlers in reverse registration order.

Continues even if a handler raises, collecting all errors.
        """
        errors: list[Exception] = []
        for handler in reversed(self._shutdown_handlers):
            try:
                await handler()
            except Exception as e:
                errors.append(e)

if errors:
            # Log errors but don't prevent shutdown
            # In production, these should be logged properly
            pass

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        ASGI lifespan interface.

Handles lifespan.startup and lifespan.shutdown events.

Args:
            scope: ASGI lifespan scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        started = False
        try:
            while True:
                message = await receive()
                message_type = message["type"]

if message_type == "lifespan.startup":
                    try:
                        await self.run_startup()
                        await send({"type": "lifespan.startup.complete"})
                        started = True
                    except Exception as exc:
                        await send({
                            "type": "lifespan.startup.failed",
                            "message": str(exc),
                        })
                        raise

elif message_type == "lifespan.shutdown":
                    try:
                        await self.run_shutdown()
                        await send({"type": "lifespan.shutdown.complete"})
                    except Exception as exc:
                        await send({
                            "type": "lifespan.shutdown.failed",
                            "message": str(exc),
                        })
                        raise
                    return

except Exception:
            # If startup failed, still try to run shutdown handlers
            if started:
                await self.run_shutdown()
            raise

class LifespanContext:
    """
    Context manager style lifespan.

Alternative API using async context manager pattern.

Example:
        @contextmanager
        async def lifespan(app):
            # Startup
            app.state.db = await create_db_pool()
            yield
            # Shutdown
            await app.state.db.close()
    """

def __init__(
        self,
        context_func: Callable[..., Awaitable[None]],
    ) -> None:
        """
        Initialize with async context manager function.

Args:
            context_func: Async generator function
        """
        self._context_func = context_func

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI lifespan interface."""
        # This is a simplified version - full implementation would
        # properly handle the async context manager protocol
        lifespan = Lifespan()

@lifespan.on_startup
        async def startup():
            pass  # Context manager handles this

@lifespan.on_shutdown
        async def shutdown():
            pass  # Context manager handles this

await lifespan(scope, receive, send)
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for Lifespan handling."""

import pytest
from genro_asgi.lifespan import Lifespan

class MockTransport:
    """Mock ASGI transport for lifespan testing."""

def __init__(self, messages: list[dict]):
        self.incoming = messages
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

class TestLifespanHandlers:
    def test_on_startup_decorator(self):
        lifespan = Lifespan()
        called = []

@lifespan.on_startup
        async def startup():
            called.append("startup")

assert len(lifespan._startup_handlers) == 1

def test_on_shutdown_decorator(self):
        lifespan = Lifespan()

@lifespan.on_shutdown
        async def shutdown():
            pass

assert len(lifespan._shutdown_handlers) == 1

def test_add_startup_handler(self):
        lifespan = Lifespan()

async def handler():
            pass

lifespan.add_startup_handler(handler)
        assert handler in lifespan._startup_handlers

def test_add_shutdown_handler(self):
        lifespan = Lifespan()

async def handler():
            pass

lifespan.add_shutdown_handler(handler)
        assert handler in lifespan._shutdown_handlers

class TestRunHandlers:
    @pytest.mark.asyncio
    async def test_run_startup(self):
        lifespan = Lifespan()
        order = []

@lifespan.on_startup
        async def first():
            order.append(1)

@lifespan.on_startup
        async def second():
            order.append(2)

await lifespan.run_startup()
        assert order == [1, 2]

@pytest.mark.asyncio
    async def test_run_shutdown_reverse_order(self):
        lifespan = Lifespan()
        order = []

@lifespan.on_shutdown
        async def first():
            order.append(1)

@lifespan.on_shutdown
        async def second():
            order.append(2)

await lifespan.run_shutdown()
        # Shutdown runs in reverse order
        assert order == [2, 1]

@pytest.mark.asyncio
    async def test_startup_error_propagates(self):
        lifespan = Lifespan()

@lifespan.on_startup
        async def failing():
            raise ValueError("Startup failed")

with pytest.raises(ValueError, match="Startup failed"):
            await lifespan.run_startup()

@pytest.mark.asyncio
    async def test_shutdown_continues_on_error(self):
        lifespan = Lifespan()
        called = []

@lifespan.on_shutdown
        async def first():
            called.append(1)

@lifespan.on_shutdown
        async def failing():
            raise ValueError("Error")

@lifespan.on_shutdown
        async def third():
            called.append(3)

await lifespan.run_shutdown()
        # All handlers should be called despite error
        assert 1 in called
        assert 3 in called

class TestLifespanASGI:
    @pytest.mark.asyncio
    async def test_full_lifespan(self):
        lifespan = Lifespan()
        events = []

@lifespan.on_startup
        async def startup():
            events.append("startup")

@lifespan.on_shutdown
        async def shutdown():
            events.append("shutdown")

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert events == ["startup", "shutdown"]
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"

@pytest.mark.asyncio
    async def test_startup_failure(self):
        lifespan = Lifespan()

@lifespan.on_startup
        async def failing():
            raise ValueError("Failed")

transport = MockTransport([
            {"type": "lifespan.startup"},
        ])

with pytest.raises(ValueError):
            await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert transport.outgoing[0]["type"] == "lifespan.startup.failed"
        assert "Failed" in transport.outgoing[0]["message"]

@pytest.mark.asyncio
    async def test_shutdown_failure(self):
        lifespan = Lifespan()
        events = []

@lifespan.on_startup
        async def startup():
            events.append("startup")

@lifespan.on_shutdown
        async def failing():
            raise ValueError("Shutdown failed")

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

with pytest.raises(ValueError):
            await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert "startup" in events
        assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.failed"

class TestLifespanEmpty:
    @pytest.mark.asyncio
    async def test_no_handlers(self):
        lifespan = Lifespan()

transport = MockTransport([
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ])

await lifespan({"type": "lifespan"}, transport.receive, transport.send)

assert transport.outgoing[0]["type"] == "lifespan.startup.complete"
        assert transport.outgoing[1]["type"] == "lifespan.shutdown.complete"
```

```python
from .lifespan import Lifespan
```

- [ ] Create `src/genro_asgi/lifespan.py`
- [ ] Create `tests/test_lifespan.py`
- [ ] Run `pytest tests/test_lifespan.py`
- [ ] Run `mypy src/genro_asgi/lifespan.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/11-wsx-handler.md

**Status**: DA REVISIONARE
**Dependencies**: 06-websockets, 10-wsx-core
**Commit message**: `feat(wsx): add WSXHandler for WebSocket connection management`

High-level handler that manages a WSX WebSocket connection, integrating the dispatcher with the WebSocket transport.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WSX WebSocket connection handler."""

import asyncio
from typing import Any

from ..exceptions import WebSocketDisconnect
from ..websockets import WebSocket
from .dispatcher import WSXDispatcher
from .types import WSXMessage

class WSXHandler:
    """
    WSX WebSocket connection handler.

Manages the lifecycle of a WSX WebSocket connection:
    - Accepts the connection
    - Receives messages and dispatches them
    - Sends responses back
    - Handles ping/pong keepalive
    - Manages graceful shutdown

Example - Standalone:
        async def ws_endpoint(websocket: WebSocket):
            dispatcher = WSXDispatcher()

@dispatcher.method("echo")
            async def echo(msg: str):
                return msg

handler = WSXHandler(websocket, dispatcher)
            await handler.run()

Example - With SmartRoute:
        async def ws_endpoint(websocket: WebSocket):
            dispatcher = WSXDispatcher(router=my_smartrouter)
            handler = WSXHandler(websocket, dispatcher)
            await handler.run()

Example - With App:
        dispatcher = WSXDispatcher(router=router)

async def ws_handler(websocket: WebSocket):
            handler = WSXHandler(websocket, dispatcher)
            await handler.run()

app = App(
            handler=http_handler,
            websocket_handler=ws_handler,
        )
    """

def __init__(
        self,
        websocket: WebSocket,
        dispatcher: WSXDispatcher,
        *,
        ping_interval: float | None = 30.0,
        ping_timeout: float | None = 10.0,
    ) -> None:
        """
        Initialize WSX handler.

Args:
            websocket: WebSocket connection
            dispatcher: WSX message dispatcher
            ping_interval: Seconds between pings (None to disable)
            ping_timeout: Seconds to wait for pong (None for no timeout)
        """
        self.websocket = websocket
        self.dispatcher = dispatcher
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self._running = False
        self._last_pong = 0.0

async def run(self, subprotocol: str | None = None) -> None:
        """
        Run the WSX handler.

Accepts the WebSocket, then processes messages until disconnect.

Args:
            subprotocol: Optional subprotocol to accept
        """
        await self.websocket.accept(subprotocol=subprotocol)
        self._running = True

try:
            if self.ping_interval:
                # Run receiver and ping loop concurrently
                await asyncio.gather(
                    self._receive_loop(),
                    self._ping_loop(),
                )
            else:
                await self._receive_loop()
        except WebSocketDisconnect:
            pass
        finally:
            self._running = False

async def _receive_loop(self) -> None:
        """Main receive loop."""
        async for message in self.websocket:
            if isinstance(message, str):
                await self._handle_text(message)
            elif isinstance(message, bytes):
                await self._handle_bytes(message)

async def _handle_text(self, text: str) -> None:
        """Handle incoming text message."""
        import json

try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            await self._send_error(None, "PARSE_ERROR", f"Invalid JSON: {e}")
            return

await self._dispatch_and_respond(data)

async def _handle_bytes(self, data: bytes) -> None:
        """Handle incoming binary message."""
        import json

try:
            text = data.decode("utf-8")
            parsed = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            await self._send_error(None, "PARSE_ERROR", f"Invalid message: {e}")
            return

await self._dispatch_and_respond(parsed)

async def _dispatch_and_respond(self, data: dict[str, Any]) -> None:
        """Dispatch message and send response if any."""
        # Track pong for keepalive
        if data.get("type") == "rpc.pong":
            self._last_pong = asyncio.get_event_loop().time()
            return

response = await self.dispatcher.dispatch(data)

if response is not None:
            await self.websocket.send_json(response.to_dict())

async def _send_error(
        self, msg_id: str | None, code: str, message: str
    ) -> None:
        """Send error response."""
        from .types import WSXError

error = WSXError(id=msg_id, code=code, message=message)
        await self.websocket.send_json(error.to_dict())

async def _ping_loop(self) -> None:
        """Ping loop for keepalive."""
        while self._running:
            await asyncio.sleep(self.ping_interval or 30.0)

if not self._running:
                break

# Send ping
            await self.websocket.send_json({"type": "rpc.ping"})

async def send_event(
        self, channel: str, payload: Any, meta: dict[str, Any] | None = None
    ) -> None:
        """
        Send an event to the client.

Args:
            channel: Event channel name
            payload: Event data
            meta: Optional metadata
        """
        from .types import WSXEvent

event = WSXEvent(channel=channel, payload=payload, meta=meta or {})
        await self.websocket.send_json(event.to_dict())

async def send_notify(
        self, event: str, payload: Any, meta: dict[str, Any] | None = None
    ) -> None:
        """
        Send a notification to the client.

Args:
            event: Event name
            payload: Event data
            meta: Optional metadata
        """
        from .types import WSXNotify

notify = WSXNotify(event=event, payload=payload, meta=meta or {})
        await self.websocket.send_json(notify.to_dict())

async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the WebSocket connection.

Args:
            code: Close code
            reason: Close reason
        """
        self._running = False
        await self.websocket.close(code=code, reason=reason)

def create_wsx_handler(
    dispatcher: WSXDispatcher,
    **kwargs: Any,
) -> "WSXHandlerFactory":
    """
    Create a WSX handler factory.

Returns a callable that creates WSXHandler instances for each connection.

Example:
        dispatcher = WSXDispatcher(router=router)
        ws_handler = create_wsx_handler(dispatcher)

app = App(
            handler=http_handler,
            websocket_handler=ws_handler,
        )
    """
    async def handler(websocket: WebSocket) -> None:
        wsx = WSXHandler(websocket, dispatcher, **kwargs)
        await wsx.run()

# Type alias for clarity
WSXHandlerFactory = Any  # Actually Callable[[WebSocket], Awaitable[None]]
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

import pytest
from genro_asgi.websockets import WebSocket, WebSocketState
from genro_asgi.wsx import WSXDispatcher
from genro_asgi.wsx.handler import WSXHandler, create_wsx_handler

class MockTransport:
    """Mock WebSocket transport for testing."""

def __init__(self, messages: list[dict] | None = None):
        self.incoming = [json.dumps(m) for m in (messages or [])]
        self.outgoing: list[dict] = []
        self._accepted = False

async def receive(self) -> dict:
        if not self.incoming:
            return {"type": "websocket.disconnect", "code": 1000}
        return {"type": "websocket.receive", "text": self.incoming.pop(0)}

async def send(self, message: dict) -> None:
        if message["type"] == "websocket.accept":
            self._accepted = True
        elif message["type"] == "websocket.send":
            if "text" in message:
                self.outgoing.append(json.loads(message["text"]))

def make_websocket(messages: list[dict] | None = None) -> tuple[WebSocket, MockTransport]:
    """Create WebSocket with mock transport."""
    transport = MockTransport(messages)
    scope = {
        "type": "websocket",
        "path": "/ws",
        "query_string": b"",
        "headers": [],
        "server": ("localhost", 8000),
        "client": ("127.0.0.1", 50000),
        "root_path": "",
        "subprotocols": [],
    }
    ws = WebSocket(scope, transport.receive, transport.send)
    return ws, transport

class TestWSXHandler:
    @pytest.mark.asyncio
    async def test_basic_rpc(self):
        dispatcher = WSXDispatcher()

@dispatcher.method("echo")
        async def echo(message: str):
            return {"echo": message}

ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "echo", "params": {"message": "hello"}}
        ])

handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

assert len(transport.outgoing) == 1
        assert transport.outgoing[0]["type"] == "rpc.response"
        assert transport.outgoing[0]["result"] == {"echo": "hello"}

@pytest.mark.asyncio
    async def test_multiple_requests(self):
        dispatcher = WSXDispatcher()

@dispatcher.method("add")
        async def add(a: int, b: int):
            return a + b

ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "add", "params": {"a": 1, "b": 2}},
            {"type": "rpc.request", "id": "2", "method": "add", "params": {"a": 10, "b": 20}},
        ])

handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

assert len(transport.outgoing) == 2
        assert transport.outgoing[0]["result"] == 3
        assert transport.outgoing[1]["result"] == 30

@pytest.mark.asyncio
    async def test_method_not_found(self):
        dispatcher = WSXDispatcher()

ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "nonexistent", "params": {}}
        ])

handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

assert transport.outgoing[0]["type"] == "rpc.error"
        assert transport.outgoing[0]["error"]["code"] == "METHOD_NOT_FOUND"

@pytest.mark.asyncio
    async def test_invalid_json(self):
        transport = MockTransport()
        transport.incoming = ["not valid json"]

scope = {
            "type": "websocket",
            "path": "/ws",
            "query_string": b"",
            "headers": [],
            "server": ("localhost", 8000),
            "client": ("127.0.0.1", 50000),
            "root_path": "",
            "subprotocols": [],
        }
        ws = WebSocket(scope, transport.receive, transport.send)

dispatcher = WSXDispatcher()
        handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

assert transport.outgoing[0]["type"] == "rpc.error"
        assert transport.outgoing[0]["error"]["code"] == "PARSE_ERROR"

@pytest.mark.asyncio
    async def test_notification_no_response(self):
        dispatcher = WSXDispatcher()
        notifications = []

@dispatcher.on_notify
        async def handle(notify):
            notifications.append(notify)

ws, transport = make_websocket([
            {"type": "rpc.notify", "method": "log", "params": {"level": "info"}}
        ])

handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

# Notifications don't generate responses
        assert len(transport.outgoing) == 0
        assert len(notifications) == 1

@pytest.mark.asyncio
    async def test_ping_pong(self):
        dispatcher = WSXDispatcher()

ws, transport = make_websocket([
            {"type": "rpc.ping"}
        ])

handler = WSXHandler(ws, dispatcher, ping_interval=None)
        await handler.run()

assert transport.outgoing[0]["type"] == "rpc.pong"

@pytest.mark.asyncio
    async def test_send_event(self):
        dispatcher = WSXDispatcher()

ws, transport = make_websocket([])

handler = WSXHandler(ws, dispatcher, ping_interval=None)

# Accept manually for this test
        await ws.accept()

await handler.send_event("user.created", {"id": 1, "name": "John"})

assert transport.outgoing[0]["type"] == "rpc.event"
        assert transport.outgoing[0]["channel"] == "user.created"
        assert transport.outgoing[0]["payload"] == {"id": 1, "name": "John"}

@pytest.mark.asyncio
    async def test_send_notify(self):
        dispatcher = WSXDispatcher()

ws, transport = make_websocket([])

handler = WSXHandler(ws, dispatcher, ping_interval=None)

await handler.send_notify("status.changed", {"status": "online"})

assert transport.outgoing[0]["type"] == "rpc.notify"
        assert transport.outgoing[0]["event"] == "status.changed"

class TestCreateWSXHandler:
    @pytest.mark.asyncio
    async def test_factory(self):
        dispatcher = WSXDispatcher()

@dispatcher.method("test")
        async def test_method():
            return "ok"

handler_func = create_wsx_handler(dispatcher, ping_interval=None)

ws, transport = make_websocket([
            {"type": "rpc.request", "id": "1", "method": "test", "params": {}}
        ])

assert transport.outgoing[0]["result"] == "ok"
```

- [ ] Create `src/genro_asgi/wsx/handler.py`
- [ ] Create `tests/test_wsx_handler.py`
- [ ] Run `pytest tests/test_wsx_handler.py`
- [ ] Run `mypy src/genro_asgi/wsx/handler.py`
- [ ] Update `wsx/__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/01-types.md

**Status**: DA REVISIONARE
**Dependencies**: None
**Commit message**: `feat(types): add ASGI type definitions`

Define ASGI type aliases for type safety throughout the codebase.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

from typing import Any, Awaitable, Callable, MutableMapping

# ASGI Scope - connection metadata
Scope = MutableMapping[str, Any]

# ASGI Message - sent/received data
Message = MutableMapping[str, Any]

# ASGI Receive - callable to receive messages
Receive = Callable[[], Awaitable[Message]]

# ASGI Send - callable to send messages
Send = Callable[[Message], Awaitable[None]]

# ASGI Application - the main callable
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for ASGI type definitions."""

from genro_asgi.types import ASGIApp, Message, Receive, Scope, Send

def test_types_importable():
    """Verify all types are importable."""
    assert Scope is not None
    assert Message is not None
    assert Receive is not None
    assert Send is not None
    assert ASGIApp is not None

def test_scope_is_mutable_mapping():
    """Scope should accept dict-like objects."""
    scope: Scope = {"type": "http", "method": "GET"}
    scope["path"] = "/"
    assert scope["type"] == "http"

def test_message_is_mutable_mapping():
    """Message should accept dict-like objects."""
    message: Message = {"type": "http.request", "body": b""}
    assert message["type"] == "http.request"
```

```python
from .types import ASGIApp, Message, Receive, Scope, Send
```

- [ ] Create `src/genro_asgi/types.py`
- [ ] Create `tests/test_types.py`
- [ ] Run `pytest tests/test_types.py`
- [ ] Run `mypy src/genro_asgi/types.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/08b-executor.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types.py, 07-lifespan.py

The Executor provides a unified execution subsystem for running:
- **Blocking tasks** in a ThreadPoolExecutor (sync I/O, legacy libraries)
- **CPU-bound tasks** in a ProcessPoolExecutor (heavy computation)

This is a key differentiator from Starlette, which does not include integrated execution pools.

```python
# Access via application
result = await app.executor.run_blocking(func, *args, **kwargs)
result = await app.executor.run_process(func, *args, **kwargs)

# Or standalone
from genro_asgi import Executor

executor = Executor()
await executor.startup()
result = await executor.run_blocking(sync_function, arg1, arg2)
await executor.shutdown()
```

**File**: `src/genro_asgi/executor.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Unified execution subsystem for blocking and CPU-bound tasks."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from functools import partial
from typing import Any, Callable, TypeVar

class Executor:
    """Unified executor for blocking and CPU-bound tasks.

Provides two execution pools:
    - ThreadPoolExecutor for blocking I/O operations
    - ProcessPoolExecutor for CPU-intensive work

Example:
        executor = Executor(max_threads=10, max_processes=4)
        await executor.startup()

# Run blocking I/O
        result = await executor.run_blocking(sync_db_query, "SELECT ...")

# Run CPU-bound work
        result = await executor.run_process(heavy_computation, data)

await executor.shutdown()
    """

def __init__(
        self,
        max_threads: int = 40,
        max_processes: int | None = None,
    ) -> None:
        """Initialize the executor.

Args:
            max_threads: Maximum threads for blocking tasks. Default 40.
            max_processes: Maximum processes for CPU tasks. Default is CPU count.
        """
        self._max_threads = max_threads
        self._max_processes = max_processes
        self._thread_pool: ThreadPoolExecutor | None = None
        self._process_pool: ProcessPoolExecutor | None = None
        self._started = False

@property
    def is_running(self) -> bool:
        """Check if executor is running."""
        return self._started

async def startup(self) -> None:
        """Start the execution pools.

Called automatically during application lifespan startup.
        """
        if self._started:
            return

self._thread_pool = ThreadPoolExecutor(
            max_workers=self._max_threads,
            thread_name_prefix="genro_blocking_"
        )
        self._process_pool = ProcessPoolExecutor(
            max_workers=self._max_processes
        )
        self._started = True

async def shutdown(self, wait: bool = True) -> None:
        """Shutdown the execution pools.

Args:
            wait: If True, wait for pending tasks to complete.

Called automatically during application lifespan shutdown.
        """
        if not self._started:
            return

if self._thread_pool:
            self._thread_pool.shutdown(wait=wait)
            self._thread_pool = None

if self._process_pool:
            self._process_pool.shutdown(wait=wait)
            self._process_pool = None

async def run_blocking(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run a blocking function in the thread pool.

Use for:
        - Legacy database drivers (non-async)
        - File system operations
        - Blocking network calls
        - Synchronous library compatibility

Args:
            func: Synchronous callable to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

Returns:
            The result of func(*args, **kwargs).

Raises:
            RuntimeError: If executor is not started.
            Exception: Any exception raised by func.

Example:
            def read_file(path):
                with open(path) as f:
                    return f.read()

content = await executor.run_blocking(read_file, "/path/to/file")
        """
        if not self._started or self._thread_pool is None:
            raise RuntimeError("Executor not started. Call startup() first.")

loop = asyncio.get_running_loop()

if kwargs:
            func = partial(func, **kwargs)

return await loop.run_in_executor(self._thread_pool, func, *args)

async def run_process(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run a CPU-bound function in the process pool.

Use for:
        - Heavy data processing
        - Image/audio transformation
        - Compression or hashing
        - Numerical computation

Note: func must be picklable (top-level function, not lambda/closure).

Args:
            func: Picklable callable to execute.
            *args: Positional arguments for func.
            **kwargs: Keyword arguments for func.

Returns:
            The result of func(*args, **kwargs).

Raises:
            RuntimeError: If executor is not started.
            Exception: Any exception raised by func.

Example:
            def compress_data(data):
                import zlib
                return zlib.compress(data)

compressed = await executor.run_process(compress_data, large_data)
        """
        if not self._started or self._process_pool is None:
            raise RuntimeError("Executor not started. Call startup() first.")

loop = asyncio.get_running_loop()

if kwargs:
            func = partial(func, **kwargs)

return await loop.run_in_executor(self._process_pool, func, *args)

# Default executor instance (optional, for simple use cases)
_default_executor: Executor | None = None

def get_executor() -> Executor:
    """Get the default executor instance.

Creates one if it doesn't exist. For most applications,
    use app.executor instead.
    """
    global _default_executor
    if _default_executor is None:
        _default_executor = Executor()
    return _default_executor
```

**File**: `tests/test_executor.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for the Executor module."""

import asyncio
import time
import pytest

from genro_asgi.executor import Executor, get_executor

class TestExecutor:
    """Tests for Executor class."""

@pytest.fixture
    async def executor(self):
        """Provide a started executor."""
        ex = Executor(max_threads=4, max_processes=2)
        await ex.startup()
        yield ex
        await ex.shutdown()

async def test_startup_shutdown(self):
        """Test executor lifecycle."""
        ex = Executor()
        assert not ex.is_running

await ex.startup()
        assert ex.is_running

await ex.shutdown()
        assert not ex.is_running

async def test_double_startup(self):
        """Test that double startup is safe."""
        ex = Executor()
        await ex.startup()
        await ex.startup()  # Should not raise
        assert ex.is_running
        await ex.shutdown()

async def test_double_shutdown(self):
        """Test that double shutdown is safe."""
        ex = Executor()
        await ex.startup()
        await ex.shutdown()
        await ex.shutdown()  # Should not raise
        assert not ex.is_running

async def test_run_blocking_simple(self, executor):
        """Test run_blocking with a simple function."""
        def add(a, b):
            return a + b

result = await executor.run_blocking(add, 2, 3)
        assert result == 5

async def test_run_blocking_with_kwargs(self, executor):
        """Test run_blocking with keyword arguments."""
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

result = await executor.run_blocking(greet, "World", greeting="Hi")
        assert result == "Hi, World!"

async def test_run_blocking_io(self, executor, tmp_path):
        """Test run_blocking with actual I/O."""
        test_file = tmp_path / "test.txt"
        content = "Hello, Executor!"

def write_file(path, data):
            with open(path, "w") as f:
                f.write(data)

def read_file(path):
            with open(path) as f:
                return f.read()

await executor.run_blocking(write_file, test_file, content)
        result = await executor.run_blocking(read_file, test_file)
        assert result == content

async def test_run_blocking_not_started(self):
        """Test run_blocking raises if not started."""
        ex = Executor()

with pytest.raises(RuntimeError, match="not started"):
            await ex.run_blocking(lambda: None)

async def test_run_blocking_exception(self, executor):
        """Test that exceptions propagate correctly."""
        def failing_func():
            raise ValueError("Test error")

with pytest.raises(ValueError, match="Test error"):
            await executor.run_blocking(failing_func)

async def test_run_process_simple(self, executor):
        """Test run_process with a simple function."""
        # Note: Must use top-level function for pickling
        result = await executor.run_process(cpu_bound_add, 10, 20)
        assert result == 30

async def test_run_process_cpu_bound(self, executor):
        """Test run_process with CPU-bound work."""
        result = await executor.run_process(cpu_bound_sum, 1000000)
        assert result == sum(range(1000000))

async def test_run_process_not_started(self):
        """Test run_process raises if not started."""
        ex = Executor()

with pytest.raises(RuntimeError, match="not started"):
            await ex.run_process(cpu_bound_add, 1, 2)

async def test_concurrent_blocking(self, executor):
        """Test multiple concurrent blocking tasks."""
        def slow_task(n):
            time.sleep(0.1)
            return n * 2

start = time.time()
        results = await asyncio.gather(
            executor.run_blocking(slow_task, 1),
            executor.run_blocking(slow_task, 2),
            executor.run_blocking(slow_task, 3),
            executor.run_blocking(slow_task, 4),
        )
        elapsed = time.time() - start

assert results == [2, 4, 6, 8]
        # Should run in parallel, so less than 0.4s
        assert elapsed < 0.3

class TestGetExecutor:
    """Tests for get_executor function."""

def test_get_executor_returns_executor(self):
        """Test that get_executor returns an Executor."""
        ex = get_executor()
        assert isinstance(ex, Executor)

def test_get_executor_singleton(self):
        """Test that get_executor returns same instance."""
        ex1 = get_executor()
        ex2 = get_executor()
        assert ex1 is ex2

# Top-level functions for ProcessPoolExecutor (must be picklable)
def cpu_bound_add(a: int, b: int) -> int:
    """Simple add for process pool test."""
    return a + b

def cpu_bound_sum(n: int) -> int:
    """CPU-bound sum for process pool test."""
    return sum(range(n))
```

After implementing this block, `applications.py` will be updated to include:

```python
class Application:
    def __init__(self, ...):
        ...
        self.executor = Executor()

async def _handle_lifespan(self, scope, receive, send):
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                await self.executor.startup()
                # ... other startup
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await self.executor.shutdown()
                # ... other shutdown
                await send({"type": "lifespan.shutdown.complete"})
                return
```

- [ ] Create `src/genro_asgi/executor.py`
- [ ] Create `tests/test_executor.py`
- [ ] Run `pytest tests/test_executor.py`
- [ ] Run `mypy src/genro_asgi/executor.py`
- [ ] Run `ruff check src/genro_asgi/executor.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

```
feat(executor): add unified execution subsystem

- Add Executor class with ThreadPoolExecutor and ProcessPoolExecutor
- Implement run_blocking() for sync I/O operations
- Implement run_process() for CPU-bound tasks
- Add startup/shutdown lifecycle management
- Add comprehensive tests

This provides a key advantage over Starlette which lacks
integrated execution pools.
```

## Source: initial_implementation_plan/archive/03-exceptions.md

**Status**: DA REVISIONARE
**Dependencies**: None
**Commit message**: `feat(exceptions): add HTTPException and WebSocketException`

Exception classes for HTTP and WebSocket error handling.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Exception classes for genro-asgi."""

class HTTPException(Exception):
    """
    HTTP exception with status code and detail.

Raise this in handlers to return an HTTP error response.

Example:
        raise HTTPException(404, detail="User not found")
    """

def __init__(
        self,
        status_code: int,
        detail: str = "",
        headers: dict[str, str] | None = None
    ) -> None:
        """
        Initialize HTTP exception.

Args:
            status_code: HTTP status code (4xx, 5xx)
            detail: Error detail message
            headers: Optional response headers
        """
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(detail)

def __repr__(self) -> str:
        return f"HTTPException(status_code={self.status_code}, detail={self.detail!r})"

class WebSocketException(Exception):
    """
    WebSocket exception with close code and reason.

Raise this to close a WebSocket connection with an error.

Example:
        raise WebSocketException(code=4000, reason="Invalid message format")
    """

def __init__(
        self,
        code: int = 1000,
        reason: str = ""
    ) -> None:
        """
        Initialize WebSocket exception.

Args:
            code: WebSocket close code (1000-4999)
            reason: Close reason message
        """
        self.code = code
        self.reason = reason
        super().__init__(reason)

def __repr__(self) -> str:
        return f"WebSocketException(code={self.code}, reason={self.reason!r})"

class WebSocketDisconnect(Exception):
    """
    Raised when a WebSocket is disconnected by the client.

This is not an error, just a signal that the connection was closed.
    """

def __init__(self, code: int = 1000, reason: str = "") -> None:
        """
        Initialize disconnect exception.

Args:
            code: WebSocket close code
            reason: Close reason (if any)
        """
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected with code {code}")
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for exception classes."""

import pytest
from genro_asgi.exceptions import HTTPException, WebSocketDisconnect, WebSocketException

class TestHTTPException:
    def test_basic(self):
        exc = HTTPException(404, detail="Not found")
        assert exc.status_code == 404
        assert exc.detail == "Not found"
        assert exc.headers is None

def test_with_headers(self):
        exc = HTTPException(401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

def test_default_detail(self):
        exc = HTTPException(500)
        assert exc.detail == ""

def test_str(self):
        exc = HTTPException(400, detail="Bad request")
        assert str(exc) == "Bad request"

def test_repr(self):
        exc = HTTPException(404, detail="Not found")
        assert "404" in repr(exc)
        assert "Not found" in repr(exc)

def test_raise_catch(self):
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(403, detail="Forbidden")
        assert exc_info.value.status_code == 403

class TestWebSocketException:
    def test_basic(self):
        exc = WebSocketException(code=4000, reason="Custom error")
        assert exc.code == 4000
        assert exc.reason == "Custom error"

def test_defaults(self):
        exc = WebSocketException()
        assert exc.code == 1000
        assert exc.reason == ""

def test_str(self):
        exc = WebSocketException(code=4001, reason="Invalid")
        assert str(exc) == "Invalid"

def test_repr(self):
        exc = WebSocketException(code=4000, reason="Error")
        assert "4000" in repr(exc)

def test_raise_catch(self):
        with pytest.raises(WebSocketException) as exc_info:
            raise WebSocketException(code=4002, reason="Test")
        assert exc_info.value.code == 4002

class TestWebSocketDisconnect:
    def test_basic(self):
        exc = WebSocketDisconnect(code=1001, reason="Going away")
        assert exc.code == 1001
        assert exc.reason == "Going away"

def test_defaults(self):
        exc = WebSocketDisconnect()
        assert exc.code == 1000
        assert exc.reason == ""

def test_str(self):
        exc = WebSocketDisconnect(code=1000)
        assert "1000" in str(exc)

def test_raise_catch(self):
        with pytest.raises(WebSocketDisconnect):
            raise WebSocketDisconnect()
```

```python
from .exceptions import HTTPException, WebSocketDisconnect, WebSocketException
```

- [ ] Create `src/genro_asgi/exceptions.py`
- [ ] Create `tests/test_exceptions.py`
- [ ] Run `pytest tests/test_exceptions.py`
- [ ] Run `mypy src/genro_asgi/exceptions.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/archive/06-websockets.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types, 02-datastructures, 03-exceptions
**Commit message**: `feat(websockets): add WebSocket transport class`

WebSocket transport class for handling WebSocket connections.
This is the foundation for genro-wsx protocol.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WebSocket transport class."""

import json
from enum import Enum
from typing import Any, AsyncIterator

from .datastructures import Address, Headers, QueryParams, State, URL
from .exceptions import WebSocketDisconnect, WebSocketException
from .types import Message, Receive, Scope, Send

# Optional fast JSON
try:
    import orjson
    HAS_ORJSON = True
except ImportError:
    HAS_ORJSON = False

class WebSocketState(Enum):
    """WebSocket connection state."""
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2

class WebSocket:
    """
    WebSocket connection wrapper.

Provides high-level interface for WebSocket communication.

Example:
        async def ws_handler(websocket: WebSocket):
            await websocket.accept()
            async for message in websocket:
                await websocket.send_text(f"Echo: {message}")
    """

__slots__ = (
        "_scope",
        "_receive",
        "_send",
        "_state",
        "_headers",
        "_query_params",
        "_url",
        "_client_state",
    )

def __init__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Initialize WebSocket from ASGI scope, receive, and send.

Args:
            scope: ASGI connection scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        self._scope = scope
        self._receive = receive
        self._send = send
        self._state = WebSocketState.CONNECTING
        self._headers: Headers | None = None
        self._query_params: QueryParams | None = None
        self._url: URL | None = None
        self._client_state: State | None = None

@property
    def scope(self) -> Scope:
        """Raw ASGI scope."""
        return self._scope

@property
    def state(self) -> State:
        """Connection state for storing custom data."""
        if self._client_state is None:
            self._client_state = State()
        return self._client_state

@property
    def headers(self) -> Headers:
        """Request headers."""
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
    def url(self) -> URL:
        """WebSocket URL."""
        if self._url is None:
            scheme = self._scope.get("scheme", "ws")
            server = self._scope.get("server")
            path = self._scope.get("root_path", "") + self._scope.get("path", "/")
            query_string = self._scope.get("query_string", b"")

if server:
                host, port = server
                if (scheme == "ws" and port == 80) or (scheme == "wss" and port == 443):
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
    def path(self) -> str:
        """Request path."""
        return self._scope.get("path", "/")

@property
    def client(self) -> Address | None:
        """Client address (host, port) if available."""
        client = self._scope.get("client")
        if client:
            return Address(client[0], client[1])
        return None

@property
    def subprotocols(self) -> list[str]:
        """Requested subprotocols."""
        return self._scope.get("subprotocols", [])

@property
    def connection_state(self) -> WebSocketState:
        """Current connection state."""
        return self._state

async def accept(
        self,
        subprotocol: str | None = None,
        headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        """
        Accept the WebSocket connection.

Args:
            subprotocol: Selected subprotocol (from client's list)
            headers: Additional response headers

Raises:
            RuntimeError: If connection is not in CONNECTING state
        """
        if self._state != WebSocketState.CONNECTING:
            raise RuntimeError(
                f"Cannot accept connection in state {self._state.name}"
            )

message: Message = {
            "type": "websocket.accept",
        }
        if subprotocol:
            message["subprotocol"] = subprotocol
        if headers:
            message["headers"] = headers

await self._send(message)
        self._state = WebSocketState.CONNECTED

async def close(self, code: int = 1000, reason: str = "") -> None:
        """
        Close the WebSocket connection.

Args:
            code: WebSocket close code (1000-4999)
            reason: Close reason message
        """
        if self._state == WebSocketState.DISCONNECTED:
            return

await self._send({
            "type": "websocket.close",
            "code": code,
            "reason": reason,
        })
        self._state = WebSocketState.DISCONNECTED

async def receive(self) -> Message:
        """
        Receive raw ASGI message.

Returns:
            ASGI message dict

Raises:
            WebSocketDisconnect: If client disconnected
        """
        if self._state == WebSocketState.DISCONNECTED:
            raise WebSocketDisconnect()

message = await self._receive()

if message["type"] == "websocket.disconnect":
            self._state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(
                code=message.get("code", 1000),
                reason=message.get("reason", ""),
            )

async def receive_text(self) -> str:
        """
        Receive text message.

Returns:
            Text message content

Raises:
            WebSocketDisconnect: If client disconnected
            RuntimeError: If message is not text
        """
        message = await self.receive()
        if message["type"] != "websocket.receive":
            raise RuntimeError(f"Unexpected message type: {message['type']}")
        if "text" in message:
            return message["text"]
        if "bytes" in message:
            return message["bytes"].decode("utf-8")
        raise RuntimeError("Message has no text or bytes content")

async def receive_bytes(self) -> bytes:
        """
        Receive binary message.

Returns:
            Binary message content

Raises:
            WebSocketDisconnect: If client disconnected
            RuntimeError: If message is not binary
        """
        message = await self.receive()
        if message["type"] != "websocket.receive":
            raise RuntimeError(f"Unexpected message type: {message['type']}")
        if "bytes" in message:
            return message["bytes"]
        if "text" in message:
            return message["text"].encode("utf-8")
        raise RuntimeError("Message has no text or bytes content")

async def receive_json(self) -> Any:
        """
        Receive and parse JSON message.

Returns:
            Parsed JSON data

Raises:
            WebSocketDisconnect: If client disconnected
            ValueError: If message is not valid JSON
        """
        text = await self.receive_text()
        if HAS_ORJSON:
            return orjson.loads(text)
        return json.loads(text)

async def send(self, message: Message) -> None:
        """
        Send raw ASGI message.

Args:
            message: ASGI message dict
        """
        if self._state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"Cannot send in state {self._state.name}"
            )
        await self._send(message)

async def send_text(self, data: str) -> None:
        """
        Send text message.

Args:
            data: Text content to send
        """
        await self.send({
            "type": "websocket.send",
            "text": data,
        })

async def send_bytes(self, data: bytes) -> None:
        """
        Send binary message.

Args:
            data: Binary content to send
        """
        await self.send({
            "type": "websocket.send",
            "bytes": data,
        })

async def send_json(self, data: Any) -> None:
        """
        Send JSON message.

Args:
            data: Python object to serialize and send
        """
        if HAS_ORJSON:
            text = orjson.dumps(data).decode("utf-8")
        else:
            text = json.dumps(data, ensure_ascii=False)
        await self.send_text(text)

async def __aiter__(self) -> AsyncIterator[str | bytes]:
        """
        Iterate over incoming messages.

Yields text or bytes depending on message type.
        Stops when connection is closed.

Example:
            async for message in websocket:
                print(f"Received: {message}")
        """
        while True:
            try:
                message = await self.receive()
                if message["type"] == "websocket.receive":
                    if "text" in message:
                        yield message["text"]
                    elif "bytes" in message:
                        yield message["bytes"]
            except WebSocketDisconnect:
                break

def __repr__(self) -> str:
        return f"WebSocket(path={self.path!r}, state={self._state.name})"
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for WebSocket class."""

import pytest
from genro_asgi.exceptions import WebSocketDisconnect
from genro_asgi.websockets import WebSocket, WebSocketState

def make_scope(
    path: str = "/ws",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    subprotocols: list[str] | None = None,
    server: tuple[str, int] | None = ("localhost", 8000),
    client: tuple[str, int] | None = ("127.0.0.1", 50000),
) -> dict:
    """Create a mock WebSocket ASGI scope."""
    return {
        "type": "websocket",
        "path": path,
        "query_string": query_string,
        "headers": headers or [],
        "subprotocols": subprotocols or [],
        "scheme": "ws",
        "server": server,
        "client": client,
        "root_path": "",
    }

class MockTransport:
    """Mock receive/send for testing."""

def __init__(self, messages: list[dict] | None = None):
        self.incoming = messages or []
        self.outgoing: list[dict] = []

async def receive(self) -> dict:
        if not self.incoming:
            return {"type": "websocket.disconnect", "code": 1000}
        return self.incoming.pop(0)

async def send(self, message: dict) -> None:
        self.outgoing.append(message)

class TestWebSocketProperties:
    def test_path(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(path="/chat"), transport.receive, transport.send)
        assert ws.path == "/chat"

def test_query_params(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(query_string=b"room=general"),
            transport.receive,
            transport.send,
        )
        assert ws.query_params.get("room") == "general"

def test_headers(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(headers=[(b"authorization", b"Bearer token")]),
            transport.receive,
            transport.send,
        )
        assert ws.headers.get("authorization") == "Bearer token"

def test_client(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(client=("192.168.1.1", 12345)),
            transport.receive,
            transport.send,
        )
        assert ws.client is not None
        assert ws.client.host == "192.168.1.1"

def test_subprotocols(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(subprotocols=["graphql-ws", "subscriptions-transport-ws"]),
            transport.receive,
            transport.send,
        )
        assert "graphql-ws" in ws.subprotocols

def test_url(self):
        transport = MockTransport()
        ws = WebSocket(
            make_scope(path="/ws", query_string=b"token=abc"),
            transport.receive,
            transport.send,
        )
        assert "/ws" in str(ws.url)
        assert "token=abc" in str(ws.url)

def test_state(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        ws.state.user_id = 123
        assert ws.state.user_id == 123

def test_initial_state(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        assert ws.connection_state == WebSocketState.CONNECTING

class TestWebSocketAccept:
    @pytest.mark.asyncio
    async def test_accept(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

assert ws.connection_state == WebSocketState.CONNECTED
        assert transport.outgoing[0]["type"] == "websocket.accept"

@pytest.mark.asyncio
    async def test_accept_with_subprotocol(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept(subprotocol="graphql-ws")

assert transport.outgoing[0]["subprotocol"] == "graphql-ws"

@pytest.mark.asyncio
    async def test_accept_twice_raises(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

with pytest.raises(RuntimeError):
            await ws.accept()

class TestWebSocketClose:
    @pytest.mark.asyncio
    async def test_close(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.close(code=1000, reason="Normal closure")

assert ws.connection_state == WebSocketState.DISCONNECTED
        close_msg = transport.outgoing[-1]
        assert close_msg["type"] == "websocket.close"
        assert close_msg["code"] == 1000

@pytest.mark.asyncio
    async def test_close_idempotent(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.close()
        await ws.close()  # Should not raise

class TestWebSocketReceive:
    @pytest.mark.asyncio
    async def test_receive_text(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": "hello"}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

text = await ws.receive_text()
        assert text == "hello"

@pytest.mark.asyncio
    async def test_receive_bytes(self):
        transport = MockTransport([
            {"type": "websocket.receive", "bytes": b"\x00\x01\x02"}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

data = await ws.receive_bytes()
        assert data == b"\x00\x01\x02"

@pytest.mark.asyncio
    async def test_receive_json(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": '{"key": "value"}'}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

data = await ws.receive_json()
        assert data == {"key": "value"}

@pytest.mark.asyncio
    async def test_receive_disconnect(self):
        transport = MockTransport([
            {"type": "websocket.disconnect", "code": 1001}
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

with pytest.raises(WebSocketDisconnect) as exc_info:
            await ws.receive_text()
        assert exc_info.value.code == 1001

class TestWebSocketSend:
    @pytest.mark.asyncio
    async def test_send_text(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.send_text("hello")

msg = transport.outgoing[-1]
        assert msg["type"] == "websocket.send"
        assert msg["text"] == "hello"

@pytest.mark.asyncio
    async def test_send_bytes(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.send_bytes(b"\x00\x01\x02")

msg = transport.outgoing[-1]
        assert msg["bytes"] == b"\x00\x01\x02"

@pytest.mark.asyncio
    async def test_send_json(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()
        await ws.send_json({"key": "value"})

msg = transport.outgoing[-1]
        assert "key" in msg["text"]

@pytest.mark.asyncio
    async def test_send_before_accept_raises(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(), transport.receive, transport.send)

with pytest.raises(RuntimeError):
            await ws.send_text("hello")

class TestWebSocketIteration:
    @pytest.mark.asyncio
    async def test_iterate(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": "msg1"},
            {"type": "websocket.receive", "text": "msg2"},
            {"type": "websocket.receive", "text": "msg3"},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

messages = []
        async for msg in ws:
            messages.append(msg)

assert messages == ["msg1", "msg2", "msg3"]

@pytest.mark.asyncio
    async def test_iterate_mixed(self):
        transport = MockTransport([
            {"type": "websocket.receive", "text": "text"},
            {"type": "websocket.receive", "bytes": b"bytes"},
            {"type": "websocket.disconnect", "code": 1000},
        ])
        ws = WebSocket(make_scope(), transport.receive, transport.send)
        await ws.accept()

messages = []
        async for msg in ws:
            messages.append(msg)

assert messages == ["text", b"bytes"]

class TestWebSocketRepr:
    def test_repr(self):
        transport = MockTransport()
        ws = WebSocket(make_scope(path="/chat"), transport.receive, transport.send)
        r = repr(ws)
        assert "/chat" in r
        assert "CONNECTING" in r
```

```python
from .websockets import WebSocket, WebSocketState
```

- [ ] Create `src/genro_asgi/websockets.py`
- [ ] Create `tests/test_websockets.py`
- [ ] Run `pytest tests/test_websockets.py`
- [ ] Run `mypy src/genro_asgi/websockets.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

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

## Source: initial_implementation_plan/archive/02-datastructures.md

**Status**: DA REVISIONARE
**Dependencies**: 01-types
**Commit message**: `feat(datastructures): add Headers, QueryParams, URL, State, Address`

Reusable data structures for request/response handling. Each is usable standalone.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Data structures for ASGI applications."""

from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlparse

class Address:
    """Client or server address."""

def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

def __repr__(self) -> str:
        return f"Address(host={self.host!r}, port={self.port})"

def __eq__(self, other: object) -> bool:
        if isinstance(other, Address):
            return self.host == other.host and self.port == other.port
        if isinstance(other, tuple) and len(other) == 2:
            return self.host == other[0] and self.port == other[1]
        return False

class URL:
    """URL parsing and components."""

__slots__ = ("_url", "_parsed")

def __init__(self, url: str) -> None:
        self._url = url
        self._parsed = urlparse(url)

@property
    def scheme(self) -> str:
        return self._parsed.scheme

@property
    def netloc(self) -> str:
        return self._parsed.netloc

@property
    def path(self) -> str:
        return unquote(self._parsed.path) or "/"

@property
    def query(self) -> str:
        return self._parsed.query

@property
    def fragment(self) -> str:
        return self._parsed.fragment

@property
    def hostname(self) -> str | None:
        return self._parsed.hostname

@property
    def port(self) -> int | None:
        return self._parsed.port

def __str__(self) -> str:
        return self._url

def __repr__(self) -> str:
        return f"URL({self._url!r})"

def __eq__(self, other: object) -> bool:
        if isinstance(other, URL):
            return self._url == other._url
        if isinstance(other, str):
            return self._url == other
        return False

class Headers:
    """
    Case-insensitive HTTP headers.

Supports multiple values per key (as per HTTP spec).
    """

def __init__(
        self,
        raw_headers: list[tuple[bytes, bytes]] | None = None,
        scope: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize headers.

Args:
            raw_headers: List of (name, value) byte tuples from ASGI scope
            scope: ASGI scope dict (will extract 'headers' key)
        """
        if scope is not None:
            raw_headers = scope.get("headers", [])
        self._headers: list[tuple[str, str]] = []
        if raw_headers:
            for name, value in raw_headers:
                self._headers.append((
                    name.decode("latin-1").lower(),
                    value.decode("latin-1")
                ))

def get(self, key: str, default: str | None = None) -> str | None:
        """Get first value for key (case-insensitive)."""
        key_lower = key.lower()
        for name, value in self._headers:
            if name == key_lower:
                return value
        return default

def getlist(self, key: str) -> list[str]:
        """Get all values for key (case-insensitive)."""
        key_lower = key.lower()
        return [value for name, value in self._headers if name == key_lower]

def keys(self) -> list[str]:
        """Return all header names."""
        seen: set[str] = set()
        result: list[str] = []
        for name, _ in self._headers:
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result

def values(self) -> list[str]:
        """Return all header values."""
        return [value for _, value in self._headers]

def items(self) -> list[tuple[str, str]]:
        """Return all (name, value) pairs."""
        return list(self._headers)

def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

def __contains__(self, key: str) -> bool:
        return self.get(key) is not None

def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

def __len__(self) -> int:
        return len(self._headers)

def __repr__(self) -> str:
        return f"Headers({self._headers!r})"

class QueryParams:
    """
    Query string parameters.

Supports multiple values per key.
    """

def __init__(
        self,
        query_string: bytes | str | None = None,
        scope: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize query params.

Args:
            query_string: Raw query string (bytes or str)
            scope: ASGI scope dict (will extract 'query_string' key)
        """
        if scope is not None:
            query_string = scope.get("query_string", b"")

if query_string is None:
            query_string = b""

if isinstance(query_string, bytes):
            query_string = query_string.decode("latin-1")

self._params = parse_qs(query_string, keep_blank_values=True)

def get(self, key: str, default: str | None = None) -> str | None:
        """Get first value for key."""
        values = self._params.get(key)
        if values:
            return values[0]
        return default

def getlist(self, key: str) -> list[str]:
        """Get all values for key."""
        return self._params.get(key, [])

def keys(self) -> list[str]:
        """Return all parameter names."""
        return list(self._params.keys())

def values(self) -> list[str]:
        """Return first value for each parameter."""
        return [v[0] for v in self._params.values() if v]

def items(self) -> list[tuple[str, str]]:
        """Return (name, first_value) pairs."""
        return [(k, v[0]) for k, v in self._params.items() if v]

def multi_items(self) -> list[tuple[str, str]]:
        """Return all (name, value) pairs including duplicates."""
        result: list[tuple[str, str]] = []
        for key, values in self._params.items():
            for value in values:
                result.append((key, value))
        return result

def __getitem__(self, key: str) -> str:
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value

def __contains__(self, key: str) -> bool:
        return key in self._params

def __iter__(self) -> Iterator[str]:
        return iter(self._params)

def __len__(self) -> int:
        return len(self._params)

def __bool__(self) -> bool:
        return bool(self._params)

def __repr__(self) -> str:
        return f"QueryParams({self._params!r})"

class State:
    """
    Request/application state container.

Allows arbitrary attribute access for storing request-scoped data.
    """

def __init__(self) -> None:
        object.__setattr__(self, "_state", {})

def __setattr__(self, name: str, value: Any) -> None:
        self._state[name] = value

def __getattr__(self, name: str) -> Any:
        try:
            return self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'")

def __delattr__(self, name: str) -> None:
        try:
            del self._state[name]
        except KeyError:
            raise AttributeError(f"State has no attribute '{name}'")

def __contains__(self, name: str) -> bool:
        return name in self._state

def __repr__(self) -> str:
        return f"State({self._state!r})"
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for data structures."""

import pytest
from genro_asgi.datastructures import Address, Headers, QueryParams, State, URL

class TestAddress:
    def test_create(self):
        addr = Address("127.0.0.1", 8000)
        assert addr.host == "127.0.0.1"
        assert addr.port == 8000

def test_equality_with_address(self):
        a1 = Address("localhost", 80)
        a2 = Address("localhost", 80)
        assert a1 == a2

def test_equality_with_tuple(self):
        addr = Address("localhost", 80)
        assert addr == ("localhost", 80)

def test_repr(self):
        addr = Address("localhost", 80)
        assert "localhost" in repr(addr)

class TestURL:
    def test_parse_full_url(self):
        url = URL("https://example.com:8080/path?query=1#frag")
        assert url.scheme == "https"
        assert url.hostname == "example.com"
        assert url.port == 8080
        assert url.path == "/path"
        assert url.query == "query=1"
        assert url.fragment == "frag"

def test_parse_simple_path(self):
        url = URL("/users/123")
        assert url.path == "/users/123"
        assert url.scheme == ""

def test_str(self):
        url = URL("http://test.com")
        assert str(url) == "http://test.com"

def test_equality(self):
        url = URL("http://test.com")
        assert url == URL("http://test.com")
        assert url == "http://test.com"

def test_unquote_path(self):
        url = URL("/path%20with%20spaces")
        assert url.path == "/path with spaces"

class TestHeaders:
    def test_from_raw_headers(self):
        raw = [(b"content-type", b"application/json"), (b"x-custom", b"value")]
        headers = Headers(raw_headers=raw)
        assert headers.get("content-type") == "application/json"
        assert headers.get("x-custom") == "value"

def test_case_insensitive(self):
        raw = [(b"Content-Type", b"text/html")]
        headers = Headers(raw_headers=raw)
        assert headers.get("content-type") == "text/html"
        assert headers.get("CONTENT-TYPE") == "text/html"

def test_getlist(self):
        raw = [(b"set-cookie", b"a=1"), (b"set-cookie", b"b=2")]
        headers = Headers(raw_headers=raw)
        assert headers.getlist("set-cookie") == ["a=1", "b=2"]

def test_getitem_raises(self):
        headers = Headers(raw_headers=[])
        with pytest.raises(KeyError):
            _ = headers["missing"]

def test_contains(self):
        raw = [(b"x-test", b"yes")]
        headers = Headers(raw_headers=raw)
        assert "x-test" in headers
        assert "missing" not in headers

def test_from_scope(self):
        scope = {"headers": [(b"host", b"localhost")]}
        headers = Headers(scope=scope)
        assert headers.get("host") == "localhost"

def test_len(self):
        raw = [(b"a", b"1"), (b"b", b"2")]
        headers = Headers(raw_headers=raw)
        assert len(headers) == 2

class TestQueryParams:
    def test_parse_query_string(self):
        params = QueryParams(query_string=b"name=john&age=30")
        assert params.get("name") == "john"
        assert params.get("age") == "30"

def test_parse_string(self):
        params = QueryParams(query_string="foo=bar")
        assert params.get("foo") == "bar"

def test_multi_values(self):
        params = QueryParams(query_string=b"tag=a&tag=b&tag=c")
        assert params.get("tag") == "a"
        assert params.getlist("tag") == ["a", "b", "c"]

def test_missing_key(self):
        params = QueryParams(query_string=b"")
        assert params.get("missing") is None
        assert params.get("missing", "default") == "default"

def test_getitem_raises(self):
        params = QueryParams(query_string=b"")
        with pytest.raises(KeyError):
            _ = params["missing"]

def test_contains(self):
        params = QueryParams(query_string=b"key=value")
        assert "key" in params
        assert "other" not in params

def test_from_scope(self):
        scope = {"query_string": b"x=1"}
        params = QueryParams(scope=scope)
        assert params.get("x") == "1"

def test_bool_empty(self):
        params = QueryParams(query_string=b"")
        assert not params

def test_bool_non_empty(self):
        params = QueryParams(query_string=b"a=1")
        assert params

def test_multi_items(self):
        params = QueryParams(query_string=b"a=1&a=2&b=3")
        items = params.multi_items()
        assert ("a", "1") in items
        assert ("a", "2") in items
        assert ("b", "3") in items

class TestState:
    def test_set_get(self):
        state = State()
        state.user_id = 123
        assert state.user_id == 123

def test_missing_attribute(self):
        state = State()
        with pytest.raises(AttributeError):
            _ = state.missing

def test_delete(self):
        state = State()
        state.temp = "value"
        del state.temp
        with pytest.raises(AttributeError):
            _ = state.temp

def test_contains(self):
        state = State()
        state.exists = True
        assert "exists" in state
        assert "missing" not in state

def test_repr(self):
        state = State()
        state.key = "value"
        assert "key" in repr(state)
```

```python
from .datastructures import Address, Headers, QueryParams, State, URL
```

- [ ] Create `src/genro_asgi/datastructures.py`
- [ ] Create `tests/test_datastructures.py`
- [ ] Run `pytest tests/test_datastructures.py`
- [ ] Run `mypy src/genro_asgi/datastructures.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

## Source: initial_implementation_plan/done/02-datastructures-01-done/initial.md

**Scopo**: Strutture dati riutilizzabili per gestione request/response ASGI.

Il modulo `datastructures.py` fornisce wrapper Pythonic attorno ai dati raw ASGI.
ASGI usa strutture primitive (bytes, tuple, dict) per efficienza. Queste classi
aggiungono ergonomia senza sacrificare performance.

```
ASGI Raw Data                    genro-asgi Classes
─────────────────                ──────────────────
scope["client"] = ("1.2.3.4", 80)  →  Address(host, port)
scope["headers"] = [(b"...", b"...")]  →  Headers (case-insensitive)
scope["query_string"] = b"a=1&b=2"  →  QueryParams (parsed)
scope["path"] + scope["query_string"]  →  URL (parsed)
scope["state"] = {}  →  State (attribute access)
```

Wrappa la tupla `(host: str, port: int)` usata in ASGI per `client` e `server`.

```python
scope["client"] = ("192.168.1.1", 54321)  # Client address
scope["server"] = ("example.com", 443)     # Server address
# Può essere None se non disponibile
```

```python
class Address:
    __slots__ = ("host", "port")

def __init__(self, host: str, port: int) -> None
    def __repr__(self) -> str
    def __eq__(self, other) -> bool  # Confronta con Address o tuple
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| **NamedTuple** | Immutabile, hashable, unpacking | Meno controllo, no custom methods |
| **dataclass** | Meno boilerplate | Più overhead, no __slots__ by default |
| **Classe custom** (proposta) | Controllo totale, __slots__ | Più codice |

1. **Hashability**: Serve `__hash__` per usare Address come dict key?
   - Pro: Utile per caching, set membership
   - Contro: Rende la classe "immutabile concettualmente"

2. **Tuple unpacking**: Serve `__iter__` per `host, port = address`?
   - Pro: Backward compatible con codice che usa tuple
   - Contro: Aggiunge complessità

Mantenere semplice come proposto. Aggiungere `__hash__` solo se emerge un caso d'uso concreto.

Parsing e accesso ai componenti URL. Wrappa `urllib.parse.urlparse`.

ASGI non fornisce URL completo, ma componenti separati:

```python
scope["scheme"] = "https"
scope["path"] = "/api/users"
scope["query_string"] = b"id=123"
scope["root_path"] = ""
# Per costruire URL completo serve anche scope["server"]
```

```python
class URL:
    __slots__ = ("_url", "_parsed")

def __init__(self, url: str) -> None

# Properties (lazy, cached via _parsed)
    @property scheme -> str
    @property netloc -> str
    @property path -> str       # Con unquote automatico
    @property query -> str
    @property fragment -> str
    @property hostname -> str | None
    @property port -> int | None

def __str__(self) -> str    # URL originale
    def __repr__(self) -> str
    def __eq__(self, other) -> bool  # Confronta con URL o str
```

```
  https://user:pass@example.com:8080/path/to/resource?query=1&b=2#section
  ─────   ─────────────────────────────────────────────────────────────
  scheme          netloc                path           query    fragment
          ──────────────────────────────
          user:pass@example.com:8080
                    ───────────  ────
                    hostname     port
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Solo urlparse** | Zero overhead | API scomoda, no caching |
| **yarl (libreria)** | Molto completa | Dipendenza esterna |
| **Classe wrapper** (proposta) | API pulita, caching | Implementazione da mantenere |

1. **Costruzione da scope**: Serve factory per creare URL da ASGI scope?
   ```python
   # Opzione A: Solo stringa
   url = URL("https://example.com/path")

# Opzione B: Anche da scope (NO - viola "no classmethod")
   url = URL.from_scope(scope)

# Opzione C: Funzione module-level
   url = url_from_scope(scope)
   ```

2. **URL modificabili**: Serve `replace()` per creare URL modificate?
   ```python
   new_url = url.replace(path="/new/path", query="x=1")
   ```
   - Pro: Utile per redirect, link building
   - Contro: Complessità, può essere aggiunto dopo

- Iniziare con costruttore solo da stringa
- Se serve `from_scope`, usare funzione module-level
- Rimandare `replace()` a quando serve

Accesso case-insensitive agli header HTTP. Supporta valori multipli per chiave.

```python
scope["headers"] = [
    (b"host", b"example.com"),
    (b"content-type", b"application/json"),
    (b"accept", b"text/html"),
    (b"accept", b"application/json"),  # Valore multiplo!
    (b"cookie", b"session=abc123"),
]
```

**Note importanti**:
- Header names sono **bytes** in ASGI
- HTTP header names sono **case-insensitive** (RFC 7230)
- Lo stesso header può apparire più volte (es. `Set-Cookie`, `Accept`)
- Encoding è Latin-1 (ISO-8859-1) per compatibilità HTTP/1.1

```python
class Headers:
    __slots__ = ("_headers",)  # list[tuple[str, str]] normalized

def __init__(
        self,
        raw_headers: list[tuple[bytes, bytes]] | None = None,
        scope: dict | None = None
    ) -> None

def get(self, key: str, default: str | None = None) -> str | None
    def getlist(self, key: str) -> list[str]
    def keys(self) -> list[str]
    def values(self) -> list[str]
    def items(self) -> list[tuple[str, str]]

def __getitem__(self, key: str) -> str      # Raises KeyError
    def __contains__(self, key: str) -> bool
    def __iter__(self) -> Iterator[str]
    def __len__(self) -> int
    def __repr__(self) -> str
```

```
Input ASGI (bytes, case-preserving):
[(b"Content-Type", b"application/json"), (b"X-Custom", b"value")]
                    ↓
            Normalizzazione
                    ↓
Internal storage (str, lowercase):
[("content-type", "application/json"), ("x-custom", "value")]
                    ↓
            Lookup case-insensitive
                    ↓
headers.get("CONTENT-TYPE") → "application/json"
```

| Opzione | Esempio | Pro | Contro |
|---------|---------|-----|--------|
| **Solo raw_headers** | `Headers(raw)` | Semplice | Verboso con scope |
| **Solo scope** | `Headers(scope)` | Diretto | Meno flessibile |
| **Entrambi (proposta)** | `Headers(raw_headers=...)` o `Headers(scope=...)` | Flessibile | Due path, confusione? |
| **Overload** | `Headers(raw)` o `Headers(scope)` by type | Magico | Type checking difficile |

1. **Pattern costruttore**: Due parametri opzionali OK?
   - Alternativa: solo `raw_headers`, con helper `headers_from_scope(scope)`

2. **Immutabilità**: Headers deve essere immutabile o mutabile?
   - Immutabile: più sicuro, ma serve `MutableHeaders` per response
   - Mutabile: un'unica classe, ma rischio side-effects

3. **Multi-value handling**: `get()` ritorna primo valore, `getlist()` tutti. OK?

- Costruttore con due parametri opzionali è accettabile (pattern comune)
- Iniziare **immutabile** (read-only)
- Per response, creare `MutableHeaders` separata (Block 05) o usare list[tuple] direttamente

Parsing e accesso ai parametri query string. Supporta valori multipli.

```python
scope["query_string"] = b"name=john&tags=python&tags=web&empty="
```

```python
class QueryParams:
    __slots__ = ("_params",)  # dict[str, list[str]] from parse_qs

def __init__(
        self,
        query_string: bytes | str | None = None,
        scope: dict | None = None
    ) -> None

def get(self, key: str, default: str | None = None) -> str | None
    def getlist(self, key: str) -> list[str]
    def keys(self) -> list[str]
    def values(self) -> list[str]      # First value per key
    def items(self) -> list[tuple[str, str]]  # First value per key
    def multi_items(self) -> list[tuple[str, str]]  # All values

def __getitem__(self, key: str) -> str
    def __contains__(self, key: str) -> bool
    def __iter__(self) -> Iterator[str]
    def __len__(self) -> int
    def __bool__(self) -> bool
    def __repr__(self) -> str
```

```
Query string: "name=john&tags=python&tags=web&empty="
                    ↓
            urllib.parse.parse_qs
                    ↓
Internal dict: {
    "name": ["john"],
    "tags": ["python", "web"],
    "empty": [""]
}
                    ↓
params.get("name") → "john"
params.getlist("tags") → ["python", "web"]
params.get("missing") → None
```

| Aspetto | Headers | QueryParams |
|---------|---------|-------------|
| Case sensitivity | Case-insensitive | Case-sensitive |
| Storage | list[tuple] | dict[str, list] |
| Empty values | N/A | Supportati (`?key=`) |
| URL encoding | No (raw bytes) | Sì (decode automatico) |

1. **Stesso pattern costruttore di Headers?** (due parametri opzionali)

2. **Encoding**: `parse_qs` decodifica automaticamente `%xx`. OK o serve controllo?

Mantenere parallelo a Headers per consistenza API. Il pattern a due parametri è accettabile se ben documentato.

Container per dati request-scoped con accesso via attributi.

```python
# Middleware authentication
state.user = User(id=123)
state.is_authenticated = True

# Handler
if request.state.is_authenticated:
    user = request.state.user
```

```python
class State:
    __slots__ = ("_state",)  # dict interno

def __init__(self) -> None
    def __setattr__(self, name: str, value: Any) -> None
    def __getattr__(self, name: str) -> Any    # Raises AttributeError
    def __delattr__(self, name: str) -> None   # Raises AttributeError
    def __contains__(self, name: str) -> bool
    def __repr__(self) -> str
```

Questo pattern usa override di `__setattr__`/`__getattr__` per intercettare
l'accesso agli attributi e redirectarlo a un dict interno.

```python
state = State()
state.user = "john"     # Chiama __setattr__ → self._state["user"] = "john"
print(state.user)       # Chiama __getattr__ → return self._state["user"]
```

**Nota implementativa**: Il costruttore deve usare `object.__setattr__` per
inizializzare `_state` senza triggerare il nostro override:

```python
def __init__(self) -> None:
    object.__setattr__(self, "_state", {})  # Bypass del nostro __setattr__
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Dict semplice** | Nessuna magia | Meno ergonomico (`state["user"]`) |
| **SimpleNamespace** | Built-in, no code | No `__contains__`, no `__slots__` |
| **Classe custom** (proposta) | Controllo totale | Pattern "magico" |
| **dataclass dinamico** | Type hints | Troppo complesso |

1. **Pattern magico accettabile?** L'override di `__getattr__`/`__setattr__` è un pattern non banale.

2. **Dict access**: Serve anche `state["key"]` oltre a `state.key`?
   - Pro: Utile per chiavi dinamiche
   - Contro: Duplicazione API

3. **Iteration**: Serve `__iter__` per iterare sulle chiavi?

Il pattern è standard (usato da Starlette, Flask, etc.). È accettabile.
Non aggiungere dict access - se serve dict, usare dict direttamente.

Tutte le classi usano `__slots__`. Benefici:
- Memoria: ~40% meno per istanza
- Performance: accesso attributi leggermente più veloce
- Previene typo negli attributi

**Raccomandazione**: Mantenere `__slots__` ovunque.

La regola dice "ogni modulo con classe primaria". Ma `datastructures.py` ha
5 classi utility, nessuna "primaria".

**Raccomandazione**: Per moduli utility puri, omettere entry point.
La regola si applica a moduli con una classe principale (Application, Request, etc.).

Headers e QueryParams accettano `raw_data` OR `scope`. Alternative:

```python
# Opzione A: Due parametri (proposta)
Headers(raw_headers=...)
Headers(scope=...)

# Opzione B: Solo raw + helper function
Headers(raw)
headers_from_scope(scope)  # Module-level function

# Opzione C: Overload by type (non Pythonic)
Headers(raw_or_scope)  # Detect type internally
```

**Raccomandazione**: Opzione A è OK, è pattern comune. Documentare chiaramente.

| # | Domanda | Raccomandazione |
|---|---------|-----------------|
| 1 | Address: aggiungere `__hash__`? | No, aggiungere se serve |
| 2 | Address: aggiungere `__iter__` per unpacking? | No, mantenere semplice |
| 3 | URL: factory `from_scope`? | No ora, funzione module-level se serve |
| 4 | URL: metodo `replace()`? | No ora, aggiungere se serve |
| 5 | Headers/QueryParams: due parametri costruttore OK? | Sì, pattern comune |
| 6 | Headers: immutabile? | Sì, MutableHeaders in Block 05 se serve |
| 7 | State: pattern magic attributes OK? | Sì, pattern standard |
| 8 | Entry point per moduli utility? | No, solo per classi principali |
| 9 | `__slots__` ovunque? | Sì, mantenere |

Dopo conferma delle decisioni:
1. Scrivere docstring completa del modulo
2. Scrivere test
3. Implementare
4. Commit

## Source: initial_implementation_plan/done/07-http-01-done/01-request-done/initial.md

**Scopo**: Classe Request per wrapping ASGI scope e receive callable.

Il modulo `requests.py` fornisce la classe `Request` che wrappa lo scope ASGI
e il callable receive, offrendo un'API ergonomica per accedere a metodo, path,
headers, query params, body, JSON, form data.

```
ASGI Raw                           Request API
────────                           ───────────
scope["method"]                    request.method
scope["path"]                      request.path
scope["headers"]                   request.headers (Headers object)
scope["query_string"]              request.query_params (QueryParams object)
await receive()                    await request.body() / request.stream()
```

Wrapper HTTP request che:
- Fornisce accesso facile ai dati dello scope
- Gestisce il body reading (con caching)
- Supporta parsing JSON e form data
- Fornisce State per dati request-scoped

```python
class Request:
    __slots__ = (
        "_scope", "_receive", "_body", "_json",
        "_headers", "_query_params", "_url", "_state"
    )

def __init__(self, scope: Scope, receive: Receive) -> None

# Properties sincrone (da scope)
    @property scope -> Scope
    @property method -> str
    @property path -> str
    @property scheme -> str
    @property url -> URL
    @property headers -> Headers
    @property query_params -> QueryParams
    @property client -> Address | None
    @property state -> State
    @property content_type -> str | None

# Metodi async (body reading)
    async def body() -> bytes
    async def stream() -> AsyncIterator[bytes]
    async def json() -> Any
    async def form() -> dict[str, Any]
```

**Problema**: Il piano usa `Headers(scope=self._scope)` ma nel Block 02 abbiamo
implementato solo `Headers(raw_headers)` con helper `headers_from_scope(scope)`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Modificare datastructures** | Piano invariato | Cambia API già committata |
| **Usare helper functions** (raccomandato) | Coerente con Block 02 | Piano va corretto |

**Decisione**: Usare `headers_from_scope(scope)` e `query_params_from_scope(scope)`.

```python
# Invece di:
self._headers = Headers(scope=self._scope)

# Usare:
from .datastructures import headers_from_scope
self._headers = headers_from_scope(self._scope)
```

**Problema**: Le properties headers e query_params sono lazy (create al primo accesso).
È il pattern corretto?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Lazy** (proposto) | Efficiente se non usati | Complessità cache |
| **Eager** | Semplice | Overhead se non usati |

**Decisione**: Mantenere **lazy loading** - è pattern standard, headers/query_params
potrebbero non essere usati in tutti i casi.

**Problema**: La costruzione dell'URL è complessa (scheme, server, path, query_string).
Il piano propone logica inline nella property.

**Considerazioni**:
- Logica complessa per determinare netloc (port default, host header fallback)
- Potrebbe essere estratta in helper function

**Decisione**: Mantenere inline nella property come nel piano. Se diventa più
complessa, estrarre in `_build_url()` metodo privato.

**Problema**: scope["client"] può essere None (es. Unix socket, test).
Il piano propone `client -> Address | None`.

**Decisione**: OK, coerente con ASGI spec. Address creato on-demand.

**Problema**: `body()` caching - una volta letto, cached in `_body`.
Ma se chiami prima `stream()` e poi `body()`?

**Piano attuale**:
```python
async def stream():
    if self._body is not None:
        yield self._body
        return
    # ... read from receive
```

**Problema**: Se fai partial stream, poi chiami body(), cosa succede?
- Il piano non gestisce questo caso
- Streaming parziale consuma receive, poi body() rileggerebbe

**Decisione**: Documentare chiaramente:

- **Il body può essere letto UNA SOLA VOLTA** dal receive
- `body()` legge tutto e cache il risultato
- `stream()` restituisce chunk raw come bytes (senza decodifica)
- `stream()` e `body()` sono mutualmente esclusivi: usare uno o l'altro
- Se chiami `body()` dopo `stream()` parziale, comportamento indefinito

**Problema**: Il piano usa try/except per orjson import. OK?

**Decisione**: OK, è pattern standard. orjson è opzionale per performance.

**Charset**: Documentare che `json()` usa **UTF-8 implicito** per decodifica.

- orjson accetta bytes direttamente (assume UTF-8)
- stdlib json.loads richiede decode, usiamo UTF-8
- Non si legge charset da Content-Type (semplificazione)

**Problema**: Il piano supporta solo `application/x-www-form-urlencoded`.
Multipart (file upload) richiede parser più complesso.

**Decisione**: OK per ora. Multipart può essere aggiunto in futuro o come
middleware separato. Documentare la limitazione.

**Charset**: Documentare che `form()` usa **UTF-8 implicito** per decodifica
(standard per urlencoded forms moderni).

**Problema**: `content_type` property è shortcut per `headers.get("content-type")`.

**Decisione**: Utile, mantenere. Potrebbe anche parsare charset etc. ma per ora
semplice string è sufficiente.

**Problema**: Con `__slots__`, le properties lazy usano attributi None iniziali:
```python
self._headers: Headers | None = None
```

Questo è corretto con `__slots__` - gli slot permettono None.

**Decisione**: OK come nel piano.

**Problema**: Ogni Request ha il suo State. Due Request dallo stesso scope
hanno State separate.

**Decisione**: Corretto, è il comportamento atteso. Lo State è request-scoped,
non scope-scoped.

**Problema**: Il piano include `root_path` nella costruzione URL:
```python
path = self._scope.get("root_path", "") + self.path
```

**Decisione**: Corretto per applicazioni montate su subpath.

**Problema**: Esiste già `src/genro_asgi/request.py` (stub). Il piano dice
`requests.py` (plurale). Quale usare?

```bash
# File esistenti
src/genro_asgi/request.py   # Stub esistente (singolare)
# Piano
src/genro_asgi/requests.py  # Plurale come responses
```

**Decisione**: Usare il singolare `request.py` già esistente per coerenza
con la struttura attuale. Il nome singolare è anche più comune (Starlette usa
singolare).

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Headers/QueryParams costruttore | Usare helper functions |
| 2 | Lazy vs eager loading | **Lazy** (come nel piano) |
| 3 | URL construction | Inline nella property |
| 4 | Client property None | OK, coerente con ASGI |
| 5 | Body caching con stream | Documentare: body letto UNA VOLTA, stream/body mutualmente esclusivi |
| 6 | orjson fallback + charset | OK, **UTF-8 implicito** per json() |
| 7 | Form urlencoded + charset | OK, **UTF-8 implicito** per form(), multipart futuro |
| 8 | Content-Type property | Mantenere, utile shortcut |
| 9 | `__slots__` con lazy | OK come nel piano |
| 10 | State isolata | Corretto, request-scoped |
| 11 | Root path | Corretto per subpath mounting |
| 12 | Nome file | **Singolare `request.py`** (esiste già) |

1. **Usare helper functions** invece di costruttore duale per Headers/QueryParams
2. **File `request.py`** (singolare) invece di `requests.py`
3. **Documentare** mutua esclusione stream/body
4. **Documentare** limitazione form (solo urlencoded)

Dopo conferma delle decisioni:
1. Scrivere docstring completa del modulo (Step 2)
2. Scrivere test (Step 3)
3. Implementare (Step 4)
4. Commit (Step 6)

## Source: initial_implementation_plan/done/07-http-01-done/02-response-done/improvements.md

**Scopo**: Miglioramenti e correzioni per il modulo response.py
**Status**: 🔴 DA REVISIONARE
**Dipendenze**: Block 05 (response.py) completato

Questo documento analizza le criticità emerse dopo l'implementazione del Block 05
e propone soluzioni per ciascuna.

`FileResponse` usa I/O sincrono nel metodo `__call__`:

```python
with open(self.path, "rb") as f:
    while True:
        chunk = f.read(self.chunk_size)  # BLOCKING!
        await send(...)
```

Ogni `f.read()` blocca l'intero event loop. Con molti download simultanei,
il server smette di rispondere ad altre richieste.

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    await send({
        "type": "http.response.start",
        "status": self.status_code,
        "headers": self._build_headers(),
    })

def read_file_sync():
        """Generator che legge il file in modo sincrono."""
        with open(self.path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break
                yield chunk

# Legge chunks in thread separato
    for chunk in read_file_sync():
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

**Nota**: Questa versione NON usa `to_thread` perché il generator non funziona
direttamente con `to_thread`. Serve un approccio diverso.

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    await send({
        "type": "http.response.start",
        "status": self.status_code,
        "headers": self._build_headers(),
    })

loop = asyncio.get_running_loop()

with open(self.path, "rb") as f:
        while True:
            # Legge in thread pool
            chunk = await loop.run_in_executor(None, f.read, self.chunk_size)
            more_body = len(chunk) == self.chunk_size
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": more_body,
            })
            if not more_body:
                break
```

**Pro**: Stdlib puro, non blocca event loop
**Contro**: Overhead thread pool per ogni chunk

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    await send({
        "type": "http.response.start",
        "status": self.status_code,
        "headers": self._build_headers(),
    })

with open(self.path, "rb") as f:
        # mmap permette accesso memory-mapped, OS gestisce il paging
        with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            file_size = len(mm)
            offset = 0
            while offset < file_size:
                end = min(offset + self.chunk_size, file_size)
                chunk = mm[offset:end]
                more_body = end < file_size
                await send({
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": more_body,
                })
                offset = end

# Caso file vuoto
    if file_size == 0:
        await send({
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        })
```

**Pro**: Molto efficiente, OS gestisce caching/paging
**Contro**:
- Complessità maggiore
- Comportamento diverso su Windows (non supporta mmap su file vuoti)
- File deve stare in memoria virtuale

async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    await send({
        "type": "http.response.start",
        "status": self.status_code,
        "headers": self._build_headers(),
    })

with open(self.path, "rb") as f:
        while True:
            chunk = f.read(self.chunk_size)
            more_body = len(chunk) == self.chunk_size
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": more_body,
            })
            if not more_body:
                break
            # Yield control all'event loop dopo ogni chunk
            await asyncio.sleep(0)
```

**Pro**: Minimale, permette ad altre coroutine di eseguire
**Contro**:
- `sleep(0)` è un hack
- Blocca comunque durante ogni `read()` (anche se breve)

Mantenere implementazione attuale ma:
1. Ridurre chunk_size default (da 64KB a 16KB)
2. Documentare chiaramente la limitation nella docstring
3. Raccomandare nginx/CDN per static files in produzione

```python
class FileResponse:
    """
    Response that streams a file from disk.

.. warning::
        File reading is synchronous and may block the event loop.
        For high-traffic production deployments, serve static files
        through a reverse proxy (nginx, Caddy) or CDN instead.

**Pro**: Semplice, onesto, pratico
**Contro**: Non risolve il problema tecnico

| Soluzione | Complessità | Performance | Zero-deps | Note |
|-----------|-------------|-------------|-----------|------|
| A: to_thread | Media | Buona | ✅ | Non funziona con generator |
| B: run_in_executor | Media | Buona | ✅ | **Raccomandato** |
| C: mmap | Alta | Ottima | ✅ | Problemi Windows |
| D: sleep(0) | Bassa | Scarsa | ✅ | Hack, non risolve |
| E: Documentare | Nessuna | Invariata | ✅ | Onesto ma limitato |

**Per Alpha**: Soluzione B (`run_in_executor`)

Motivi:
- Stdlib puro (zero dipendenze)
- Risolve effettivamente il problema
- Pattern standard e ben testato
- Overhead accettabile per file serving

**Alternativa conservativa**: Soluzione E (documentare limitation)
- Se si vuole rimandare la complessità
- Con nota che in produzione si usa reverse proxy

Per settare un cookie l'utente deve:

```python
Response(headers=[("Set-Cookie", "session=123; Path=/; HttpOnly; Secure")])
```

Problemi:
- Scomodo e verboso
- Facile dimenticare attributi di sicurezza (HttpOnly, Secure)
- Encoding del valore non gestito
- Nessuna validazione

```python
class Response:
    def set_cookie(
        self,
        key: str,
        value: str = "",
        max_age: int | None = None,
        expires: datetime | str | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: Literal["strict", "lax", "none"] | None = "lax",
    ) -> None:
        """
        Set a cookie in the response.

Args:
            key: Cookie name
            value: Cookie value (will be URL-encoded)
            max_age: Max age in seconds
            expires: Expiration datetime or string
            path: Cookie path (default "/")
            domain: Cookie domain
            secure: Require HTTPS
            httponly: Prevent JavaScript access
            samesite: SameSite policy ("strict", "lax", "none")
        """
        from urllib.parse import quote

cookie = f"{key}={quote(value, safe='')}"

if max_age is not None:
            cookie += f"; Max-Age={max_age}"
        if expires is not None:
            if isinstance(expires, datetime):
                expires = expires.strftime("%a, %d %b %Y %H:%M:%S GMT")
            cookie += f"; Expires={expires}"
        if path:
            cookie += f"; Path={path}"
        if domain:
            cookie += f"; Domain={domain}"
        if secure:
            cookie += "; Secure"
        if httponly:
            cookie += "; HttpOnly"
        if samesite:
            cookie += f"; SameSite={samesite.capitalize()}"

self._headers.append(("set-cookie", cookie))
```

**Pro**: API pulita, validazione implicita
**Contro**:
- Response è "immutabile dopo costruzione" (design principle violato)
- Richiede che Response non sia ancora inviata

```python
def delete_cookie(
    self,
    key: str,
    path: str = "/",
    domain: str | None = None,
) -> None:
    """Delete a cookie by setting it expired."""
    self.set_cookie(
        key=key,
        value="",
        max_age=0,
        path=path,
        domain=domain,
    )
```

```python
def make_cookie(
    key: str,
    value: str = "",
    max_age: int | None = None,
    expires: datetime | str | None = None,
    path: str = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    samesite: Literal["strict", "lax", "none"] | None = "lax",
) -> tuple[str, str]:
    """
    Create a Set-Cookie header tuple.

Returns:
        Tuple of (header_name, header_value) for use in Response headers.

Example:
        >>> headers = [make_cookie("session", "abc123", httponly=True)]
        >>> response = Response(content="OK", headers=headers)
    """
    ...
    return ("set-cookie", cookie)
```

**Pro**: Non viola immutabilità Response, funzione pura
**Contro**: Meno ergonomico

```python
@dataclass
class Cookie:
    """HTTP Cookie builder."""
    key: str
    value: str = ""
    max_age: int | None = None
    expires: datetime | str | None = None
    path: str = "/"
    domain: str | None = None
    secure: bool = False
    httponly: bool = False
    samesite: Literal["strict", "lax", "none"] | None = "lax"

def to_header(self) -> tuple[str, str]:
        """Convert to Set-Cookie header tuple."""
        ...
        return ("set-cookie", cookie_string)

def __str__(self) -> str:
        """Return cookie string value."""
        return self.to_header()[1]

# Usage
cookie = Cookie("session", "abc123", httponly=True, secure=True)
response = Response(content="OK", headers=[cookie.to_header()])
```

**Pro**:
- Oggetto riutilizzabile
- Non viola design Response
- Testabile separatamente
**Contro**: Più verboso

Documentare il pattern manuale nella docstring di Response:

```python
"""
Setting cookies:
    For simple cookies, use header tuples directly::

Response(headers=[("Set-Cookie", "session=abc123; Path=/; HttpOnly")])

Response(headers=[
            ("Set-Cookie", "session=abc123; Path=/; HttpOnly"),
            ("Set-Cookie", "prefs=dark; Path=/; Max-Age=31536000"),
        ])

A dedicated Cookie helper may be added in a future version.
"""
```

| Soluzione | Ergonomia | Complessità | Coerenza Design | Note |
|-----------|-----------|-------------|-----------------|------|
| A: set_cookie() | Ottima | Media | ❌ Viola immutabilità | Come Starlette |
| B: delete_cookie() | - | Bassa | Dipende da A | Complemento |
| C: make_cookie() | Buona | Bassa | ✅ | Funzione pura |
| D: Classe Cookie | Buona | Media | ✅ | Più strutturato |
| E: Rimandare | - | Nessuna | ✅ | Onesto |

**Per Alpha**: Soluzione E (Rimandare) + Soluzione C (make_cookie function)

Motivi:
- `make_cookie()` è semplice e non viola il design
- Può essere aggiunta senza modificare Response
- Documentazione chiara per uso manuale
- `set_cookie()` metodo può essere aggiunto in futuro se richiesto

**Implementazione minima**:
```python
# In response.py o nuovo modulo cookies.py

def make_cookie(
    key: str,
    value: str = "",
    *,
    max_age: int | None = None,
    path: str = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    samesite: str | None = "lax",
) -> tuple[str, str]:
    """Create a Set-Cookie header tuple."""
    from urllib.parse import quote

cookie = f"{key}={quote(value, safe='')}"
    if max_age is not None:
        cookie += f"; Max-Age={max_age}"
    if path:
        cookie += f"; Path={path}"
    if domain:
        cookie += f"; Domain={domain}"
    if secure:
        cookie += "; Secure"
    if httponly:
        cookie += "; HttpOnly"
    if samesite:
        cookie += f"; SameSite={samesite.capitalize()}"

return ("set-cookie", cookie)
```

```python
Response(status_code=204, content="body")  # Viola RFC!
```

HTTP RFC specifica che 204 No Content e 304 Not Modified NON devono avere body.

```python
NO_BODY_STATUS_CODES = {204, 304}

def __init__(self, content=None, status_code=200, ...):
    if status_code in NO_BODY_STATUS_CODES and content:
        raise ValueError(f"Status {status_code} must not have body content")
    ...
```

**Pro**: Previene errori
**Contro**: Viola principio "nessuna validazione" già stabilito

```python
def __init__(self, content=None, status_code=200, ...):
    if status_code in NO_BODY_STATUS_CODES:
        content = None  # Ignora body per questi status
    ...
```

**Pro**: Evita problemi server
**Contro**: Comportamento sorprendente, nasconde errori utente

```python
"""
Args:
    status_code: HTTP status code (default 200).

Note:
    Status codes 204 (No Content) and 304 (Not Modified) must not
    have body content per HTTP specification. The server may reject
    or truncate responses that violate this.
"""
```

**Pro**: Informativo, non invasivo
**Contro**: Non previene l'errore

Lasciare la responsabilità all'utente e al server ASGI.

**Per Alpha**: Soluzione C (Warning in docstring)

Motivi:
- Coerente con decisione "nessuna validazione"
- HTTPException non valida status codes
- Documentazione chiara
- Server ASGI gestirà appropriatamente

`StreamingResponse` non auto-appende charset per text/* media types come fa `Response`:

```python
# Response aggiunge charset
Response(media_type="text/plain")  # -> "text/plain; charset=utf-8"

# StreamingResponse NO
StreamingResponse(content=gen(), media_type="text/plain")  # -> "text/plain"
```

```python
class StreamingResponse:
    charset: str = "utf-8"

def __init__(self, ...):
        ...
        if self.media_type is not None:
            header_names = {name.lower() for name, _ in self._headers}
            if "content-type" not in header_names:
                content_type = self.media_type
                # Auto-append charset for text/* types
                if content_type.startswith("text/") and "charset" not in content_type:
                    content_type = f"{content_type}; charset={self.charset}"
                self._headers.append(("content-type", content_type))
```

**Per Alpha**: Implementare la correzione

È una piccola modifica che allinea il comportamento con Response.

| # | Criticità | Azione | Priorità | Complessità |
|---|-----------|--------|----------|-------------|
| 1 | 🔴 FileResponse I/O | run_in_executor | Alta | Media |
| 2 | 🟠 set_cookie | make_cookie() function | Media | Bassa |
| 3 | 🟡 204 body | Docstring warning | Bassa | Nessuna |
| 4 | 🟡 Streaming charset | Fix charset append | Bassa | Bassa |

**File**: `src/genro_asgi/response.py`

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    """
    ASGI application interface.

Streams file content in chunks using thread pool for non-blocking I/O.
    """
    import asyncio

await send({
        "type": "http.response.start",
        "status": self.status_code,
        "headers": self._build_headers(),
    })

loop = asyncio.get_running_loop()

with open(self.path, "rb") as f:
        while True:
            chunk = await loop.run_in_executor(None, f.read, self.chunk_size)
            more_body = len(chunk) == self.chunk_size
            await send({
                "type": "http.response.body",
                "body": chunk,
                "more_body": more_body,
            })
            if not more_body:
                break
```

**Test da aggiungere**:
- Test che verifica non-blocking (mock executor)
- Test file grande con multiple chunks

**File**: `src/genro_asgi/response.py` (aggiungere)

```python
def make_cookie(
    key: str,
    value: str = "",
    *,
    max_age: int | None = None,
    path: str = "/",
    domain: str | None = None,
    secure: bool = False,
    httponly: bool = False,
    samesite: str | None = "lax",
) -> tuple[str, str]:
    """
    Create a Set-Cookie header tuple.

Args:
        key: Cookie name.
        value: Cookie value (will be URL-encoded).
        max_age: Max age in seconds. None means session cookie.
        path: Cookie path (default "/").
        domain: Cookie domain. None means current domain.
        secure: If True, cookie only sent over HTTPS.
        httponly: If True, cookie not accessible via JavaScript.
        samesite: SameSite policy ("strict", "lax", "none", or None).

Returns:
        Tuple of ("set-cookie", cookie_string) for use in Response headers.

Example:
        >>> from genro_asgi import Response, make_cookie
        >>> response = Response(
        ...     content="OK",
        ...     headers=[
        ...         make_cookie("session", "abc123", httponly=True, secure=True),
        ...         make_cookie("prefs", "dark", max_age=31536000),
        ...     ]
        ... )
    """
    from urllib.parse import quote

cookie = f"{key}={quote(value, safe='')}"
    if max_age is not None:
        cookie += f"; Max-Age={max_age}"
    if path:
        cookie += f"; Path={path}"
    if domain:
        cookie += f"; Domain={domain}"
    if secure:
        cookie += "; Secure"
    if httponly:
        cookie += "; HttpOnly"
    if samesite:
        cookie += f"; SameSite={samesite.capitalize()}"

return ("set-cookie", cookie)
```

**Export**: Aggiungere a `__all__` e `__init__.py`

**Test da aggiungere**:
- Test basic cookie
- Test con tutti i parametri
- Test encoding caratteri speciali
- Test samesite variations

**File**: `src/genro_asgi/response.py`

Aggiungere note a:
- `Response.__init__` docstring: nota su 204/304
- `FileResponse` class docstring: già OK (sync I/O warning può essere rimosso dopo fix)

**File**: `src/genro_asgi/response.py`

Modificare `StreamingResponse.__init__` per auto-append charset.

- [ ] FileResponse: implementare run_in_executor
- [ ] FileResponse: aggiornare docstring (rimuovere warning sync)
- [ ] FileResponse: aggiungere test async I/O
- [ ] make_cookie(): implementare function
- [ ] make_cookie(): aggiungere test
- [ ] make_cookie(): esportare in __init__.py
- [ ] Response: aggiungere nota 204/304 in docstring
- [ ] StreamingResponse: fix charset auto-append
- [ ] StreamingResponse: aggiungere test charset
- [ ] Aggiornare docstring modulo se necessario
- [ ] pytest + mypy + ruff
- [ ] Commit

| # | Item | Decisione |
|---|------|-----------|
| 1 | FileResponse I/O | **DA DECIDERE**: run_in_executor o documentare? |
| 2 | set_cookie | **DA DECIDERE**: make_cookie() function? |
| 3 | 204 body | Docstring warning (nessuna validazione) |
| 4 | Streaming charset | Fix per coerenza |

1. **Confermare decisioni** su punti 1 e 2 ← SIAMO QUI
2. Implementare modifiche
3. Test
4. Commit come "fix(response): improve FileResponse async I/O and add cookie helper"
5. Proseguire con Block 06 (websockets)

## Source: initial_implementation_plan/to-do/09-utils-01/09-utils-initial.md

**Purpose**: Define shared utilities for URL construction, TYTX hydration/serialization, and the RequestEnvelope pattern.
**Status**: IN DISCUSSION → DECISIONS MADE

- **URL**: Request and WebSocket duplicate URL construction logic from scope. A shared function avoids divergence and bugs.
- **TYTX**: The TYTX protocol requires hydration/serialization hooks. Centralize decode/encode logic and `::TYTX` marker handling.
- **Envelope**: Unified request/response tracking across HTTP and WebSocket transports.

### 1. URL Utility Location
**Decision**: New `utils.py` module

Rationale: More utilities will likely be needed in the future.

### 2. TYTX Auto-Declaration
**Decision**: Marker `::TYTX` at end of text is self-declaring

```
{"price": "100.50::D", "date": "2025-01-15::d"}::TYTX
```

- Receiver auto-detects: `if text.endswith("::TYTX")`
- Works on any text channel (WebSocket, HTTP body, query string)
- Backward compatible: JSON without marker is plain JSON

### 3. TYTX Symmetry Rule
**Decision**: If you receive `::TYTX`, respond with `::TYTX`

- `receive_json()` auto-detects marker, sets `tytx_mode=True` on envelope
- `send_json()` checks `tytx_mode`, appends marker if True
- Zero configuration, client declares protocol with first message

### 4. Behavior Without genro-tytx
**Decision**: Explicit `ImportError`

No silent degradation. If marker present but library missing, raise ImportError.

### 5. Request/Response Model
**Decision**: Everything is request/response with ack

| Type        | Request           | Response              |
|-------------|-------------------|-----------------------|
| RPC call    | method + params   | result                |
| Notify      | event + payload   | ack                   |
| Subscribe   | channel           | ack (subscription_id) |
| Unsubscribe | subscription_id   | ack                   |
| Server push | event + payload   | ack (from client)     |

No "fire and forget". Sender always expects ack. If not received → timeout → sender's problem.

### 6. Envelope Pattern
**Decision**: `RequestEnvelope` / `ResponseEnvelope`

Unified wrapper for HTTP and WebSocket:

```python
@dataclass
class RequestEnvelope:
    internal_id: str           # Server-generated, always present
    external_id: str | None    # Client-provided, optional (echoed back)
    tytx_mode: bool            # Detected from ::TYTX marker
    params: dict               # Already hydrated if TYTX
    metadata: dict             # Additional context
    created_at: float          # Timestamp

# Transport-specific (one of these)
    _http_request: Request | None
    _wsx_message: WSXMessage | None

@dataclass
class ResponseEnvelope:
    request_id: str            # Reference to RequestEnvelope.internal_id
    external_id: str | None    # Echoed from request
    tytx_mode: bool            # Inherited from request
    data: Any                  # Response payload
```

### 7. Envelope Registry
**Decision**: Per-connection for WebSocket, per-request for HTTP

**WebSocket:**
```python
class WSXHandler:
    envelopes: dict[str, RequestEnvelope]  # internal_id → envelope
```
- Request arrives → create envelope, store in `envelopes[internal_id]`
- Process
- Respond
- Cleanup: `del envelopes[internal_id]`
- Connection closes → automatic cleanup of all envelopes

**HTTP:**
- Envelope lives in request scope, no registry needed
- Created at request start, destroyed at response end

### 8. ID Strategy
**Decision**: Always generate internal ID, preserve external ID

- `internal_id`: Server-generated (uuid or sequential), always present
- `external_id`: Client-provided (e.g., WSX message `id`), optional
- Response echoes `external_id` for client correlation
- Internal tracking uses `internal_id`

```python
# src/genro_asgi/utils.py

def url_from_scope(
    scope: Scope,
    default_scheme: str = "http",
) -> URL:
    """
    Construct URL from ASGI scope.

Supports:
    - scheme from scope (http/https, ws/wss), with fallback
    - host/port from server; fallback Host header; fallback localhost
    - default port omission (80/443)
    - path = root_path + path, default "/"
    - query_string decode latin-1
    """
    ...
```

```python
# src/genro_asgi/envelope.py

@dataclass
class RequestEnvelope:
    ...

@classmethod
    def from_http(cls, request: Request) -> RequestEnvelope:
        """Create envelope from HTTP request."""
        ...

@classmethod
    def from_wsx(cls, message: WSXMessage) -> RequestEnvelope:
        """Create envelope from WSX message."""
        ...

@dataclass
class ResponseEnvelope:
    ...

def to_http(self) -> Response:
        """Convert to HTTP Response."""
        ...

def to_wsx(self) -> WSXMessage:
        """Convert to WSX message."""
        ...
```

```python
def detect_tytx(text: str) -> tuple[str, bool]:
    """
    Detect and strip ::TYTX marker.

Returns:
        (content, is_tytx) - content without marker, flag if marker was present
    """
    if text.endswith("::TYTX"):
        return text[:-6], True
    return text, False

def append_tytx(text: str) -> str:
    """Append ::TYTX marker to text."""
    return text + "::TYTX"
```

- Remove duplicate URL construction, use `url_from_scope()`
- Update `receive_json()` to auto-detect TYTX
- Update `send_json()` to respect `tytx_mode`

- [ ] Create `src/genro_asgi/utils.py` with `url_from_scope()`
- [ ] Create `src/genro_asgi/envelope.py` with `RequestEnvelope`, `ResponseEnvelope`
- [ ] Add TYTX helpers: `detect_tytx()`, `append_tytx()`
- [ ] Refactor `Request.url` to use `url_from_scope()`
- [ ] Refactor `WebSocket.url` to use `url_from_scope()`
- [ ] Tests for URL construction (all edge cases)
- [ ] Tests for TYTX detection/append
- [ ] Tests for Envelope creation from HTTP/WSX
- [ ] Update docstrings
- [ ] Commit

1. Write docstring for `utils.py` (Step 2)
2. Get approval
3. Write tests (Step 3)
4. Implement (Step 4)
5. Commit (Step 6)

## Source: plan_2025_12_29/14-openapi-info.md

**Stato**: ⚠️ PARZIALMENTE IMPLEMENTATO
**File**: `src/genro_asgi/server.py`, `src/genro_asgi/application.py`
**Data**: 2025-12-29

Il documento originale proponeva:
- `openapi_info` come dict su ogni RoutingClass
- Merge automatico dalla catena parent (child eredita campi mancanti)
- Property `self.routing.openapi_info` su `_RoutingProxy`
- Server popola `openapi_info` da config.yaml
- Endpoint `_openapi/shop` → info di Shop con merge dal parent

```python
# application.py
class AsgiApplication(RoutingClass):
    """Base class for apps mounted on AsgiServer."""

openapi_info: ClassVar[dict[str, Any]] = {}
```

Le app definiscono le proprie info:

```python
class ShopApp(AsgiApplication):
    openapi_info = {
        "title": "Shop API",
        "version": "1.0.0",
        "description": "E-commerce API"
    }
```

```python
# server.py
class AsgiServer(RoutingClass):
    def __init__(self, ...):
        # ...
        # OpenAPI info from config (plain dict via property)
        self.openapi_info: dict[str, Any] = self.config.openapi
```

```yaml
openapi:
  title: "Demo Shop API"
  version: "1.0.0"
  description: "A sample e-commerce API"
  contact:
    name: "Genropy Team"
```

```python
# server.py
@route("root", meta_mime_type="application/json")
def _openapi(self, *args: str) -> dict[str, Any]:
    """OpenAPI schema endpoint."""
    basepath = "/".join(args) if args else None
    paths = self.router.nodes(basepath=basepath, mode="openapi")
    return {
        "openapi": "3.1.0",
        "info": self.openapi_info,  # ← usa info del server
        **paths,
    }
```

Il piano proponeva merge automatico child → parent:

```python
# PIANO (NON implementato)
@property
def openapi_info(self) -> dict:
    """OpenAPI info con merge dalla catena parent."""
    result = {"title": "API", "version": "0.1.0"}
    chain: list[dict] = []
    current: RoutingClass | None = self._owner
    while current is not None:
        info = getattr(current, 'openapi_info', None)
        if info:
            chain.append(info)
        current = getattr(current, '_routing_parent', None)
    for info in reversed(chain):
        result.update(info)
    return result
```

Attualmente ogni livello usa solo le proprie info, senza merge.

Il piano proponeva:
- `_openapi` → info del Server
- `_openapi/shop` → info di Shop (con merge)
- `_openapi/shop/article` → info di Article (con merge)

Attualmente `_openapi` con args filtra solo i paths, non cambia le info.

Il metodo per risolvere un basepath a una RoutingClass non è implementato.

```
GET /_openapi
    │
    ▼
AsgiServer._openapi()
    │
    ├── basepath = None
    ├── paths = self.router.nodes(mode="openapi")
    └── return {"openapi": "3.1.0", "info": self.openapi_info, **paths}

GET /_openapi/shop
    │
    ▼
AsgiServer._openapi("shop")
    │
    ├── basepath = "shop"
    ├── paths = self.router.nodes(basepath="shop", mode="openapi")
    └── return {"openapi": "3.1.0", "info": self.openapi_info, **paths}
                                           ↑
                                    Info del SERVER, non di Shop!
```

Le app usano `openapi_info` per la splash page di default:

```python
# application.py
@route(meta_mime_type="text/html")
def index(self) -> str:
    """Return HTML splash page. Override for custom index."""
    info = getattr(self, "openapi_info", {})
    title = info.get("title", self.__class__.__name__)
    version = info.get("version", "")
    description = info.get("description", "")
    # ... genera HTML ...
```

E in GenroApiApp/SwaggerApp per l'endpoint `openapi()`:

```python
# swagger/main.py
if app and app in self.server.apps:
    instance = self.server.apps[app]
    title = getattr(instance, "title", app)  # NON usa openapi_info!
    version = getattr(instance, "version", "1.0.0")
```

**Nota**: SwaggerApp non usa `openapi_info` ma cerca `title`/`version` direttamente.

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Demo Shop API",
    "version": "1.0.0",
    "description": "A sample e-commerce API"
  },
  "paths": {
    "/shop/products": {...},
    "/shop/orders": {...}
  }
}
```

```json
{
  "openapi": "3.1.0",
  "info": {
    "title": "Shop API",           // ← da ShopApp.openapi_info
    "version": "1.0.0",            // ← ereditato
    "description": "E-commerce API", // ← da ShopApp.openapi_info
    "contact": {...}               // ← ereditato da server
  },
  "paths": {...}
}
```

```yaml
openapi:
  title: "Demo Shop API"
  version: "1.0.0"
  description: "A sample e-commerce API"
  contact:
    name: "Genropy Team"
    email: "info@genropy.org"
  license:
    name: "Apache 2.0"
  servers:
    - url: "https://api.example.com"
      description: "Production server"
```

Tutti questi campi vengono passati a `self.openapi_info` nel server.

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| `openapi_info` su RoutingClass | ✅ Su AsgiApplication | ✅ Class variable |
| `openapi_info` da config.yaml | ✅ Su AsgiServer | ✅ `self.config.openapi` |
| Merge gerarchico | Proposto | ❌ Non implementato |
| `_openapi/{basepath}` con info diverse | Proposto | ❌ Usa sempre info server |
| `_RoutingProxy.openapi_info` | Proposto | ❌ Non implementato |
| `_resolve_routing_class` | Proposto | ❌ Non implementato |

1. [ ] Implementare `openapi_info` property in `_RoutingProxy` (genro-routes)
2. [ ] Implementare `_resolve_routing_class(basepath)` nel server
3. [ ] Aggiornare `_openapi()` per usare info del target, non del server
4. [ ] Aggiornare SwaggerApp per usare `openapi_info` invece di `title`/`version`
5. [ ] Test per merge gerarchico

**Ultimo aggiornamento**: 2025-12-29

## Source: plan_2025_12_29/13-swagger-app.md

**Stato**: ✅ IMPLEMENTATO E VERIFICATO
**File**: `applications/swagger/main.py` (80 linee)
**Risorse**: `applications/swagger/resources/index.html`
**Data**: 2025-12-29

Il documento originale proponeva:
- SwaggerApp come applicazione standalone per esplorare API OpenAPI
- Struttura `applications/swagger/` con risorse proprie
- Endpoints: `index()` per UI, `openapi()` per schema
- Welcome page con menu dropdown per API predefinite
- Auto-load via param `?url=...`
- Supporto CORS per cross-origin

```
applications/swagger/
├── __init__.py
├── main.py             # SwaggerApp class (80 linee)
├── config.yaml         # Config standalone per sviluppo
└── resources/
    └── index.html      # Swagger UI HTML
```

```python
"""SwaggerApp - OpenAPI/Swagger documentation app."""

from pathlib import Path
from genro_routes import route
from genro_asgi import AsgiApplication

class SwaggerApp(AsgiApplication):
    """Swagger UI and OpenAPI schema app.

Mount in config.yaml:
        apps:
          _swagger:
            module: "applications.swagger:SwaggerApp"
    """

openapi_info = {
        "title": "Swagger UI",
        "version": "1.0.0",
        "description": "OpenAPI/Swagger documentation interface",
    }

@route()
    def index(self):
        """Swagger UI page with toolbar."""
        return self.load_resource(name="index.html")

@route()
    def openapi(self, app: str = "") -> dict:
        """OpenAPI schema."""
        if not self.server:
            return {"openapi": "3.0.3", "info": {"title": "API", "version": "1.0.0"}, "paths": {}}

# Get auth_tags and capabilities from current request
        request = self.server.request
        auth_tags = request.auth_tags if request else ""
        capabilities = request.capabilities if request else ""

if app and app in self.server.apps:
            instance = self.server.apps[app]
            if hasattr(instance, "api"):
                paths = instance.api.nodes(
                    mode="openapi",
                    auth_tags=auth_tags,
                    env_capabilities=capabilities,
                ).get("paths", {})
                title = getattr(instance, "title", app)
                version = getattr(instance, "version", "1.0.0")
            else:
                paths = {}
                title = app
                version = "1.0.0"
        else:
            paths = self.server.router.nodes(
                mode="openapi",
                auth_tags=auth_tags,
                env_capabilities=capabilities,
            ).get("paths", {})
            title = "GenroASGI API"
            version = "1.0.0"

return {
            "openapi": "3.0.3",
            "info": {"title": title, "version": version},
            "paths": paths,
        }
```

| Path | Metodo | Descrizione |
|------|--------|-------------|
| `/_swagger/` | GET | Swagger UI HTML |
| `/_swagger/openapi` | GET | OpenAPI schema |
| `/_swagger/openapi?app=shop` | GET | OpenAPI per app specifica |

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `app` | str | "" | Nome app (vuoto = server router) |

L'app usa `self.load_resource()` per caricare risorse:

```python
@route()
def index(self):
    """Swagger UI page with toolbar."""
    return self.load_resource(name="index.html")
```

`load_resource()` è ereditato da `AsgiApplication` e usa il `ResourceLoader` del server con fallback gerarchico.

L'endpoint `openapi()` filtra gli endpoint visibili in base alle credenziali:

```python
# Get auth_tags and capabilities from current request
request = self.server.request
auth_tags = request.auth_tags if request else ""
capabilities = request.capabilities if request else ""

paths = self.server.router.nodes(
    mode="openapi",
    auth_tags=auth_tags,           # ← filtro per permessi
    env_capabilities=capabilities,  # ← filtro per capabilities
).get("paths", {})
```

Un utente senza tag `admin` non vedrà endpoint protetti con `auth_tags="admin"` nello schema OpenAPI.

```yaml
apps:
  shop:
    module: "shop:ShopApp"

_swagger:
    module: "applications.swagger:SwaggerApp"
```

```yaml
# applications/swagger/config.yaml
server:
  host: "127.0.0.1"
  port: 8001
  main_app: _swagger

middleware:
  auth: on
  cors: on

auth_middleware:
  bearer:
    reader_token:
      token: "tk_reader123"
      tags: "read"

apps:
  _swagger:
    module: "main:SwaggerApp"
```

```bash
cd applications/swagger
python -m genro_asgi serve . --port 8001
```

L'HTML in `resources/index.html` usa Swagger UI bundle da CDN:
- Non fa auto-load all'apertura (solo se `?url=` presente)
- Menu include "This server (/_openapi)" come prima opzione
- Supporta selezione da dropdown o campo libero

| Aspetto | SwaggerApp | GenroApiApp |
|---------|------------|-------------|
| UI | Swagger UI standard | Custom explorer |
| Tree view | No | Sì, gerarchico |
| Lazy loading | No | Sì |
| Doc singoli nodi | No | Sì via `getdoc()` |
| Tester | Swagger UI integrato | Custom |
| Uso tipico | Docs standard OpenAPI | Esplorazione avanzata |

| Aspetto | Piano 2025-12-21 | Implementazione |
|---------|------------------|-----------------|
| Welcome page | Menzionato | UI via index.html |
| Menu dropdown | Menzionato | Sì, nel HTML |
| Auto-load | `?url=...` | Supportato da Swagger UI |
| CORS | Menzionato | Via middleware CORS |
| App selection | Via `?app=xxx` | ✅ Implementato |
| auth_tags filtering | Non menzionato | ✅ Implementato |

L'app è testata manualmente. Test automatici per:
- Endpoint `index()` ritorna HTML
- Endpoint `openapi()` ritorna schema valido
- Filtraggio per app specifica

**Ultimo aggiornamento**: 2025-12-29

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

## Source: plan_2025_12_29/10-api-application.md

**Stato**: ❌ NON IMPLEMENTATO
**Priorità**: P2 (Nice to have)
**Data**: 2025-12-29

Il documento originale proponeva:
- `ApiApplication` come subclass specializzata per API M2M
- No session (stateless by design)
- Token auth only
- Rate limiting built-in
- Standard error responses (RFC 7807)

**Non implementato**. Attualmente si usa `AsgiApplication` per tutto.

- `AsgiApplication` - Base class generica
- `AuthMiddleware` - Supporta bearer/basic/JWT
- `Response.set_error()` - Error mapping base

- `ApiApplication` subclass
- Rate limiting built-in
- RFC 7807 error responses
- Helper per auth validation

```python
class ApiApplication(AsgiApplication):
    """Specialized application for M2M APIs.

Features:
    - Stateless by design (no session support)
    - Token authentication helpers
    - Rate limiting per-endpoint or global
    - RFC 7807 Problem Details error responses
    - Standard headers (X-Request-ID, X-RateLimit-*)
    """

# Class-level configuration
    rate_limit: str | None = None  # e.g., "100/minute", "1000/hour"
    require_auth: bool = True       # Require auth by default

openapi_info: ClassVar[dict[str, Any]] = {
        "title": "API",
        "version": "1.0.0",
    }

def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._rate_limiter: RateLimiter | None = None
        if self.rate_limit:
            self._rate_limiter = RateLimiter.from_string(self.rate_limit)

@property
    def auth(self) -> dict[str, Any]:
        """Get auth info. Raises HTTPUnauthorized if not authenticated."""
        request = self.server.request
        if not request:
            raise HTTPUnauthorized("No request context")

auth = request.scope.get("auth")
        if auth is None and self.require_auth:
            raise HTTPUnauthorized("Authentication required")

@property
    def identity(self) -> str | None:
        """Get authenticated identity. None if anonymous."""
        return self.auth.get("identity")

@property
    def tags(self) -> list[str]:
        """Get auth tags."""
        return self.auth.get("tags", [])

def require_tag(self, *required_tags: str, mode: str = "any") -> None:
        """Require specific auth tags.

Args:
            *required_tags: Tags to check
            mode: "any" (at least one) or "all" (all required)

Raises:
            HTTPForbidden: If tags not present
        """
        user_tags = self.tags

if mode == "any":
            if not any(tag in user_tags for tag in required_tags):
                raise HTTPForbidden(f"Requires one of: {', '.join(required_tags)}")
        else:  # all
            missing = [tag for tag in required_tags if tag not in user_tags]
            if missing:
                raise HTTPForbidden(f"Missing required tags: {', '.join(missing)}")

def require_identity(self) -> str:
        """Require authenticated identity.

Returns:
            Identity string

Raises:
            HTTPUnauthorized: If not authenticated
        """
        identity = self.identity
        if identity is None:
            raise HTTPUnauthorized("Authentication required")
        return identity

def problem(
        self,
        status: int,
        title: str,
        detail: str | None = None,
        type_uri: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        """Create RFC 7807 Problem Details response.

Args:
            status: HTTP status code
            title: Short human-readable summary
            detail: Longer explanation (optional)
            type_uri: URI identifying problem type
            **extra: Additional fields

Returns:
            Problem Details dict (set response.status_code manually)
        """
        response = self.server.response
        if response:
            response.status_code = status
            response._media_type = "application/problem+json"

problem = {
            "type": type_uri or "about:blank",
            "title": title,
            "status": status,
        }
        if detail:
            problem["detail"] = detail
        problem.update(extra)

def paginate(
        self,
        items: list[Any],
        page: int = 1,
        per_page: int = 20,
        max_per_page: int = 100,
    ) -> dict[str, Any]:
        """Helper for paginated responses.

Args:
            items: Full list of items
            page: Page number (1-indexed)
            per_page: Items per page
            max_per_page: Maximum allowed per_page

Returns:
            Dict with items, pagination info
        """
        per_page = min(per_page, max_per_page)
        total = len(items)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page

return {
            "items": items[start:end],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }
```

```python
class RateLimiter:
    """Simple rate limiter using token bucket algorithm."""

def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._buckets: dict[str, tuple[int, float]] = {}

@classmethod
    def from_string(cls, spec: str) -> RateLimiter:
        """Parse rate limit spec like "100/minute" or "1000/hour"."""
        limit_str, period = spec.split("/")
        limit = int(limit_str)

windows = {
            "second": 1,
            "minute": 60,
            "hour": 3600,
            "day": 86400,
        }
        window = windows.get(period, 60)

def check(self, key: str) -> tuple[bool, dict[str, int]]:
        """Check if request is allowed.

Args:
            key: Rate limit key (e.g., IP, user ID)

Returns:
            Tuple of (allowed, headers_dict)
            headers_dict contains X-RateLimit-* values
        """
        now = time.time()

if key in self._buckets:
            count, window_start = self._buckets[key]
            if now - window_start > self.window:
                # Window expired, reset
                count = 0
                window_start = now
        else:
            count = 0
            window_start = now

count += 1
        self._buckets[key] = (count, window_start)

remaining = max(0, self.limit - count)
        reset_time = int(window_start + self.window)

headers = {
            "X-RateLimit-Limit": self.limit,
            "X-RateLimit-Remaining": remaining,
            "X-RateLimit-Reset": reset_time,
        }

return count <= self.limit, headers
```

```python
class OrdersApi(ApiApplication):
    """Orders API with rate limiting."""

rate_limit = "100/minute"
    require_auth = True

openapi_info = {
        "title": "Orders API",
        "version": "1.0.0",
    }

@route()
    def list_orders(self, page: int = 1, per_page: int = 20) -> dict:
        """List orders for authenticated user."""
        user_id = self.require_identity()
        orders = self.db.get_orders(user_id)
        return self.paginate(orders, page, per_page)

@route(auth_tags="admin")
    def all_orders(self) -> dict:
        """List all orders (admin only)."""
        self.require_tag("admin")
        return {"orders": self.db.get_all_orders()}

@route()
    def get_order(self, order_id: int) -> dict:
        """Get single order."""
        user_id = self.require_identity()
        order = self.db.get_order(order_id)

if not order:
            return self.problem(
                status=404,
                title="Order not found",
                detail=f"Order {order_id} does not exist",
            )

if order["user_id"] != user_id:
            return self.problem(
                status=403,
                title="Access denied",
                detail="You can only view your own orders",
            )

```yaml
apps:
  orders:
    module: "orders:OrdersApi"

auth_middleware:
  bearer:
    api_key:
      token: "tk_production_key"
      tags: "orders"
    admin_key:
      token: "tk_admin_key"
      tags: "orders,admin"
```

| Aspetto | AsgiApplication | ApiApplication |
|---------|-----------------|----------------|
| Session | Supportata | No (stateless) |
| Avatar | Opzionale | No |
| Auth default | Optional | Required |
| Rate limiting | No | Built-in |
| Error format | Semplice | RFC 7807 |
| Pagination | No | Built-in helper |

```json
{
  "type": "https://api.example.com/errors/insufficient-balance",
  "title": "Insufficient balance",
  "status": 400,
  "detail": "Your account balance of $10 is not enough for $25 purchase",
  "balance": 10,
  "required": 25
}
```

Content-Type: `application/problem+json`

- **ApiApplication class**: 4h
- **RateLimiter**: 2h
- **Problem Details**: 1h
- **Pagination helper**: 1h
- **Tests**: 4h
- **Totale**: ~1.5 giorni

**Ultimo aggiornamento**: 2025-12-29

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

## Source: plan_2025_12_29/spa-manager/02-worker-pool.md

**Stato**: 📋 DA PROGETTARE
**Priorità**: P2 (Necessario per computazioni pesanti)
**Dipendenze**: SpaManager core
**Data**: 2025-12-30

SpaManager gestisce un pool di processi worker per delegare computazioni pesanti, con **affinità utente**: ogni utente viene sempre assegnato allo stesso worker.

```text
┌─────────────────────────────────────────────────────────────┐
│                      AsgiServer                              │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                   SpaManager                         │    │
│  │                                                      │    │
│  │   Users/Sessions/Pages (in-memory)                  │    │
│  │                                                      │    │
│  │   WorkerPool                                        │    │
│  │   ├── Worker 0 ◄── users hash % N == 0             │    │
│  │   ├── Worker 1 ◄── users hash % N == 1             │    │
│  │   ├── Worker 2 ◄── users hash % N == 2             │    │
│  │   └── Worker 3 ◄── users hash % N == 3             │    │
│  │                                                      │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

```python
def get_worker_for_user(self, identity: str) -> Worker:
    """Ritorna sempre lo stesso worker per un dato utente."""
    worker_index = hash(identity) % len(self._workers)
    return self._workers[worker_index]
```

**Vantaggi affinità**:
- Cache locale per utente nel worker
- Nessun conflitto di stato tra worker
- Predicibile e debuggabile

```python
@dataclass
class WorkerInfo:
    worker_id: int
    process: Process
    queue_in: Queue          # Task da eseguire
    queue_out: Queue         # Risultati
    assigned_users: set[str] # Utenti assegnati (per stats)

class WorkerPool:
    """Pool di worker processes con affinità utente."""

__slots__ = ("_workers", "_num_workers")

def __init__(self, num_workers: int = 4) -> None:
        self._num_workers = num_workers
        self._workers: list[WorkerInfo] = []

async def start(self) -> None:
        """Avvia i worker processes."""
        for i in range(self._num_workers):
            queue_in = Queue()
            queue_out = Queue()
            process = Process(
                target=worker_main,
                args=(i, queue_in, queue_out),
            )
            process.start()
            self._workers.append(WorkerInfo(
                worker_id=i,
                process=process,
                queue_in=queue_in,
                queue_out=queue_out,
                assigned_users=set(),
            ))

async def stop(self) -> None:
        """Ferma tutti i worker."""
        for worker in self._workers:
            worker.queue_in.put(None)  # Segnale di stop
            worker.process.join(timeout=5)
            if worker.process.is_alive():
                worker.process.terminate()

def get_worker(self, identity: str) -> WorkerInfo:
        """Ritorna il worker assegnato all'utente."""
        idx = hash(identity) % self._num_workers
        worker = self._workers[idx]
        worker.assigned_users.add(identity)
        return worker

async def submit(self, identity: str, task: dict) -> Any:
        """Sottomette task al worker dell'utente."""
        worker = self.get_worker(identity)
        task_id = uuid()

worker.queue_in.put({
            "task_id": task_id,
            "identity": identity,
            **task,
        })

# Attendi risultato (async)
        result = await self._wait_result(worker, task_id)
        return result

async def _wait_result(self, worker: WorkerInfo, task_id: str) -> Any:
        """Attende risultato dal worker."""
        # Implementazione con asyncio.Queue o polling
        ...
```

```python
def worker_main(worker_id: int, queue_in: Queue, queue_out: Queue) -> None:
    """Main loop del worker process."""
    while True:
        task = queue_in.get()

if task is None:  # Segnale di stop
            break

task_id = task.pop("task_id")
        identity = task.pop("identity")

try:
            result = execute_task(task)
            queue_out.put({
                "task_id": task_id,
                "success": True,
                "result": result,
            })
        except Exception as e:
            queue_out.put({
                "task_id": task_id,
                "success": False,
                "error": str(e),
            })
```

```python
class SpaManager:
    def __init__(
        self,
        server: AsgiServer,
        num_workers: int = 4,
        # ... altri parametri
    ) -> None:
        self._worker_pool = WorkerPool(num_workers)
        # ...

async def on_startup(self) -> None:
        await self._worker_pool.start()

async def on_shutdown(self) -> None:
        await self._worker_pool.stop()

async def delegate_to_worker(self, identity: str, task: dict) -> Any:
        """Delega task al worker dell'utente."""
        return await self._worker_pool.submit(identity, task)
```

```python
class MyApp(AsgiApplication):

@route("heavy_computation")
    async def heavy_computation(self, data: dict) -> dict:
        """Delega computazione pesante al worker."""
        identity = self.request.auth.get("identity", "anonymous")

result = await self.server.spa_manager.delegate_to_worker(
            identity,
            {"type": "compute", "data": data}
        )

```yaml
spa_manager:
  workers:
    enabled: true
    num_workers: 4          # Default: CPU count
    affinity: user          # user | round_robin | least_loaded
```

| Componente | Effort |
|------------|--------|
| WorkerPool class | 4h |
| Worker process main | 2h |
| Integrazione SpaManager | 2h |
| Tests | 4h |
| **Totale** | ~1.5 giorni |

**Ultimo aggiornamento**: 2025-12-30

