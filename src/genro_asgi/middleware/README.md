# genro-asgi Middleware System

## Overview

Il sistema middleware di genro-asgi usa un pattern **onion-style** con auto-registrazione.
I middleware wrappano l'applicazione ASGI e possono intercettare/modificare request e response.

## Due Modalità di Utilizzo

### 1. Config-Driven (raccomandato)

Middleware dichiarati in configurazione TOML, risolti per nome dal registry:

```toml
[[middleware]]
name = "CORSMiddleware"
allowOrigins = ["*"]

[[middleware]]
name = "CompressionMiddleware"
minimumSize = 1000
```

**Requisito**: il middleware deve ereditare da `BaseMiddleware` per auto-registrarsi.

### 2. Programmatico (override)

Chi eredita da `AsgiServer` può fare override di `_build_middleware_chain`:

```python
class MyServer(AsgiServer):
    def _build_middleware_chain(self) -> Any:
        # Usa qualsiasi middleware ASGI-compatibile
        from some_library import TheirMiddleware

        app = self.dispatcher.dispatch
        app = TheirMiddleware(app, option="value")
        app = MyCustomMiddleware(app)
        return app
```

Oppure mix (config + custom):

```python
class MyServer(AsgiServer):
    def _build_middleware_chain(self) -> Any:
        # Prima applica i middleware da config
        app = super()._build_middleware_chain()
        # Poi aggiungi middleware custom
        app = MyCustomMiddleware(app)
        return app
```

**Nessun requisito**: qualsiasi callable ASGI `(scope, receive, send) -> None` funziona.

## Architettura

```text
Request → [Middleware1 → [Middleware2 → [App] → Middleware2] → Middleware1] → Response
```

Ogni middleware:

1. Riceve `scope`, `receive`, `send` (interfaccia ASGI standard)
2. Può modificare lo scope o intercettare i messaggi
3. Chiama `self.app(scope, receive, send)` per passare al layer successivo
4. Può wrappare `send` per modificare la response

## Creare un Middleware Compatibile

### Struttura Base

```python
# my_middleware.py
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import BaseMiddleware

if TYPE_CHECKING:
    from ..types import ASGIApp, Receive, Scope, Send


class MyMiddleware(BaseMiddleware):
    """Descrizione del middleware.

    Config options:
        option1: Descrizione. Default: value
        option2: Descrizione. Default: value
    """

    __slots__ = ("option1", "option2")

    def __init__(
        self,
        app: ASGIApp,
        option1: str = "default",
        option2: int = 100,
        **kwargs: Any,
    ) -> None:
        super().__init__(app, **kwargs)
        self.option1 = option1
        self.option2 = option2

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        # Filtra solo HTTP (o websocket se necessario)
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # La tua logica qui
        await self.app(scope, receive, send)


if __name__ == "__main__":
    pass
```

### Requisiti Obbligatori

| Requisito | Descrizione |
|-----------|-------------|
| Eredita `BaseMiddleware` | Auto-registrazione nel registry |
| `__slots__` | Dichiara tutti gli attributi dell'istanza |
| `super().__init__(app, **kwargs)` | Passa app e kwargs al parent |
| `**kwargs` nel costruttore | Permette configurazioni future |
| `async def __call__` | Implementa l'interfaccia ASGI |
| `if __name__ == "__main__": pass` | Entry point obbligatorio |

### Auto-Registrazione

Quando crei una sottoclasse di `BaseMiddleware`:

- `__init_subclass__` registra automaticamente la classe in `MIDDLEWARE_REGISTRY`
- Il nome di default è `cls.__name__` (es. `"MyMiddleware"`)
- Puoi customizzare con `middleware_name` class attribute

```python
class MyMiddleware(BaseMiddleware):
    middleware_name = "my_custom_name"  # opzionale
```

## Pattern Comuni

### 1. Pass-Through (solo HTTP)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    # logica per HTTP
    await self.app(scope, receive, send)
```

### 2. Wrapping di `send` (modifica response)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    async def wrapped_send(message: MutableMapping[str, Any]) -> None:
        if message["type"] == "http.response.start":
            # Modifica headers
            headers = list(message.get("headers", []))
            headers.append((b"x-custom-header", b"value"))
            message = {**message, "headers": headers}
        await send(message)

    await self.app(scope, receive, wrapped_send)
```

### 3. Buffering Response (es. compression)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    initial_message: MutableMapping[str, Any] | None = None
    body_parts: list[bytes] = []

    async def buffer_send(message: MutableMapping[str, Any]) -> None:
        nonlocal initial_message, body_parts

        if message["type"] == "http.response.start":
            initial_message = message

        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            more_body = message.get("more_body", False)

            if body:
                body_parts.append(body)

            if not more_body:
                full_body = b"".join(body_parts)
                # Processa full_body
                await send(initial_message)
                await send({"type": "http.response.body", "body": full_body})

    await self.app(scope, receive, buffer_send)
```

### 4. Short-Circuit (risponde senza chiamare app)

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    # Condizione per rispondere direttamente
    if self._should_handle_directly(scope):
        await self._send_direct_response(send)
        return  # Non chiama self.app

    await self.app(scope, receive, send)
```

### 5. Error Handling

```python
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope["type"] != "http":
        await self.app(scope, receive, send)
        return

    try:
        await self.app(scope, receive, send)
    except Exception as e:
        await self._send_error_response(send, e)
```

## Uso del Middleware

### Diretto

```python
from genro_asgi.middleware.cors import CORSMiddleware

app = CORSMiddleware(my_app, allow_origins=["*"])
```

### Via Registry (configurazione)

```python
from genro_asgi.middleware import build_middleware_chain

middlewares = [
    ("CORSMiddleware", {"allow_origins": ["*"]}),
    ("CompressionMiddleware", {"minimum_size": 1000}),
    ("LoggingMiddleware", {"level": "DEBUG"}),
]

app = build_middleware_chain(my_app, middlewares)
```

## Middleware Inclusi

| Middleware | Scopo |
|------------|-------|
| `CORSMiddleware` | Cross-Origin Resource Sharing |
| `CompressionMiddleware` | Gzip compression |
| `ErrorMiddleware` | Error handling |
| `StaticFilesMiddleware` | Serve static files |
| `LoggingMiddleware` | Request/response logging |

## Checklist per Nuovo Middleware

- [ ] File in `src/genro_asgi/middleware/`
- [ ] Copyright header Apache 2.0
- [ ] Eredita `BaseMiddleware`
- [ ] Usa `__slots__`
- [ ] Costruttore con `**kwargs`
- [ ] Chiama `super().__init__(app, **kwargs)`
- [ ] Implementa `async def __call__`
- [ ] Filtra per `scope["type"]`
- [ ] Docstring con config options
- [ ] `if __name__ == "__main__": pass`
- [ ] Test corrispondente
