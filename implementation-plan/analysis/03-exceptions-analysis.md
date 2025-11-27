# Block 03: exceptions.py - Analisi Dettagliata

**Scopo**: Classi di eccezione per gestione errori HTTP e WebSocket.

---

## Panoramica del Modulo

Il modulo `exceptions.py` fornisce eccezioni tipizzate per segnalare errori
nel ciclo request/response HTTP e nelle connessioni WebSocket.

```
Tipo Errore                      Eccezione genro-asgi
───────────                      ────────────────────
HTTP 4xx/5xx                     HTTPException(status_code, detail, headers)
WebSocket close con errore       WebSocketException(code, reason)
WebSocket disconnessione client  WebSocketDisconnect(code, reason)
```

---

## Classe 1: HTTPException

### Scopo

Eccezione da sollevare negli handler per ritornare una risposta HTTP di errore.

### Uso Tipico

```python
# In un handler
async def get_user(request):
    user = await db.get_user(request.path_params["id"])
    if not user:
        raise HTTPException(404, detail="User not found")
    return JSONResponse(user)

# Con headers custom
raise HTTPException(
    401,
    detail="Authentication required",
    headers={"WWW-Authenticate": "Bearer realm='api'"}
)
```

### Design Proposto (dal piano)

```python
class HTTPException(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str = "",
        headers: dict[str, str] | None = None
    ) -> None

    def __repr__(self) -> str
```

### Decisioni da Prendere

#### 1. Validazione status_code

**Domanda**: Validare che status_code sia nel range 400-599?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Nessuna validazione** | KISS, flessibile | Permette valori insensati |
| **Validazione 400-599** | Correttezza garantita | Overhead, meno flessibile |
| **Validazione 100-599** | Include tutti i codici HTTP | 1xx/2xx/3xx non sono "errori" |

**Riferimenti**:
- Starlette: nessuna validazione
- FastAPI: nessuna validazione
- Django Rest Framework: nessuna validazione

**Raccomandazione**: Nessuna validazione. Documentare che ci si aspetta 4xx/5xx.

---

#### 2. Tipo di headers

**Domanda**: `dict[str, str]` è sufficiente o serve supporto multi-value?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **dict[str, str]** | Semplice, API chiara | No multi-value (es. Set-Cookie multipli) |
| **dict[str, str \| list[str]]** | Multi-value supportato | API più complessa |
| **list[tuple[str, str]]** | Massima flessibilità | Scomodo da usare |

**Considerazioni**:
- HTTPException è per errori, raramente serve Set-Cookie multiplo
- Se servono header complessi, l'handler può gestirli direttamente
- Casi d'uso comuni (WWW-Authenticate, Retry-After) sono single-value

**Raccomandazione**: `dict[str, str]` per semplicità. Casi edge gestiti a livello handler.

---

#### 3. `__slots__`

**Domanda**: Aggiungere `__slots__` per consistenza con altre classi?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Con `__slots__`** | Consistenza, memoria | Inusuale per Exception |
| **Senza `__slots__`** | Pattern standard | Inconsistenza con datastructures |

**Considerazioni**:
- Le eccezioni con `__slots__` funzionano ma sono inusuali
- Le eccezioni sono tipicamente short-lived, il risparmio memoria è trascurabile
- Exception base non usa `__slots__`

**Raccomandazione**: NON usare `__slots__` per eccezioni. Fanno eccezione alla regola generale.

---

## Classe 2: WebSocketException

### Scopo

Eccezione da sollevare per chiudere una connessione WebSocket con un codice di errore.

### Uso Tipico

```python
async def websocket_handler(websocket):
    message = await websocket.receive_json()
    if not validate(message):
        raise WebSocketException(code=4000, reason="Invalid message format")
```

### WebSocket Close Codes (RFC 6455)

```
Codice    Significato
──────    ───────────
1000      Normal closure
1001      Going away (server shutdown, browser navigating)
1002      Protocol error
1003      Unsupported data type
1006      Abnormal closure (reserved, no close frame)
1007      Invalid payload data
1008      Policy violation
1009      Message too big
1010      Missing extension
1011      Internal server error
1015      TLS handshake failure (reserved)

4000-4999 Application-specific codes (usabili liberamente)
```

### Design Proposto (dal piano)

```python
class WebSocketException(Exception):
    def __init__(
        self,
        code: int = 1000,
        reason: str = ""
    ) -> None

    def __repr__(self) -> str
```

### Decisioni da Prendere

#### 4. Validazione code

**Domanda**: Validare che code sia nel range valido?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Nessuna validazione** | KISS, flessibile | Permette codici riservati |
| **Validazione 1000-4999** | Correttezza | Overhead |

**Raccomandazione**: Nessuna validazione. Come HTTPException, documentare l'uso atteso.

---

#### 5. Default code=1000

**Domanda**: Il default 1000 (normal closure) ha senso per un'eccezione?

**Considerazioni**:
- 1000 = chiusura normale, non è tecnicamente un errore
- Potrebbe essere più appropriato un default come 1011 (internal error)
- Ma 1000 con reason custom è pattern comune

**Raccomandazione**: Mantenere default 1000 per flessibilità. L'utente può specificare codici di errore espliciti.

---

## Classe 3: WebSocketDisconnect

### Scopo

Eccezione sollevata quando il client chiude la connessione WebSocket.
Non è un errore, è un segnale per il codice chiamante.

### Differenza da WebSocketException

| Aspetto | WebSocketException | WebSocketDisconnect |
|---------|-------------------|---------------------|
| Chi la solleva | Server (raise esplicito) | Framework (receive fallita) |
| Semantica | Errore, chiudi connessione | Informazione, client andato |
| Handling | Log errore, cleanup | Cleanup normale |

### Uso Tipico

```python
async def websocket_handler(websocket):
    try:
        while True:
            data = await websocket.receive_text()
            await process(data)
    except WebSocketDisconnect:
        # Client se n'è andato, cleanup normale
        logger.info("Client disconnected")
```

### Design Proposto (dal piano)

```python
class WebSocketDisconnect(Exception):
    def __init__(self, code: int = 1000, reason: str = "") -> None

    # __repr__ non definito, usa default di Exception
```

### Decisioni da Prendere

#### 6. Aggiungere `__repr__`?

**Domanda**: Il piano non include `__repr__` per WebSocketDisconnect. Aggiungerlo per consistenza?

**Raccomandazione**: Sì, aggiungere `__repr__` per consistenza con le altre due eccezioni.

---

## Domande Trasversali

### 7. Entry point `if __name__ == '__main__'`

**Domanda**: Serve entry point per modulo con solo eccezioni?

**Raccomandazione**: No. Come deciso per datastructures.py, i moduli utility puri non hanno entry point.

---

### 8. Gerarchia di ereditarietà

**Domanda**: Le eccezioni devono ereditare da una base comune?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Tutte da Exception** | Semplice, indipendenti | No catch comune |
| **Base GenroException** | Catch `except GenroException` | Over-engineering |
| **WebSocket da base comune** | Catch tutti WS errors | Complessità |

**Raccomandazione**: Tutte da Exception direttamente. KISS. Se serve catch comune, si può usare tuple:
```python
except (HTTPException, WebSocketException):
```

---

## Riepilogo Decisioni

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Validare HTTPException.status_code? | **No** - KISS, documentare uso atteso |
| 2 | HTTPException.headers tipo? | **dict[str, str]** - semplicità |
| 3 | `__slots__` per eccezioni? | **No** - eccezioni fanno eccezione alla regola |
| 4 | Validare WebSocketException.code? | **No** - KISS |
| 5 | WebSocketException default code=1000? | **Sì** - flessibile |
| 6 | `__repr__` per WebSocketDisconnect? | **Sì** - consistenza |
| 7 | Entry point per exceptions.py? | **No** - modulo utility |
| 8 | Base exception comune? | **No** - KISS, tutte da Exception |

---

## Modifiche al Piano Originale

Basandosi sulle decisioni, il piano originale va modificato:

1. **Aggiungere `__repr__` a WebSocketDisconnect** (decisione #6)
2. **NON aggiungere `__slots__`** (decisione #3 - eccezione alla regola)
3. **Nessuna validazione** per status_code e code (decisioni #1, #4)

---

## Prossimi Passi

Dopo conferma delle decisioni:
1. Scrivere docstring completa del modulo (Step 2)
2. Scrivere test (Step 3)
3. Implementare (Step 4)
4. Commit (Step 6)
