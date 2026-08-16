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

"""WorkerHandler tests: real child processes, real sockets, real kills.

The handler governs an operating-system process, so every test here spawns one: a
scripted child written to disk at test time (``CHILD_SCRIPT``), started by the
handler itself as ``python -m <module>`` and configured by the very payload the
handler puts in ``GENRO_ASGI_WORKER``. The child answers every CALL with a photo,
or stays mute on purpose, or never shows up at all — the three behaviours the
surveillance has to tell apart.

The sockets live under a short ``mkdtemp`` root: the system caps a UDS path at
about a hundred characters and pytest's own directory is already past it, which
is the very reason handler names are short.

``GroupStub`` is the level above. The only thing the handler asks of it is
``on_worker_abort``, so that is all it has, and the tests read what reached it.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.channel.frame import Frame
from genro_asgi.spa.orchestration.worker_connector import WORKER_SNAPSHOT_KEY
from genro_asgi.spa.orchestration import LocalWorkerHandler, WorkerHandler
from genro_asgi.spa.orchestration.worker_handler import OCCUPANCY_OP_PATH, WORKER_ENV_VAR

CHILD_SCRIPT = '''
"""A scripted worker process: presents itself, answers with a photo, nothing else."""

import asyncio
import json
import os

from genro_asgi.channel.frame import REGISTER_METHOD, REGISTER_PATH, Frame, FrameStream


def photo_of(payload):
    return {{"pid": os.getpid(), "asked_on": "presentation", "rss_mb": 42}}


async def live() -> None:
    payload = json.loads(os.environ["{env_var}"])
    behaviour = payload["kwargs"].get("behaviour", "answer")
    if behaviour == "absent":
        await asyncio.sleep(60)
        return
    reader, writer = await asyncio.open_unix_connection(payload["uds_url"].removeprefix("uds:"))
    stream = FrameStream(reader, writer)
    await stream.write(
        Frame(
            method=REGISTER_METHOD,
            path=REGISTER_PATH,
            data={{"pid": os.getpid(), "config": payload, "{snapshot_key}": photo_of(payload)}},
        )
    )
    await stream.read()
    while True:
        frame = await stream.read()
        if frame is None:
            return
        if frame.method == "CALL" and behaviour == "answer":
            photo = {{"pid": os.getpid(), "asked_on": frame.path, "rss_mb": 42}}
            await stream.write(
                Frame(
                    id=frame.id,
                    method="REPLY",
                    path=frame.path,
                    data={{"result": {{}}, "{snapshot_key}": photo}},
                )
            )


asyncio.run(live())
'''.format(env_var=WORKER_ENV_VAR, snapshot_key=WORKER_SNAPSHOT_KEY)

CHILD_MODULE = "scripted_child"


class GroupStub:
    """The GroupHandler seen by its handler: it is told, and it remembers."""

    def __init__(self) -> None:
        self.aborted: list[Any] = []

    def on_worker_abort(self, worker_handler: Any) -> None:
        self.aborted.append(worker_handler)


@pytest.fixture
def group():
    return GroupStub()


@pytest.fixture
def instance_root(monkeypatch):
    """A short root holding the sockets, the deposit and the scripted child."""
    root = Path(tempfile.mkdtemp(prefix="gnrwh_"))
    (root / f"{CHILD_MODULE}.py").write_text(CHILD_SCRIPT)
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(root), inherited]).rstrip(os.pathsep))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
async def make_handler(instance_root, group):
    """Build handlers, and let no process or socket of theirs outlive the test."""
    handlers: list[WorkerHandler] = []

    def build(name: str = "standard_0001", behaviour: str = "answer", **kwargs: Any):
        handler = WorkerHandler(
            group,
            name,
            instance_dir=instance_root / "i",
            frozen_users_path=instance_root / "frozen_users",
            entry_module=CHILD_MODULE,
            worker_kwargs={"behaviour": behaviour},
            process_ping_timeout=1.0,
            **kwargs,
        )
        handlers.append(handler)
        return handler

    yield build
    for handler in handlers:
        if handler.process is not None:
            handler.process.kill()
            handler.process.wait()
        await handler.connector.stop()


async def wait_for(condition, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the handler never reached the awaited state")
        await asyncio.sleep(0.01)


async def test_the_spawn_payload_carries_the_child_whole_configuration(make_handler, instance_root):
    handler = make_handler(
        main_threadpool_size=8,
        aux_threadpool_size=2,
        worker_class="genro_asgi.spa.worker:UserStickyWorker",
    )

    assert handler.spawn_payload == {
        "name": "standard_0001",
        "uds_url": f"uds:{instance_root / 'i' / 'standard_0001.sock'}",
        "frozen_users_path": str(instance_root / "frozen_users"),
        "main_threadpool_size": 8,
        "aux_threadpool_size": 2,
        "worker_class": "genro_asgi.spa.worker:UserStickyWorker",
        "kwargs": {"behaviour": "answer"},
    }


async def test_the_global_store_is_not_answerable_before_its_owner_exists(make_handler):
    assert make_handler().global_register_item_tytx == "not yet ready --- wait next phase"


async def test_a_launched_process_presents_itself_on_the_handlers_socket(make_handler):
    handler = make_handler()

    await handler.launch_process()

    assert handler.process.poll() is None
    assert handler.connector.connected is True
    assert handler.connector.socket_path.exists()


async def test_the_photo_arrives_with_the_presentation_and_every_envelope_after(make_handler):
    handler = make_handler()
    await handler.launch_process()

    assert handler.worker_snapshot == {
        "pid": handler.process.pid,
        "asked_on": "presentation",
        "rss_mb": 42,
    }

    await handler.ping_process()

    assert handler.worker_snapshot == {
        "pid": handler.process.pid,
        "asked_on": "/op/occupancy",
        "rss_mb": 42,
    }
    assert OCCUPANCY_OP_PATH == "/op/occupancy"


async def test_a_mute_process_is_killed_after_one_repeated_beat(make_handler, group, caplog):
    handler = make_handler(behaviour="mute")
    await handler.launch_process()
    process = handler.process

    with caplog.at_level("WARNING"):
        await handler.ping_process()

    assert "beat 1 of 2 unanswered" in caplog.text
    assert "beat 2 of 2 unanswered" in caplog.text
    assert process.poll() is not None
    assert handler.process is None
    assert handler.worker_snapshot["pid"] == process.pid
    await wait_for(lambda: group.aborted == [handler])


async def test_a_wild_death_reaches_the_group_with_the_handler_and_its_users(make_handler, group):
    handler = make_handler()
    await handler.launch_process()
    handler.hosted_users.update({"mario", "anna"})

    handler.process.kill()
    await wait_for(lambda: len(group.aborted) == 1)

    assert group.aborted[0] is handler
    assert group.aborted[0].hosted_users == {"mario", "anna"}
    assert handler.connector.connected is False


async def test_a_bare_termination_is_not_a_governed_death(make_handler, group):
    handler = make_handler()
    await handler.launch_process()

    await handler.terminate_process()

    assert handler.process is None
    await wait_for(lambda: group.aborted == [handler])


async def test_a_governed_restart_announces_nothing_and_keeps_the_address(make_handler, group):
    handler = make_handler()
    await handler.launch_process()
    first = handler.process
    address = handler.connector.address

    await handler.restart_process()

    assert first.poll() is not None
    assert handler.process.pid != first.pid
    assert handler.process.poll() is None
    assert handler.connector.address == address
    assert handler.connector.connected is True
    assert group.aborted == []

    await handler.ping_process()
    assert handler.worker_snapshot["pid"] == handler.process.pid


async def test_a_second_launch_over_a_living_process_is_refused(make_handler):
    handler = make_handler()
    await handler.launch_process()
    resident = handler.process

    with pytest.raises(RuntimeError, match="is still alive"):
        await handler.launch_process()

    assert handler.process is resident
    assert resident.poll() is None


async def test_a_restart_of_a_handler_whose_process_already_died_stays_hearing(make_handler, group):
    handler = make_handler()
    await handler.launch_process()
    handler.process.kill()
    await wait_for(lambda: group.aborted == [handler])

    await handler.restart_process()
    assert handler.connector.connected is True

    handler.process.kill()
    await wait_for(lambda: group.aborted == [handler, handler])


async def test_the_death_after_a_governed_one_is_wild_again(make_handler, group):
    handler = make_handler()
    await handler.launch_process()
    await handler.restart_process()

    handler.process.kill()
    await wait_for(lambda: group.aborted == [handler])


async def test_a_process_that_never_presents_itself_is_killed_and_the_wait_raises(
    make_handler, group
):
    handler = make_handler(behaviour="absent")

    with pytest.raises(TimeoutError):
        await handler.launch_process()

    assert handler.process is None
    assert group.aborted == []


async def test_an_event_from_the_process_is_logged_and_consumed_by_nobody(make_handler, caplog):
    handler = make_handler()

    with caplog.at_level("INFO"):
        handler.on_child_message(Frame(method="EVENT", path="/lock_taken", data={"user": "mario"}))

    assert "/lock_taken" in caplog.text
    assert "not consumed yet" in caplog.text


async def test_the_local_handler_refuses_every_process_order(instance_root, group):
    handler = _local_handler(instance_root, group)

    for order in (
        handler.launch_process(),
        handler.terminate_process(),
        handler.restart_process(),
        handler.ping_process(),
    ):
        with pytest.raises(RuntimeError, match="its health is the server"):
            await order

    assert handler.process is None


async def test_the_local_handler_is_a_handler_in_everything_else(instance_root, group):
    handler = _local_handler(instance_root, group)

    handler.hosted_users.add("mario")

    assert isinstance(handler, WorkerHandler)
    assert handler.global_register_item_tytx == "not yet ready --- wait next phase"
    assert handler.worker_snapshot is None
    assert handler.spawn_payload["name"] == "single_0001"
    assert handler.hosted_users == {"mario"}


def _local_handler(instance_root: Path, group: GroupStub) -> LocalWorkerHandler:
    """The in-process handler, built the way its group would build it."""
    return LocalWorkerHandler(
        group,
        "single_0001",
        instance_dir=instance_root / "i",
        frozen_users_path=instance_root / "frozen_users",
        entry_module=CHILD_MODULE,
    )
