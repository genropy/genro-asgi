# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ASGI type definitions for genro-asgi.

Purpose
=======
This module defines type aliases for the ASGI (Asynchronous Server Gateway
Interface) specification. These types provide type safety and documentation
throughout the genro-asgi codebase.

ASGI is the asynchronous successor to WSGI, designed for async Python web
frameworks. It defines a standard interface between async web servers and
Python applications.

Imports Required
================
::

    from typing import Any, Awaitable, Callable, MutableMapping

Type Definitions
================

Scope : MutableMapping[str, Any]
    Connection metadata dictionary passed to the application at connection
    start. Contains information about the connection type, HTTP method,
    path, headers, client/server addresses, etc.

    The scope type varies by connection:
    - HTTP: type="http", includes method, path, headers, query_string
    - WebSocket: type="websocket", includes path, headers, subprotocols
    - Lifespan: type="lifespan", for startup/shutdown events

    Definition::

        Scope = MutableMapping[str, Any]

Message : MutableMapping[str, Any]
    Dictionary representing messages sent between application and server.
    Each message has a "type" key identifying the message type.

    Common message types:
    - "http.request": incoming HTTP body chunks
    - "http.response.start": response status and headers
    - "http.response.body": response body chunks
    - "websocket.connect": WebSocket connection request
    - "websocket.receive": incoming WebSocket message
    - "websocket.send": outgoing WebSocket message
    - "lifespan.startup": application startup event
    - "lifespan.shutdown": application shutdown event

    Definition::

        Message = MutableMapping[str, Any]

Receive : Callable[[], Awaitable[Message]]
    Async callable to receive the next message from the client/server.
    Called without arguments, returns the next Message.

    Definition::

        Receive = Callable[[], Awaitable[Message]]

Send : Callable[[Message], Awaitable[None]]
    Async callable to send a message to the client/server.
    Takes a Message as argument, returns None.

    Definition::

        Send = Callable[[Message], Awaitable[None]]

ASGIApp : Callable[[Scope, Receive, Send], Awaitable[None]]
    The main ASGI application callable. Every ASGI application must be
    callable with this signature.

    Definition::

        ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

Public Exports
==============
The module exports (via __all__)::

    __all__ = ["Scope", "Message", "Receive", "Send", "ASGIApp"]

Examples
========
Minimal ASGI application::

    from genro_asgi.types import ASGIApp, Scope, Receive, Send

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [[b"content-type", b"text/plain"]],
            })
            await send({
                "type": "http.response.body",
                "body": b"Hello, World!",
            })

Type checking usage::

    from genro_asgi.types import Scope, Message

    def process_scope(scope: Scope) -> str:
        return scope.get("path", "/")

    def process_message(message: Message) -> bytes:
        return message.get("body", b"")

Design Decisions
================
1. **MutableMapping instead of TypedDict for Scope/Message**:
   ASGI allows server-specific extensions and custom fields. TypedDict would
   be too rigid and require `total=False` with many optional fields.
   MutableMapping provides flexibility while still indicating dict-like
   behavior. Real validation happens at runtime in Request/Response classes.

2. **No Headers type alias**:
   Headers in ASGI are `list[tuple[bytes, bytes]]`. Rather than a simple
   alias, we will create a proper Headers class with utility methods
   (case-insensitive lookup, iteration, etc.) in the datastructures module
   (Block 02). A raw alias would be confusing alongside a class.

3. **Simple Callable aliases instead of Protocol**:
   For Receive, Send, and ASGIApp we use Callable type aliases rather than
   Protocol classes. Both work equally well for type checking, but Callable
   is simpler and more familiar. The ASGI spec itself uses callable notation.

4. **No message-specific TypedDicts**:
   Like Scope, Message types vary widely (http.request, http.response.start,
   websocket.receive, etc.). Defining TypedDict for each would be verbose
   and fragile. Generic MutableMapping with runtime validation is preferred.

What This Module Does NOT Include
=================================
- **Headers class**: Will be in datastructures.py (Block 02) as a proper
  class with methods, not a simple type alias.
- **Specific scope TypedDicts** (HTTPScope, WebSocketScope, LifespanScope):
  Too rigid for ASGI's extensible nature. Use generic Scope.
- **Message validation**: Runtime validation belongs in Request/Response
  classes, not in type definitions.
- **Protocol definitions**: Simple Callable aliases are sufficient.

References
==========
- ASGI Specification: https://asgi.readthedocs.io/en/latest/specs/main.html
- ASGI HTTP Spec: https://asgi.readthedocs.io/en/latest/specs/www.html
- ASGI WebSocket Spec: https://asgi.readthedocs.io/en/latest/specs/www.html#websocket
- ASGI Lifespan Spec: https://asgi.readthedocs.io/en/latest/specs/lifespan.html
"""

from typing import Any, Awaitable, Callable, MutableMapping

__all__ = ["Scope", "Message", "Receive", "Send", "ASGIApp"]

# ASGI Scope - connection metadata
Scope = MutableMapping[str, Any]

# ASGI Message - sent/received data
Message = MutableMapping[str, Any]

# ASGI Receive - callable to receive messages
Receive = Callable[[], Awaitable[Message]]

# ASGI Send - callable to send messages
Send = Callable[[Message], Awaitable[None]]

# ASGI Application - the main callable
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
