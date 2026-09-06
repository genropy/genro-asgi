# Copyright 2025 Softwell S.r.l.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The WSX envelope: one message on a websocket, in either direction.

A WSX message is the text ``WSX://`` followed by JSON. ``WsxEnvelope`` is that
message as an object, and it is built two ways — from the text a socket
delivered, or from the fields somebody is about to send::

    envelope = WsxEnvelope(text)                                # read one
    reply = WsxEnvelope(id=envelope.id, status=200, data=…)     # write one
    await socket.send_text(reply.encode())

The prefix is what tells a WSX message from any other text on the socket, and
the fields are the ones the channel's own ``Frame`` already carries, so a
message copies into a CALL one field at a time.

**A request carries ``method`` and ``path``; an answer carries ``status``.**
Both carry ``data`` and, when they belong to a page, ``page_id``. ``id`` is
what correlates an answer with the message it answers, and its ABSENCE is
meaningful twice: a message with no id is an event nobody answers, and a
message the server sends by itself never has one. ``reply_path`` is where a
page asks to be called back when the work is done. A field nobody set does not
reach the wire — a null there would read as a value.

**``data`` is a value here and a string on the wire.** What travels inside the
JSON body is the TYTX string ``to_tytx(value, "json")`` produces, and reading
an envelope hydrates it back: Decimals, dates and Bags survive, in both
languages. Whoever writes a client reads ``data`` as a string to hydrate, never
as a nested object to walk.

**A text that is not a WSX message raises.** So does a body that is not JSON,
and one that is not an object. All three are the same thing to a reader — this
text is not a message of ours — and the read loop logs and moves on.

``WsxConnection`` is one live connection speaking that protocol: ``serve()`` is
its whole life. It gates the handshake, accepts, reads messages until the
client leaves, and waits for what is still in flight. Every message with an
``id`` becomes a synthetic HTTP request with the method ``WSK``, handed to the
application its ``path`` names through the server's own demux — so an
application learns no new method and a websocket message travels the road a
request travels. A message with no ``id`` is an event: served, answered by
nothing.

**The gate answers in one shape: accept, then close with a readable code.** A
server that is not running closes 1013; a handshake on a path no application
serves, or one missing the cookie its home application demands, closes 1008.
The single exception is a hostile Origin, refused BEFORE the accept — there is
nobody to tell, because nobody was admitted.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from genro_tytx import from_tytx, to_tytx

from .application import BaseApplication
from .exceptions import HTTPException, WebSocketDisconnect
from .lifespan import RUNNING
from .middleware.session import SessionMiddleware
from .types import Receive, Scope, Send
from .websocket import WebSocket

__all__ = ["WsxConnection", "WsxEnvelope"]

WSX_PREFIX = "WSX://"

#: The reserved first segment: what the server answers itself, never an
#: application. ``/_wsx/ping`` is the control ping, served inline.
WSX_ROOT = "_wsx"
PING_PATH = f"/{WSX_ROOT}/ping"

#: How long the closing connection waits for the messages still in flight.
DRAIN_TIMEOUT_SECONDS = 5.0


class WsxEnvelope:
    """One WSX message: read from its text, or built to be sent."""

    def __init__(
        self,
        text: str | None = None,
        *,
        id: str | None = None,
        method: str | None = None,
        path: str | None = None,
        data: Any = None,
        page_id: str | None = None,
        reply_path: str | None = None,
        status: int | None = None,
    ) -> None:
        """Args:
        text: a WSX message to read; the keywords are ignored when it is given.
        id: what correlates an answer with its message; ``None`` for an event.
        method: the request's method — ``WSK`` for a page's rpc.
        path: the request's path, which names the application and the route.
        data: the payload, as a Python value.
        page_id: the page the message belongs to, when it belongs to one.
        reply_path: where the page asks to be called back.
        status: the answer's status; ``None`` on a request.

        Raises:
            ValueError: ``text`` is not a WSX message, its body is not JSON, or
                that body is not an object.
        """
        if text is not None:
            fields = self.read_text(text)
            id = fields.get("id")
            method = fields.get("method")
            path = fields.get("path")
            page_id = fields.get("page_id")
            reply_path = fields.get("reply_path")
            status = fields.get("status")
            data = from_tytx(fields["data"], "json") if fields.get("data") is not None else None
        self.id = id
        self.method = method
        self.path = path
        self.data = data
        self.page_id = page_id
        self.reply_path = reply_path
        self.status = status

    def read_text(self, text: str) -> dict[str, Any]:
        """The JSON body of one WSX message.

        Args:
            text: the message as the socket delivered it.

        Returns:
            The body, its ``data`` still the TYTX string.

        Raises:
            ValueError: no ``WSX://`` prefix, a body that is not JSON, or a
                body that is not an object.
        """
        if not text.startswith(WSX_PREFIX):
            raise ValueError("this text is not a WSX:// message")
        try:
            body = json.loads(text[len(WSX_PREFIX) :])
        except ValueError as exc:
            raise ValueError(f"this WSX message carries no JSON: {exc}") from None
        if not isinstance(body, dict):
            raise ValueError(f"a WSX body must be an object, got {type(body).__name__}")
        return body

    def encode(self) -> str:
        """The wire text: the prefix and the JSON body.

        Returns:
            ``WSX://`` followed by the JSON of the fields that were set —
            ``data`` as its TYTX string, and nothing for a field left out.
        """
        body: dict[str, Any] = {}
        for name in ("id", "method", "path", "page_id", "reply_path", "status"):
            value = getattr(self, name)
            if value is not None:
                body[name] = value
        if self.data is not None:
            body["data"] = to_tytx(self.data, "json")
        return WSX_PREFIX + json.dumps(body)

    def __repr__(self) -> str:
        told = f"{self.method} {self.path}" if self.status is None else f"status {self.status}"
        return f"<WsxEnvelope {told} id={self.id}>"


class WsxConnection:
    """One websocket connection speaking WSX, from the handshake to the end."""

    def __init__(self, server: Any, scope: Scope, receive: Receive, send: Send) -> None:
        """Args:
        server: the server this connection belongs to — it owns the demux, the
            identity, the request registry and the websocket registry.
        scope: the ASGI websocket scope of the handshake.
        receive: the ASGI receive callable.
        send: the ASGI send callable.
        """
        self.server = server
        self.socket = WebSocket(scope, receive, send)
        self.avatar: Any = None
        self.session: Any = None
        self.home: BaseApplication | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._slots = asyncio.Semaphore(server.websocket_max_concurrent)
        self._logger = logging.getLogger(__name__)

    async def serve(self) -> None:
        """Live this connection: gate, accept, read, drain.

        Returns when the socket is over — the client left, or the gate turned
        it away. Registers the socket for the span of the connection and takes
        it out in the ``finally``, whatever happened.
        """
        if not await self._open_gate():
            return
        self.server.websockets.register(self.socket)
        try:
            await self._read_messages()
        finally:
            await self._drain()
            self.server.websockets.unregister(self.socket)

    async def _open_gate(self) -> bool:
        """Judge the handshake and accept it; ``False`` when it was turned away.

        Sets ``avatar``, ``session`` and ``home``.
        """
        refusal = self._origin_refusal()
        if refusal is not None:
            await self.socket.refuse(1008, refusal)
            return False
        await self.socket.accept()
        if self.server.state != RUNNING:
            await self.socket.close(1013, "server restarting")
            return False
        app, _ = self.server.demux(self.socket.scope)
        if not isinstance(app, BaseApplication):
            await self.socket.close(1008, "no application at this path")
            return False
        self.home = app
        cookie = app.handshake_cookie
        if cookie is not None and cookie not in self.socket.cookies:
            await self.socket.close(1008, f"connection cookie required: {cookie}")
            return False
        try:
            self.avatar = self.server.authenticate(self.socket.scope)
        except HTTPException as refused:
            await self.socket.close(1008, refused.detail or "unauthorized")
            return False
        self.session = self._read_session()
        return True

    def _origin_refusal(self) -> str | None:
        """Why this Origin is not admitted, or ``None`` when it is.

        No ``Origin`` at all passes: it is not a browser, and the gate exists
        against a page on another site, not against a client of its own. With a
        declared list the header must be in it (``*`` admits everyone);
        without one, the Origin must be the host the handshake came to.
        """
        origin = self.socket.headers.get("origin")
        if not origin:
            return None
        allowed = self.server.websocket_origins
        if allowed:
            if "*" in allowed or origin in allowed:
                return None
            return f"origin not allowed: {origin}"
        host = self.socket.headers.get("host") or ""
        if str(origin).partition("://")[2] == host:
            return None
        return f"origin not allowed: {origin}"

    def _read_session(self) -> Any:
        """The session of the handshake, read from the layer that owns it.

        The middleware chain never sees a websocket scope, so the session is
        asked of ``SessionMiddleware`` itself — a pure reading, which creates
        nothing. ``None`` when that middleware is off or no cookie arrived.
        """
        layer = self.server.get_middleware(SessionMiddleware)
        return layer.get_session(self.socket.scope) if layer is not None else None

    async def _read_messages(self) -> None:
        """Read until the client leaves, serving each message on a task of its own.

        What is not a WSX message is logged and dropped — a text of another
        shape, and a binary frame, which this protocol has no use for: the
        socket may carry other traffic, and one message nobody understands
        never ends a connection. The control ping is answered inline, outside
        the ceiling, so a connection whose slots are all busy still answers
        "are you there".
        """
        try:
            while True:
                message = await self.socket.read_message()
                text = message.get("text")
                if text is None:
                    self._logger.warning("Websocket: a binary frame carries no WSX message")
                    continue
                try:
                    envelope = WsxEnvelope(text)
                except ValueError as broken:
                    self._logger.warning("Websocket: message dropped, %s", broken)
                    continue
                if envelope.path == PING_PATH:
                    await self._answer(envelope, 200, "pong")
                    continue
                task = asyncio.create_task(self._serve_message(envelope))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
        except WebSocketDisconnect:
            return

    async def _drain(self) -> None:
        """Wait for the messages still in flight, then cut what is left."""
        if not self._tasks:
            return
        done, pending = await asyncio.wait(set(self._tasks), timeout=DRAIN_TIMEOUT_SECONDS)
        for task in pending:
            task.cancel()

    async def _serve_message(self, envelope: WsxEnvelope) -> None:
        """Serve one message as a request, and answer it when it asked to be.

        A message with an ``id`` is registered in the server's request registry
        — the shutdown waits for it, and it shows in the picture — and answered
        with its status. A message without one is an event: served the same
        way, answered by nothing, its failure logged.
        """
        item = self.server.requests.register(self._request_scope(envelope)) if envelope.id else None
        try:
            async with self._slots:
                status, data = await self._call_application(envelope)
        finally:
            if item is not None:
                item.run_cleanups()
                self.server.requests.unregister(item)
        if envelope.id is not None:
            await self._answer(envelope, status, data)

    async def _call_application(self, envelope: WsxEnvelope) -> tuple[int, Any]:
        """Hand one message to the application its path names.

        Returns:
            The status and the data of the answer. An ``HTTPException`` becomes
            its own status, anything else a 500 — the socket survives either.
        """
        scope = self._request_scope(envelope)
        collected: list[Any] = []
        try:
            app, target = self.server.demux(scope)
            await app(target, self._request_body(envelope), self._collector(collected))
        except HTTPException as refused:
            return refused.status, refused.detail
        except Exception as failure:
            self._logger.exception("Websocket: message %s failed", envelope.path)
            return 500, f"{type(failure).__name__}: {failure}"
        return self._answer_of(collected)

    def _request_scope(self, envelope: WsxEnvelope) -> Scope:
        """The synthetic HTTP scope of one message.

        The method is ``WSK``, the convention an application accepts by serving
        rpc over a websocket; the path is the message's own. The handshake's
        headers, identity and session travel with EVERY message: they were
        judged once, and they hold for the connection. ``genro.page_id`` and
        ``genro.reply_path`` are there only when the message carried them.
        """
        scope: Scope = {
            **self.socket.scope,
            "type": "http",
            "method": "WSK",
            "path": envelope.path or "/",
            "headers": list(self.socket.scope.get("headers") or [])
            + [(b"content-type", b"application/json"), (b"x-tytx-transport", b"json")],
            "auth": self.avatar,
            "session": self.session,
        }
        if envelope.page_id is not None:
            scope["genro.page_id"] = envelope.page_id
        if envelope.reply_path is not None:
            scope["genro.reply_path"] = envelope.reply_path
        return scope

    def _request_body(self, envelope: WsxEnvelope) -> Receive:
        """A ``receive`` that hands the message's data over as the request body."""
        encoded = to_tytx(envelope.data, "json") if envelope.data is not None else b""
        body = encoded if isinstance(encoded, bytes) else encoded.encode("utf-8")

        async def receive() -> Any:
            return {"type": "http.request", "body": body, "more_body": False}

        return receive

    def _collector(self, collected: list[Any]) -> Send:
        """A ``send`` that keeps the answer instead of writing it to a socket."""

        async def send(message: Any) -> None:
            if message["type"] == "http.response.body" and message.get("more_body"):
                raise RuntimeError("a streaming answer cannot travel on a websocket message")
            collected.append(message)

        return send

    def _answer_of(self, collected: list[Any]) -> tuple[int, Any]:
        """The status and the data an application's answer carried.

        The body is read by its content-type, the way a request reads one: a
        TYTX or JSON body comes back hydrated, anything else as the text or the
        bytes it is.
        """
        status = 200
        content_type = ""
        for message in collected:
            if message["type"] == "http.response.start":
                status = message["status"]
                content_type = dict(message.get("headers") or {}).get(b"content-type", b"").decode()
        body = b"".join(m.get("body", b"") for m in collected if m["type"] == "http.response.body")
        if not body:
            return status, None
        if "json" in content_type or "xml" in content_type:
            return status, from_tytx(body.decode("utf-8"), "json" if "json" in content_type else "xml")
        try:
            return status, body.decode("utf-8")
        except UnicodeDecodeError:
            return status, body

    async def _answer(self, envelope: WsxEnvelope, status: int, data: Any) -> None:
        """Write the answer to one message back onto the socket."""
        if not self.socket.connected:
            return
        await self.socket.send_text(
            WsxEnvelope(id=envelope.id, status=status, data=data).encode()
        )
