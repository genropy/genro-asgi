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

"""The single role: one process, one worker, the whole 2a protocol.

``UserStickyCommander(workers=0, local_worker=True)`` holds its worker in this
very process, on a ``LocalChannel`` instead of a socket. Nothing else changes —
same REGISTER, same CALL/REPLY carrying the causal envelope of that call, same
occupancy probe, same fold — so these tests are the protocol's own collaudo: what they exercise is
byte-for-byte what a spawned child would exercise (design §3.5a).

The login belongs here too, and it is no shortcut: one road even when the only
worker is the one the user just left — evicted onto the event, installed back
from the package, released only once the room is ready (R1/R3).
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import pytest

import genro_asgi.channel as channel_package
import genro_asgi.spa as spa_package
from genro_asgi.channel.hub import ChannelCallError
from genro_asgi.spa.commander import UserStickyCommander

SETTLE_TIMEOUT = 5.0


async def until(predicate: Any, timeout: float = SETTLE_TIMEOUT) -> None:
    """Await a condition without blocking the loop."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() >= deadline:
            raise TimeoutError("condition never became true")
        await asyncio.sleep(0.01)


@pytest.fixture
async def single() -> Any:
    """A commander in the single role: no child, its own worker, no heartbeat.

    The hub owns its own socket directory: a ``tmp_path`` under the pytest root
    overflows the ``AF_UNIX`` path limit.
    """
    commander = UserStickyCommander(
        workers=0,
        local_worker=True,
        guest_occupancy_limit=1000,
    )
    await commander.start()
    try:
        yield commander
    finally:
        await commander.stop()


# ----------------------------------------------------------------------
# The wiring: one member, in this process, and it is the reception
# ----------------------------------------------------------------------


async def test_the_local_worker_registers_like_any_child(single: UserStickyCommander) -> None:
    name = single.worker.name
    assert single.active_workers == [name]
    assert single.hub.resolve(name).pid == os.getpid()
    assert single.worker_roster[name]["process"] is None


async def test_the_reception_is_the_local_worker(single: UserStickyCommander) -> None:
    assert single.reception == single.worker.name
    assert single.worker_for("nobody-knows-me") == single.worker.name


async def test_no_child_is_spawned(single: UserStickyCommander) -> None:
    single.reconcile()
    assert single.target == 0
    assert single.living_workers == [single.worker.name]


# ----------------------------------------------------------------------
# The whole envelope round trip, over the queue wire
# ----------------------------------------------------------------------


async def test_a_lifecycle_call_folds_its_events_before_the_reply_is_released(
    single: UserStickyCommander,
) -> None:
    entry = await single.forward_call("sess-1", "/op/new_user")
    assert entry["register_item_id"] == "sess-1"
    # The fold ran inside the hub's REPLY handling: the surface is already current.
    assert single.user_worker_map == {"sess-1": single.worker.name}
    assert single.users_on(single.worker.name) == {"sess-1"}


async def test_every_frame_crosses_the_codec(single: UserStickyCommander) -> None:
    entry = await single.forward_call("sess-1", "/op/new_user", {"lang": "it"})
    stored = single.worker.user_items.get("sess-1")
    assert entry == stored
    # Decoded from bytes, never a shared reference to the worker's own item.
    assert entry is not stored


async def test_an_unknown_op_comes_back_as_an_error_reply(
    single: UserStickyCommander,
) -> None:
    with pytest.raises(ChannelCallError, match="unknown op"):
        await single.forward_call("sess-1", "/op/no_such_op")


async def test_a_drop_rides_the_reply_of_the_call_that_caused_it(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user")
    await single.forward_call("sess-1", "/op/drop_user")
    # The envelope is causal: the fold ran before the caller was resolved, so
    # the surface is already current when the drop returns.
    assert single.user_worker_map == {}
    assert single.users_on(single.worker.name) == set()


def spy_on_replies(commander: UserStickyCommander) -> list[tuple[str, list[dict[str, Any]]]]:
    """Record the path and the envelope of every REPLY the hub reads back.

    The payload reaches the caller verbatim from the frame, so this is what
    crossed the wire: one entry per CALL, in the order the hub resolved them.
    """
    seen: list[tuple[str, list[dict[str, Any]]]] = []
    original = commander.hub.call

    async def spying(name: str, path: str, data: Any = None, timeout: float | None = None) -> Any:
        payload = await original(name, path, data, timeout=timeout)
        seen.append((path, payload.get("events", [])))
        return payload

    commander.hub.call = spying
    return seen


async def test_every_reply_carries_only_the_events_of_its_own_call(
    single: UserStickyCommander,
) -> None:
    seen = spy_on_replies(single)
    await single.forward_call("sess-1", "/op/new_user")
    await single.forward_call("sess-2", "/op/new_user")
    await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    await single.probe_worker(single.worker.name)
    # Causal attribution: the lifecycle a call produced rides that call's REPLY —
    # never a neighbour's, and never an operational op's empty envelope.
    assert [(path, [event["op"] for event in events]) for path, events in seen] == [
        ("/op/new_user", ["new_user"]),
        ("/op/new_user", ["new_user"]),
        ("/op/change_connection_user", ["change_connection_user"]),
        ("/op/install_package", []),
        ("/op/occupancy", []),
    ]
    assert [event["user"] for _, events in seen for event in events] == [
        "sess-1",
        "sess-2",
        "alice",
    ]


async def test_the_occupancy_probe_is_answered_over_the_queue_wire(
    single: UserStickyCommander,
) -> None:
    name = single.worker.name
    await single.probe_worker(name)
    window = single.worker_roster[name]["occupancy"]
    assert window[-1]["report"]["worker"] == name


# ----------------------------------------------------------------------
# The login: one road even when the destination is the worker it left
# ----------------------------------------------------------------------


def gate_the_install(commander: UserStickyCommander, gate: asyncio.Event) -> dict[str, Any]:
    """Hold every install CALL on ``gate`` and record what the worker held then.

    The install is the middle of the ratified sequence, so parking there is the
    only way to observe the window in which the user exists nowhere but in the
    package riding the event.
    """
    seen: dict[str, Any] = {}
    original = commander.hub.call

    async def gated(name: str, path: str, data: Any = None, timeout: float | None = None) -> Any:
        if path.endswith("install_package"):
            seen["identity"] = data["identity"]
            seen["held"] = commander.worker.user_items.get(data["identity"])
            seen["flag"] = commander.user_worker_map.get(data["identity"], "missing")
            await gate.wait()
        return await original(name, path, data, timeout=timeout)

    commander.hub.call = gated
    return seen


async def test_a_login_evicts_the_slice_and_installs_it_back(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user", {"lang": "it"})
    before = single.worker.user_items.get("sess-1")
    entry = await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    installed = single.worker.user_items.get("alice")
    assert entry["register_item_id"] == "alice"
    assert single.worker.user_items.get("sess-1") is None
    # A fresh item under the new key, carrying what the anonymous one carried.
    assert installed is not before
    assert installed["register_item_id"] == "alice"
    assert installed["lang"] == "it"
    assert single.user_worker_map == {"alice": single.worker.name}
    assert single.users_on(single.worker.name) == {"alice"}


async def test_the_login_is_released_only_once_the_room_is_ready(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user")
    gate = asyncio.Event()
    seen = gate_the_install(single, gate)
    login = asyncio.create_task(
        single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    )
    await until(lambda: "held" in seen)
    # Mid-sequence: the source spent its copy, the map carries the flag, and the
    # login caller is still parked on the install.
    assert seen["identity"] == "alice"
    assert seen["held"] is None
    assert seen["flag"] is None
    assert not login.done()
    gate.set()
    entry = await login
    assert entry["register_item_id"] == "alice"
    assert single.worker.user_items.get("alice") is not None


async def test_a_call_parked_on_the_flag_lands_after_the_placement(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user")
    gate = asyncio.Event()
    seen = gate_the_install(single, gate)
    login = asyncio.create_task(
        single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    )
    await until(lambda: "held" in seen)
    parked = asyncio.create_task(single.forward_call("alice", "/op/drop_user"))
    await asyncio.sleep(0.05)
    assert not parked.done()
    gate.set()
    await login
    dropped = await parked
    assert dropped["register_item_id"] == "alice"
    assert single.user_worker_map == {}


async def test_an_install_that_fails_leaves_the_user_nowhere(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("sess-1", "/op/new_user")
    original = single.hub.call

    async def failing(name: str, path: str, data: Any = None, timeout: float | None = None) -> Any:
        if path.endswith("install_package"):
            raise RuntimeError("no room")
        return await original(name, path, data, timeout=timeout)

    single.hub.call = failing
    with pytest.raises(RuntimeError, match="no room"):
        await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert single.user_worker_map == {}
    assert single.worker.user_items.get("alice") is None
    # Nobody holds the user, so the next call for it is a guest arriving.
    single.hub.call = original
    assert single.worker_for("alice") == single.reception


async def test_the_user_stays_reachable_after_the_login(single: UserStickyCommander) -> None:
    await single.forward_call("sess-1", "/op/new_user")
    await single.forward_call("sess-1", "/op/change_connection_user", {"user": "alice"})
    assert single.worker_for("alice") == single.worker.name
    dropped = await single.forward_call("alice", "/op/drop_user")
    assert dropped["register_item_id"] == "alice"
    assert single.user_worker_map == {}


# ----------------------------------------------------------------------
# The public faces, after the pruning
# ----------------------------------------------------------------------


def test_the_packages_export_no_pruned_name() -> None:
    pruned = {
        "PendingMove",
        "MOVE_TIMEOUT",
        "MOVE_QUIESCE_TIMEOUT",
        "OPEN_REQUEST_TTL",
        "CALL_TIMEOUT",
        "MOVE_INSTALL_TIMEOUT",
        "OCCUPANCY_PATH",
        "OCCUPANCY_INTERVAL",
        "spawn_placements",
        "throttle_crash",
    }
    assert pruned.isdisjoint(spa_package.__all__)
    assert pruned.isdisjoint(channel_package.__all__)
    assert all(hasattr(spa_package, name) for name in spa_package.__all__)
    assert all(hasattr(channel_package, name) for name in channel_package.__all__)


# ----------------------------------------------------------------------
# Shutdown
# ----------------------------------------------------------------------


async def test_stopping_the_commander_takes_the_local_worker_down() -> None:
    commander = UserStickyCommander(workers=0, local_worker=True)
    await commander.start()
    worker = commander.worker
    channel = commander.local_channel
    await commander.stop()
    assert commander.worker is None
    assert not channel.connected
    assert worker.channel is channel
    assert commander.hub.members == {}
