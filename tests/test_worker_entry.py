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

"""Worker entry point tests: real children on a real UDS hub.

The spawn contract is only worth what the process actually does, so these
tests run ``python -m genro_asgi.spa.worker_entry`` for real: the REGISTER
lands in the hub's rubric with the child's own pid, a CALL crosses the socket
and comes back as a REPLY, and both deaths (hub gone, SIGTERM) end the child
with exit code 0. The payload validation is checked on the class itself, where
no subprocess is needed.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
from typing import Any

import pytest

from genro_asgi.channel import ChannelHub
from genro_asgi.spa.worker_entry import WorkerEntry

SPAWN_TIMEOUT = 15.0


class ChildHarness:
    """A UDS hub plus the children spawned against it, all reaped at teardown.

    The hub owns its own short-pathed 0700 socket directory (``AF_UNIX`` paths
    are far shorter than a pytest ``tmp_path``) and removes it at ``stop()``.
    """

    def __init__(self) -> None:
        self.hub = ChannelHub()
        self.children: list[subprocess.Popen[bytes]] = []

    async def start(self) -> None:
        await self.hub.start()

    def spawn(self, name: str, **payload: Any) -> subprocess.Popen[bytes]:
        """Launch one worker child with the given ``GENRO_ASGI_WORKER`` payload."""
        env = dict(os.environ)
        env["GENRO_ASGI_WORKER"] = json.dumps(
            {"name": name, "address": self.hub.address, **payload}
        )
        child = subprocess.Popen(
            [sys.executable, "-m", "genro_asgi.spa.worker_entry"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.children.append(child)
        return child

    def spawn_raw(self, payload: str | None) -> subprocess.Popen[bytes]:
        """Launch a child with a deliberately broken (or absent) payload."""
        env = dict(os.environ)
        env.pop("GENRO_ASGI_WORKER", None)
        if payload is not None:
            env["GENRO_ASGI_WORKER"] = payload
        child = subprocess.Popen(
            [sys.executable, "-m", "genro_asgi.spa.worker_entry"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.children.append(child)
        return child

    async def wait_member(self, name: str, timeout: float = SPAWN_TIMEOUT) -> Any:
        """Await the child's REGISTER landing in the rubric."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            member = self.hub.resolve(name)
            if member is not None:
                return member
            if loop.time() >= deadline:
                raise TimeoutError(f"{name} never registered")
            await asyncio.sleep(0.02)

    async def wait_exit(
        self, child: subprocess.Popen[bytes], timeout: float = SPAWN_TIMEOUT
    ) -> int:
        """Await the child's exit without blocking the loop."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while child.poll() is None:
            if loop.time() >= deadline:
                raise TimeoutError(f"child {child.pid} did not exit")
            await asyncio.sleep(0.02)
        return child.returncode

    async def stop(self) -> None:
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=SPAWN_TIMEOUT)
            if child.stdout is not None:
                child.stdout.close()
        await self.hub.stop()


@pytest.fixture
async def harness() -> Any:
    probe = ChildHarness()
    await probe.start()
    try:
        yield probe
    finally:
        await probe.stop()


# ----------------------------------------------------------------------
# The spawn payload — read and validated without a subprocess
# ----------------------------------------------------------------------


def test_config_defaults_to_the_usersticky_worker_class() -> None:
    entry = WorkerEntry({"name": "W:w1", "address": "uds:/tmp/x.sock"})
    assert entry.worker_class == WorkerEntry.DEFAULT_WORKER_CLASS
    assert entry.kwargs == {}
    assert entry.load_class(entry.worker_class).__name__ == "UserStickyWorker"


def test_config_is_read_from_the_environment(monkeypatch: Any) -> None:
    monkeypatch.setenv(
        "GENRO_ASGI_WORKER",
        json.dumps({"name": "W:w9", "address": "uds:/tmp/y.sock", "kwargs": {"max_threads": 3}}),
    )
    entry = WorkerEntry()
    assert (entry.name, entry.address, entry.kwargs) == ("W:w9", "uds:/tmp/y.sock", {"max_threads": 3})


@pytest.mark.parametrize(
    "payload,message",
    [
        (None, "is not set"),
        ("not json at all", "not valid JSON"),
        ("[1, 2]", "must be a JSON object"),
        ('{"address": "uds:/tmp/x.sock"}', "missing name"),
        ('{"name": "W:w1"}', "missing address"),
    ],
)
def test_a_broken_payload_is_a_spawn_contract_violation(
    monkeypatch: Any, payload: str | None, message: str
) -> None:
    monkeypatch.delenv("GENRO_ASGI_WORKER", raising=False)
    if payload is not None:
        monkeypatch.setenv("GENRO_ASGI_WORKER", payload)
    with pytest.raises(SystemExit, match=message):
        WorkerEntry()


def test_a_malformed_worker_class_reference_is_refused() -> None:
    entry = WorkerEntry(
        {"name": "W:w1", "address": "uds:/tmp/x.sock", "worker_class": "no_colon_here"}
    )
    with pytest.raises(SystemExit, match="module.path:ClassName"):
        entry.build_worker()


# ----------------------------------------------------------------------
# Real children on a real hub
# ----------------------------------------------------------------------


async def test_child_registers_with_its_own_name_and_pid(harness: Any) -> None:
    child = harness.spawn("W:w1")
    member = await harness.wait_member("W:w1")
    assert member.name == "W:w1"
    assert member.pid == child.pid


async def test_child_serves_a_call_over_the_socket(harness: Any) -> None:
    harness.spawn("W:w1")
    await harness.wait_member("W:w1")
    payload = await harness.hub.call(
        "W:w1", "/op/new_user", {"identity": "u-1", "kwargs": {"tenant": "acme"}}, timeout=5.0
    )
    assert payload["result"]["register_item_id"] == "u-1"


async def test_hub_stop_ends_the_child_cleanly(harness: Any) -> None:
    child = harness.spawn("W:w1")
    await harness.wait_member("W:w1")
    await harness.hub.stop()
    assert await harness.wait_exit(child) == 0


async def test_sigterm_ends_the_child_cleanly(harness: Any) -> None:
    child = harness.spawn("W:w1")
    await harness.wait_member("W:w1")
    child.send_signal(signal.SIGTERM)
    assert await harness.wait_exit(child) == 0


async def test_a_broken_payload_ends_the_process_with_a_message(harness: Any) -> None:
    child = harness.spawn_raw("not json at all")
    assert await harness.wait_exit(child) != 0
    assert b"not valid JSON" in child.stdout.read()
