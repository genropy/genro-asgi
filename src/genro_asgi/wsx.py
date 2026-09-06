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
"""

from __future__ import annotations

import json
from typing import Any

from genro_tytx import from_tytx, to_tytx

__all__ = ["WsxEnvelope"]

WSX_PREFIX = "WSX://"


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
