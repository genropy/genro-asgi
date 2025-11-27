# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for exception classes."""

import pytest

from genro_asgi.exceptions import (
    HTTPException,
    WebSocketDisconnect,
    WebSocketException,
)


class TestHTTPException:
    """Tests for HTTPException class."""

    def test_basic_creation(self) -> None:
        """Test creating exception with status code and detail."""
        exc = HTTPException(404, detail="Not found")
        assert exc.status_code == 404
        assert exc.detail == "Not found"
        assert exc.headers is None

    def test_with_headers(self) -> None:
        """Test creating exception with custom headers."""
        headers = {"WWW-Authenticate": "Bearer realm='api'"}
        exc = HTTPException(401, detail="Unauthorized", headers=headers)
        assert exc.status_code == 401
        assert exc.detail == "Unauthorized"
        assert exc.headers == headers

    def test_default_detail(self) -> None:
        """Test that detail defaults to empty string."""
        exc = HTTPException(500)
        assert exc.detail == ""

    def test_default_headers(self) -> None:
        """Test that headers defaults to None."""
        exc = HTTPException(400, detail="Bad request")
        assert exc.headers is None

    def test_str_returns_detail(self) -> None:
        """Test that str() returns the detail message."""
        exc = HTTPException(400, detail="Bad request")
        assert str(exc) == "Bad request"

    def test_str_empty_detail(self) -> None:
        """Test str() with empty detail."""
        exc = HTTPException(500)
        assert str(exc) == ""

    def test_repr(self) -> None:
        """Test __repr__ format."""
        exc = HTTPException(404, detail="Not found")
        repr_str = repr(exc)
        assert "HTTPException" in repr_str
        assert "404" in repr_str
        assert "Not found" in repr_str

    def test_repr_with_quotes_in_detail(self) -> None:
        """Test __repr__ properly escapes quotes in detail."""
        exc = HTTPException(400, detail="Invalid 'value'")
        repr_str = repr(exc)
        assert "Invalid" in repr_str

    def test_raise_and_catch(self) -> None:
        """Test raising and catching the exception."""
        with pytest.raises(HTTPException) as exc_info:
            raise HTTPException(403, detail="Forbidden")
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "Forbidden"

    def test_catch_as_exception(self) -> None:
        """Test that HTTPException can be caught as Exception."""
        with pytest.raises(Exception):
            raise HTTPException(500, detail="Internal error")

    def test_various_status_codes(self) -> None:
        """Test with various HTTP status codes."""
        # 4xx client errors
        assert HTTPException(400).status_code == 400
        assert HTTPException(401).status_code == 401
        assert HTTPException(403).status_code == 403
        assert HTTPException(404).status_code == 404
        assert HTTPException(422).status_code == 422
        assert HTTPException(429).status_code == 429

        # 5xx server errors
        assert HTTPException(500).status_code == 500
        assert HTTPException(502).status_code == 502
        assert HTTPException(503).status_code == 503

    def test_headers_not_modified(self) -> None:
        """Test that headers dict is stored as-is."""
        headers = {"X-Custom": "value"}
        exc = HTTPException(400, headers=headers)
        assert exc.headers is headers  # Same object


class TestWebSocketException:
    """Tests for WebSocketException class."""

    def test_basic_creation(self) -> None:
        """Test creating exception with code and reason."""
        exc = WebSocketException(code=4000, reason="Custom error")
        assert exc.code == 4000
        assert exc.reason == "Custom error"

    def test_defaults(self) -> None:
        """Test default values."""
        exc = WebSocketException()
        assert exc.code == 1000
        assert exc.reason == ""

    def test_default_reason(self) -> None:
        """Test that reason defaults to empty string."""
        exc = WebSocketException(code=4001)
        assert exc.reason == ""

    def test_default_code(self) -> None:
        """Test that code defaults to 1000."""
        exc = WebSocketException(reason="test")
        assert exc.code == 1000

    def test_str_returns_reason(self) -> None:
        """Test that str() returns the reason."""
        exc = WebSocketException(code=4001, reason="Invalid message")
        assert str(exc) == "Invalid message"

    def test_str_empty_reason(self) -> None:
        """Test str() with empty reason."""
        exc = WebSocketException(code=4000)
        assert str(exc) == ""

    def test_repr(self) -> None:
        """Test __repr__ format."""
        exc = WebSocketException(code=4000, reason="Error")
        repr_str = repr(exc)
        assert "WebSocketException" in repr_str
        assert "4000" in repr_str
        assert "Error" in repr_str

    def test_raise_and_catch(self) -> None:
        """Test raising and catching the exception."""
        with pytest.raises(WebSocketException) as exc_info:
            raise WebSocketException(code=4002, reason="Test error")
        assert exc_info.value.code == 4002
        assert exc_info.value.reason == "Test error"

    def test_catch_as_exception(self) -> None:
        """Test that WebSocketException can be caught as Exception."""
        with pytest.raises(Exception):
            raise WebSocketException(code=4000)

    def test_standard_close_codes(self) -> None:
        """Test with standard WebSocket close codes."""
        # Normal closure
        assert WebSocketException(code=1000).code == 1000
        # Going away
        assert WebSocketException(code=1001).code == 1001
        # Protocol error
        assert WebSocketException(code=1002).code == 1002
        # Policy violation
        assert WebSocketException(code=1008).code == 1008
        # Internal error
        assert WebSocketException(code=1011).code == 1011

    def test_application_codes(self) -> None:
        """Test with application-specific codes (4000-4999)."""
        for code in [4000, 4001, 4100, 4500, 4999]:
            exc = WebSocketException(code=code)
            assert exc.code == code


class TestWebSocketDisconnect:
    """Tests for WebSocketDisconnect class."""

    def test_basic_creation(self) -> None:
        """Test creating disconnect with code and reason."""
        exc = WebSocketDisconnect(code=1001, reason="Going away")
        assert exc.code == 1001
        assert exc.reason == "Going away"

    def test_defaults(self) -> None:
        """Test default values."""
        exc = WebSocketDisconnect()
        assert exc.code == 1000
        assert exc.reason == ""

    def test_default_reason(self) -> None:
        """Test that reason defaults to empty string."""
        exc = WebSocketDisconnect(code=1001)
        assert exc.reason == ""

    def test_default_code(self) -> None:
        """Test that code defaults to 1000."""
        exc = WebSocketDisconnect(reason="test")
        assert exc.code == 1000

    def test_str_contains_code(self) -> None:
        """Test that str() contains the disconnect code."""
        exc = WebSocketDisconnect(code=1001)
        assert "1001" in str(exc)

    def test_str_format(self) -> None:
        """Test the format of str()."""
        exc = WebSocketDisconnect(code=1000)
        assert str(exc) == "WebSocket disconnected with code 1000"

    def test_repr(self) -> None:
        """Test __repr__ format."""
        exc = WebSocketDisconnect(code=1001, reason="Going away")
        repr_str = repr(exc)
        assert "WebSocketDisconnect" in repr_str
        assert "1001" in repr_str
        assert "Going away" in repr_str

    def test_raise_and_catch(self) -> None:
        """Test raising and catching the exception."""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            raise WebSocketDisconnect(code=1000, reason="Normal")
        assert exc_info.value.code == 1000

    def test_catch_as_exception(self) -> None:
        """Test that WebSocketDisconnect can be caught as Exception."""
        with pytest.raises(Exception):
            raise WebSocketDisconnect()

    def test_not_caught_by_websocket_exception(self) -> None:
        """Test that WebSocketDisconnect is NOT caught by WebSocketException."""
        with pytest.raises(WebSocketDisconnect):
            try:
                raise WebSocketDisconnect()
            except WebSocketException:
                pytest.fail("WebSocketDisconnect should not be caught by WebSocketException")


class TestExceptionHierarchy:
    """Tests for exception inheritance and relationships."""

    def test_all_inherit_from_exception(self) -> None:
        """Test that all exceptions inherit from Exception."""
        assert issubclass(HTTPException, Exception)
        assert issubclass(WebSocketException, Exception)
        assert issubclass(WebSocketDisconnect, Exception)

    def test_not_related_to_each_other(self) -> None:
        """Test that exceptions are not subclasses of each other."""
        assert not issubclass(HTTPException, WebSocketException)
        assert not issubclass(HTTPException, WebSocketDisconnect)
        assert not issubclass(WebSocketException, HTTPException)
        assert not issubclass(WebSocketException, WebSocketDisconnect)
        assert not issubclass(WebSocketDisconnect, HTTPException)
        assert not issubclass(WebSocketDisconnect, WebSocketException)

    def test_catch_multiple_with_tuple(self) -> None:
        """Test catching multiple exception types with tuple."""
        caught = False

        # Test HTTPException
        try:
            raise HTTPException(400)
        except (HTTPException, WebSocketException):
            caught = True
        assert caught

        # Test WebSocketException
        caught = False
        try:
            raise WebSocketException(code=4000)
        except (HTTPException, WebSocketException):
            caught = True
        assert caught

    def test_isinstance_checks(self) -> None:
        """Test isinstance for all exception types."""
        http_exc = HTTPException(400)
        ws_exc = WebSocketException(code=4000)
        ws_disc = WebSocketDisconnect()

        assert isinstance(http_exc, Exception)
        assert isinstance(ws_exc, Exception)
        assert isinstance(ws_disc, Exception)

        assert isinstance(http_exc, HTTPException)
        assert not isinstance(http_exc, WebSocketException)
        assert not isinstance(http_exc, WebSocketDisconnect)

        assert isinstance(ws_exc, WebSocketException)
        assert not isinstance(ws_exc, HTTPException)
        assert not isinstance(ws_exc, WebSocketDisconnect)

        assert isinstance(ws_disc, WebSocketDisconnect)
        assert not isinstance(ws_disc, HTTPException)
        assert not isinstance(ws_disc, WebSocketException)
