# CORS Middleware

Cross-Origin Resource Sharing middleware.

## Classe

```python
class CorsMiddleware(BaseMiddleware):
    middleware_name = "cors"
    middleware_order = 300
    middleware_default = False
```

## Parametri

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `allow_origins` | list[str] | ["*"] | Origini permesse |
| `allow_methods` | list[str] | ["*"] | Metodi permessi |
| `allow_headers` | list[str] | ["*"] | Headers permessi |
| `allow_credentials` | bool | False | Allow cookies/auth |
| `expose_headers` | list[str] | [] | Headers esposti al browser |
| `max_age` | int | 600 | Preflight cache (secondi) |

## Config YAML

```yaml
middleware:
  cors: on

cors_middleware:
  allow_origins: ["https://mysite.com", "https://api.mysite.com"]
  allow_methods: ["GET", "POST", "PUT", "DELETE"]
  allow_headers: ["Authorization", "Content-Type"]
  allow_credentials: true
  max_age: 3600
```

## Comportamento

### Richieste Normali

1. Check origin in `allow_origins`
2. Se permesso, aggiungi headers CORS alla response
3. Se `allow_credentials=true`, aggiungi `access-control-allow-credentials`

### Preflight (OPTIONS)

1. Detect `OPTIONS` + `access-control-request-method`
2. Rispondi 204 con headers CORS completi
3. Non inoltrare alla app

## Headers Response

```
access-control-allow-origin: https://mysite.com
access-control-allow-methods: GET, POST, PUT, DELETE
access-control-allow-headers: Authorization, Content-Type
access-control-allow-credentials: true
access-control-max-age: 3600
vary: Origin
```

## Decisioni

- **Wildcard default** - `["*"]` per sviluppo rapido
- **Vary header** - Aggiunto automaticamente se origin non è `*`
- **Preflight 204** - No body per preflight response
