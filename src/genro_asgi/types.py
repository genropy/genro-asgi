# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""ASGI type definitions."""

from typing import Any, Awaitable, Callable, MutableMapping

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
