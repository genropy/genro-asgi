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

"""The common ground of the orchestration tests: the root, the path, the wait.

``desk_lane`` is a live lane — a real worker on a real UDS under a real
commander — for the tests that exercise the site's verbs, which now place calls
on it. ``short_root`` is a temporary directory whose name fits inside the system's cap
on a UDS path — about a hundred characters, which pytest's own ``tmp_path`` is
already past, and the very reason worker names are short. ``repo_on_pythonpath``
puts this repository where a spawned child can import the stub modules of the
test package from. ``wait_for`` polls a condition instead of sleeping a guessed
amount: a process dying, a wire ending, a round landing — none has a duration.
"""

from __future__ import annotations

import asyncio
import functools
import os
import shutil
import signal
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, GroupHandler, SpaCommander, SpaWorker
from genro_asgi.spa.orchestration import spa_worker as spa_worker_module
from genro_asgi.spa.orchestration.worker_handler import WorkerHandler

#: The name the lane's handler and worker share: short, because a UDS path is.
WORKER_NAME = "standard_0001"


@pytest.fixture
def short_root():
    """A temporary root short enough for a socket path; it dies with the test."""
    root = Path(tempfile.mkdtemp(prefix="gnrorch_"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


def kill_process(worker_process) -> None:
    """SIGKILL one worker's process by its pid, the way the handler itself does.

    The tests reach a process through the two questions its handler asks — ``alive``
    and ``pid`` — and never through the Popen underneath, because a forked worker
    has none. Waiting for the death is the caller's next line: ``await wait_for(
    lambda: not handler.process.alive)``.

    One already gone is the same outcome, as it is for the handler's own kill.
    """
    try:
        os.kill(worker_process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def wait_for(condition, timeout: float = 10.0) -> None:
    """Poll until the condition holds, or give up loudly at the deadline."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the machine never reached the awaited state")
        await asyncio.sleep(0.01)


@pytest.fixture
def repo_on_pythonpath(monkeypatch):
    """Let a spawned child import the test package: this repository on its path."""
    repo_root = Path(__file__).resolve().parents[2]
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([str(repo_root), inherited]).rstrip(os.pathsep)
    )


class XT_DeskLane:
    """A worker and its real handler on one UDS, the commander's desk above it.

    Args:
        commander: the vertex whose desk the lane calls reach.
        group: the group the handler hangs under.
        freeze_handler: the deposit the worker is built with.
        worker_name: the name shared by the handler and the worker.

    The site's verbs are served on a traffic-pool thread, and a request IS a
    thread here too: ``verb`` runs them on ONE dedicated thread, so everything a
    test does belongs to the same request slot, and ``open_request`` starts a new
    one on it.
    """

    def __init__(self, commander, group, freeze_handler, worker_name=WORKER_NAME) -> None:
        self.commander = commander
        self.worker_handler = WorkerHandler(group, worker_name, **group.worker_settings)
        self.worker = SpaWorker(
            worker_name, freeze_handler=freeze_handler, deposit_lock_retry_interval=0.01
        )
        self.request_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xt-request")
        self._reader_task = None

    @property
    def desk(self):
        """The desk the calls of this lane land on."""
        return self.commander.delivery_desk

    async def open(self) -> None:
        """Bind, connect, present, and put the worker's read loop on the air."""
        connector = self.worker_handler.connector
        await connector.start()
        reader, writer = await asyncio.open_unix_connection(str(connector.socket_path))
        self.worker.attach_stream(spa_worker_module.FrameStream(reader, writer))
        await self.worker.send_presentation({})
        self._reader_task = asyncio.create_task(self.worker.receive_frames())
        await connector.wait_connected()

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        self.request_pool.shutdown(wait=True)
        self.worker.exit_process()
        await self.worker_handler.connector.stop()

    async def verb(self, name, *args, **kwargs):
        """Call one of the worker's site verbs where the site calls it: off the loop."""
        return await asyncio.get_running_loop().run_in_executor(
            self.request_pool, functools.partial(getattr(self.worker, name), *args, **kwargs)
        )

    async def open_request(self) -> None:
        """Start a fresh request on the thread the verbs run on."""
        await asyncio.get_running_loop().run_in_executor(
            self.request_pool, self.worker.open_request_slot
        )


@pytest.fixture
async def desk_lane(short_root, tmp_path):
    """A live lane: the site's verbs on a worker, the real desk on a real commander."""
    commander = SpaCommander(short_root / "frozen_users")
    group = GroupHandler(
        commander,
        "standard",
        memory_concession_bytes=8 * 1024 * 1024 * 1024,
        instance_dir=short_root / "i",
        frozen_users_path=short_root / "frozen_users",
        entry_module="never.launched",
    )
    lane = XT_DeskLane(commander, group, FreezeHandler(tmp_path / "frozen_users"))
    await lane.open()
    yield lane
    await lane.close()
