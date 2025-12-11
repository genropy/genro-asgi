# Block 06: websockets.py - Analisi Dettagliata

**Scopo**: Classe WebSocket per connessioni WebSocket ASGI.
**Status**: 🔴 DA REVISIONARE

---

## Panoramica del Modulo

Il modulo `websockets.py` fornisce la classe `WebSocket` per gestire connessioni WebSocket
attraverso l'interfaccia ASGI. Questa classe è la base per il protocollo genro-wsx.

```
Client                            WebSocket Class                    ASGI Server
──────                            ───────────────                    ───────────
Connect  ─────────────────────>   WebSocket(scope, receive, send)
                                  await ws.accept()  ───────────>    websocket.accept
                                  await ws.receive_text()  <────────  websocket.receive
                                  await ws.send_text()  ──────────>  websocket.send
                                  await ws.close()  ──────────────>  websocket.close
```

### Componenti dal Piano

| Componente | Descrizione |
|------------|-------------|
| WebSocketState | Enum: CONNECTING, CONNECTED, DISCONNECTED |
| WebSocket | Wrapper per connessione WebSocket |

---

## Decisioni da Prendere

### 1. Nome file: `websockets.py` (plurale) vs `websocket.py` (singolare)

**Problema**: Il piano usa `websockets.py` (plurale), coerente con la convenzione
che il modulo contiene più di una classe (WebSocket + WebSocketState).

| Opzione | Pro | Contro |
|---------|-----|--------|
| `websockets.py` (plurale) | Coerente col piano, indica modulo multi-classe | Potenziale conflitto nome con libreria `websockets` |
| `websocket.py` (singolare) | Come `request.py`, `response.py` | Non segue il piano |

**Domanda**: Usare il plurale come nel piano?

---

### 2. Costruttore Headers: `raw_headers` vs `scope`

**Problema**: Il piano passa `scope` a `Headers`:
```python
self._headers = Headers(scope=self._scope)
```

Ma l'implementazione attuale di Headers accetta `raw_headers`:
```python
def __init__(self, raw_headers: list[tuple[bytes, bytes]] | None = None, scope: Scope | None = None)
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Passare `scope` | Semplice, Headers estrae headers dallo scope | - |
| Passare `raw_headers` | Esplicito | Più verboso |

**Verifica**: Headers accetta `scope` e può estrarre headers automaticamente?

**Domanda**: Usare `Headers(scope=self._scope)` come nel piano?

---

### 3. URL construction: lazy vs eager

**Problema**: Il piano costruisce l'URL lazily con logica complessa:
```python
@property
def url(self) -> URL:
    if self._url is None:
        scheme = self._scope.get("scheme", "ws")
        server = self._scope.get("server")
        # ... 15+ righe di logica
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Lazy (come piano) | Calcolo solo se usato | Logica duplicata con Request |
| Fattorizzare in utility | DRY, riuso tra Request/WebSocket | Nuova dipendenza |

**Nota**: Request ha logica simile per URL construction.

**Domanda**: Accettabile duplicare la logica? O creare una utility condivisa?

---

### 4. Proprietà `state` vs attributo `state`

**Problema**: Il piano usa `state` come property che inizializza lazily:
```python
@property
def state(self) -> State:
    if self._client_state is None:
        self._client_state = State()
    return self._client_state
```

Ma il nome `_client_state` è confusionario (in `__slots__` c'è `_client_state`).

| Opzione | Pro | Contro |
|---------|-----|--------|
| `_client_state` | Come nel piano | Nome confuso |
| `_state` | Più chiaro, coerente con pattern | Diverso dal piano |

**Domanda**: Rinominare a `_state` per chiarezza?

---

### 5. WebSocketState: classe vs modulo-level constants

**Problema**: Il piano usa un Enum:
```python
class WebSocketState(Enum):
    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Enum | Type-safe, auto-completamento | Overhead minimo |
| Constants | Più semplice | Meno type-safe |

**Domanda**: Enum OK?

---

### 6. `accept()` headers: `list[tuple[bytes, bytes]]` vs formato più friendly

**Problema**: Il piano accetta headers per accept come bytes:
```python
async def accept(
    self,
    subprotocol: str | None = None,
    headers: list[tuple[bytes, bytes]] | None = None,
) -> None:
```

Questo è coerente con ASGI ma poco ergonomico.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `list[tuple[bytes, bytes]]` | Diretto ASGI | Poco user-friendly |
| `dict[str, str]` | User-friendly | Richiede conversione |
| `Mapping[str, str] | list[tuple[str, str]]` | Flessibile, come Response | Più complesso |

**Domanda**: Mantenere formato ASGI per semplicità? O essere più user-friendly?

---

### 7. `receive_text()` fallback da bytes

**Problema**: Il piano converte bytes a text se necessario:
```python
if "text" in message:
    return message["text"]
if "bytes" in message:
    return message["bytes"].decode("utf-8")
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Fallback (come piano) | Flessibile | Potrebbe nascondere problemi |
| Strict (solo text) | Chiaro, fallisce se tipo sbagliato | Meno flessibile |

**Nota**: Alcuni server WebSocket inviano sempre bytes anche per text.

**Domanda**: Mantenere il fallback?

---

### 8. `receive_json()` error handling

**Problema**: Il piano lascia che json.loads/orjson.loads sollevi ValueError:
```python
async def receive_json(self) -> Any:
    text = await self.receive_text()
    if HAS_ORJSON:
        return orjson.loads(text)
    return json.loads(text)
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Propagare ValueError | Semplice, standard | Utente deve gestire |
| Wrappare in custom exception | Più contesto | Over-engineering |

**Domanda**: OK propagare ValueError/JSONDecodeError?

---

### 9. `send()` method name collision

**Problema**: Il piano ha un metodo `send()` pubblico che wrappa `_send`:
```python
async def send(self, message: Message) -> None:
    if self._state != WebSocketState.CONNECTED:
        raise RuntimeError(...)
    await self._send(message)
```

Ma `send` è anche il nome del callable ASGI interno.

| Opzione | Pro | Contro |
|---------|-----|--------|
| `send()` | Intuitivo | Collisione nomi |
| `send_raw()` | Più esplicito | Meno intuitivo |
| `send_message()` | Chiaro | Più lungo |

**Domanda**: Mantenere `send()` come nel piano?

---

### 10. `__aiter__` yield type: `str | bytes`

**Problema**: L'iteratore può yielddare sia str che bytes:
```python
async def __aiter__(self) -> AsyncIterator[str | bytes]:
    if "text" in message:
        yield message["text"]
    elif "bytes" in message:
        yield message["bytes"]
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| `str | bytes` | Flessibile | Type checking meno utile |
| Solo `str` | Type-safe | Perde dati binari |
| Metodi separati | Chiaro | Più verboso |

**Domanda**: Union type OK per iterazione?

---

### 11. Close idempotenza

**Problema**: Il piano rende close idempotente:
```python
async def close(self, code: int = 1000, reason: str = "") -> None:
    if self._state == WebSocketState.DISCONNECTED:
        return  # No-op se già disconnesso
```

| Opzione | Pro | Contro |
|---------|-----|--------|
| Idempotente | Safe, user-friendly | Nasconde chiamate multiple |
| Raise se già chiuso | Esplicito | Meno friendly |

**Domanda**: Idempotenza OK?

---

### 12. Entry point `if __name__ == '__main__'`

**Problema**: Le regole richiedono entry point. Ma WebSocket richiede
un server ASGI mock completo per demo.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Demo con mock | Segue regole | Mock complesso |
| Solo print info | Minimale | Non testa funzionalità |
| Skip entry point | Semplice | Non segue regole |

**Domanda**: Quale approccio per entry point?

---

### 13. Dipendenze: import Address, Headers, QueryParams, State, URL

**Problema**: Il piano importa tutto da datastructures:
```python
from .datastructures import Address, Headers, QueryParams, State, URL
```

Queste classi esistono e sono testate nel Block 02.

**Domanda**: Import OK? O verificare API compatibility?

---

### 14. `subprotocols` property: return type

**Problema**: Il piano ritorna `list[str]`:
```python
@property
def subprotocols(self) -> list[str]:
    return self._scope.get("subprotocols", [])
```

Ma potrebbe ritornare la lista mutabile dallo scope.

| Opzione | Pro | Contro |
|---------|-----|--------|
| Return diretto | Semplice | Mutabile, può causare bug |
| Copy `list(...)` | Immutabile | Overhead |
| Tuple | Immutabile | Diverso tipo |

**Domanda**: Return diretto OK?

---

### 15. `connection_state` vs `state` naming

**Problema**: Il piano ha due "state":
- `state` - custom data storage (State object)
- `connection_state` - WebSocketState enum

| Opzione | Pro | Contro |
|---------|-----|--------|
| Come piano | Distingue chiaramente | Verboso |
| `ws_state` | Più corto | Meno chiaro |

**Domanda**: Naming OK?

---

### 16. Gestione `websocket.connect` message

**Problema**: Il piano NON gestisce esplicitamente il messaggio `websocket.connect`.
ASGI spec dice che il primo messaggio ricevuto dopo `scope` potrebbe essere
`websocket.connect` (dipende dal server).

| Opzione | Pro | Contro |
|---------|-----|--------|
| Ignorare (come piano) | Semplice | Potrebbe fallire con alcuni server |
| Gestire in accept() | Completo | Più complesso |

**Domanda**: Serve gestire `websocket.connect`?

---

### 17. Test: async fixtures con pytest-asyncio

**Problema**: I test usano `@pytest.mark.asyncio`. Serve verificare che
pytest-asyncio sia nelle dev dependencies.

**Domanda**: pytest-asyncio è già configurato?

---

## Domande Aperte Riassunto

1. **Nome file**: `websockets.py` (plurale) o `websocket.py` (singolare)?
2. **Headers constructor**: Passare `scope` direttamente?
3. **URL construction**: Duplicare logica o fattorizzare utility?
4. **State naming**: `_client_state` o `_state`?
5. **WebSocketState**: Enum OK?
6. **accept() headers**: Format ASGI bytes o più friendly?
7. **receive_text() fallback**: Da bytes a text OK?
8. **receive_json() errors**: Propagare ValueError?
9. **send() method**: Nome OK nonostante collisione?
10. **__aiter__ type**: `str | bytes` union OK?
11. **close() idempotenza**: OK?
12. **Entry point**: Quale approccio?
13. **Imports**: Da datastructures OK?
14. **subprotocols return**: Diretto o copy?
15. **Naming**: `state` vs `connection_state` OK?
16. **websocket.connect**: Gestire?
17. **pytest-asyncio**: Configurato?

---

## Decisioni Finali

| # | Domanda | Decisione |
|---|---------|-----------|
| 1 | Nome file | **DA DECIDERE** |
| 2 | Headers | **DA DECIDERE** |
| 3 | URL construction | **DA DECIDERE** |
| 4 | State naming | **DA DECIDERE** |
| 5 | WebSocketState | **DA DECIDERE** |
| 6 | accept() headers | **DA DECIDERE** |
| 7 | receive_text() fallback | **DA DECIDERE** |
| 8 | receive_json() errors | **DA DECIDERE** |
| 9 | send() method | **DA DECIDERE** |
| 10 | __aiter__ type | **DA DECIDERE** |
| 11 | close() idempotenza | **DA DECIDERE** |
| 12 | Entry point | **DA DECIDERE** |
| 13 | Imports | **DA DECIDERE** |
| 14 | subprotocols return | **DA DECIDERE** |
| 15 | Naming | **DA DECIDERE** |
| 16 | websocket.connect | **DA DECIDERE** |
| 17 | pytest-asyncio | **DA VERIFICARE** |

---

## Prossimi Passi

1. **Confermare le decisioni** ← SIAMO QUI
2. Scrivere docstring modulo (Step 2)
3. Scrivere test (Step 3)
4. Implementare (Step 4)
5. Commit (Step 6)
