# Block 01: types.py

**Status**: DA REVISIONARE
**Dependencies**: None
**Commit message**: `feat(types): add ASGI type definitions`

---

## Purpose

Define ASGI type aliases for type safety throughout the codebase.

## File: `src/genro_asgi/types.py`

```python
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
```

## Tests: `tests/test_types.py`

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for ASGI type definitions."""

from genro_asgi.types import ASGIApp, Message, Receive, Scope, Send


def test_types_importable():
    """Verify all types are importable."""
    assert Scope is not None
    assert Message is not None
    assert Receive is not None
    assert Send is not None
    assert ASGIApp is not None


def test_scope_is_mutable_mapping():
    """Scope should accept dict-like objects."""
    scope: Scope = {"type": "http", "method": "GET"}
    scope["path"] = "/"
    assert scope["type"] == "http"


def test_message_is_mutable_mapping():
    """Message should accept dict-like objects."""
    message: Message = {"type": "http.request", "body": b""}
    assert message["type"] == "http.request"
```

## Exports in `__init__.py`

```python
from .types import ASGIApp, Message, Receive, Scope, Send
```

## Checklist

- [ ] Create `src/genro_asgi/types.py`
- [ ] Create `tests/test_types.py`
- [ ] Run `pytest tests/test_types.py`
- [ ] Run `mypy src/genro_asgi/types.py`
- [ ] Update `__init__.py` exports
- [ ] Commit
