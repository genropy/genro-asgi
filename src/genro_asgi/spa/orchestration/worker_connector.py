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
answer by itself it asks ``self.worker_handler`` — the payload of the
presentation reply, where an inbound EVENT goes, that the wire has died. No
callbacks are handed in at construction: a second road to an object already in
hand is one road too many.

**The store goes whole, every time.** There is no delta and no version number:
the master replaces the replica entire, at the presentation like at every later
change, so the newborn is not a special case and nothing can arrive out of
order. It costs the whole store per change, which at this scale is nothing —
the global store is measured in kilobytes and changes something like once every
three hours.

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

**Three envelopes, the ratified division of labour.** A REPLY hands its payload
to the parked caller inline — O(1), it stays in the receive loop. An EVENT runs
a consumer, so it goes on its own task and the loop returns to the wire; per-
event ordering is therefore not preserved. A CALL arriving from the child has
no consumer today and is logged as an unexpected envelope.

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
EVENT_METHOD = "EVENT"
GLOBAL_STORE_KEY = "global_register_item_tytx"

__all__ = [
    "CALL_METHOD",
    "EVENT_METHOD",
    "GLOBAL_STORE_KEY",
    "REPLY_METHOD",
    "WorkerConnector",
]


class WorkerConnector:
    """The accept side of one worker's socket: presentation, envelopes, end of wire.

    Args:
        worker_handler: the handler this wire belongs to, and the only thing it
            asks — ``global_register_item_tytx`` for the presentation reply,
            ``on_child_message`` for an inbound EVENT, ``on_child_lost`` when
            the wire dies on its own.
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
        self._event_tasks: set[asyncio.Task[None]] = set()
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
        """Bind the socket and start listening for the child of this handler.

        Creates the socket directory private (0700), clears whatever the
        previous life left at the path, and binds.
        """
        self.socket_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._serve_connection, path=str(self.socket_path)
        )
        self._logger.info("Wire listening on %s", self.socket_path)

    async def stop(self) -> None:
        """Close the wire and take the socket away — an ordered end, announced to nobody.

        Closes the child's stream and the listening socket, fails the pending
        CALLs and unlinks the socket file.
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

    async def send_event(self, path: str, data: Any = None) -> str:
        """Send one EVENT to the child, fire-and-forget.

        Args:
            path: the routing key of the event.
            data: the payload, JSON-serializable.

        Returns:
            The frame id.

        Raises:
            ConnectionError: no child is on the wire.
        """
        frame = Frame(method=EVENT_METHOD, path=path, data=data)
        await self._live_stream().write(frame)
        return frame.id

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
        """Read the presentation and answer it with the whole global store; False if it is not one."""
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
                data={GLOBAL_STORE_KEY: self.worker_handler.global_register_item_tytx},
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
        """Route one inbound frame: resolve a REPLY inline, serve an EVENT on a task."""
        if frame.method == REPLY_METHOD:
            self._resolve_reply(frame)
        elif frame.method == EVENT_METHOD:
            task = asyncio.create_task(self._fire(self.worker_handler.on_child_message, frame))
            self._event_tasks.add(task)
            task.add_done_callback(self._event_tasks.discard)
        else:
            self._logger.warning(
                "Unexpected envelope %s from the child on %s", frame.method, self.socket_path.name
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
