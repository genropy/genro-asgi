# Copyright 2025 Softwell S.r.l.
# Licensed under the Apache License, Version 2.0

"""Tests for ASGI type definitions.

These tests verify the type aliases defined in genro_asgi.types module.
Tests cover:
- Import availability
- Type compatibility with dict-like objects
- Callable signature compatibility
- __all__ exports
"""

from typing import Any, Awaitable, Callable, MutableMapping

import pytest

from genro_asgi.types import ASGIApp, Message, Receive, Scope, Send


class TestTypeImports:
    """Test that all types are importable and correctly defined."""

    def test_all_types_importable(self):
        """Verify all types are importable from the module."""
        assert Scope is not None
        assert Message is not None
        assert Receive is not None
        assert Send is not None
        assert ASGIApp is not None

    def test_all_exports(self):
        """Verify __all__ contains exactly the expected exports."""
        from genro_asgi import types

        expected = {"Scope", "Message", "Receive", "Send", "ASGIApp"}
        assert set(types.__all__) == expected

    def test_types_importable_from_package(self):
        """Verify types can be imported from main package."""
        from genro_asgi import ASGIApp, Message, Receive, Scope, Send

        assert Scope is not None
        assert Message is not None
        assert Receive is not None
        assert Send is not None
        assert ASGIApp is not None


class TestScopeType:
    """Test Scope type alias behavior."""

    def test_scope_accepts_dict(self):
        """Scope should accept regular dict."""
        scope: Scope = {"type": "http", "method": "GET"}
        assert scope["type"] == "http"

    def test_scope_is_mutable(self):
        """Scope should be mutable (can add/modify keys)."""
        scope: Scope = {"type": "http"}
        scope["path"] = "/"
        scope["method"] = "POST"
        assert scope["path"] == "/"
        assert scope["method"] == "POST"

    def test_scope_http_example(self):
        """Scope should accept typical HTTP scope structure."""
        scope: Scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/users",
            "raw_path": b"/api/users",
            "query_string": b"id=123",
            "root_path": "",
            "headers": [(b"host", b"example.com")],
            "server": ("example.com", 443),
            "client": ("192.168.1.1", 54321),
        }
        assert scope["type"] == "http"
        assert scope["method"] == "GET"

    def test_scope_websocket_example(self):
        """Scope should accept typical WebSocket scope structure."""
        scope: Scope = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "wss",
            "path": "/ws",
            "query_string": b"",
            "headers": [(b"host", b"example.com")],
            "subprotocols": ["graphql-ws"],
        }
        assert scope["type"] == "websocket"

    def test_scope_lifespan_example(self):
        """Scope should accept typical Lifespan scope structure."""
        scope: Scope = {
            "type": "lifespan",
            "asgi": {"version": "3.0"},
        }
        assert scope["type"] == "lifespan"


class TestMessageType:
    """Test Message type alias behavior."""

    def test_message_accepts_dict(self):
        """Message should accept regular dict."""
        message: Message = {"type": "http.request", "body": b""}
        assert message["type"] == "http.request"

    def test_message_http_request(self):
        """Message should accept HTTP request message."""
        message: Message = {
            "type": "http.request",
            "body": b'{"key": "value"}',
            "more_body": False,
        }
        assert message["type"] == "http.request"
        assert message["body"] == b'{"key": "value"}'

    def test_message_http_response_start(self):
        """Message should accept HTTP response start message."""
        message: Message = {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
        assert message["type"] == "http.response.start"
        assert message["status"] == 200

    def test_message_http_response_body(self):
        """Message should accept HTTP response body message."""
        message: Message = {
            "type": "http.response.body",
            "body": b"Hello, World!",
            "more_body": False,
        }
        assert message["type"] == "http.response.body"

    def test_message_websocket_receive(self):
        """Message should accept WebSocket receive message."""
        message: Message = {
            "type": "websocket.receive",
            "text": '{"action": "subscribe"}',
        }
        assert message["type"] == "websocket.receive"

    def test_message_websocket_send(self):
        """Message should accept WebSocket send message."""
        message: Message = {
            "type": "websocket.send",
            "bytes": b"\x00\x01\x02",
        }
        assert message["type"] == "websocket.send"

    def test_message_lifespan_startup(self):
        """Message should accept lifespan startup message."""
        message: Message = {"type": "lifespan.startup"}
        assert message["type"] == "lifespan.startup"


class TestCallableTypes:
    """Test Receive, Send, and ASGIApp callable type aliases."""

    @pytest.mark.asyncio
    async def test_receive_callable_signature(self):
        """Receive should match Callable[[], Awaitable[Message]]."""

        async def mock_receive() -> Message:
            return {"type": "http.request", "body": b""}

        receive: Receive = mock_receive
        message = await receive()
        assert message["type"] == "http.request"

    @pytest.mark.asyncio
    async def test_send_callable_signature(self):
        """Send should match Callable[[Message], Awaitable[None]]."""
        sent_messages: list[Message] = []

        async def mock_send(message: Message) -> None:
            sent_messages.append(message)

        send: Send = mock_send
        await send({"type": "http.response.start", "status": 200, "headers": []})
        assert len(sent_messages) == 1
        assert sent_messages[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_asgi_app_callable_signature(self):
        """ASGIApp should match Callable[[Scope, Receive, Send], Awaitable[None]]."""
        responses: list[Message] = []

        async def mock_receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def mock_send(message: Message) -> None:
            responses.append(message)

        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        asgi_app: ASGIApp = app
        await asgi_app({"type": "http"}, mock_receive, mock_send)

        assert len(responses) == 2
        assert responses[0]["type"] == "http.response.start"
        assert responses[1]["type"] == "http.response.body"


class TestDocstringExample:
    """Test the example from the module docstring."""

    @pytest.mark.asyncio
    async def test_minimal_asgi_application(self):
        """Test the minimal ASGI application example from docstring."""
        responses: list[Message] = []

        async def mock_receive() -> Message:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def mock_send(message: Message) -> None:
            responses.append(message)

        # This is the exact example from the docstring
        async def app(scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] == "http":
                await send(
                    {
                        "type": "http.response.start",
                        "status": 200,
                        "headers": [[b"content-type", b"text/plain"]],
                    }
                )
                await send(
                    {
                        "type": "http.response.body",
                        "body": b"Hello, World!",
                    }
                )

        await app({"type": "http"}, mock_receive, mock_send)

        assert len(responses) == 2
        assert responses[0]["status"] == 200
        assert responses[1]["body"] == b"Hello, World!"

    def test_type_checking_usage_scope(self):
        """Test the type checking usage example for Scope from docstring."""

        def process_scope(scope: Scope) -> str:
            return scope.get("path", "/")

        assert process_scope({"path": "/api"}) == "/api"
        assert process_scope({"type": "http"}) == "/"

    def test_type_checking_usage_message(self):
        """Test the type checking usage example for Message from docstring."""

        def process_message(message: Message) -> bytes:
            return message.get("body", b"")

        assert process_message({"body": b"data"}) == b"data"
        assert process_message({"type": "http.request"}) == b""
