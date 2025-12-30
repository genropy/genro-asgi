# AuthMiddleware

Autenticazione con O(1) lookup.

## Config YAML

```yaml
middleware:
  auth: on

auth_middleware:
  bearer:
    reader_token:
      token: "tk_abc123"
      tags: "read"
  basic:
    admin:
      password: "secret"
      tags: "admin"
  jwt:
    internal:
      secret: "my-secret"
      algorithm: "HS256"
```

## Preprocessing (Init)

| Tipo | Chiave lookup | Valore |
|------|---------------|--------|
| bearer | token value | `{tags, identity}` |
| basic | base64(user:pass) | `{tags, identity}` |
| jwt | config name | `{secret, algorithm, default_tags}` |

## scope["auth"] Output

```python
# Bearer
{"tags": ["read"], "identity": "reader_token", "backend": "bearer"}

# Basic
{"tags": ["admin"], "identity": "admin", "backend": "basic"}

# JWT
{"tags": ["read"], "identity": "sub_from_token", "backend": "jwt:internal"}

# No header
None
```

## Comportamento

| Scenario | Risultato |
|----------|-----------|
| No Authorization header | `scope["auth"] = None`, procede |
| Header valido | `scope["auth"] = {...}` |
| Header invalido | `HTTPException(401)` |

## Flusso

1. AuthMiddleware estrae header Authorization
2. Dispatch dinamico: `_auth_{type}(credentials)`
3. Bearer fa fallback a JWT se token non trovato
4. Risultato in `scope["auth"]` e `scope["auth_tags"]`
5. Dispatcher passa `auth_tags` a `router.node()`

## Metodo verify_credentials

Per endpoint login:
```python
middleware.verify_credentials("user", "pass") -> {"tags": [...], "identity": "user"} | None
```

## Decisioni

- **O(1) lookup** - preprocessing in `__init__`
- **Bearer fallback JWT** - token bearer non trovato → prova come JWT
- **401 solo se header presente e invalido** - no header = anonimo
