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
