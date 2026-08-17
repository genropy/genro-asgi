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

"""WorkerConnector tests: one socket, one child, the handshake and the end.

Everything runs on a real UDS: the wire is the one place that has to behave
like the kernel behaves, so a fake transport would assert nothing. The child is
a ``ChildPeer`` over the package's own ``FrameStream`` — it presents itself,
answers CALLs reusing their id, and dies by closing the socket, which is
exactly what a worker process does.

The sockets live under a short ``mkdtemp`` root and not under ``tmp_path``:
the system caps a UDS path at about a hundred characters, which is the very
reason worker names are short — pytest's own directory is already past it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.channel.frame import REGISTER_METHOD, REGISTER_PATH, Frame, FrameStream
from genro_asgi.spa.orchestration import WorkerConnector
from genro_asgi.spa.orchestration.worker_connector import (
    CALL_METHOD,
    GLOBAL_STORE_KEY,
    REPLY_METHOD,
)


class ChildPeer:
    """The worker process, seen from the other end of the socket."""

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self.received: list[Frame] = []
        self.handshake_reply: Frame | None = None
        self.reply_result: Any = None
        self.answer_calls = True
        self.stream: FrameStream | None = None
        self._task: asyncio.Task[None] | None = None

    async def present(self, config: Any = None) -> Frame:
        """Connect, send the presentation, return the REPLY that came back."""
        reader, writer = await asyncio.open_unix_connection(self.socket_path)
        self.stream = FrameStream(reader, writer)
        await self.stream.write(
            Frame(
                method=REGISTER_METHOD,
                path=REGISTER_PATH,
                data={"pid": os.getpid(), "config": config},
            )
        )
        self.handshake_reply = await self.stream.read()
        self._task = asyncio.create_task(self._receive_loop())
        return self.handshake_reply

    async def connect_without_presenting(self) -> None:
        reader, writer = await asyncio.open_unix_connection(self.socket_path)
        self.stream = FrameStream(reader, writer)

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self.stream.close()

    async def send(self, method: str, path: str, data: Any = None) -> None:
        await self.stream.write(Frame(method=method, path=path, data=data))

    async def wait_frames(self, count: int, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while len(self.received) < count:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"the child got {len(self.received)}/{count} frames")
            await asyncio.sleep(0.01)

    async def _receive_loop(self) -> None:
        while True:
            frame = await self.stream.read()
            if frame is None:
                return
            self.received.append(frame)
            if frame.method == CALL_METHOD and self.answer_calls:
                await self.stream.write(
                    Frame(
                        id=frame.id,
                        method=REPLY_METHOD,
                        path=frame.path,
                        data={"result": self.reply_result, "events": []},
                    )
                )


class HandlerStub:
    """The WorkerHandler seen by its wire: what it hands over, what it is told."""

    def __init__(self, name: str = "standard_0001") -> None:
        self.name = name
        self.global_register_item_tytx = "::T::the whole store"
        self.losses = 0

    def on_child_lost(self) -> None:
        self.losses += 1


@pytest.fixture
def handler():
    return HandlerStub()


@pytest.fixture
def socket_root():
    root = tempfile.mkdtemp(prefix="gnrwire_")
    yield Path(root)
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
async def connector(socket_root, handler):
    wire = WorkerConnector(handler, socket_root / "i" / f"{handler.name}.sock")
    await wire.start()
    yield wire
    await wire.stop()


async def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the wire never reached the awaited state")
        await asyncio.sleep(0.01)


async def test_the_socket_is_bound_in_a_private_directory(connector):
    assert connector.socket_path.exists()
    assert os.stat(connector.socket_path.parent).st_mode & 0o777 == 0o700
    assert connector.address == f"uds:{connector.socket_path}"
    assert connector.connected is False


async def test_a_stale_socket_is_unlinked_before_the_bind(socket_root, handler):
    socket_path = socket_root / "i" / f"{handler.name}.sock"
    socket_path.parent.mkdir(mode=0o700, parents=True)
    socket_path.write_bytes(b"what the crash left behind")

    wire = WorkerConnector(handler, socket_path)
    await wire.start()
    try:
        child = ChildPeer(str(socket_path))
        await child.present()
        await child.close()
    finally:
        await wire.stop()


async def test_the_presentation_is_answered_with_the_whole_global_store(connector, handler):
    child = ChildPeer(str(connector.socket_path))
    reply = await child.present(config={"pool_size": 4})

    assert reply.method == REPLY_METHOD
    assert reply.data == {GLOBAL_STORE_KEY: handler.global_register_item_tytx}
    await connector.wait_connected()
    assert connector.connected is True

    await child.close()


async def test_a_call_travels_and_its_reply_comes_back(connector):
    child = ChildPeer(str(connector.socket_path))
    await child.present()
    child.reply_result = {"alive": True}

    payload = await connector.call("/probe", {"kwargs": {}})

    assert payload == {"result": {"alive": True}, "events": []}
    assert child.received[0].method == CALL_METHOD
    assert child.received[0].path == "/probe"
    assert child.received[0].data == {"kwargs": {}}

    await child.close()


async def test_an_envelope_that_is_not_a_reply_has_no_lane_and_is_denounced(
    connector, handler, caplog
):
    child = ChildPeer(str(connector.socket_path))
    await child.present()

    with caplog.at_level("WARNING"):
        await child.send(CALL_METHOD, "/lock_taken", {"user": "mario"})
        await wait_for(lambda: "Unexpected envelope" in caplog.text)

    assert f"Unexpected envelope {CALL_METHOD}" in caplog.text
    assert handler.losses == 0

    await child.close()


async def test_the_death_of_the_child_is_a_local_event(connector, handler):
    child = ChildPeer(str(connector.socket_path))
    await child.present()
    await connector.wait_connected()

    await child.close()
    await wait_for(lambda: handler.losses == 1)

    assert connector.connected is False


async def test_a_call_in_flight_dies_with_the_child(connector):
    child = ChildPeer(str(connector.socket_path))
    await child.present()
    await connector.wait_connected()
    child.answer_calls = False

    async def kill_the_child() -> None:
        await asyncio.sleep(0.05)
        await child.close()

    asyncio.create_task(kill_the_child())
    with pytest.raises(ConnectionError):
        await connector.call("/freeze_everybody")


async def test_a_deliberate_stop_announces_no_death(socket_root, handler):
    wire = WorkerConnector(handler, socket_root / "i" / f"{handler.name}.sock")
    await wire.start()
    child = ChildPeer(str(wire.socket_path))
    await child.present()
    await wire.wait_connected()

    await wire.stop()

    assert handler.losses == 0
    assert wire.connected is False
    assert not wire.socket_path.exists()


async def test_the_successor_finds_the_same_socket(connector, handler):
    first = ChildPeer(str(connector.socket_path))
    await first.present()
    await connector.wait_connected()
    await first.close()
    await wait_for(lambda: connector.connected is False)

    handler.global_register_item_tytx = "::T::the store as it is now"
    successor = ChildPeer(str(connector.socket_path))
    reply = await successor.present()
    await connector.wait_connected()

    assert reply.data == {GLOBAL_STORE_KEY: "::T::the store as it is now"}

    await successor.close()


async def test_a_second_child_on_a_taken_wire_is_refused(connector):
    resident = ChildPeer(str(connector.socket_path))
    await resident.present()
    await connector.wait_connected()

    intruder = ChildPeer(str(connector.socket_path))
    await intruder.connect_without_presenting()
    assert await intruder.stream.read() is None

    resident.reply_result = "still here"
    assert await connector.call("/probe") == {"result": "still here", "events": []}

    await resident.close()


async def test_a_child_that_does_not_present_itself_is_refused(connector):
    intruder = ChildPeer(str(connector.socket_path))
    await intruder.connect_without_presenting()
    await intruder.stream.write(Frame(method=CALL_METHOD, path="/whatever"))

    assert await intruder.stream.read() is None
    assert connector.connected is False


async def test_calling_a_wire_with_no_child_is_an_error(connector):
    with pytest.raises(ConnectionError):
        await connector.call("/probe")
