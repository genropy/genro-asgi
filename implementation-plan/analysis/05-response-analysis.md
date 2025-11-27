# Block 05: response.py - Analisi Dettagliata

**Scopo**: Classi Response per invio risposte HTTP tramite ASGI.
**Status**: 🟢 APPROVATO

---

## Panoramica del Modulo

Il modulo `response.py` fornisce le classi Response per costruire e inviare
risposte HTTP attraverso l'interfaccia ASGI `send()`.

```
User Code                          ASGI Send
─────────                          ─────────
Response(content, status)          http.response.start (status, headers)
await response(scope, receive, send)  http.response.body (body, more_body)
```

### Classi Proposte dal Piano

| Classe | Uso | Note |
|--------|-----|------|
| Response | Base, content bytes/str | Media type generico |
| JSONResponse | Serializza Python → JSON | orjson fallback |
| HTMLResponse | HTML content | text/html |
| PlainTextResponse | Plain text | text/plain |
| RedirectResponse | HTTP redirect | Location header |
| StreamingResponse | Body da async iterator | Chunked |
| FileResponse | Download file da disco | Content-Disposition |

---

## Decisioni da Prendere

### 1. Nome file: `response.py` (singolare) vs `responses.py` (plurale)

**Problema**: Il piano usa `responses.py` (plurale), ma lo stub esistente è `response.py` (singolare).

| Opzione | Pro | Contro |
|---------|-----|--------|
| `response.py` (singolare) | Coerente con stub, con Starlette | - |
| `responses.py` (plurale) | Coerente col piano | Richiede rename |

**Domanda**: Usare il singolare come per `request.py`?

---

### 2. API Response: `__call__` vs `send()`

**Problema**: Il piano usa `__call__(scope, receive, send)` come interfaccia ASGI.
Lo stub esistente usa `send(send)` che richiede solo il callable send.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `__call__(scope, receive, send)` | Standard ASGI, componibile | receive non usato |
| `send(send)` | Più semplice | Non standard ASGI |

```python
# Piano: __call__
response = Response(content=b"Hello")
await response(scope, receive, send)

# Stub esistente: send()
response = Response(content=b"Hello")
await response.send(send)
```

**Domanda**: Usare `__call__` per coerenza ASGI?

---

### 3. Parametro `status_code` vs `status`

**Problema**: Il piano usa `status_code`, lo stub usa `status`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `status_code` | Esplicito, come Starlette | Più lungo |
| `status` | Più breve | Ambiguo |

**Domanda**: Preferenza?

---

### 4. Headers: `Mapping[str, str]` vs `dict[str, str]`

**Problema**: Il piano accetta `Mapping[str, str] | None`, lo stub `dict[str, str] | None`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `Mapping[str, str]` | Più flessibile (accetta Headers, dict, etc) | - |
| `dict[str, str]` | Specifico | Meno flessibile |

**Nota**: Headers del Block 02 è un Mapping, quindi accettarlo sarebbe utile.

**Domanda**: Usare `Mapping` per flessibilità?

---

### 5. Response base: media_type di default

**Problema**: Il piano ha `media_type: str | None = None` a livello di classe.
Lo stub ha `media_type: str = "text/plain"`.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Default `None` | Nessun Content-Type automatico | Utente deve specificare |
| Default `"text/plain"` | Sempre un content-type | Potrebbe non essere desiderato |

**Comportamento Starlette**: `media_type = None` (nessun default)

**Domanda**: Seguire Starlette con `None` default?

---

### 6. Response base: charset handling

**Problema**: Il piano ha logica per aggiungere charset a text/* media types:
```python
if self.media_type.startswith("text/") and "charset" not in self.media_type:
    return f"{self.media_type}; charset={self.charset}"
```

**Domanda**: Questa logica è corretta? Charset default dovrebbe essere "utf-8"?

---

### 7. StreamingResponse: content come AsyncIterator o AsyncIterable?

**Problema**: Il piano specifica `AsyncIterator[bytes]`, ma `AsyncIterable[bytes]`
sarebbe più flessibile (accetta anche async generators).

```python
# AsyncIterator - solo oggetti con __anext__
async def generate():
    yield b"chunk"

# AsyncIterable - oggetti con __aiter__ (include async generators)
async def generate():
    yield b"chunk"
```

**Nota**: async generators sono `AsyncGenerator` che è sottotipo di `AsyncIterator`,
ma tecnicamente il type hint `AsyncIterator` è corretto per async generators.

**Domanda**: Mantenere `AsyncIterator[bytes]`?

---

### 8. StreamingResponse: supporto sync iterator?

**Problema**: Il piano supporta solo async iterator. Starlette supporta anche sync.

```python
# Solo async (piano)
async def generate():
    yield b"chunk"

# Starlette supporta anche sync
def generate():
    yield b"chunk"
```

**Domanda**: Supportare solo async per semplicità? O anche sync?

---

### 9. FileResponse: lettura sincrona vs asincrona

**Problema**: Il piano usa `open()` sincrono:
```python
with open(self.path, "rb") as f:
    while True:
        chunk = f.read(self.chunk_size)
```

Questo blocca l'event loop per file grandi.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Sync `open()` | Semplice, stdlib | Blocca event loop |
| Async con `aiofiles` | Non blocca | Aggiunge dipendenza |
| Async con thread pool | Non blocca | Complessità |

**Domanda**: Per ora sync è accettabile? O serve async?

---

### 10. FileResponse: gestione file non esistente

**Problema**: Il piano controlla `path.exists()` solo per content-length:
```python
if self.path.exists():
    self._headers["content-length"] = str(self.path.stat().st_size)
```

Ma se il file non esiste, `open()` in `__call__` solleverà `FileNotFoundError`.

**Domanda**: Comportamento OK (eccezione naturale)? O validare nel costruttore?

---

### 11. RedirectResponse: validazione status code

**Problema**: Il piano non valida che status_code sia un redirect code (301, 302, 303, 307, 308).

**Domanda**: Validare o lasciare libertà all'utente?

---

### 12. Response: `__slots__` vs no slots

**Problema**: Le decisioni di design del progetto richiedono `__slots__` ovunque.
Il piano non mostra `__slots__`.

**Domanda**: Aggiungere `__slots__` a tutte le Response classes?

---

### 13. Headers encoding: latin-1 vs utf-8

**Problema**: Il piano usa latin-1 per header encoding:
```python
(k.lower().encode("latin-1"), v.encode("latin-1"))
```

Questo è corretto per HTTP/1.1 (RFC 7230), ma alcuni server potrebbero voler UTF-8.

**Domanda**: Mantenere latin-1 (standard HTTP)?

---

### 14. Content-Length automatico

**Problema**: Il piano NON aggiunge automaticamente Content-Length per Response base.
Solo FileResponse lo aggiunge.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Aggiungere Content-Length | Più completo | Overhead calcolo |
| Non aggiungere | Semplice | Client non sa dimensione |

**Comportamento Starlette**: Aggiunge Content-Length automaticamente.

**Domanda**: Aggiungere Content-Length per Response base?

---

### 15. JSONResponse: ensure_ascii

**Problema**: Il piano usa `ensure_ascii=False` per stdlib json:
```python
json.dumps(content, ensure_ascii=False).encode("utf-8")
```

Questo è corretto per output UTF-8.

**Domanda**: OK così? Servono opzioni per separatori/indent?

---

### 16. Entry point `if __name__ == '__main__'`

**Problema**: Le regole del progetto richiedono entry point per moduli con classe primaria.

**Domanda**: Quale demo per Response? Server mock non è triviale.

---

### 17. Esportazioni in `__init__.py`

**Problema**: Quali classi esportare dal package?

**Piano**: Tutte (Response, JSONResponse, HTMLResponse, PlainTextResponse,
RedirectResponse, StreamingResponse, FileResponse)

**Domanda**: OK esportare tutte?

---

## Domande Aperte Riassunto

1. **Nome file**: `response.py` (singolare) o `responses.py` (plurale)?
2. **API**: `__call__(scope, receive, send)` o `send(send)`?
3. **Parametro**: `status_code` o `status`?
4. **Headers input**: `Mapping[str, str]` o `dict[str, str]`?
5. **Media type default**: `None` o `"text/plain"`?
6. **Charset auto-append**: Per text/* media types?
7. **StreamingResponse type hint**: `AsyncIterator` OK?
8. **Sync iterator support**: Solo async o anche sync?
9. **FileResponse I/O**: Sync blocking OK per ora?
10. **File non esistente**: Eccezione naturale OK?
11. **Redirect status validation**: Validare o no?
12. **`__slots__`**: Aggiungere a tutte le classi?
13. **Header encoding**: latin-1 (standard)?
14. **Content-Length**: Aggiungere automaticamente a Response?
15. **JSONResponse options**: Solo ensure_ascii o più opzioni?
16. **Entry point**: Quale demo?
17. **Exports**: Tutte le classi?

---

## Decisioni Finali

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Nome file | `response.py` (singolare, come request.py) |
| 2 | API | `__call__(scope, receive, send)` - standard ASGI |
| 3 | Parametro | `status_code` - esplicito |
| 4 | Headers | `Mapping[str, str]` - flessibile |
| 5 | Media type | `None` default - come Starlette |
| 6 | Charset | Sì, auto-append per text/* |
| 7 | Streaming type | `AsyncIterator[bytes]` - corretto |
| 8 | Sync iterator | Solo async per semplicità |
| 9 | FileResponse I/O | Sync OK per ora (v1) |
| 10 | File missing | Eccezione naturale OK |
| 11 | Redirect validation | No - libertà utente |
| 12 | `__slots__` | Sì - per efficienza |
| 13 | Header encoding | latin-1 - standard HTTP |
| 14 | Content-Length | **Sì per non-streaming, No per StreamingResponse** |
| 15 | JSON options | Solo base per ora |
| 16 | Entry point | Demo con mock send |
| 17 | Exports | Tutte le classi |

### Nota su Content-Length (decisione #14)

Content-Length viene aggiunto automaticamente **solo** per:

- `Response` (base) - body noto al costruttore
- `JSONResponse` - body noto al costruttore
- `HTMLResponse` - body noto al costruttore
- `PlainTextResponse` - body noto al costruttore
- `RedirectResponse` - body vuoto (Content-Length: 0)
- `FileResponse` - solo se file esiste e size è nota

**NON** viene aggiunto per:

- `StreamingResponse` - size non nota a priori (chunked transfer)

---

## Prossimi Passi

1. ~~Confermare le decisioni~~ ✅ FATTO
2. **Scrivere docstring** modulo (Step 2)
3. **Scrivere test** (Step 3)
4. **Implementare** (Step 4)
5. **Commit** (Step 6)
