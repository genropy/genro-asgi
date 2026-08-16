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

"""The foundations end to end: a worker is born, works, dies wild, and leaves its traces.

The three foundations are exercised together, in one story, on the real things:
a real child process (``child_stub``), a real Unix socket, a real deposit on
disk. Nothing here is doubled except the level above — ``GroupStub``, because
the GroupHandler is Macro 2's — and the test reads the deposit from the parent
side through a FreezeHandler of its own, over the same root the child was given.

The story: the handler launches its process, which presents itself and is
answered with the whole global store; the beat brings back the photo; the child
takes a user's semaphore, announces it, parks that user's connection under it
and gives the semaphore back; it takes it again, and while it holds it the
process goes mute and the surveillance kills it.

**What the death leaves is the point.** The handler denounces the wild death to
its group, carrying itself and the users that were on board — and stops there.
The parcel is still in the deposit, the semaphore of the interrupted operation
is still held by a process that no longer exists. Macro 1 cleans nothing: the
sweep of the traces belongs to the Commander, which does not exist yet, and this
test is the picture it will inherit.

The sockets and the deposit live under a short ``mkdtemp`` root: the system caps
a UDS path at about a hundred characters and pytest's own directory is already
past it, which is the very reason worker names are short.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.spa.orchestration import FreezeHandler
from genro_asgi.spa.orchestration.worker_handler import WorkerHandler

from .child_stub import (
    GO_MUTE_EVENT,
    LOCK_TAKEN_EVENT,
    RELEASE_LOCK_OP,
    TAKE_LOCK_OP,
    WRITE_CONNECTION_ITEM_OP,
)

CHILD_MODULE = "tests.orchestration.child_stub"
PARKED_CONNECTION = {"cid": "c-1", "pages": ["main", "invoices"]}


class GroupStub:
    """The GroupHandler seen from below: what it is told, and who was on board when."""

    def __init__(self) -> None:
        self.aborted: list[Any] = []
        self.users_on_board: list[set[str]] = []

    def on_worker_abort(self, worker_handler: Any) -> None:
        self.aborted.append(worker_handler)
        self.users_on_board.append(set(worker_handler.hosted_users))


@pytest.fixture
def group():
    return GroupStub()


@pytest.fixture
def foundations_root():
    """The short root holding both the socket directory and the deposit."""
    root = Path(tempfile.mkdtemp(prefix="gnre2e_"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def deposit(foundations_root):
    """The deposit as the parent reads it — the same root the child is given."""
    return FreezeHandler(foundations_root / "frozen_users")


@pytest.fixture
async def handler(foundations_root, group, monkeypatch):
    """The handler under test; no process and no socket of its own outlives the test."""
    repo_root = Path(__file__).resolve().parents[2]
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([str(repo_root), inherited]).rstrip(os.pathsep)
    )
    worker_handler = WorkerHandler(
        group,
        "standard_0001",
        instance_dir=foundations_root / "i",
        frozen_users_path=foundations_root / "frozen_users",
        entry_module=CHILD_MODULE,
        worker_kwargs={"group": "standard"},
        process_ping_timeout=1.0,
    )
    yield worker_handler
    if worker_handler.process is not None:
        worker_handler.process.kill()
        worker_handler.process.wait()
    await worker_handler.connector.stop()


async def order(handler: WorkerHandler, path: str, data: Any = None) -> Any:
    """Drive one order of the child through the wire and give back what it answered."""
    payload = await handler.connector.call(path, data, timeout=5.0)
    return payload["result"]


async def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the foundations never reached the awaited state")
        await asyncio.sleep(0.01)


async def test_a_worker_is_born_works_dies_wild_and_leaves_its_traces_behind(
    handler, group, deposit, caplog
):
    caplog.set_level(logging.INFO)
    handler.hosted_users.update({"mario", "anna"})

    # It is born: the process presents itself on its handler's own socket.
    await handler.launch_process()
    assert handler.connector.connected is True
    presentation = next((line for line in caplog.messages if "presented itself" in line), "")
    assert f"'pid': {handler.process.pid}" in presentation
    assert f"'name': '{handler.name}'" in presentation

    # It is alive: the beat brings back its photo, with the whole global store
    # it was handed in the answer to that presentation.
    await handler.ping_process()
    assert handler.worker_snapshot == {
        "pid": handler.process.pid,
        "name": "standard_0001",
        "global_store": handler.global_register_item_tytx,
    }

    # It takes the semaphore of one of its users, and announces it upward.
    assert await order(handler, TAKE_LOCK_OP, {"user": "mario"}) == {"taken": True}
    assert deposit.lock_holder("mario") == "standard_0001"
    assert deposit.read_connection_item("mario", "c-1") is None
    await wait_for(lambda: LOCK_TAKEN_EVENT in caplog.text)

    # It parks that user's connection under the semaphore it holds, and the
    # parent reads back from the deposit exactly what the child wrote.
    written = await order(
        handler,
        WRITE_CONNECTION_ITEM_OP,
        {"user": "mario", "cid": "c-1", "payload": PARKED_CONNECTION},
    )
    assert written == {"written": "c-1"}
    assert deposit.read_connection_item("mario", "c-1") == PARKED_CONNECTION
    assert deposit.get_item_header("mario", "c-1") == {
        "writer": "standard_0001",
        "ts": pytest.approx(time.time(), abs=60),
        "cause": "freeze",
        "group": "standard",
    }

    # It gives the semaphore back: the operation is over, the parcel stays.
    assert await order(handler, RELEASE_LOCK_OP, {"user": "mario"}) == {"released": "mario"}
    assert deposit.lock_holder("mario") is None
    assert deposit.read_connection_item("mario", "c-1") == PARKED_CONNECTION

    # It takes the semaphore again — this is the operation the death interrupts.
    assert await order(handler, TAKE_LOCK_OP, {"user": "mario"}) == {"taken": True}
    assert deposit.lock_holder("mario") == "standard_0001"

    # It goes mute: up, and no longer serving. The beat is repeated once past
    # the timeout and then the process group is killed and its death awaited.
    condemned = handler.process
    await handler.connector.send_event(GO_MUTE_EVENT)
    started = time.monotonic()
    await handler.ping_process()
    elapsed = time.monotonic() - started

    assert elapsed < 4 * handler.process_ping_timeout
    assert condemned.poll() is not None
    assert handler.process is None

    # The death was nobody's order: the handler denounces it to its group,
    # carrying itself and the users that were on board, and its job ends there.
    await wait_for(lambda: group.aborted == [handler])
    assert group.users_on_board == [{"mario", "anna"}]
    assert handler.connector.connected is False
    assert handler.worker_snapshot["pid"] == condemned.pid

    # And the deposit is exactly as the dead process left it: the parcel it
    # parked, and the semaphore of the operation it never finished. Macro 1
    # cleans nothing — the traces are the Commander's to sweep.
    assert deposit.user_folders == {deposit.user_to_userkey("mario")}
    assert deposit.read_connection_item("mario", "c-1") == PARKED_CONNECTION
    assert deposit.lock_holder("mario") == "standard_0001"
