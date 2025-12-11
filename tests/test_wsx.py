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

"""Tests for the WSX protocol module and MsgRequest."""

import json

import pytest

from genro_asgi.wsx import (
    WSX_PREFIX,
    build_wsx_message,
    build_wsx_response,
    is_wsx_message,
    parse_wsx_message,
)
from genro_asgi.request import (
    BaseRequest,
    MsgRequest,
    RequestRegistry,
    REQUEST_FACTORIES,
)


class TestWsxProtocol:
    """Tests for WSX:// message parsing and building."""

    def test_wsx_prefix(self) -> None:
        assert WSX_PREFIX == "WSX://"

    def test_is_wsx_message_string(self) -> None:
        assert is_wsx_message('WSX://{"id":"123"}')
        assert not is_wsx_message('{"id":"123"}')
        assert not is_wsx_message("TYTX://data")

    def test_is_wsx_message_bytes(self) -> None:
        assert is_wsx_message(b'WSX://{"id":"123"}')
        assert not is_wsx_message(b'{"id":"123"}')

    def test_parse_wsx_message_with_prefix(self) -> None:
        msg = 'WSX://{"id":"abc","method":"POST"}'
        parsed = parse_wsx_message(msg)
        assert parsed["id"] == "abc"
        assert parsed["method"] == "POST"

    def test_parse_wsx_message_without_prefix(self) -> None:
        msg = '{"id":"abc","method":"GET"}'
        parsed = parse_wsx_message(msg)
        assert parsed["id"] == "abc"
        assert parsed["method"] == "GET"

    def test_parse_wsx_message_bytes(self) -> None:
        msg = b'WSX://{"id":"xyz","method":"DELETE"}'
        parsed = parse_wsx_message(msg)
        assert parsed["id"] == "xyz"
        assert parsed["method"] == "DELETE"

    def test_build_wsx_message_minimal(self) -> None:
        msg = build_wsx_message(id="123", method="GET", path="/users")
        assert msg.startswith(WSX_PREFIX)
        parsed = json.loads(msg[len(WSX_PREFIX):])
        assert parsed["id"] == "123"
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/users"

    def test_build_wsx_message_full(self) -> None:
        msg = build_wsx_message(
            id="456",
            method="POST",
            path="/users",
            headers={"content-type": "application/json"},
            cookies={"session": "abc"},
            query={"page": 1},
            data={"name": "Mario"},
        )
        parsed = json.loads(msg[len(WSX_PREFIX):])
        assert parsed["headers"] == {"content-type": "application/json"}
        assert parsed["cookies"] == {"session": "abc"}
        assert parsed["query"] == {"page": 1}
        assert parsed["data"] == {"name": "Mario"}

    def test_build_wsx_message_with_tytx(self) -> None:
        msg = build_wsx_message(id="789", method="GET", tytx=True)
        parsed = json.loads(msg[len(WSX_PREFIX):])
        assert parsed["tytx"] is True

    def test_build_wsx_response(self) -> None:
        msg = build_wsx_response(id="resp1", status=201, data={"created": True})
        assert msg.startswith(WSX_PREFIX)
        parsed = json.loads(msg[len(WSX_PREFIX):])
        assert parsed["id"] == "resp1"
        assert parsed["status"] == 201
        assert parsed["data"] == {"created": True}

    def test_build_wsx_response_with_headers(self) -> None:
        msg = build_wsx_response(
            id="resp2",
            headers={"x-custom": "value"},
            cookies={"session": {"value": "abc"}},
        )
        parsed = json.loads(msg[len(WSX_PREFIX):])
        assert parsed["headers"] == {"x-custom": "value"}
        assert parsed["cookies"] == {"session": {"value": "abc"}}


class TestMsgRequest:
    """Tests for MsgRequest (message-based request)."""

    def test_parse_minimal_request(self) -> None:
        msg = 'WSX://{"id":"req1","method":"GET"}'
        request = MsgRequest(msg)
        # external_id is the client's id from the message
        assert request.external_id == "req1"
        # internal id is server-generated UUID
        assert request.id != "req1"
        assert len(request.id) == 36  # UUID format
        assert request.method == "GET"
        assert request.path == "/"
        assert request.headers == {}
        assert request.cookies == {}
        assert request.query == {}
        assert request.data is None
        assert request.transport == "websocket"

    def test_parse_full_request(self) -> None:
        msg = 'WSX://{"id":"req2","method":"POST","path":"/api/users","headers":{"authorization":"Bearer xyz"},"cookies":{"lang":"it"},"query":{"limit":"10"},"data":{"name":"Luigi"}}'
        request = MsgRequest(msg)
        assert request.external_id == "req2"
        assert request.method == "POST"
        assert request.path == "/api/users"
        assert request.headers == {"authorization": "Bearer xyz"}
        assert request.cookies == {"lang": "it"}
        assert request.query == {"limit": "10"}
        assert request.data == {"name": "Luigi"}

    def test_missing_id_raises(self) -> None:
        msg = 'WSX://{"method":"GET"}'
        with pytest.raises(ValueError, match="missing required 'id' field"):
            MsgRequest(msg)

    def test_missing_method_raises(self) -> None:
        msg = 'WSX://{"id":"123"}'
        with pytest.raises(ValueError, match="missing required 'method' field"):
            MsgRequest(msg)

    def test_method_uppercase(self) -> None:
        msg = 'WSX://{"id":"123","method":"post"}'
        request = MsgRequest(msg)
        assert request.method == "POST"

    def test_transport_type_configurable(self) -> None:
        msg = 'WSX://{"id":"test","method":"GET"}'
        request = MsgRequest(msg, transport_type="nats")
        assert request.transport == "nats"

    def test_tytx_mode_from_message(self) -> None:
        msg = 'WSX://{"id":"tytx1","method":"GET","tytx":true}'
        request = MsgRequest(msg)
        assert request.tytx_mode is True

    def test_tytx_mode_from_header(self) -> None:
        msg = 'WSX://{"id":"tytx2","method":"GET","headers":{"content-type":"application/json+tytx"}}'
        request = MsgRequest(msg)
        assert request.tytx_mode is True

    def test_base_request_properties(self) -> None:
        msg = 'WSX://{"id":"base-test","method":"GET"}'
        request = MsgRequest(msg)
        # From BaseRequest
        assert request.app_name is None
        assert request.created_at > 0
        assert request.age >= 0
        # Set app_name
        request.app_name = "shop"
        assert request.app_name == "shop"

    def test_is_base_request(self) -> None:
        msg = 'WSX://{"id":"test","method":"GET"}'
        request = MsgRequest(msg)
        assert isinstance(request, BaseRequest)


class TestMsgRequestFromScope:
    """Tests for MsgRequest.from_scope factory."""

    @pytest.mark.asyncio
    async def test_from_scope(self) -> None:
        scope = {"type": "websocket", "client": ("127.0.0.1", 12345)}
        message = 'WSX://{"id":"ws-test","method":"GET","path":"/chat"}'

        async def receive():
            return {}

        async def send(msg):
            pass

        request = await MsgRequest.from_scope(scope, receive, send, message=message)
        assert request.external_id == "ws-test"
        assert request.method == "GET"
        assert request.path == "/chat"
        assert request.transport == "websocket"

    @pytest.mark.asyncio
    async def test_from_scope_missing_message(self) -> None:
        scope = {"type": "websocket"}

        async def receive():
            return {}

        with pytest.raises(ValueError, match="requires 'message' kwarg"):
            await MsgRequest.from_scope(scope, receive)


class TestRequestRegistryWithMsg:
    """Tests for RequestRegistry with MsgRequest."""

    def test_default_factories(self) -> None:
        assert "websocket" in REQUEST_FACTORIES
        assert REQUEST_FACTORIES["websocket"] is MsgRequest

    @pytest.mark.asyncio
    async def test_create_websocket_request(self) -> None:
        registry = RequestRegistry()
        scope = {"type": "websocket", "client": ("127.0.0.1", 12345)}
        message = 'WSX://{"id":"ws-reg-test","method":"POST","path":"/api"}'

        async def receive():
            return {}

        async def send(msg):
            pass

        request = await registry.create(scope, receive, send, message=message)

        assert isinstance(request, MsgRequest)
        assert request.external_id == "ws-reg-test"
        assert request.method == "POST"
        assert request.path == "/api"
        assert len(registry) == 1
        assert request.id in registry

    @pytest.mark.asyncio
    async def test_unregister(self) -> None:
        registry = RequestRegistry()
        scope = {"type": "websocket"}
        message = 'WSX://{"id":"unreg-test","method":"GET"}'

        async def receive():
            return {}

        request = await registry.create(scope, receive, message=message)
        request_id = request.id
        assert len(registry) == 1

        removed = registry.unregister(request_id)
        assert removed is request
        assert len(registry) == 0

    @pytest.mark.asyncio
    async def test_count_by_app(self) -> None:
        registry = RequestRegistry()

        async def receive():
            return {}

        # Create requests with different app_names
        for i, app_name in enumerate(["shop", "shop", "accounting"]):
            scope = {"type": "websocket"}
            message = f'WSX://{{"id":"app-{i}","method":"GET"}}'
            request = await registry.create(scope, receive, message=message)
            request.app_name = app_name

        assert registry.count_by_app("shop") == 2
        assert registry.count_by_app("accounting") == 1
        assert registry.count_by_app("unknown") == 0
