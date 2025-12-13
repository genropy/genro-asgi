# Creating Applications

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2025-12-13

## Introduction

Questa guida spiega come creare applicazioni per genro-asgi. Un'app è un modulo autocontenuto che può essere montato su `AsgiServer`.

## Quick Start

### 1. Creare una semplice app

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

### 2. Registrarla nel server

```yaml
# config.yaml
apps:
  myapp:
    module: "myapp.app:MyApp"
```

### 3. Avviare il server

```bash
python -m genro_asgi --config config.yaml
```

L'app risponde a:
- `GET /myapp/index` → `{"message": "Hello from MyApp!"}`
- `GET /myapp/hello/world` → `{"message": "Hello, world!"}`

## App Structure

### Minimal (single file)

```
myapp/
└── app.py
```

### Standard (with config)

```
myapp/
├── __init__.py
├── app.py
└── config.yaml
```

### Full (with middleware and plugins)

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

## Configuration

### App config.yaml

Ogni app può avere un proprio `config.yaml`:

```yaml
# myapp/config.yaml

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

### Accedere alla configurazione

```python
class MyApp(AsgiApplication):
    def __init__(self, setting1: str, setting2: int = 10):
        self.setting1 = setting1
        self.setting2 = setting2
```

I valori da `config.yaml` vengono passati automaticamente al costruttore.

## Mounting Apps

### Method 1: Module reference

```yaml
apps:
  api:
    module: "myapp.app:MyApp"
    setting1: "inline_value"
```

### Method 2: Path reference

```yaml
apps:
  api:
    path: "./myapp"
```

Con path reference, genro-asgi:
1. Cerca `./myapp/config.yaml`
2. Importa l'app da `./myapp/__init__.py` o `./myapp/app.py`
3. Passa i parametri dal config.yaml

## App Middleware

Le app possono avere middleware propri che si applicano solo alle richieste per quell'app.

### Definire middleware inline

```yaml
# myapp/config.yaml
middleware:
  - type: "compression"
    level: 6
  - type: "cache"
    max_age: 3600
```

### Definire middleware custom

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

## App Plugins

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

## Examples

### Static Site App

Usa l'app built-in `StaticSite`:

```yaml
apps:
  docs:
    module: "genro_asgi:StaticSite"
    directory: "./public"
    name: "docs"
```

### API App

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

### App with Resources

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

## Best Practices

### 1. Keep apps focused

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

### 2. Use config.yaml for settings

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

### 3. Use app middleware for app-specific concerns

```yaml
# myapp/config.yaml
middleware:
  - type: "auth"  # Only for this app
```

### 4. Namespace your routes

Il prefix dell'app (nome nel config) è automatico. I tuoi routes sono relativi.

```python
@route("users")  # Becomes /myapp/users
def list_users(self):
    pass
```

## See Also

- [Architecture: Applications](../architecture/applications.md) - Dettagli tecnici
- [Configuration](../interview/answers/E-configuration.md) - Sistema di configurazione
- [Routing](../interview/answers/D-routing.md) - Come funziona il routing
