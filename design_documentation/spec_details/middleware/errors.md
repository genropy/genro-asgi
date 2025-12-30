# Error Middleware

Gestione centralizzata errori HTTP.

## Classe

```python
class ErrorMiddleware(BaseMiddleware):
    middleware_name = "errors"
    middleware_order = 100     # Prima nella catena
    middleware_default = True  # Sempre attivo
```

## Parametri

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `debug` | bool | False | Mostra traceback completi |
| `handler` | Callable | None | Custom error handler |

## Config YAML

```yaml
middleware:
  errors: on  # default già True

errors_middleware:
  debug: true  # Solo in development
```

## Comportamento

| Scenario | Response |
|----------|----------|
| HTTPException | Status + detail dall'eccezione |
| Exception (debug=False) | 500 "Internal Server Error" |
| Exception (debug=True) | 500 + full traceback |
| Response già iniziata | Re-raise (non può modificare) |

## HTTPException

```python
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = "", headers: dict = None):
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
```

Eccezioni predefinite:

```python
HTTPBadRequest       # 400
HTTPUnauthorized     # 401
HTTPForbidden        # 403
HTTPNotFound         # 404
HTTPMethodNotAllowed # 405
HTTPConflict         # 409
HTTPUnprocessable    # 422
HTTPInternalError    # 500
```

## Custom Handler

```python
def my_error_handler(exc: Exception) -> Response:
    if isinstance(exc, ValidationError):
        return JSONResponse(
            {"errors": exc.errors},
            status_code=422
        )
    return JSONResponse(
        {"error": "Internal error"},
        status_code=500
    )

# Config
errors_middleware:
  handler: "myapp:my_error_handler"
```

## Decisioni

- **Default True** - ErrorMiddleware sempre attivo per sicurezza
- **Order 100** - Outermost per catturare tutto
- **Debug off default** - Mai esporre traceback in produzione
- **Re-raise se started** - Non può modificare response già iniziata
