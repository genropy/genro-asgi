## Source: initial_implementation_plan/archive/03-exceptions.md

**Status**: DA REVISIONARE
**Dependencies**: None
**Commit message**: `feat(exceptions): add HTTPException and WebSocketException`

Exception classes for HTTP and WebSocket error handling.

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Exception classes for genro-asgi."""

class HTTPException(Exception):
    """
    HTTP exception with status code and detail.

Raise this in handlers to return an HTTP error response.

Example:
        raise HTTPException(404, detail="User not found")
    """

def __init__(
        self,
        status_code: int,
        detail: str = "",
        headers: dict[str, str] | None = None
    ) -> None:
        """
        Initialize HTTP exception.

Args:
            status_code: HTTP status code (4xx, 5xx)
            detail: Error detail message
            headers: Optional response headers
        """
        self.status_code = status_code
        self.detail = detail
        self.headers = headers
        super().__init__(detail)

def __repr__(self) -> str:
        return f"HTTPException(status_code={self.status_code}, detail={self.detail!r})"

class WebSocketException(Exception):
    """
    WebSocket exception with close code and reason.

Raise this to close a WebSocket connection with an error.

Example:
        raise WebSocketException(code=4000, reason="Invalid message format")
    """

def __init__(
        self,
        code: int = 1000,
        reason: str = ""
    ) -> None:
        """
        Initialize WebSocket exception.

Args:
            code: WebSocket close code (1000-4999)
            reason: Close reason message
        """
        self.code = code
        self.reason = reason
        super().__init__(reason)

def __repr__(self) -> str:
        return f"WebSocketException(code={self.code}, reason={self.reason!r})"

class WebSocketDisconnect(Exception):
    """
    Raised when a WebSocket is disconnected by the client.

This is not an error, just a signal that the connection was closed.
    """

def __init__(self, code: int = 1000, reason: str = "") -> None:
        """
        Initialize disconnect exception.

Args:
            code: WebSocket close code
            reason: Close reason (if any)
        """
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket disconnected with code {code}")
```

```python
# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for exception classes."""

import pytest
from genro_asgi.exceptions import HTTPException, WebSocketDisconnect, WebSocketException

class TestHTTPException:
    def test_basic(self):
        exc = HTTPException(404, detail="Not found")
        assert exc.status_code == 404
        assert exc.detail == "Not found"
        assert exc.headers is None

def test_with_headers(self):
        exc = HTTPException(401, detail="Unauthorized", headers={"WWW-Authenticate": "Bearer"})
        assert exc.headers == {"WWW-Authenticate": "Bearer"}

def test_default_detail(self):
        exc = HTTPException(500)
        assert exc.detail == ""

def test_str(self):
        exc = HTTPException(400, detail="Bad request")
        assert str(exc) == "Bad request"

def test_repr(self):
        exc = HTTPException(404, detail="Not found")
        assert "404" in repr(exc)
        assert "Not found" in repr(exc)

def test_raise_catch(self):
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(403, detail="Forbidden")
        assert exc_info.value.status_code == 403

class TestWebSocketException:
    def test_basic(self):
        exc = WebSocketException(code=4000, reason="Custom error")
        assert exc.code == 4000
        assert exc.reason == "Custom error"

def test_defaults(self):
        exc = WebSocketException()
        assert exc.code == 1000
        assert exc.reason == ""

def test_str(self):
        exc = WebSocketException(code=4001, reason="Invalid")
        assert str(exc) == "Invalid"

def test_repr(self):
        exc = WebSocketException(code=4000, reason="Error")
        assert "4000" in repr(exc)

def test_raise_catch(self):
        with pytest.raises(WebSocketException) as exc_info:
            raise WebSocketException(code=4002, reason="Test")
        assert exc_info.value.code == 4002

class TestWebSocketDisconnect:
    def test_basic(self):
        exc = WebSocketDisconnect(code=1001, reason="Going away")
        assert exc.code == 1001
        assert exc.reason == "Going away"

def test_defaults(self):
        exc = WebSocketDisconnect()
        assert exc.code == 1000
        assert exc.reason == ""

def test_str(self):
        exc = WebSocketDisconnect(code=1000)
        assert "1000" in str(exc)

def test_raise_catch(self):
        with pytest.raises(WebSocketDisconnect):
            raise WebSocketDisconnect()
```

```python
from .exceptions import HTTPException, WebSocketDisconnect, WebSocketException
```

- [ ] Create `src/genro_asgi/exceptions.py`
- [ ] Create `tests/test_exceptions.py`
- [ ] Run `pytest tests/test_exceptions.py`
- [ ] Run `mypy src/genro_asgi/exceptions.py`
- [ ] Update `__init__.py` exports
- [ ] Commit

