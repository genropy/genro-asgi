# Block 04: requests.py - Analisi Dettagliata

**Scopo**: Classe Request per wrapping ASGI scope e receive callable.

---

## Panoramica del Modulo

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

---

## Classe Request

### Scopo

Wrapper HTTP request che:
- Fornisce accesso facile ai dati dello scope
- Gestisce il body reading (con caching)
- Supporta parsing JSON e form data
- Fornisce State per dati request-scoped

### Design Proposto (dal piano)

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

---

## Decisioni da Prendere

### 1. Headers/QueryParams: costruttore duale vs helper function

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

---

### 2. Lazy loading vs eager loading per headers/query_params

**Problema**: Le properties headers e query_params sono lazy (create al primo accesso).
È il pattern corretto?

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Lazy** (proposto) | Efficiente se non usati | Complessità cache |
| **Eager** | Semplice | Overhead se non usati |

**Decisione**: Mantenere **lazy loading** - è pattern standard, headers/query_params
potrebbero non essere usati in tutti i casi.

---

### 3. URL construction

**Problema**: La costruzione dell'URL è complessa (scheme, server, path, query_string).
Il piano propone logica inline nella property.

**Considerazioni**:
- Logica complessa per determinare netloc (port default, host header fallback)
- Potrebbe essere estratta in helper function

**Decisione**: Mantenere inline nella property come nel piano. Se diventa più
complessa, estrarre in `_build_url()` metodo privato.

---

### 4. Client property: restituisce Address o None

**Problema**: scope["client"] può essere None (es. Unix socket, test).
Il piano propone `client -> Address | None`.

**Decisione**: OK, coerente con ASGI spec. Address creato on-demand.

---

### 5. Body caching e lettura singola

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

---

### 6. JSON parsing: orjson fallback e charset

**Problema**: Il piano usa try/except per orjson import. OK?

**Decisione**: OK, è pattern standard. orjson è opzionale per performance.

**Charset**: Documentare che `json()` usa **UTF-8 implicito** per decodifica.

- orjson accetta bytes direttamente (assume UTF-8)
- stdlib json.loads richiede decode, usiamo UTF-8
- Non si legge charset da Content-Type (semplificazione)

---

### 7. Form parsing: solo urlencoded e charset

**Problema**: Il piano supporta solo `application/x-www-form-urlencoded`.
Multipart (file upload) richiede parser più complesso.

**Decisione**: OK per ora. Multipart può essere aggiunto in futuro o come
middleware separato. Documentare la limitazione.

**Charset**: Documentare che `form()` usa **UTF-8 implicito** per decodifica
(standard per urlencoded forms moderni).

---

### 8. Content-Type property

**Problema**: `content_type` property è shortcut per `headers.get("content-type")`.

**Decisione**: Utile, mantenere. Potrebbe anche parsare charset etc. ma per ora
semplice string è sufficiente.

---

### 9. `__slots__` e lazy attributes

**Problema**: Con `__slots__`, le properties lazy usano attributi None iniziali:
```python
self._headers: Headers | None = None
```

Questo è corretto con `__slots__` - gli slot permettono None.

**Decisione**: OK come nel piano.

---

### 10. State isolata per request

**Problema**: Ogni Request ha il suo State. Due Request dallo stesso scope
hanno State separate.

**Decisione**: Corretto, è il comportamento atteso. Lo State è request-scoped,
non scope-scoped.

---

### 11. Root path handling

**Problema**: Il piano include `root_path` nella costruzione URL:
```python
path = self._scope.get("root_path", "") + self.path
```

**Decisione**: Corretto per applicazioni montate su subpath.

---

### 12. Request file esistente

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

---

## Riepilogo Decisioni

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

---

## Correzioni al Piano Originale

1. **Usare helper functions** invece di costruttore duale per Headers/QueryParams
2. **File `request.py`** (singolare) invece di `requests.py`
3. **Documentare** mutua esclusione stream/body
4. **Documentare** limitazione form (solo urlencoded)

---

## Prossimi Passi

Dopo conferma delle decisioni:
1. Scrivere docstring completa del modulo (Step 2)
2. Scrivere test (Step 3)
3. Implementare (Step 4)
4. Commit (Step 6)
