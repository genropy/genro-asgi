# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""WebSocket connection handling for ASGI applications.

Purpose
=======
This module provides the ``WebSocket`` class for handling WebSocket connections
through the ASGI interface. It wraps the low-level ASGI receive/send callables
with a Pythonic API for managing connection lifecycle, sending and receiving
messages.

WebSocket flow in ASGI::

    Client                            WebSocket Class                    ASGI Server
    ──────                            ───────────────                    ───────────
    Connect  ─────────────────────>   WebSocket(scope, receive, send)
                                      state: CONNECTING
                                                 │
                                      await ws.accept()  ───────────>    websocket.accept
                                      (consumes websocket.connect)
                                      state: CONNECTED
                                                 │
                                      await ws.receive_text()  <────────  websocket.receive
                                      await ws.send_text()  ──────────>  websocket.send
                                                 │
                                      await ws.close()  ──────────────>  websocket.close
                                      state: DISCONNECTED

Connection States
=================
WebSocket connections go through three states::

    CONNECTING  ─────>  CONNECTED  ─────>  DISCONNECTED
        │                   │                    │
    Initial state       After accept()      After close() or
    Before accept()     Can send/receive    client disconnect

The ``WebSocketState`` enum represents these states.

Imports Required
================
::

    from enum import IntEnum
    from typing import Any, AsyncIterator
    import json

    from .types import Scope, Receive, Send, Message
    from .datastructures import (
        Address, Headers, QueryParams, State, URL,
        headers_from_scope, query_params_from_scope
    )

Classes
=======

WebSocketState
--------------
Enum representing WebSocket connection states.

Definition::

    class WebSocketState(IntEnum):
        CONNECTING = 0    # Initial state, before accept()
        CONNECTED = 1     # After accept(), can send/receive messages
        DISCONNECTED = 2  # After close() or client disconnect

    Note: IntEnum used for easy comparisons and potential serialization.

WebSocket
---------
Main class for WebSocket connection handling.

Definition::

    class WebSocket:
        __slots__ = (
            "_scope",           # Scope: ASGI scope dict
            "_receive",         # Receive: ASGI receive callable
            "_send",            # Send: ASGI send callable
            "_connection_state", # WebSocketState: current state
            "_headers",         # Headers | None: lazy headers
            "_query_params",    # QueryParams | None: lazy query params
            "_url",             # URL | None: lazy URL object
            "_state",           # State | None: lazy user state
            "_accepted_subprotocol",  # str | None: negotiated subprotocol
        )

        def __init__(
            self,
            scope: Scope,
            receive: Receive,
            send: Send,
        ) -> None:
            '''
            Initialize WebSocket connection wrapper.

            Args:
                scope: ASGI WebSocket scope dictionary. Must have type="websocket".
                receive: ASGI receive callable for incoming messages.
                send: ASGI send callable for outgoing messages.

            Raises:
                ValueError: If scope type is not "websocket".
            '''
            if scope.get("type") != "websocket":
                raise ValueError(
                    f"Expected scope type 'websocket', got '{scope.get('type')}'"
                )
            self._scope = scope
            self._receive = receive
            self._send = send
            self._connection_state = WebSocketState.CONNECTING
            self._headers: Headers | None = None
            self._query_params: QueryParams | None = None
            self._url: URL | None = None
            self._state: State | None = None
            self._accepted_subprotocol: str | None = None

Constructor validates that scope type is "websocket". All properties are
lazy-initialized for efficiency.

Properties
==========

``scope -> Scope``
    The raw ASGI scope dictionary.

``connection_state -> WebSocketState``
    Current connection state (CONNECTING, CONNECTED, or DISCONNECTED).

``path -> str``
    The URL path component from scope. Defaults to "/" if not present.

``scheme -> str``
    URL scheme: "ws" or "wss". Derived from scope, defaults to "ws".

``url -> URL``
    Full WebSocket URL constructed from scope. Built lazily.
    URL construction rules:
    - scheme: "ws" or "wss" from scope
    - host: from server tuple or Host header
    - port: omitted if default (80 for ws, 443 for wss)
    - path: root_path + path
    - query: query_string if present

``headers -> Headers``
    Connection headers (case-insensitive). Created lazily using
    ``headers_from_scope()``.

``query_params -> QueryParams``
    Query string parameters. Created lazily using ``query_params_from_scope()``.

``state -> State``
    Per-connection state container for middleware/application data.
    Created lazily on first access.

``client -> Address | None``
    Client address (host, port) if available.

``subprotocols -> tuple[str, ...]``
    Subprotocols requested by the client (immutable tuple).

``accepted_subprotocol -> str | None``
    The subprotocol selected in accept(), or None if not set.

Methods
=======

Connection Lifecycle
--------------------

``accept()``
~~~~~~~~~~~~
Accept the WebSocket connection.

Definition::

    async def accept(
        self,
        subprotocol: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        '''
        Accept the WebSocket connection.

        This method MUST be called before sending or receiving messages.
        It consumes the ``websocket.connect`` message and sends
        ``websocket.accept`` to complete the handshake.

        Args:
            subprotocol: Optional subprotocol to use for this connection.
                         Must be one of the client's requested subprotocols.
            headers: Optional headers to include in the accept response.
                     Dict of str:str, converted to ASGI bytes format internally.

        Raises:
            RuntimeError: If connection is not in CONNECTING state.

        Note:
            After calling accept(), connection_state becomes CONNECTED.
            The websocket.connect message is consumed internally.
        '''
        if self._connection_state != WebSocketState.CONNECTING:
            raise RuntimeError(
                f"Cannot accept: connection in {self._connection_state.name} state"
            )

        # Consume the websocket.connect message
        message = await self._receive()
        if message["type"] != "websocket.connect":
            raise RuntimeError(
                f"Expected websocket.connect, got {message['type']}"
            )

        # Build accept message
        accept_message: Message = {"type": "websocket.accept"}
        if subprotocol is not None:
            accept_message["subprotocol"] = subprotocol
            self._accepted_subprotocol = subprotocol
        if headers is not None:
            # Convert str:str to bytes:bytes for ASGI
            accept_message["headers"] = [
                (k.encode("latin-1"), v.encode("latin-1"))
                for k, v in headers.items()
            ]

        await self._send(accept_message)
        self._connection_state = WebSocketState.CONNECTED

``close()``
~~~~~~~~~~~
Close the WebSocket connection.

Definition::

    async def close(
        self,
        code: int = 1000,
        reason: str = "",
    ) -> None:
        '''
        Close the WebSocket connection.

        This method is idempotent: calling it multiple times on an already
        closed connection is safe and does nothing.

        Args:
            code: WebSocket close code. Default 1000 (normal closure).
                  Common codes:
                  - 1000: Normal closure
                  - 1001: Going away
                  - 1002: Protocol error
                  - 1003: Unsupported data type
                  - 1008: Policy violation
                  - 1011: Internal server error
            reason: Optional human-readable close reason (max 123 bytes UTF-8).

        Note:
            After calling close(), connection_state becomes DISCONNECTED.
            Calling close() when already DISCONNECTED is a no-op.
            Calling close() when CONNECTING raises RuntimeError.
        '''
        if self._connection_state == WebSocketState.DISCONNECTED:
            return  # Idempotent: already closed

        if self._connection_state == WebSocketState.CONNECTING:
            raise RuntimeError("Cannot close: connection not accepted yet")

        await self._send({
            "type": "websocket.close",
            "code": code,
            "reason": reason,
        })
        self._connection_state = WebSocketState.DISCONNECTED

Receiving Messages
------------------

``receive_text()``
~~~~~~~~~~~~~~~~~~
Receive a text message.

Definition::

    async def receive_text(self) -> str:
        '''
        Receive a text message from the WebSocket.

        Returns:
            The text message content.

        Raises:
            RuntimeError: If not in CONNECTED state.
            TypeError: If received message is bytes (use receive_bytes()).
            WebSocketDisconnect: If client disconnected.

        Note:
            STRICT mode: This method only accepts text frames. If the client
            sends binary data, TypeError is raised. This prevents silent
            encoding bugs. Use receive_bytes() for binary data.
        '''
        message = await self._receive_message()
        if "bytes" in message and message["bytes"] is not None:
            raise TypeError(
                "Received binary message. Use receive_bytes() for binary data."
            )
        return message.get("text", "")

``receive_bytes()``
~~~~~~~~~~~~~~~~~~~
Receive a binary message.

Definition::

    async def receive_bytes(self) -> bytes:
        '''
        Receive a binary message from the WebSocket.

        Returns:
            The binary message content.

        Raises:
            RuntimeError: If not in CONNECTED state.
            TypeError: If received message is text (use receive_text()).
            WebSocketDisconnect: If client disconnected.

        Note:
            STRICT mode: This method only accepts binary frames. If the client
            sends text data, TypeError is raised. Use receive_text() for text.
        '''
        message = await self._receive_message()
        if "text" in message and message["text"] is not None:
            raise TypeError(
                "Received text message. Use receive_text() for text data."
            )
        return message.get("bytes", b"")

``receive_json()``
~~~~~~~~~~~~~~~~~~
Receive and parse a JSON message.

Definition::

    async def receive_json(self) -> Any:
        '''
        Receive a text message and parse it as JSON.

        Returns:
            The parsed JSON value (dict, list, str, int, float, bool, None).

        Raises:
            RuntimeError: If not in CONNECTED state.
            TypeError: If received message is bytes.
            json.JSONDecodeError: If message is not valid JSON.
            WebSocketDisconnect: If client disconnected.

        Note:
            Uses orjson if available for faster parsing, falls back to stdlib.
            JSON decode errors are propagated directly (not wrapped).
            For typed JSON with hydration, see receive_typed() (requires genro-tytx).
        '''
        text = await self.receive_text()
        # Use orjson if available
        if HAS_ORJSON:
            return orjson.loads(text)
        return json.loads(text)

``_receive_message()``
~~~~~~~~~~~~~~~~~~~~~~
Internal method to receive the next message with state validation.

Definition::

    async def _receive_message(self) -> Message:
        '''
        Internal: receive next message with state validation.

        Returns:
            The raw ASGI message dict.

        Raises:
            RuntimeError: If not in CONNECTED state.
            WebSocketDisconnect: If websocket.disconnect received.
        '''
        if self._connection_state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"Cannot receive: connection in {self._connection_state.name} state"
            )

        message = await self._receive()
        if message["type"] == "websocket.disconnect":
            self._connection_state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(
                code=message.get("code", 1000),
                reason=message.get("reason", ""),
            )
        return message

Sending Messages
----------------

``send_text()``
~~~~~~~~~~~~~~~
Send a text message.

Definition::

    async def send_text(self, data: str) -> None:
        '''
        Send a text message to the WebSocket.

        Args:
            data: The text message to send.

        Raises:
            RuntimeError: If not in CONNECTED state.
        '''
        await self._send_message({"type": "websocket.send", "text": data})

``send_bytes()``
~~~~~~~~~~~~~~~~
Send a binary message.

Definition::

    async def send_bytes(self, data: bytes) -> None:
        '''
        Send a binary message to the WebSocket.

        Args:
            data: The binary message to send.

        Raises:
            RuntimeError: If not in CONNECTED state.
        '''
        await self._send_message({"type": "websocket.send", "bytes": data})

``send_json()``
~~~~~~~~~~~~~~~
Send data as JSON.

Definition::

    async def send_json(self, data: Any) -> None:
        '''
        Serialize data to JSON and send as text message.

        Args:
            data: Data to serialize (must be JSON-serializable).

        Raises:
            RuntimeError: If not in CONNECTED state.
            TypeError: If data is not JSON-serializable.

        Note:
            Uses orjson if available for faster serialization, falls back to stdlib.
            For typed JSON with serialization, see send_typed() (requires genro-tytx).
        '''
        if HAS_ORJSON:
            text = orjson.dumps(data).decode("utf-8")
        else:
            text = json.dumps(data)
        await self.send_text(text)

``_send_message()``
~~~~~~~~~~~~~~~~~~~
Internal method to send a message with state validation.

Definition::

    async def _send_message(self, message: Message) -> None:
        '''
        Internal: send message with state validation.

        Args:
            message: ASGI message dict to send.

        Raises:
            RuntimeError: If not in CONNECTED state.
        '''
        if self._connection_state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"Cannot send: connection in {self._connection_state.name} state"
            )
        await self._send(message)

Iteration
---------

``iter_text()``
~~~~~~~~~~~~~~~
Async iterator for text messages.

Definition::

    async def iter_text(self) -> AsyncIterator[str]:
        '''
        Async iterator yielding text messages.

        Yields text messages until the connection closes or client disconnects.

        Yields:
            str: Each text message received.

        Raises:
            TypeError: If a binary message is received.

        Example:
            async for message in ws.iter_text():
                print(f"Received: {message}")
        '''
        try:
            while True:
                yield await self.receive_text()
        except WebSocketDisconnect:
            return

``iter_bytes()``
~~~~~~~~~~~~~~~~
Async iterator for binary messages.

Definition::

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        '''
        Async iterator yielding binary messages.

        Yields binary messages until the connection closes or client disconnects.

        Yields:
            bytes: Each binary message received.

        Raises:
            TypeError: If a text message is received.

        Example:
            async for data in ws.iter_bytes():
                process_binary(data)
        '''
        try:
            while True:
                yield await self.receive_bytes()
        except WebSocketDisconnect:
            return

``__aiter__()``
~~~~~~~~~~~~~~~
Async iteration support (alias for iter_text).

Definition::

    def __aiter__(self) -> AsyncIterator[str]:
        '''
        Support async iteration over text messages.

        Equivalent to iter_text(). Use iter_bytes() for binary messages.

        Example:
            async for message in ws:  # Same as: async for message in ws.iter_text()
                handle_message(message)
        '''
        return self.iter_text()

Typed Messages (requires genro-tytx)
------------------------------------

``receive_typed()``
~~~~~~~~~~~~~~~~~~~
Receive JSON with TYTX hydration.

Definition::

    async def receive_typed(self) -> dict[str, Any]:
        '''
        Receive a text message with optional TYTX hydration.

        If the message ends with "::TYTX" marker, the content is parsed as
        JSON and hydrated using genro-tytx to restore Python types
        (Decimal, datetime, etc.).

        Returns:
            The parsed and optionally hydrated dict.

        Raises:
            RuntimeError: If not in CONNECTED state.
            ImportError: If genro-tytx is not installed.
            json.JSONDecodeError: If message is not valid JSON.
            WebSocketDisconnect: If client disconnected.

        Note:
            Requires genro-tytx package to be installed.
            Plain JSON (without ::TYTX marker) is returned as-is.

        Example:
            # Client sends: {"price": "100.50::D", "date": "2025-01-15::d"}::TYTX
            data = await ws.receive_typed()
            # data["price"] is Decimal("100.50")
            # data["date"] is date(2025, 1, 15)
        '''
        text = await self.receive_text()

        if text.endswith("::TYTX"):
            if not HAS_TYTX:
                raise ImportError(
                    "genro-tytx package required for receive_typed(). "
                    "Install with: pip install genro-tytx"
                )
            json_str = text[:-6]  # Remove "::TYTX" marker
            data = json.loads(json_str)
            return hydrate(data)  # From genro-tytx
        else:
            return json.loads(text)

``send_typed()``
~~~~~~~~~~~~~~~~
Send data with TYTX serialization.

Definition::

    async def send_typed(self, data: dict[str, Any]) -> None:
        '''
        Serialize data with TYTX and send with marker.

        Serializes Python types (Decimal, datetime, etc.) to TYTX format
        and appends "::TYTX" marker for the receiver to identify typed data.

        Args:
            data: Dict containing potentially typed values (Decimal, date, etc.).

        Raises:
            RuntimeError: If not in CONNECTED state.
            ImportError: If genro-tytx is not installed.

        Note:
            Requires genro-tytx package to be installed.

        Example:
            await ws.send_typed({
                "price": Decimal("100.50"),
                "created": datetime.now(),
            })
            # Sends: {"price": "100.50::D", "created": "2025-01-15T12:30:00::dt"}::TYTX
        '''
        if not HAS_TYTX:
            raise ImportError(
                "genro-tytx package required for send_typed(). "
                "Install with: pip install genro-tytx"
            )
        serialized = serialize(data)  # From genro-tytx
        text = json.dumps(serialized) + "::TYTX"
        await self.send_text(text)

Exception Classes
=================

WebSocketDisconnect
-------------------
Exception raised when client disconnects.

Definition::

    class WebSocketDisconnect(Exception):
        '''
        Raised when the WebSocket client disconnects.

        Attributes:
            code: WebSocket close code (default 1000).
            reason: Optional close reason string.

        Example:
            try:
                data = await ws.receive_text()
            except WebSocketDisconnect as e:
                print(f"Client disconnected: code={e.code}, reason={e.reason}")
        '''
        def __init__(self, code: int = 1000, reason: str = "") -> None:
            self.code = code
            self.reason = reason
            super().__init__(f"WebSocket disconnected: code={code}, reason={reason}")

Module Constants
================
::

    HAS_ORJSON: bool  # True if orjson is available
    HAS_TYTX: bool    # True if genro-tytx is available

    # Conditional imports
    try:
        import orjson
        HAS_ORJSON = True
    except ImportError:
        HAS_ORJSON = False

    try:
        from genro_tytx import hydrate, serialize
        HAS_TYTX = True
    except ImportError:
        HAS_TYTX = False
        hydrate = None  # type: ignore
        serialize = None  # type: ignore

Public Exports
==============
::

    __all__ = [
        "WebSocket",
        "WebSocketState",
        "WebSocketDisconnect",
    ]

Examples
========
Basic WebSocket handler::

    from genro_asgi.websocket import WebSocket, WebSocketDisconnect

    async def websocket_handler(scope, receive, send):
        ws = WebSocket(scope, receive, send)

        await ws.accept()
        print(f"Client connected from {ws.client}")

        try:
            async for message in ws:
                # Echo back
                await ws.send_text(f"You said: {message}")
        except WebSocketDisconnect:
            print("Client disconnected")

With subprotocol negotiation::

    async def handler(scope, receive, send):
        ws = WebSocket(scope, receive, send)

        # Check client's requested subprotocols
        if "graphql-ws" in ws.subprotocols:
            await ws.accept(subprotocol="graphql-ws")
        else:
            await ws.close(code=1002, reason="Unsupported protocol")
            return

        # Handle GraphQL WebSocket protocol
        ...

JSON messaging::

    async def handler(scope, receive, send):
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        try:
            while True:
                data = await ws.receive_json()
                response = {"received": data, "status": "ok"}
                await ws.send_json(response)
        except WebSocketDisconnect:
            pass

With TYTX typed data::

    from decimal import Decimal
    from datetime import date

    async def handler(scope, receive, send):
        ws = WebSocket(scope, receive, send)
        await ws.accept()

        # Receive typed data
        data = await ws.receive_typed()
        # data["amount"] might be Decimal, data["date"] might be date

        # Send typed data
        await ws.send_typed({
            "total": Decimal("123.45"),
            "processed_at": date.today(),
        })

Design Decisions
================
1. **WebSocketState as IntEnum**:
   IntEnum provides both type safety and easy comparisons. Integer values
   match the conceptual progression: 0 (not connected), 1 (connected),
   2 (disconnected).

2. **STRICT receive_text()/receive_bytes()**:
   Unlike some frameworks that auto-convert between text and bytes, we
   raise TypeError if the wrong type is received. This prevents silent
   encoding bugs and makes type mismatches explicit.

3. **accept() consumes websocket.connect**:
   Per ASGI spec, a websocket.connect message may be sent before
   websocket.accept. Our accept() method handles this transparently,
   consuming the connect message before sending accept.

4. **close() is idempotent**:
   Calling close() multiple times is safe (no-op if already disconnected).
   This simplifies cleanup code and context managers.

5. **Separate iter_text()/iter_bytes()**:
   Instead of a generic iterator that returns Union[str, bytes], we provide
   separate methods for type safety. __aiter__ aliases iter_text() as the
   common case.

6. **User-friendly accept() headers**:
   The accept() method takes Mapping[str, str] for headers instead of
   ASGI's list[tuple[bytes, bytes]]. Conversion is handled internally.

7. **Lazy property initialization**:
   Headers, query_params, URL, and state are created only when accessed.
   This avoids unnecessary work for simple echo handlers.

8. **URL construction duplicated from Request**:
   Rather than creating a shared utility prematurely, URL construction logic
   is duplicated. A shared url_from_scope() utility will be added in Block 13
   during final integration if the pattern proves valuable.

9. **Typed methods require explicit import**:
   receive_typed()/send_typed() raise ImportError if genro-tytx is not
   installed, rather than silently degrading. This makes dependencies explicit.

10. **subprotocols returns tuple**:
    Returns immutable tuple[str, ...] instead of mutable list to prevent
    accidental modification of scope data.

What This Module Does NOT Include
=================================
- **Message buffering**: No internal message queue. Each receive() call
  goes directly to ASGI. Buffering can be added at application level.

- **Ping/pong handling**: ASGI servers typically handle ping/pong frames
  automatically. We don't expose these.

- **Connection timeout**: No built-in timeout for receive operations.
  Use asyncio.timeout() or similar at application level.

- **Automatic reconnection**: This is a single-connection wrapper.
  Reconnection logic belongs at application level.

- **Message validation**: No schema validation. Use pydantic or similar
  after receive_json() if needed.

References
==========
- ASGI WebSocket Spec: https://asgi.readthedocs.io/en/latest/specs/www.html#websocket
- WebSocket Close Codes: https://developer.mozilla.org/en-US/docs/Web/API/CloseEvent/code
- RFC 6455 (WebSocket Protocol): https://tools.ietf.org/html/rfc6455
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from enum import IntEnum
from typing import TYPE_CHECKING, Any, AsyncIterator

from .datastructures import (
    Address,
    Headers,
    QueryParams,
    State,
    URL,
    headers_from_scope,
    query_params_from_scope,
)
from .exceptions import WebSocketDisconnect
from .types import Message, Receive, Scope, Send

__all__ = [
    "WebSocket",
    "WebSocketState",
]

# Optional dependency: orjson for faster JSON
try:
    import orjson

    HAS_ORJSON = True
except ImportError:
    orjson = None  # type: ignore[assignment]
    HAS_ORJSON = False

# Optional dependency: genro-tytx for typed serialization
try:
    from genro_tytx import hydrate, serialize

    HAS_TYTX = True
except ImportError:
    HAS_TYTX = False

    def hydrate(data: Any) -> Any:  # type: ignore[misc]
        """Placeholder when genro-tytx not installed."""
        raise ImportError("genro-tytx required")

    def serialize(data: Any) -> Any:  # type: ignore[misc]
        """Placeholder when genro-tytx not installed."""
        raise ImportError("genro-tytx required")


if TYPE_CHECKING:
    pass


class WebSocketState(IntEnum):
    """
    WebSocket connection state.

    Represents the three possible states of a WebSocket connection:

    - CONNECTING: Initial state, before accept() is called
    - CONNECTED: After accept(), can send and receive messages
    - DISCONNECTED: After close() or client disconnect

    Example:
        >>> ws = WebSocket(scope, receive, send)
        >>> ws.connection_state == WebSocketState.CONNECTING
        True
        >>> await ws.accept()
        >>> ws.connection_state == WebSocketState.CONNECTED
        True
    """

    CONNECTING = 0
    CONNECTED = 1
    DISCONNECTED = 2


class WebSocket:
    """
    WebSocket connection wrapper for ASGI.

    Provides a Pythonic interface for handling WebSocket connections through
    the ASGI protocol. Manages connection lifecycle (accept, close) and
    message sending/receiving.

    Attributes:
        scope: The ASGI scope dictionary.
        connection_state: Current WebSocketState.

    Example:
        >>> async def handler(scope, receive, send):
        ...     ws = WebSocket(scope, receive, send)
        ...     await ws.accept()
        ...     message = await ws.receive_text()
        ...     await ws.send_text(f"Echo: {message}")
        ...     await ws.close()
    """

    __slots__ = (
        "_scope",
        "_receive",
        "_send",
        "_connection_state",
        "_headers",
        "_query_params",
        "_url",
        "_state",
        "_accepted_subprotocol",
    )

    def __init__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """
        Initialize WebSocket connection wrapper.

        Args:
            scope: ASGI WebSocket scope dictionary.
            receive: ASGI receive callable.
            send: ASGI send callable.

        Raises:
            ValueError: If scope type is not "websocket".
        """
        if scope.get("type") != "websocket":
            raise ValueError(
                f"Expected scope type 'websocket', got '{scope.get('type')}'"
            )
        self._scope = scope
        self._receive = receive
        self._send = send
        self._connection_state = WebSocketState.CONNECTING
        self._headers: Headers | None = None
        self._query_params: QueryParams | None = None
        self._url: URL | None = None
        self._state: State | None = None
        self._accepted_subprotocol: str | None = None

    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def scope(self) -> Scope:
        """The raw ASGI scope dictionary."""
        return self._scope

    @property
    def connection_state(self) -> WebSocketState:
        """Current connection state."""
        return self._connection_state

    @property
    def path(self) -> str:
        """URL path component."""
        return str(self._scope.get("path", "/"))

    @property
    def scheme(self) -> str:
        """URL scheme ('ws' or 'wss')."""
        return str(self._scope.get("scheme", "ws"))

    @property
    def url(self) -> URL:
        """
        Full WebSocket URL.

        Constructed lazily from scope fields: scheme, server, root_path,
        path, and query_string.

        Returns:
            URL object representing the complete WebSocket URL.
        """
        if self._url is None:
            scheme = self.scheme
            server = self._scope.get("server")
            path = self._scope.get("root_path", "") + self.path
            query_string = self._scope.get("query_string", b"")

            if server:
                host, port = server
                # Omit default ports
                if (scheme == "ws" and port == 80) or (scheme == "wss" and port == 443):
                    netloc = host
                else:
                    netloc = f"{host}:{port}"
            else:
                netloc = self.headers.get("host", "localhost")

            url_str = f"{scheme}://{netloc}{path}"
            if query_string:
                url_str += f"?{query_string.decode('latin-1')}"

            self._url = URL(url_str)
        return self._url

    @property
    def headers(self) -> Headers:
        """Connection headers (case-insensitive)."""
        if self._headers is None:
            self._headers = headers_from_scope(self._scope)
        return self._headers

    @property
    def query_params(self) -> QueryParams:
        """Query string parameters."""
        if self._query_params is None:
            self._query_params = query_params_from_scope(self._scope)
        return self._query_params

    @property
    def state(self) -> State:
        """Per-connection state container."""
        if self._state is None:
            self._state = State()
        return self._state

    @property
    def client(self) -> Address | None:
        """Client address (host, port) if available."""
        client = self._scope.get("client")
        if client:
            return Address(client[0], client[1])
        return None

    @property
    def subprotocols(self) -> tuple[str, ...]:
        """Subprotocols requested by the client (immutable)."""
        return tuple(self._scope.get("subprotocols", []))

    @property
    def accepted_subprotocol(self) -> str | None:
        """The subprotocol selected in accept(), or None."""
        return self._accepted_subprotocol

    # =========================================================================
    # Connection Lifecycle
    # =========================================================================

    async def accept(
        self,
        subprotocol: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """
        Accept the WebSocket connection.

        Must be called before sending or receiving messages. Consumes the
        ``websocket.connect`` message and sends ``websocket.accept``.

        Args:
            subprotocol: Optional subprotocol to negotiate.
            headers: Optional headers to include in accept response.

        Raises:
            RuntimeError: If not in CONNECTING state or unexpected message.
        """
        if self._connection_state != WebSocketState.CONNECTING:
            raise RuntimeError(
                f"Cannot accept: connection in {self._connection_state.name} state"
            )

        # Consume the websocket.connect message
        message = await self._receive()
        if message["type"] != "websocket.connect":
            raise RuntimeError(f"Expected websocket.connect, got {message['type']}")

        # Build accept message
        accept_message: Message = {"type": "websocket.accept"}
        if subprotocol is not None:
            accept_message["subprotocol"] = subprotocol
            self._accepted_subprotocol = subprotocol
        if headers is not None:
            accept_message["headers"] = [
                (k.encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()
            ]

        await self._send(accept_message)
        self._connection_state = WebSocketState.CONNECTED

    async def close(
        self,
        code: int = 1000,
        reason: str = "",
    ) -> None:
        """
        Close the WebSocket connection.

        Idempotent: safe to call multiple times.

        Args:
            code: WebSocket close code (default 1000).
            reason: Optional close reason.

        Raises:
            RuntimeError: If connection not accepted yet.
        """
        if self._connection_state == WebSocketState.DISCONNECTED:
            return  # Idempotent

        if self._connection_state == WebSocketState.CONNECTING:
            raise RuntimeError("Cannot close: connection not accepted yet")

        await self._send({
            "type": "websocket.close",
            "code": code,
            "reason": reason,
        })
        self._connection_state = WebSocketState.DISCONNECTED

    # =========================================================================
    # Receiving Messages
    # =========================================================================

    async def _receive_message(self) -> Message:
        """
        Internal: receive message with state validation.

        Returns:
            The ASGI message dict.

        Raises:
            RuntimeError: If not connected.
            WebSocketDisconnect: If client disconnected.
        """
        if self._connection_state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"Cannot receive: connection in {self._connection_state.name} state"
            )

        message = await self._receive()
        if message["type"] == "websocket.disconnect":
            self._connection_state = WebSocketState.DISCONNECTED
            raise WebSocketDisconnect(
                code=message.get("code", 1000),
                reason=message.get("reason", ""),
            )
        return message

    async def receive_text(self) -> str:
        """
        Receive a text message.

        Returns:
            The text message content.

        Raises:
            RuntimeError: If not connected.
            TypeError: If received binary data.
            WebSocketDisconnect: If client disconnected.
        """
        message = await self._receive_message()
        if "bytes" in message and message["bytes"] is not None:
            raise TypeError(
                "Received binary message. Use receive_bytes() for binary data."
            )
        text: str = message.get("text", "")
        return text

    async def receive_bytes(self) -> bytes:
        """
        Receive a binary message.

        Returns:
            The binary message content.

        Raises:
            RuntimeError: If not connected.
            TypeError: If received text data.
            WebSocketDisconnect: If client disconnected.
        """
        message = await self._receive_message()
        if "text" in message and message["text"] is not None:
            raise TypeError(
                "Received text message. Use receive_text() for text data."
            )
        data: bytes = message.get("bytes", b"")
        return data

    async def receive_json(self) -> Any:
        """
        Receive and parse a JSON text message.

        Returns:
            The parsed JSON value.

        Raises:
            RuntimeError: If not connected.
            TypeError: If received binary data.
            json.JSONDecodeError: If not valid JSON.
            WebSocketDisconnect: If client disconnected.
        """
        text = await self.receive_text()
        if HAS_ORJSON and orjson is not None:
            return orjson.loads(text)
        return json.loads(text)

    # =========================================================================
    # Sending Messages
    # =========================================================================

    async def _send_message(self, message: Message) -> None:
        """
        Internal: send message with state validation.

        Args:
            message: ASGI message dict.

        Raises:
            RuntimeError: If not connected.
        """
        if self._connection_state != WebSocketState.CONNECTED:
            raise RuntimeError(
                f"Cannot send: connection in {self._connection_state.name} state"
            )
        await self._send(message)

    async def send_text(self, data: str) -> None:
        """
        Send a text message.

        Args:
            data: Text to send.

        Raises:
            RuntimeError: If not connected.
        """
        await self._send_message({"type": "websocket.send", "text": data})

    async def send_bytes(self, data: bytes) -> None:
        """
        Send a binary message.

        Args:
            data: Bytes to send.

        Raises:
            RuntimeError: If not connected.
        """
        await self._send_message({"type": "websocket.send", "bytes": data})

    async def send_json(self, data: Any) -> None:
        """
        Serialize data to JSON and send.

        Args:
            data: JSON-serializable data.

        Raises:
            RuntimeError: If not connected.
            TypeError: If data not serializable.
        """
        if HAS_ORJSON and orjson is not None:
            text = orjson.dumps(data).decode("utf-8")
        else:
            text = json.dumps(data)
        await self.send_text(text)

    # =========================================================================
    # Iteration
    # =========================================================================

    async def iter_text(self) -> AsyncIterator[str]:
        """
        Async iterator yielding text messages.

        Yields:
            Each text message until disconnect.

        Raises:
            TypeError: If binary message received.
        """
        try:
            while True:
                yield await self.receive_text()
        except WebSocketDisconnect:
            return

    async def iter_bytes(self) -> AsyncIterator[bytes]:
        """
        Async iterator yielding binary messages.

        Yields:
            Each binary message until disconnect.

        Raises:
            TypeError: If text message received.
        """
        try:
            while True:
                yield await self.receive_bytes()
        except WebSocketDisconnect:
            return

    def __aiter__(self) -> AsyncIterator[str]:
        """
        Support async iteration (alias for iter_text).

        Returns:
            Async iterator over text messages.
        """
        return self.iter_text()

    # =========================================================================
    # Typed Messages (requires genro-tytx)
    # =========================================================================

    async def receive_typed(self) -> dict[str, Any]:
        """
        Receive JSON with optional TYTX hydration.

        Returns:
            Parsed dict, hydrated if ::TYTX marker present.

        Raises:
            ImportError: If genro-tytx not installed and marker present.
            RuntimeError: If not connected.
            json.JSONDecodeError: If not valid JSON.
        """
        text = await self.receive_text()

        if text.endswith("::TYTX"):
            if not HAS_TYTX:
                raise ImportError(
                    "genro-tytx package required for receive_typed(). "
                    "Install with: pip install genro-tytx"
                )
            json_str = text[:-6]  # Remove "::TYTX" marker
            parsed = json.loads(json_str)
            hydrated: dict[str, Any] = hydrate(parsed)
            return hydrated
        else:
            result: dict[str, Any] = json.loads(text)
            return result

    async def send_typed(self, data: dict[str, Any]) -> None:
        """
        Serialize with TYTX and send with marker.

        Args:
            data: Dict with potentially typed values.

        Raises:
            ImportError: If genro-tytx not installed.
            RuntimeError: If not connected.
        """
        if not HAS_TYTX:
            raise ImportError(
                "genro-tytx package required for send_typed(). "
                "Install with: pip install genro-tytx"
            )
        serialized = serialize(data)
        text = json.dumps(serialized) + "::TYTX"
        await self.send_text(text)


if __name__ == "__main__":
    # Minimal demo with mock ASGI interface
    import asyncio

    async def demo() -> None:
        """Demo WebSocket class with mock receive/send."""
        # Mock scope
        scope: Scope = {
            "type": "websocket",
            "scheme": "wss",
            "path": "/ws/chat",
            "query_string": b"room=general",
            "headers": [
                (b"host", b"example.com"),
                (b"sec-websocket-protocol", b"chat, superchat"),
            ],
            "server": ("example.com", 443),
            "client": ("192.168.1.100", 54321),
            "subprotocols": ["chat", "superchat"],
        }

        # Mock message queue
        messages: list[Message] = [
            {"type": "websocket.connect"},
            {"type": "websocket.receive", "text": "Hello, server!"},
            {"type": "websocket.receive", "text": '{"action": "ping"}'},
            {"type": "websocket.disconnect", "code": 1000},
        ]
        msg_index = 0
        sent_messages: list[Message] = []

        async def mock_receive() -> Message:
            nonlocal msg_index
            if msg_index < len(messages):
                msg = messages[msg_index]
                msg_index += 1
                return msg
            return {"type": "websocket.disconnect", "code": 1000}

        async def mock_send(message: Message) -> None:
            sent_messages.append(message)

        # Create WebSocket instance
        ws = WebSocket(scope, mock_receive, mock_send)

        print(f"Path: {ws.path}")
        print(f"Scheme: {ws.scheme}")
        print(f"URL: {ws.url}")
        print(f"Client: {ws.client}")
        print(f"Subprotocols: {ws.subprotocols}")
        print(f"State: {ws.connection_state.name}")
        print()

        # Accept connection
        await ws.accept(subprotocol="chat")
        print(f"Accepted with subprotocol: {ws.accepted_subprotocol}")
        print(f"State after accept: {ws.connection_state.name}")
        print()

        # Receive messages
        try:
            message = await ws.receive_text()
            print(f"Received text: {message}")

            data = await ws.receive_json()
            print(f"Received JSON: {data}")

            # This will trigger disconnect
            await ws.receive_text()
        except WebSocketDisconnect as e:
            print(f"Disconnected: code={e.code}")
            print(f"State after disconnect: {ws.connection_state.name}")

        print()
        print(f"Sent messages: {len(sent_messages)}")
        for msg in sent_messages:
            print(f"  {msg}")

    asyncio.run(demo())
