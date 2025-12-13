# WSX Protocol Specification

**Version**: 0.1.0
**Status**: 🔴 DA REVISIONARE
**Last Updated**: 2025-12-02

## Overview

WSX (WebSocket eXtended) è un protocollo per RPC transport-agnostic che porta la semantica HTTP sopra WebSocket e NATS. Permette di scrivere handler che funzionano identicamente indipendentemente dal trasporto sottostante.

## Motivazione

### Il Problema

I diversi trasporti hanno API diverse:

- **HTTP**: method, path, headers, cookies, query params, body
- **WebSocket**: solo messaggi binari/testo, nessuna struttura predefinita
- **NATS**: subject, payload bytes, reply-to automatico

Questo costringe a scrivere handler diversi per ogni trasporto, duplicando la business logic.

### La Soluzione

WSX definisce un formato messaggio che incapsula la semantica HTTP-like, permettendo:

```
HTTP Request  ─────┐
                   │
WebSocket RPC ─────┼──► BaseRequest ──► Handler ──► BaseResponse
                   │
NATS Message  ─────┘
```

L'handler riceve sempre `BaseRequest` e produce `BaseResponse`, ignorando il trasporto.

## Formato Messaggio

### Prefisso

I messaggi WSX iniziano con il prefisso `WSX://` seguito da JSON:

```
WSX://{"id":"...","method":"...","path":"...","headers":{},"data":{}}
```

### WSX Request

```json
WSX://{
    "id": "uuid-123",
    "method": "POST",
    "path": "/users/42",
    "headers": {
        "content-type": "application/json",
        "authorization": "Bearer xxx",
        "accept-language": "it-IT",
        "x-request-id": "trace-456"
    },
    "cookies": {
        "session_id": "xyz-789",
        "preferences": "dark_mode=true"
    },
    "query": {
        "limit": "10::L",
        "active": "true::B"
    },
    "data": {
        "name": "Mario",
        "birth": "1990-05-15::D",
        "balance": "1234.56::N"
    }
}
```

#### Campi Request

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `id` | string | Sì | Correlation ID per correlare request/response |
| `method` | string | Sì | HTTP method: GET, POST, PUT, DELETE, PATCH |
| `path` | string | Sì | Routing path (es. "/users/42") |
| `headers` | object | No | HTTP headers come dict |
| `cookies` | object | No | Cookies come dict |
| `query` | object | No | Query parameters (supporta TYTX types) |
| `data` | any | No | Payload della request (supporta TYTX types) |

### WSX Response

```json
WSX://{
    "id": "uuid-123",
    "status": 200,
    "headers": {
        "content-type": "application/json",
        "x-request-id": "trace-456",
        "cache-control": "no-cache"
    },
    "cookies": {
        "session_id": {
            "value": "new-xyz",
            "max_age": "3600::L",
            "path": "/",
            "httponly": "true::B",
            "secure": "true::B"
        }
    },
    "data": {
        "id": "42::L",
        "created": "2025-12-02T10:30:00+01:00::DHZ",
        "message": "User created"
    }
}
```

#### Campi Response

| Campo | Tipo | Obbligatorio | Descrizione |
|-------|------|--------------|-------------|
| `id` | string | Sì | Stesso correlation ID della request |
| `status` | int | Sì | HTTP status code (200, 404, 500, etc.) |
| `headers` | object | No | Response headers |
| `cookies` | object | No | Set-Cookie equivalents |
| `data` | any | No | Payload della response |

### Cookies nella Response

I cookies nella response possono essere:
- Stringa semplice: `"session_id": "value"`
- Oggetto con opzioni: `"session_id": {"value": "...", "max_age": "3600::L", ...}`

Opzioni supportate:
- `value`: valore del cookie
- `max_age`: durata in secondi
- `path`: path del cookie
- `domain`: dominio
- `secure`: solo HTTPS
- `httponly`: non accessibile da JS
- `samesite`: "strict", "lax", "none"

## Integrazione con TYTX

I valori in `query`, `data`, e `cookies` supportano la sintassi TYTX per i tipi:

```
"price": "99.50::N"     → Decimal("99.50")
"date": "2025-01-15::D" → date(2025, 1, 15)
"count": "42::L"        → 42 (int)
"active": "true::B"     → True (bool)
```

Il parsing WSX idrata automaticamente questi valori.

## Architettura Classi

### Gerarchia Request

```
BaseRequest (ABC)
    │
    ├── HttpRequest
    │       └── Wrappa ASGI scope per HTTP
    │
    └── WsxRequest
            │   └── Parsa messaggi WSX://
            │
            ├── WsRequest
            │       └── Trasporto: ASGI WebSocket
            │
            └── NatsRequest
                    └── Trasporto: NATS
```

### Gerarchia Response

```
BaseResponse (ABC)
    │
    ├── HttpResponse
    │       └── Produce ASGI HTTP response
    │
    └── WsxResponse
            │   └── Serializza in formato WSX://
            │
            ├── WsResponse
            │       └── Invia su WebSocket
            │
            └── NatsResponse
                    └── Pubblica su NATS reply-to
```

### Interfaccia BaseRequest

```python
class BaseRequest(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Correlation ID per request/response matching."""

    @property
    @abstractmethod
    def method(self) -> str:
        """HTTP method (GET, POST, PUT, DELETE, PATCH)."""

    @property
    @abstractmethod
    def path(self) -> str:
        """Request path (es. '/users/42')."""

    @property
    @abstractmethod
    def headers(self) -> dict[str, str]:
        """Request headers."""

    @property
    @abstractmethod
    def cookies(self) -> dict[str, str]:
        """Request cookies."""

    @property
    @abstractmethod
    def query(self) -> dict[str, Any]:
        """Query parameters (già idratati)."""

    @property
    @abstractmethod
    def data(self) -> Any:
        """Request body/payload (già idratato)."""

    @property
    @abstractmethod
    def transport(self) -> str:
        """Trasporto: 'http', 'websocket', 'nats'."""
```

### Interfaccia BaseResponse

```python
class BaseResponse(ABC):
    @property
    @abstractmethod
    def id(self) -> str:
        """Correlation ID (stesso della request)."""

    @property
    @abstractmethod
    def status(self) -> int:
        """HTTP status code."""

    @abstractmethod
    def set_header(self, name: str, value: str) -> None:
        """Aggiunge un header alla response."""

    @abstractmethod
    def set_cookie(
        self,
        name: str,
        value: str,
        *,
        max_age: int | None = None,
        path: str = "/",
        domain: str | None = None,
        secure: bool = False,
        httponly: bool = False,
        samesite: str = "lax"
    ) -> None:
        """Imposta un cookie."""

    @abstractmethod
    async def send(self, data: Any) -> None:
        """Invia la response con il payload."""
```

## Flusso per Trasporto

### HTTP (ASGI)

```
1. ASGI receive() → body bytes
2. Parse body (JSON/TYTX/XTYTX)
3. Crea HttpRequest da ASGI scope
4. Handler processa → HttpResponse
5. HttpResponse → ASGI send()
```

### WebSocket (ASGI)

```
1. WebSocket receive() → text message
2. Detect WSX:// prefix
3. Parse JSON, hydrate TYTX values
4. Crea WsRequest
5. Handler processa → WsResponse
6. WsResponse.send() → serialize WSX:// → WebSocket send()
```

### NATS

```
1. NATS subscribe callback → msg
2. msg.data contiene WSX://...
3. Parse JSON, hydrate TYTX values
4. Crea NatsRequest (conserva msg.reply)
5. Handler processa → NatsResponse
6. NatsResponse.send() → serialize WSX:// → nc.publish(msg.reply, ...)
```

## Esempio di Handler Transport-Agnostic

```python
async def get_user(request: BaseRequest) -> dict:
    """Handler che funziona con qualsiasi trasporto."""

    user_id = request.path.split("/")[-1]  # /users/42 → "42"

    # Accesso uniforme a headers, cookies, query, data
    auth = request.headers.get("authorization")
    session = request.cookies.get("session_id")
    include_details = request.query.get("details", False)

    # Business logic
    user = await db.get_user(user_id)

    return {
        "id": user.id,
        "name": user.name,
        "email": user.email if include_details else None
    }
```

## Vantaggi del Design

1. **Uniformità**: Stesso handler per HTTP, WebSocket, NATS
2. **Type Safety**: TYTX preserva i tipi attraverso il trasporto
3. **Familiar API**: Semantica HTTP-like anche su messaging
4. **Estensibilità**: Facile aggiungere nuovi trasporti
5. **Testabilità**: Mock semplificato con BaseRequest/BaseResponse

## Note Implementative

### Correlation ID

- Per HTTP: generato dal server o da header `x-request-id`
- Per WebSocket: obbligatorio nel messaggio WSX
- Per NATS: usa il meccanismo reply-to nativo, `id` è per tracing applicativo

### Error Handling

Gli errori vengono ritornati come response con status appropriato:

```json
WSX://{
    "id": "uuid-123",
    "status": 404,
    "data": {
        "error": "User not found",
        "code": "USER_NOT_FOUND"
    }
}
```

### Streaming

Per risposte streaming (es. Server-Sent Events equivalent):
- Multiple WSX response con stesso `id`
- Campo aggiuntivo `"stream": true` per indicare che seguono altri messaggi
- `"stream": false` o assente indica messaggio finale

## Stato Implementazione

| Componente | Stato | Note |
|------------|-------|------|
| `WSX_PREFIX`, `is_wsx_message()` | ✅ Implementato | `wsx/protocol.py` |
| `parse_wsx_message()` | ✅ Implementato | `wsx/protocol.py` |
| `build_wsx_message()` | ✅ Implementato | `wsx/protocol.py` |
| `build_wsx_response()` | ✅ Implementato | `wsx/protocol.py` |
| `BaseRequest` | ✅ Implementato | `request.py` |
| `HttpRequest` | ✅ Implementato | `request.py` |
| `MsgRequest` | ✅ Implementato | `request.py` - usa WSX parsing |
| `WsxRequest`, `WsRequest` | ❌ Non implementato | Planned |
| `NatsRequest` | ❌ Non implementato | Planned |
| `BaseResponse` | ❌ Non implementato | Planned |
| `WsxResponse`, `WsResponse` | ❌ Non implementato | Planned |
| `NatsResponse` | ❌ Non implementato | Planned |
| Integrazione NATS | ❌ Non implementato | Planned |

## Implementazione Pianificata

1. **Fase 1**: BaseRequest/BaseResponse ABC ✅ (parziale - solo BaseRequest)
2. **Fase 2**: HttpRequest/HttpResponse (ASGI HTTP) ✅ (parziale - solo HttpRequest)
3. **Fase 3**: WsxRequest/WsxResponse (parsing WSX) ❌
4. **Fase 4**: WsRequest/WsResponse (ASGI WebSocket) ❌
5. **Fase 5**: NatsRequest/NatsResponse (quando necessario) ❌

---

**Copyright**: Softwell S.r.l. (2025)
**License**: Apache License 2.0
