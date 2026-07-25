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

"""Frame protocol: length-prefixed wsx envelopes, zero external dependencies.

The wire unit of the channel (SPECIFICATION.md ◆D10: the frame protocol —
tiny, zero deps) is a ``Frame``: a wsx envelope (``WSX://`` prefix + JSON with
``id``/``method``/``path``/``data``, the same payload text the old pool
channel carried) preceded by a 4-byte big-endian length. The transport is a
plain asyncio stream — the length prefix replaces the websocket framing of
the old channel so the minimal package stays dependency-free; the envelope
format is unchanged.

``FrameStream`` is the codec over one ``(StreamReader, StreamWriter)`` pair:
``write(frame)`` sends the wire bytes, ``read()`` returns the next ``Frame``
or ``None`` when the peer is gone — on same-host sockets the channel drops
iff a process dies, so EOF is the death signal. Frames are fire-and-forget
events (no acks, no replay); the envelope ``id`` stays on the wire at zero
cost for a future request/response extension.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

__all__ = ["MAX_FRAME_SIZE", "REGISTER_METHOD", "REGISTER_PATH", "Frame", "FrameStream"]

# Frames carry wsx envelopes; the cap is generous (moves will carry pickled
# user slices at adoption time). Configurable per FrameStream instance.
MAX_FRAME_SIZE = 16 * 1024 * 1024
HEADER_SIZE = 4
WSX_PREFIX = b"WSX://"

REGISTER_METHOD = "REGISTER"
REGISTER_PATH = "/register"


class Frame:
    """One envelope on the channel (D18: slotted, high cardinality).

    An immutable record: ``id`` (generated when not given), ``method``,
    ``path`` and ``data``. ``encode()`` produces the wire bytes.
    """

    __slots__ = ("_id", "_method", "_path", "_data")

    def __init__(
        self,
        *,
        id: str | None = None,
        method: str = "POST",
        path: str = "/",
        data: Any = None,
    ) -> None:
        self._id = id or str(uuid.uuid4())
        self._method = method
        self._path = path
        self._data = data

    @property
    def id(self) -> str:
        """Correlation id (kept on the wire for a future request/response)."""
        return self._id

    @property
    def method(self) -> str:
        """Envelope method (``REGISTER`` presents a child, ``POST`` events)."""
        return self._method

    @property
    def path(self) -> str:
        """Envelope path, the HTTP-like routing key for the consumer."""
        return self._path

    @property
    def data(self) -> Any:
        """JSON-serializable payload (``None`` for no payload)."""
        return self._data

    def encode(self) -> bytes:
        """The wire bytes: 4-byte big-endian length + ``WSX://`` + JSON."""
        envelope: dict[str, Any] = {"id": self.id, "method": self.method, "path": self.path}
        if self.data is not None:
            envelope["data"] = self.data
        payload = WSX_PREFIX + json.dumps(envelope).encode("utf-8")
        return len(payload).to_bytes(HEADER_SIZE, "big") + payload

    def __repr__(self) -> str:
        return f"<Frame {self.method} {self.path} id={self.id}>"


class FrameStream:
    """Frame codec over one asyncio stream pair (either end of the channel).

    ``read()`` returns ``None`` when the peer is gone (EOF or reset) — the
    death signal, not an error. An oversized or non-wsx frame is a protocol
    violation and raises ``ValueError``.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        max_size: int = MAX_FRAME_SIZE,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.max_size = max_size

    async def read(self) -> Frame | None:
        """The next frame, or ``None`` when the channel ended."""
        try:
            header = await self.reader.readexactly(HEADER_SIZE)
            length = int.from_bytes(header, "big")
            if length > self.max_size:
                raise ValueError(f"frame of {length} bytes exceeds max_size={self.max_size}")
            payload = await self.reader.readexactly(length)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return None
        if not payload.startswith(WSX_PREFIX):
            raise ValueError("frame payload is not a wsx envelope")
        envelope = json.loads(payload[len(WSX_PREFIX) :])
        try:
            return Frame(
                id=envelope["id"],
                method=envelope["method"],
                path=envelope["path"],
                data=envelope.get("data"),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"invalid wsx envelope: {exc}") from exc

    async def write(self, frame: Frame) -> None:
        """Send one frame; an oversized payload raises ``ValueError``."""
        wire = frame.encode()
        if len(wire) - HEADER_SIZE > self.max_size:
            raise ValueError(
                f"frame of {len(wire) - HEADER_SIZE} bytes exceeds max_size={self.max_size}"
            )
        self.writer.write(wire)
        await self.writer.drain()

    async def close(self) -> None:
        """Close the writing side; a peer already gone is not an error."""
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass
