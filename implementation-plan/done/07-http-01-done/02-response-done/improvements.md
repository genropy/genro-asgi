# Block 05bis: Response Improvements - Analisi

**Scopo**: Miglioramenti e correzioni per il modulo response.py
**Status**: 🔴 DA REVISIONARE
**Dipendenze**: Block 05 (response.py) completato

---

## Panoramica

Questo documento analizza le criticità emerse dopo l'implementazione del Block 05
e propone soluzioni per ciascuna.

---

## 🔴 Criticità Alta: Blocking I/O in FileResponse

### Problema

`FileResponse` usa I/O sincrono nel metodo `__call__`:

```python
with open(self.path, "rb") as f:
    while True:
        chunk = f.read(self.chunk_size)  # BLOCKING!
        await send(...)
```

Ogni `f.read()` blocca l'intero event loop. Con molti download simultanei,
il server smette di rispondere ad altre richieste.

### Soluzioni Possibili

#### Soluzione A: `asyncio.to_thread()` (Python 3.9+)

```python
import asyncio

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

#### Soluzione B: `run_in_executor` per ogni chunk

```python
import asyncio

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

#### Soluzione C: Memory-mapped file (mmap)

```python
import mmap

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

#### Soluzione D: Chunk piccoli + yield control

```python
import asyncio

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

#### Soluzione E: Documentare + raccomandare reverse proxy

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

    ...
    """
```

**Pro**: Semplice, onesto, pratico
**Contro**: Non risolve il problema tecnico

### Confronto Soluzioni

| Soluzione | Complessità | Performance | Zero-deps | Note |
|-----------|-------------|-------------|-----------|------|
| A: to_thread | Media | Buona | ✅ | Non funziona con generator |
| B: run_in_executor | Media | Buona | ✅ | **Raccomandato** |
| C: mmap | Alta | Ottima | ✅ | Problemi Windows |
| D: sleep(0) | Bassa | Scarsa | ✅ | Hack, non risolve |
| E: Documentare | Nessuna | Invariata | ✅ | Onesto ma limitato |

### Raccomandazione

**Per Alpha**: Soluzione B (`run_in_executor`)

Motivi:
- Stdlib puro (zero dipendenze)
- Risolve effettivamente il problema
- Pattern standard e ben testato
- Overhead accettabile per file serving

**Alternativa conservativa**: Soluzione E (documentare limitation)
- Se si vuole rimandare la complessità
- Con nota che in produzione si usa reverse proxy

---

## 🟠 Criticità Media: Manca set_cookie helper

### Problema

Per settare un cookie l'utente deve:

```python
Response(headers=[("Set-Cookie", "session=123; Path=/; HttpOnly; Secure")])
```

Problemi:
- Scomodo e verboso
- Facile dimenticare attributi di sicurezza (HttpOnly, Secure)
- Encoding del valore non gestito
- Nessuna validazione

### Soluzioni Possibili

#### Soluzione A: Metodo set_cookie() su Response

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

#### Soluzione B: Metodo delete_cookie()

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

#### Soluzione C: Factory function (non metodo)

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

#### Soluzione D: Classe Cookie separata

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

#### Soluzione E: Rimandare

Documentare il pattern manuale nella docstring di Response:

```python
"""
Setting cookies:
    For simple cookies, use header tuples directly::

        Response(headers=[("Set-Cookie", "session=abc123; Path=/; HttpOnly")])

    For multiple cookies::

        Response(headers=[
            ("Set-Cookie", "session=abc123; Path=/; HttpOnly"),
            ("Set-Cookie", "prefs=dark; Path=/; Max-Age=31536000"),
        ])

    A dedicated Cookie helper may be added in a future version.
"""
```

### Confronto Soluzioni

| Soluzione | Ergonomia | Complessità | Coerenza Design | Note |
|-----------|-----------|-------------|-----------------|------|
| A: set_cookie() | Ottima | Media | ❌ Viola immutabilità | Come Starlette |
| B: delete_cookie() | - | Bassa | Dipende da A | Complemento |
| C: make_cookie() | Buona | Bassa | ✅ | Funzione pura |
| D: Classe Cookie | Buona | Media | ✅ | Più strutturato |
| E: Rimandare | - | Nessuna | ✅ | Onesto |

### Raccomandazione

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

---

## 🟡 Criticità Minore: Status Code 204 con body

### Problema

È possibile creare:

```python
Response(status_code=204, content="body")  # Viola RFC!
```

HTTP RFC specifica che 204 No Content e 304 Not Modified NON devono avere body.

### Soluzioni Possibili

#### Soluzione A: Validazione nel costruttore

```python
NO_BODY_STATUS_CODES = {204, 304}

def __init__(self, content=None, status_code=200, ...):
    if status_code in NO_BODY_STATUS_CODES and content:
        raise ValueError(f"Status {status_code} must not have body content")
    ...
```

**Pro**: Previene errori
**Contro**: Viola principio "nessuna validazione" già stabilito

#### Soluzione B: Ignorare body silenziosamente

```python
def __init__(self, content=None, status_code=200, ...):
    if status_code in NO_BODY_STATUS_CODES:
        content = None  # Ignora body per questi status
    ...
```

**Pro**: Evita problemi server
**Contro**: Comportamento sorprendente, nasconde errori utente

#### Soluzione C: Warning in docstring

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

#### Soluzione D: Nessuna azione

Lasciare la responsabilità all'utente e al server ASGI.

### Raccomandazione

**Per Alpha**: Soluzione C (Warning in docstring)

Motivi:
- Coerente con decisione "nessuna validazione"
- HTTPException non valida status codes
- Documentazione chiara
- Server ASGI gestirà appropriatamente

---

## 🟡 Criticità Minore: StreamingResponse charset

### Problema

`StreamingResponse` non auto-appende charset per text/* media types come fa `Response`:

```python
# Response aggiunge charset
Response(media_type="text/plain")  # -> "text/plain; charset=utf-8"

# StreamingResponse NO
StreamingResponse(content=gen(), media_type="text/plain")  # -> "text/plain"
```

### Soluzione

Allineare comportamento:

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

### Raccomandazione

**Per Alpha**: Implementare la correzione

È una piccola modifica che allinea il comportamento con Response.

---

## Piano di Implementazione

### Priorità e Tempistiche

| # | Criticità | Azione | Priorità | Complessità |
|---|-----------|--------|----------|-------------|
| 1 | 🔴 FileResponse I/O | run_in_executor | Alta | Media |
| 2 | 🟠 set_cookie | make_cookie() function | Media | Bassa |
| 3 | 🟡 204 body | Docstring warning | Bassa | Nessuna |
| 4 | 🟡 Streaming charset | Fix charset append | Bassa | Bassa |

### Modifiche Proposte

#### 1. FileResponse: Async I/O con run_in_executor

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

#### 2. make_cookie() function

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

#### 3. Docstring warnings

**File**: `src/genro_asgi/response.py`

Aggiungere note a:
- `Response.__init__` docstring: nota su 204/304
- `FileResponse` class docstring: già OK (sync I/O warning può essere rimosso dopo fix)

#### 4. StreamingResponse charset fix

**File**: `src/genro_asgi/response.py`

Modificare `StreamingResponse.__init__` per auto-append charset.

---

## Checklist Implementazione

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

---

## Decisioni Finali

| # | Item | Decisione |
|---|------|-----------|
| 1 | FileResponse I/O | **DA DECIDERE**: run_in_executor o documentare? |
| 2 | set_cookie | **DA DECIDERE**: make_cookie() function? |
| 3 | 204 body | Docstring warning (nessuna validazione) |
| 4 | Streaming charset | Fix per coerenza |

---

## Prossimi Passi

1. **Confermare decisioni** su punti 1 e 2 ← SIAMO QUI
2. Implementare modifiche
3. Test
4. Commit come "fix(response): improve FileResponse async I/O and add cookie helper"
5. Proseguire con Block 06 (websockets)
