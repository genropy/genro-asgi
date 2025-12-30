# Middleware Chain

Sistema configurazione middleware con auto-discovery.

## BaseMiddleware

```python
class BaseMiddleware(ABC):
    middleware_name: str = ""      # Registry key
    middleware_order: int = 500    # Order (lower = earlier)
    middleware_default: bool = False  # Default on/off

    def __init__(self, app: ASGIApp, **kwargs): ...

    def __init_subclass__(cls):
        # Auto-registrazione in MIDDLEWARE_REGISTRY
```

## Range di Ordine

| Range | Categoria | Esempi |
|-------|-----------|--------|
| 100 | Core | errors |
| 200 | Logging/Tracing | logging |
| 300 | Security | cors, csrf |
| 400 | Authentication | auth |
| 500-800 | Business Logic | custom |
| 900 | Transformation | compression, caching |

## Config YAML

### Format Dict (raccomandato)

```yaml
middleware:
  errors: on      # default=True
  cors: on
  auth: on

cors_middleware:
  allow_origins: ["https://mysite.com"]

auth_middleware:
  bearer:
    api_key:
      token: "tk_xxx"
      tags: "read,write"
```

### Format alternativi

```yaml
# String (legacy)
middleware: cors, auth

# List (legacy)
middleware:
  - cors
  - auth
```

## middleware_chain()

```python
def middleware_chain(
    middleware_config: str | list[str] | dict[str, Any],
    app: ASGIApp,
    full_config: Any = None,
) -> ASGIApp:
    # 1. Parse config in {name: enabled}
    # 2. Collect enabled + class default
    # 3. Sort by order
    # 4. Build chain (reversed)
```

## Flusso Catena

```
Request →
    ErrorMiddleware (100, outermost)
    └── CorsMiddleware (300)
        └── AuthMiddleware (400)
            └── Dispatcher (innermost)
                Response
```

## headers_dict Decorator

Per middleware che accedono agli headers:

```python
@headers_dict
async def __call__(self, scope, receive, send):
    auth_header = scope["_headers"].get("authorization")
```

## Decisioni

- **Auto-discovery** - Import automatico moduli in `middleware/`
- **Class defaults** - `middleware_order` e `middleware_default` nelle classi
- **Config per nome** - `{name}_middleware` per parametri specifici
- **Ordine fisso** - Definito dalla classe, non configurabile
