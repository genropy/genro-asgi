# Block 02: datastructures.py - Analisi Dettagliata

**Scopo**: Strutture dati riutilizzabili per gestione request/response ASGI.

---

## Panoramica del Modulo

Il modulo `datastructures.py` fornisce wrapper Pythonic attorno ai dati raw ASGI.
ASGI usa strutture primitive (bytes, tuple, dict) per efficienza. Queste classi
aggiungono ergonomia senza sacrificare performance.

```
ASGI Raw Data                    genro-asgi Classes
─────────────────                ──────────────────
scope["client"] = ("1.2.3.4", 80)  →  Address(host, port)
scope["headers"] = [(b"...", b"...")]  →  Headers (case-insensitive)
scope["query_string"] = b"a=1&b=2"  →  QueryParams (parsed)
scope["path"] + scope["query_string"]  →  URL (parsed)
scope["state"] = {}  →  State (attribute access)
```

---

## Classe 1: Address

### Scopo

Wrappa la tupla `(host: str, port: int)` usata in ASGI per `client` e `server`.

### Dati ASGI

```python
scope["client"] = ("192.168.1.1", 54321)  # Client address
scope["server"] = ("example.com", 443)     # Server address
# Può essere None se non disponibile
```

### Design Proposto

```python
class Address:
    __slots__ = ("host", "port")

    def __init__(self, host: str, port: int) -> None
    def __repr__(self) -> str
    def __eq__(self, other) -> bool  # Confronta con Address o tuple
```

### Alternative Considerate

| Opzione | Pro | Contro |
|---------|-----|--------|
| **NamedTuple** | Immutabile, hashable, unpacking | Meno controllo, no custom methods |
| **dataclass** | Meno boilerplate | Più overhead, no __slots__ by default |
| **Classe custom** (proposta) | Controllo totale, __slots__ | Più codice |

### Decisioni da Prendere

1. **Hashability**: Serve `__hash__` per usare Address come dict key?
   - Pro: Utile per caching, set membership
   - Contro: Rende la classe "immutabile concettualmente"

2. **Tuple unpacking**: Serve `__iter__` per `host, port = address`?
   - Pro: Backward compatible con codice che usa tuple
   - Contro: Aggiunge complessità

### Raccomandazione

Mantenere semplice come proposto. Aggiungere `__hash__` solo se emerge un caso d'uso concreto.

---

## Classe 2: URL

### Scopo

Parsing e accesso ai componenti URL. Wrappa `urllib.parse.urlparse`.

### Dati ASGI

ASGI non fornisce URL completo, ma componenti separati:

```python
scope["scheme"] = "https"
scope["path"] = "/api/users"
scope["query_string"] = b"id=123"
scope["root_path"] = ""
# Per costruire URL completo serve anche scope["server"]
```

### Design Proposto

```python
class URL:
    __slots__ = ("_url", "_parsed")

    def __init__(self, url: str) -> None

    # Properties (lazy, cached via _parsed)
    @property scheme -> str
    @property netloc -> str
    @property path -> str       # Con unquote automatico
    @property query -> str
    @property fragment -> str
    @property hostname -> str | None
    @property port -> int | None

    def __str__(self) -> str    # URL originale
    def __repr__(self) -> str
    def __eq__(self, other) -> bool  # Confronta con URL o str
```

### Schema Parsing URL

```
  https://user:pass@example.com:8080/path/to/resource?query=1&b=2#section
  ─────   ─────────────────────────────────────────────────────────────
  scheme          netloc                path           query    fragment
          ──────────────────────────────
          user:pass@example.com:8080
                    ───────────  ────
                    hostname     port
```

### Alternative Considerate

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Solo urlparse** | Zero overhead | API scomoda, no caching |
| **yarl (libreria)** | Molto completa | Dipendenza esterna |
| **Classe wrapper** (proposta) | API pulita, caching | Implementazione da mantenere |

### Decisioni da Prendere

1. **Costruzione da scope**: Serve factory per creare URL da ASGI scope?
   ```python
   # Opzione A: Solo stringa
   url = URL("https://example.com/path")

   # Opzione B: Anche da scope (NO - viola "no classmethod")
   url = URL.from_scope(scope)

   # Opzione C: Funzione module-level
   url = url_from_scope(scope)
   ```

2. **URL modificabili**: Serve `replace()` per creare URL modificate?
   ```python
   new_url = url.replace(path="/new/path", query="x=1")
   ```
   - Pro: Utile per redirect, link building
   - Contro: Complessità, può essere aggiunto dopo

### Raccomandazione

- Iniziare con costruttore solo da stringa
- Se serve `from_scope`, usare funzione module-level
- Rimandare `replace()` a quando serve

---

## Classe 3: Headers

### Scopo

Accesso case-insensitive agli header HTTP. Supporta valori multipli per chiave.

### Dati ASGI

```python
scope["headers"] = [
    (b"host", b"example.com"),
    (b"content-type", b"application/json"),
    (b"accept", b"text/html"),
    (b"accept", b"application/json"),  # Valore multiplo!
    (b"cookie", b"session=abc123"),
]
```

**Note importanti**:
- Header names sono **bytes** in ASGI
- HTTP header names sono **case-insensitive** (RFC 7230)
- Lo stesso header può apparire più volte (es. `Set-Cookie`, `Accept`)
- Encoding è Latin-1 (ISO-8859-1) per compatibilità HTTP/1.1

### Design Proposto

```python
class Headers:
    __slots__ = ("_headers",)  # list[tuple[str, str]] normalized

    def __init__(
        self,
        raw_headers: list[tuple[bytes, bytes]] | None = None,
        scope: dict | None = None
    ) -> None

    def get(self, key: str, default: str | None = None) -> str | None
    def getlist(self, key: str) -> list[str]
    def keys(self) -> list[str]
    def values(self) -> list[str]
    def items(self) -> list[tuple[str, str]]

    def __getitem__(self, key: str) -> str      # Raises KeyError
    def __contains__(self, key: str) -> bool
    def __iter__(self) -> Iterator[str]
    def __len__(self) -> int
    def __repr__(self) -> str
```

### Schema Funzionamento

```
Input ASGI (bytes, case-preserving):
[(b"Content-Type", b"application/json"), (b"X-Custom", b"value")]
                    ↓
            Normalizzazione
                    ↓
Internal storage (str, lowercase):
[("content-type", "application/json"), ("x-custom", "value")]
                    ↓
            Lookup case-insensitive
                    ↓
headers.get("CONTENT-TYPE") → "application/json"
```

### Alternative per Costruttore

| Opzione | Esempio | Pro | Contro |
|---------|---------|-----|--------|
| **Solo raw_headers** | `Headers(raw)` | Semplice | Verboso con scope |
| **Solo scope** | `Headers(scope)` | Diretto | Meno flessibile |
| **Entrambi (proposta)** | `Headers(raw_headers=...)` o `Headers(scope=...)` | Flessibile | Due path, confusione? |
| **Overload** | `Headers(raw)` o `Headers(scope)` by type | Magico | Type checking difficile |

### Decisioni da Prendere

1. **Pattern costruttore**: Due parametri opzionali OK?
   - Alternativa: solo `raw_headers`, con helper `headers_from_scope(scope)`

2. **Immutabilità**: Headers deve essere immutabile o mutabile?
   - Immutabile: più sicuro, ma serve `MutableHeaders` per response
   - Mutabile: un'unica classe, ma rischio side-effects

3. **Multi-value handling**: `get()` ritorna primo valore, `getlist()` tutti. OK?

### Raccomandazione

- Costruttore con due parametri opzionali è accettabile (pattern comune)
- Iniziare **immutabile** (read-only)
- Per response, creare `MutableHeaders` separata (Block 05) o usare list[tuple] direttamente

---

## Classe 4: QueryParams

### Scopo

Parsing e accesso ai parametri query string. Supporta valori multipli.

### Dati ASGI

```python
scope["query_string"] = b"name=john&tags=python&tags=web&empty="
```

### Design Proposto

```python
class QueryParams:
    __slots__ = ("_params",)  # dict[str, list[str]] from parse_qs

    def __init__(
        self,
        query_string: bytes | str | None = None,
        scope: dict | None = None
    ) -> None

    def get(self, key: str, default: str | None = None) -> str | None
    def getlist(self, key: str) -> list[str]
    def keys(self) -> list[str]
    def values(self) -> list[str]      # First value per key
    def items(self) -> list[tuple[str, str]]  # First value per key
    def multi_items(self) -> list[tuple[str, str]]  # All values

    def __getitem__(self, key: str) -> str
    def __contains__(self, key: str) -> bool
    def __iter__(self) -> Iterator[str]
    def __len__(self) -> int
    def __bool__(self) -> bool
    def __repr__(self) -> str
```

### Schema Parsing

```
Query string: "name=john&tags=python&tags=web&empty="
                    ↓
            urllib.parse.parse_qs
                    ↓
Internal dict: {
    "name": ["john"],
    "tags": ["python", "web"],
    "empty": [""]
}
                    ↓
params.get("name") → "john"
params.getlist("tags") → ["python", "web"]
params.get("missing") → None
```

### Differenze da Headers

| Aspetto | Headers | QueryParams |
|---------|---------|-------------|
| Case sensitivity | Case-insensitive | Case-sensitive |
| Storage | list[tuple] | dict[str, list] |
| Empty values | N/A | Supportati (`?key=`) |
| URL encoding | No (raw bytes) | Sì (decode automatico) |

### Decisioni da Prendere

1. **Stesso pattern costruttore di Headers?** (due parametri opzionali)

2. **Encoding**: `parse_qs` decodifica automaticamente `%xx`. OK o serve controllo?

### Raccomandazione

Mantenere parallelo a Headers per consistenza API. Il pattern a due parametri è accettabile se ben documentato.

---

## Classe 5: State

### Scopo

Container per dati request-scoped con accesso via attributi.

### Uso Tipico

```python
# Middleware authentication
state.user = User(id=123)
state.is_authenticated = True

# Handler
if request.state.is_authenticated:
    user = request.state.user
```

### Design Proposto

```python
class State:
    __slots__ = ("_state",)  # dict interno

    def __init__(self) -> None
    def __setattr__(self, name: str, value: Any) -> None
    def __getattr__(self, name: str) -> Any    # Raises AttributeError
    def __delattr__(self, name: str) -> None   # Raises AttributeError
    def __contains__(self, name: str) -> bool
    def __repr__(self) -> str
```

### Pattern "Magic Attributes"

Questo pattern usa override di `__setattr__`/`__getattr__` per intercettare
l'accesso agli attributi e redirectarlo a un dict interno.

```python
state = State()
state.user = "john"     # Chiama __setattr__ → self._state["user"] = "john"
print(state.user)       # Chiama __getattr__ → return self._state["user"]
```

**Nota implementativa**: Il costruttore deve usare `object.__setattr__` per
inizializzare `_state` senza triggerare il nostro override:

```python
def __init__(self) -> None:
    object.__setattr__(self, "_state", {})  # Bypass del nostro __setattr__
```

### Alternative Considerate

| Opzione | Pro | Contro |
|---------|-----|--------|
| **Dict semplice** | Nessuna magia | Meno ergonomico (`state["user"]`) |
| **SimpleNamespace** | Built-in, no code | No `__contains__`, no `__slots__` |
| **Classe custom** (proposta) | Controllo totale | Pattern "magico" |
| **dataclass dinamico** | Type hints | Troppo complesso |

### Decisioni da Prendere

1. **Pattern magico accettabile?** L'override di `__getattr__`/`__setattr__` è un pattern non banale.

2. **Dict access**: Serve anche `state["key"]` oltre a `state.key`?
   - Pro: Utile per chiavi dinamiche
   - Contro: Duplicazione API

3. **Iteration**: Serve `__iter__` per iterare sulle chiavi?

### Raccomandazione

Il pattern è standard (usato da Starlette, Flask, etc.). È accettabile.
Non aggiungere dict access - se serve dict, usare dict direttamente.

---

## Domande Trasversali

### 1. `__slots__` ovunque

Tutte le classi usano `__slots__`. Benefici:
- Memoria: ~40% meno per istanza
- Performance: accesso attributi leggermente più veloce
- Previene typo negli attributi

**Raccomandazione**: Mantenere `__slots__` ovunque.

### 2. Entry point `if __name__ == '__main__'`

La regola dice "ogni modulo con classe primaria". Ma `datastructures.py` ha
5 classi utility, nessuna "primaria".

**Raccomandazione**: Per moduli utility puri, omettere entry point.
La regola si applica a moduli con una classe principale (Application, Request, etc.).

### 3. Pattern costruttore duale

Headers e QueryParams accettano `raw_data` OR `scope`. Alternative:

```python
# Opzione A: Due parametri (proposta)
Headers(raw_headers=...)
Headers(scope=...)

# Opzione B: Solo raw + helper function
Headers(raw)
headers_from_scope(scope)  # Module-level function

# Opzione C: Overload by type (non Pythonic)
Headers(raw_or_scope)  # Detect type internally
```

**Raccomandazione**: Opzione A è OK, è pattern comune. Documentare chiaramente.

---

## Riepilogo Decisioni da Confermare

| # | Domanda | Raccomandazione |
|---|---------|-----------------|
| 1 | Address: aggiungere `__hash__`? | No, aggiungere se serve |
| 2 | Address: aggiungere `__iter__` per unpacking? | No, mantenere semplice |
| 3 | URL: factory `from_scope`? | No ora, funzione module-level se serve |
| 4 | URL: metodo `replace()`? | No ora, aggiungere se serve |
| 5 | Headers/QueryParams: due parametri costruttore OK? | Sì, pattern comune |
| 6 | Headers: immutabile? | Sì, MutableHeaders in Block 05 se serve |
| 7 | State: pattern magic attributes OK? | Sì, pattern standard |
| 8 | Entry point per moduli utility? | No, solo per classi principali |
| 9 | `__slots__` ovunque? | Sì, mantenere |

---

## Prossimi Passi

Dopo conferma delle decisioni:
1. Scrivere docstring completa del modulo
2. Scrivere test
3. Implementare
4. Commit
