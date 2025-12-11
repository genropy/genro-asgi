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

"""
WSX protocol utilities.

WSX (WebSocket eXtended) is a protocol that brings HTTP-like semantics
to WebSocket and NATS messaging. Messages are prefixed with WSX://
followed by JSON containing id, method, path, headers, cookies, query, data.

Format:
    WSX://{"id":"uuid","method":"POST","path":"/users","headers":{},"data":{}}

This module provides:
- WSX_PREFIX: Protocol prefix constant
- is_wsx_message(): Check if data is WSX format
- parse_wsx_message(): Parse WSX message to dict
- build_wsx_message(): Build WSX message from components
- build_wsx_response(): Build WSX response message

Request handling uses MsgRequest from request.py which calls these functions.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = [
    "WSX_PREFIX",
    "is_wsx_message",
    "parse_wsx_message",
    "build_wsx_message",
    "build_wsx_response",
]

# Protocol prefix
WSX_PREFIX = "WSX://"


def is_wsx_message(data: str | bytes) -> bool:
    """
    Check if data is a WSX protocol message.

    Args:
        data: String or bytes to check

    Returns:
        True if data starts with WSX:// prefix
    """
    if isinstance(data, bytes):
        return data.startswith(b"WSX://")
    return data.startswith(WSX_PREFIX)


def parse_wsx_message(data: str | bytes) -> dict[str, Any]:
    """
    Parse a WSX message into a dictionary.

    Args:
        data: WSX message (with or without prefix)

    Returns:
        Parsed message dict with id, method, path, headers, etc.

    Raises:
        ValueError: If message is not valid WSX format
        json.JSONDecodeError: If JSON is invalid
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8")

    if data.startswith(WSX_PREFIX):
        data = data[len(WSX_PREFIX):]

    return dict(json.loads(data))


def build_wsx_message(
    *,
    id: str,
    method: str,
    path: str = "/",
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    query: dict[str, Any] | None = None,
    data: Any = None,
    tytx: bool = False,
) -> str:
    """
    Build a WSX request message string.

    Args:
        id: Correlation ID (required)
        method: HTTP method (required)
        path: Request path (default: "/")
        headers: Headers dict
        cookies: Cookies dict
        query: Query parameters
        data: Payload data
        tytx: Whether to use TYTX serialization

    Returns:
        WSX:// prefixed message string
    """
    msg: dict[str, Any] = {
        "id": id,
        "method": method,
        "path": path,
    }

    if headers:
        msg["headers"] = headers
    if cookies:
        msg["cookies"] = cookies
    if query:
        msg["query"] = query
    if data is not None:
        msg["data"] = data
    if tytx:
        msg["tytx"] = True

    return WSX_PREFIX + json.dumps(msg)


def build_wsx_response(
    *,
    id: str,
    status: int = 200,
    headers: dict[str, str] | None = None,
    cookies: dict[str, Any] | None = None,
    data: Any = None,
) -> str:
    """
    Build a WSX response message string.

    Args:
        id: Correlation ID from request (required)
        status: HTTP status code (default: 200)
        headers: Response headers dict
        cookies: Response cookies dict
        data: Response payload

    Returns:
        WSX:// prefixed response message string
    """
    msg: dict[str, Any] = {
        "id": id,
        "status": status,
    }

    if headers:
        msg["headers"] = headers
    if cookies:
        msg["cookies"] = cookies
    if data is not None:
        msg["data"] = data

    return WSX_PREFIX + json.dumps(msg)


if __name__ == "__main__":
    # Demo
    request_msg = build_wsx_message(
        id="123",
        method="POST",
        path="/users",
        data={"name": "Mario"},
    )
    print(f"Request: {request_msg}")

    response_msg = build_wsx_response(
        id="123",
        status=200,
        data={"user_id": 42},
    )
    print(f"Response: {response_msg}")

    print(f"Is WSX: {is_wsx_message(request_msg)}")
    print(f"Parsed: {parse_wsx_message(request_msg)}")
