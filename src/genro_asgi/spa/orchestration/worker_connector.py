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

"""WorkerConnector: the wire of ONE WorkerHandler, and nothing but that wire.

One socket per handler, created and owned by it, its path handed to the child
in the spawn payload: whoever connects there IS the process of that handler.
Identity comes from the address, so the presentation carries no name — the
child says its pid and echoes the config it was given, and the answer brings
back the global store. Nothing else travels at birth: the cold memory (the
parcels) the child fetches itself from the deposit.

**The wire knows its handler, and asks it.** Everything the connector cannot
answer by itself it asks ``self.worker_handler`` — what to do with an envelope
that arrived, what the answer to the presentation is, that the wire has died. No
callbacks are handed in at construction: a second road to an object already in
hand is one road too many.

**The wire reads nothing.** It does not know what a worker event means, what a
photo is, or that a global store exists: an envelope that arrives goes WHOLE to
the handler, which pushes it into the chain of the fold, and what comes back is
written down as the answer. An envelope that leaves was composed by that same
chain, by whoever is sending it. So the protocol lives here and the meaning lives
there, and neither has to be changed for the other.

**The store goes whole, every time.** There is no delta and no version number:
the master replaces the replica entire, so nothing can arrive out of order. It
costs the whole store per change, which at this scale is nothing — the global
store is measured in kilobytes and changes something like once every three
hours. Today it travels on one envelope only, the answer to the presentation,
because that is the only process holding none of it; the update to a process
already alive replaces the replica the same way when it arrives.

**Stale socket, always unlinked.** The socket file outlives the process that
crashed, and a bind over it fails; the path is cleared before every bind. The
directory holding the sockets is private (0700): connecting there means
commanding a worker.

**One connector, one stream.** There is no rubric here and no routing by name —
the multi-member switchboard belongs to the machine that dies at the cutover.
A second connection arriving while the wire is taken is refused, loudly: the
handler never runs two processes at once, so the newcomer is the anomaly and
the resident is the real one. The address survives the relaunch: the killed
child's successor presents itself on the same socket and the wire lives again.

**Every envelope may carry the photo.** Whatever the child sends — its
presentation or a reply — can bring a ``worker_snapshot`` slot beside its own
payload, and it travels up with the rest of the envelope: whoever reads photos
reads it there. So the photo has ONE road instead of three, a live process has a
photo from birth, and the beat is left with the only question its name asks: are
you alive.

**The protocol is ASYMMETRIC, and that is what keeps it small.** Down go CALLs;
up come the presentation at birth and then REPLYs, nothing else. So a REPLY is
the only envelope this wire routes — its payload handed to the parked caller
inline, O(1), the loop staying on the wire — and whatever the child announces
travels in that payload, riding the answer to whatever was asked of it. Anything
else arriving from below is logged as an unexpected envelope: there is no lane
for it to be on.

**The end of the wire is a LOCAL fact of this handler.** EOF — the death signal
on a same-host socket — or a protocol violation closes the stream, fails every
pending CALL and tells the handler through ``on_child_lost``, which is where the
burial starts. A deliberate ``stop()`` announces nothing: that death was
ordered.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any, Callable

from ...channel.frame import MAX_FRAME_SIZE, REGISTER_METHOD, Frame, FrameStream

CALL_METHOD = "CALL"
REPLY_METHOD = "REPLY"
GLOBAL_STORE_KEY = "global_register_item_tytx"
WORKER_SNAPSHOT_KEY = "worker_snapshot"

__all__ = [
    "CALL_METHOD",
    "GLOBAL_STORE_KEY",
    "REPLY_METHOD",
    "WORKER_SNAPSHOT_KEY",
    "WorkerConnector",
]


class WorkerConnector:
    """The accept side of one worker's socket: presentation, envelopes, end of wire.

    Args:
        worker_handler: the handler this wire belongs to, and the only thing it
            asks — ``read_envelope`` for every envelope that arrives, whose
            answer is what goes back down, and ``on_child_lost`` when the wire
            dies on its own.
        socket_path: the UDS path to bind, ``<instance_dir>/<name>.sock``.
        max_size: the frame ceiling on this wire.
    """

    def __init__(
        self,
        worker_handler: Any,
        socket_path: str | Path,
        *,
        max_size: int = MAX_FRAME_SIZE,
    ) -> None:
        self.worker_handler = worker_handler
        self.socket_path = Path(socket_path)
        self.max_size = max_size
        self._logger = logging.getLogger(__name__)
        self._server: asyncio.Server | None = None
        self._stream: FrameStream | None = None
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._connected_event = asyncio.Event()
        self._closing = False

    @property
    def address(self) -> str:
        """The address the child is spawned with, in the channel's own form."""
        return f"uds:{self.socket_path}"

    @property
    def connected(self) -> bool:
        """Whether a child is on the wire and has presented itself."""
        return self._connected_event.is_set()

    async def start(self) -> None:
        """Bind the socket and start listening: the directory private, the stale path cleared."""
        self.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._serve_connection, path=str(self.socket_path)
        )
        self._logger.info("Wire listening on %s", self.socket_path)

    async def stop(self) -> None:
        """Close the wire for good and take the socket away — announced to nobody.

        Acts on the stream, the listening socket, the pending CALLs and the socket
        file. FINAL: this connector does not reopen.
        """
        self._closing = True
        if self._stream is not None:
            await self._stream.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._connected_event.clear()
        self._fail_pending(f"the wire of {self.socket_path.name} was closed")
        self.socket_path.unlink(missing_ok=True)
        self._logger.info("Wire on %s closed", self.socket_path)

    async def wait_connected(self) -> None:
        """Block until a child has presented itself; the wait after a spawn."""
        await self._connected_event.wait()

    async def call(self, path: str, data: Any = None, timeout: float | None = None) -> Any:
        """CALL the child and await its REPLY; returns the REPLY ``data`` verbatim.

        Args:
            path: the routing key of the call.
            data: the payload, JSON-serializable.
            timeout: the caller's own deadline; None waits until the REPLY lands
                or the child dies (``ConnectionError``).

        Returns:
            The child's payload, untouched — reading it is the caller's job.

        Raises:
            ConnectionError: no child is on the wire, or it died waiting.
        """
        stream = self._live_stream()
        frame = Frame(method=CALL_METHOD, path=path, data=data)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[frame.id] = future
        try:
            await stream.write(frame)
            if timeout is None:
                return await future
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(frame.id, None)

    def _live_stream(self) -> FrameStream:
        """The child's stream, or ``ConnectionError`` when there is no child."""
        if self._stream is None:
            raise ConnectionError(f"no child on the wire of {self.socket_path.name}")
        return self._stream

    async def _serve_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Per-connection task: take the wire, present the child, then relay."""
        stream = FrameStream(reader, writer, max_size=self.max_size)
        if self._stream is not None:
            self._logger.warning(
                "Connection refused on %s: the wire is already taken", self.socket_path.name
            )
            await stream.close()
            return
        self._stream = stream
        presented = False
        try:
            presented = await self._present(stream)
            if presented:
                self._connected_event.set()
                await self._receive_loop(stream)
        finally:
            self._stream = None
            self._connected_event.clear()
            await stream.close()
            self._fail_pending(f"the wire of {self.socket_path.name} is down")
            if presented and not self._closing:
                self._logger.info("Wire lost on %s", self.socket_path.name)
                await self._fire(self.worker_handler.on_child_lost)

    async def _present(self, stream: FrameStream) -> bool:
        """Read the presentation and answer it with what the chain composed; False if it is not one."""
        try:
            frame = await stream.read()
        except ValueError:
            self._logger.exception(
                "Protocol violation presenting on %s; refusing the connection",
                self.socket_path.name,
            )
            return False
        if frame is None or frame.method != REGISTER_METHOD:
            self._logger.warning(
                "Connection refused on %s: the first frame is not %s",
                self.socket_path.name,
                REGISTER_METHOD,
            )
            return False
        await stream.write(
            Frame(
                id=frame.id,
                method=REPLY_METHOD,
                path=frame.path,
                data=self.worker_handler.read_envelope(frame.data or {}),
            )
        )
        self._logger.info("Child presented itself on %s: %s", self.socket_path.name, frame.data)
        return True

    async def _receive_loop(self, stream: FrameStream) -> None:
        """Read the child's frames until the wire ends; EOF is the death signal."""
        while True:
            try:
                frame = await stream.read()
            except ValueError:
                self._logger.exception(
                    "Protocol violation from the child on %s; closing the wire",
                    self.socket_path.name,
                )
                return
            if frame is None:
                return
            self._dispatch(frame)

    def _dispatch(self, frame: Frame) -> None:
        """Route one inbound frame: a REPLY is read then resolved, and there is no other lane."""
        if frame.method == REPLY_METHOD:
            self._take_envelope(frame)
            self._resolve_reply(frame)
        else:
            self._logger.warning(
                "Unexpected envelope %s from the child on %s", frame.method, self.socket_path.name
            )

    def _take_envelope(self, frame: Frame) -> None:
        """Push the envelope into the fold before the caller is answered.

        Whatever it composed for the descent is dropped: nothing goes down in
        answer to an answer. A fold that raises is denounced and the caller is
        answered anyway.
        """
        try:
            self.worker_handler.read_envelope(frame.data or {})
        except Exception:
            self._logger.exception(
                "The fold refused the envelope %s from the child on %s",
                frame.id,
                self.socket_path.name,
            )

    def _resolve_reply(self, frame: Frame) -> None:
        """Hand the REPLY payload to the parked caller; a caller already gone drops it."""
        future = self._pending.get(frame.id)
        if future is None or future.done():
            self._logger.debug(
                "REPLY %s on %s has no parked caller", frame.id, self.socket_path.name
            )
            return
        future.set_result(frame.data or {})

    def _fail_pending(self, reason: str) -> None:
        """Fail every CALL still waiting with ``ConnectionError``; each caller pops its own."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(reason))

    async def _fire(self, callback: Callable[..., Any], *args: Any) -> None:
        """Tell the handler something, sync or async; its bug must not sever the wire."""
        try:
            result = callback(*args)
            if inspect.isawaitable(result):
                await result
        except Exception:
            self._logger.exception("Wire callback %r failed", callback)
