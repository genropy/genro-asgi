# Docstring Remediation Plan - genro-asgi

**Data**: 2024-12-31
**Standard**: Google Style Python Docstrings
**Stato**: 🔴 DA REVISIONARE

---

## Obiettivo

Portare tutte le docstring del progetto a:
- **100%** copertura metodi pubblici
- **90%+** copertura metodi privati (quelli non banali)
- **100%** aderenza Google Style
- **English only** - Nessun commento/docstring in italiano

---

## Piano di Intervento

### Fase 1: Critici (Priorità Alta)

#### 1.1 `applications/server_application.py` 🔴

**Effort stimato**: 1-2 ore

**Interventi**:

1. **Riscrivere docstring modulo** (linee 4-14)
   ```python
   """System endpoints for AsgiServer.

   This module provides built-in endpoints for server-level operations,
   automatically mounted at /_server/ path.

   Endpoints:
       /: Index page with redirect to main application
       /openapi: OpenAPI schema generation
       /resource/<path>: Hierarchical resource loader with fallback
       /create_jwt: JWT token creation (requires superadmin auth)

   The ServerApplication implements RoutingClass interface and integrates
   with genro-routes for endpoint routing.

   Example:
       Server automatically mounts this application:

       server = AsgiServer()
       # ServerApplication available at /_server/
   """
   ```

2. **Tradurre commenti italiani in inglese** (linea 60 e altri)

3. **Documentare metodi HTTP**:
   - `index()` - Args, Returns, comportamento redirect
   - `openapi()` - Args, Returns, formato schema
   - `load_resource()` - Args, Returns, Raises, algoritmo fallback
   - `create_jwt()` - Args, Returns, Raises, requisiti auth

**Template per metodo HTTP**:
```python
@route("openapi")
def openapi(self, format: str = "json") -> dict | str:
    """Generate OpenAPI schema for the server.

    Produces OpenAPI 3.0 specification documenting all mounted
    applications and their routes.

    Args:
        format: Output format, either "json" or "yaml". Defaults to "json".

    Returns:
        OpenAPI schema as dict (json) or string (yaml).

    Raises:
        ValueError: If format is not "json" or "yaml".

    Example:
        GET /_server/openapi?format=yaml
    """
```

---

#### 1.2 `middleware/errors.py` 🔴

**Effort stimato**: 30 min

**Interventi**:

1. **`_send_redirect()`** (linea 58)
   ```python
   async def _send_redirect(self, send: Send, exc: Redirect) -> None:
       """Send HTTP redirect response to client.

       Args:
           send: ASGI send callable for response transmission.
           exc: Redirect exception containing target URL and status code.

       Note:
           Uses exc.status_code (default 307) and exc.url for Location header.
       """
   ```

2. **`_send_http_error()`** (linea 69)
   ```python
   async def _send_http_error(self, send: Send, exc: HTTPException) -> None:
       """Send HTTP error response with JSON body.

       Args:
           send: ASGI send callable for response transmission.
           exc: HTTPException with status_code, detail, and optional headers.

       Note:
           Response body format: {"error": exc.detail}
           Content-Type: application/json
       """
   ```

3. **`_send_server_error()`** (linea 86)
   ```python
   async def _send_server_error(
       self, send: Send, exc: Exception, include_traceback: bool
   ) -> None:
       """Send 500 Internal Server Error response.

       Args:
           send: ASGI send callable for response transmission.
           exc: The caught exception.
           include_traceback: If True, include stack trace in response body.

       Note:
           When include_traceback is False, returns generic error message.
           Traceback is always logged regardless of include_traceback setting.
       """
   ```

---

### Fase 2: Moderati (Priorità Media)

#### 2.1 `request.py`

**Effort stimato**: 30 min

**Interventi**:

1. **`_parse_wsx_message()`** (linea 516)
   ```python
   def _parse_wsx_message(self, message: Message) -> tuple[str, Any]:
       """Parse WebSocket message extracting type and data.

       Args:
           message: ASGI WebSocket message dict with 'type' key.

       Returns:
           Tuple of (message_type, data) where:
           - message_type: One of 'text', 'bytes', 'disconnect'
           - data: Message payload (str, bytes, or None)

       Raises:
           ValueError: If message type is not recognized.

       Note:
           Handles websocket.receive, websocket.disconnect message types.
       """
   ```

---

#### 2.2 `response.py`

**Effort stimato**: 20 min

**Interventi**:

1. **`_encode_content()`** (linea 190)
   ```python
   def _encode_content(self, content: Any) -> bytes:
       """Encode response content to bytes.

       Args:
           content: Content to encode. Can be str, bytes, dict, or None.

       Returns:
           Encoded content as bytes.

       Note:
           - str: Encoded using response charset (default utf-8)
           - bytes: Returned as-is
           - dict/list: JSON encoded
           - None: Returns empty bytes
       """
   ```

---

#### 2.3 Middleware components

**Effort stimato**: 1 ora (tutti)

**File**: `cors.py`, `authentication.py`, `compression.py`

**Pattern comune per metodi privati middleware**:
```python
async def _process_request(self, scope: Scope, receive: Receive) -> dict:
    """Process incoming request before passing to next middleware.

    Args:
        scope: ASGI scope dictionary.
        receive: ASGI receive callable.

    Returns:
        Modified scope or processing result dict.

    Note:
        Called before the wrapped application handles the request.
    """
```

---

### Fase 3: Minori (Priorità Bassa)

#### 3.1 Uniformare quote style

**Intervento**: Usare sempre `"""` (triple double quotes)

**File interessati**: Scan completo, sostituire `'''` con `"""`

---

#### 3.2 Aggiungere Examples dove mancano

**Moduli target** (quelli senza `__main__` o examples inline):
- `middleware/cors.py`
- `middleware/authentication.py`
- `datastructures/state.py`

---

## Checklist di Completamento

### Fase 1 - Critici
- [ ] `server_application.py` - Docstring modulo
- [ ] `server_application.py` - Traduzione italiano → inglese
- [ ] `server_application.py` - Metodo `index()`
- [ ] `server_application.py` - Metodo `openapi()`
- [ ] `server_application.py` - Metodo `load_resource()`
- [ ] `server_application.py` - Metodo `create_jwt()`
- [ ] `errors.py` - `_send_redirect()`
- [ ] `errors.py` - `_send_http_error()`
- [ ] `errors.py` - `_send_server_error()`

### Fase 2 - Moderati
- [ ] `request.py` - `_parse_wsx_message()`
- [ ] `response.py` - `_encode_content()`
- [ ] `cors.py` - Metodi privati
- [ ] `authentication.py` - Metodi privati
- [ ] `compression.py` - Metodi privati

### Fase 3 - Minori
- [ ] Uniformare quote style (`"""`)
- [ ] Aggiungere examples mancanti

---

## Riferimenti Google Style

### Docstring Modulo
```python
"""One-line summary.

Extended description. Can reference other modules and provide
context about the module's role in the system.

Example:
    Basic usage example::

        from module import Class
        obj = Class()

Attributes:
    MODULE_CONSTANT: Description of module-level constant.

Todo:
    * Item 1
    * Item 2
"""
```

### Docstring Classe
```python
class ClassName:
    """One-line summary.

    Extended description of the class purpose and behavior.

    Attributes:
        attr1: Description of attr1.
        attr2: Description of attr2.

    Example:
        >>> obj = ClassName("value")
        >>> obj.method()
    """
```

### Docstring Metodo
```python
def method(self, arg1: str, arg2: int = 0) -> bool:
    """One-line summary.

    Extended description if needed.

    Args:
        arg1: Description of arg1.
        arg2: Description of arg2. Defaults to 0.

    Returns:
        Description of return value.

    Raises:
        ValueError: Description of when this is raised.

    Example:
        >>> obj.method("test")
        True

    Note:
        Additional information about behavior or side effects.
    """
```

### Docstring Property
```python
@property
def name(self) -> str:
    """str: One-line description of the property."""
    return self._name
```

---

## Verifica Finale

Dopo completamento di ogni fase, eseguire:

```bash
# Check docstring coverage (se disponibile pydocstyle)
pydocstyle src/genro_asgi/ --convention=google

# Check for Italian text
grep -rn "[àèìòùé]" src/genro_asgi/*.py

# Manual review of changed files
```

---

## Note

- Ogni docstring deve essere **autosufficiente**: leggendolo si deve capire cosa fa il metodo senza leggere il codice
- Preferire **concisione** ma non a scapito della completezza
- I metodi privati (`_method`) vanno documentati se non banali
- I metodi molto semplici (getter/setter) possono avere docstring one-line

---

**Piano creato da**: Claude Code
**Documento correlato**: DOCSTRING_AUDIT_REPORT.md
