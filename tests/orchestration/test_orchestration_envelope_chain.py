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

"""The chain of the envelope: who reads what, and what goes back down.

Every worker event of the census is exercised here, one test each, on the real
three layers over a real ``SpaCommander``: the handler is a real
``WorkerHandler`` with no process under it — construction alone builds its layer
of the chain — and the group is the stub that stands in for the level not yet
built, whose own verbs are the contract that level will owe.

The last test is the whole thing with a REAL child process: a worker event born
in another process lands in the vertex's indexes, the store answers the
presentation and only it, and a fold that refuses an envelope is denounced
without severing the wire.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from genro_tytx import to_tytx

from genro_asgi.spa.orchestration import UserOnHold, WorkerHandler
from genro_asgi.spa.orchestration.envelope_handler import PRESENTATION_KEY, WORKER_EVENTS_KEY
from genro_asgi.spa.orchestration.worker_connector import GLOBAL_STORE_KEY, WORKER_SNAPSHOT_KEY

from .child_stub import ANNOUNCE_OP
from .group_stub import GroupStub

CHILD_MODULE = "tests.orchestration.child_stub"
WORKER_NAME = "standard_0001"
CALL_TIMEOUT = 5.0


def envelope(*worker_events: dict[str, Any], photo: dict[str, Any] | None = None) -> dict[str, Any]:
    """One envelope as a child composes it: its worker events, and its photo if due."""
    made: dict[str, Any] = {WORKER_EVENTS_KEY: list(worker_events)}
    if photo is not None:
        made[WORKER_SNAPSHOT_KEY] = photo
    return made


def presentation(**payload: Any) -> dict[str, Any]:
    """The envelope of a child being born: what only a presentation carries."""
    return {PRESENTATION_KEY: 4242, **payload}


def photo_of(**users: str | None) -> dict[str, Any]:
    """A photo carrying one row per user, each with the flag the shot decided."""
    return {
        "name": WORKER_NAME,
        "user_count": len(users),
        "users": {user: {"item": {}, "transfer_flag": flag} for user, flag in users.items()},
    }


@pytest.fixture
def group(short_root):
    """The group of the tests, with the real chain and the real vertex above it."""
    return GroupStub(short_root / "frozen_users")


@pytest.fixture
def commander(group):
    """The vertex the chain writes through."""
    return group.spa_commander


@pytest.fixture
async def handler(short_root, group):
    """A real handler with no process under it: enough to own its layer of the chain."""
    worker_handler = WorkerHandler(
        group,
        WORKER_NAME,
        instance_dir=short_root / "i",
        frozen_users_path=short_root / "frozen_users",
        entry_module=CHILD_MODULE,
        worker_kwargs={"group": "standard"},
        process_ping_timeout=1.0,
    )
    group.worker_handler = worker_handler
    yield worker_handler
    if worker_handler.process is not None and worker_handler.process.poll() is None:
        worker_handler.process.kill()
        worker_handler.process.wait()
    await worker_handler.connector.stop()


async def test_the_photo_is_filed_by_the_bottom_layer_and_may_wait_for_its_round(handler, group):
    photo = photo_of(mario=None)

    handler.read_envelope(envelope(photo=photo))

    assert handler.worker_snapshot == photo
    assert group.wakes == []


async def test_an_urgent_photo_brings_the_groups_round_forward(handler, group):
    group.urgent_snapshots = True

    handler.read_envelope(envelope(photo=photo_of(mario=None)))

    assert group.wakes == ["starting"]


async def test_a_user_the_photo_shows_leaving_is_put_in_the_waiting_room(handler, commander):
    commander.resolve_user("cid-a")
    commander.resolve_user("cid-b")

    handler.read_envelope(
        envelope(photo=photo_of(**{"guest_cid-a": "T", "guest_cid-b": None}))
    )

    with pytest.raises(UserOnHold) as refusal:
        commander.resolve_user("cid-a")
    assert refusal.value.user == "guest_cid-a"
    assert "T" in refusal.value.cause
    assert commander.resolve_user("cid-b") == "guest_cid-b"


async def test_the_births_of_the_reception_find_the_rows_already_written(handler, commander):
    user = commander.resolve_user("cid-a")
    row = dict(commander.user_map[user])

    handler.read_envelope(
        envelope(
            {"op": "new_user", "worker": WORKER_NAME, "user": user},
            {"op": "new_connection", "worker": WORKER_NAME, "user": user, "session_id": "cid-a"},
        )
    )

    assert commander.user_map[user] == row
    assert commander.connection_user_map == {"cid-a": user}


async def test_a_page_is_written_where_it_belongs_and_forgotten_one_by_one(handler, commander):
    handler.read_envelope(
        envelope(
            {"op": "new_page", "worker": WORKER_NAME, "page_id": "p1", "session_id": "cid-a"},
            {"op": "new_page", "worker": WORKER_NAME, "page_id": "p2", "session_id": "cid-a"},
        )
    )
    assert commander.page_connection_map == {"p1": "cid-a", "p2": "cid-a"}

    handler.read_envelope(
        envelope({"op": "drop_page", "worker": WORKER_NAME, "page_id": "p1"})
    )
    assert commander.page_connection_map == {"p2": "cid-a"}


async def test_a_cascade_of_pages_goes_in_one_worker_event(handler, commander):
    handler.read_envelope(
        envelope(
            {"op": "new_page", "worker": WORKER_NAME, "page_id": "p1", "session_id": "cid-a"},
            {"op": "new_page", "worker": WORKER_NAME, "page_id": "p2", "session_id": "cid-a"},
            {"op": "drop_pages", "worker": WORKER_NAME, "page_ids": ["p1", "p2"]},
        )
    )

    assert commander.page_connection_map == {}


async def test_a_connection_leaves_its_pages_and_keeps_its_identity(handler, commander):
    user = commander.resolve_user("cid-a")
    handler.read_envelope(
        envelope({"op": "new_page", "worker": WORKER_NAME, "page_id": "p1", "session_id": "cid-a"})
    )

    handler.read_envelope(
        envelope({"op": "drop_connection", "worker": WORKER_NAME, "session_id": "cid-a"})
    )

    assert commander.page_connection_map == {}
    assert commander.connection_user_map == {"cid-a": user}
    assert commander.resolve_user("cid-a") == user


async def test_several_connections_leave_in_one_worker_event(handler, commander):
    commander.resolve_user("cid-a")
    commander.resolve_user("cid-b")
    handler.read_envelope(
        envelope(
            {"op": "new_page", "worker": WORKER_NAME, "page_id": "p1", "session_id": "cid-a"},
            {"op": "new_page", "worker": WORKER_NAME, "page_id": "p2", "session_id": "cid-b"},
        )
    )

    handler.read_envelope(
        envelope(
            {"op": "drop_connections", "worker": WORKER_NAME, "session_ids": ["cid-a", "cid-b"]}
        )
    )

    assert commander.page_connection_map == {}
    assert sorted(commander.connection_user_map) == ["cid-a", "cid-b"]


async def test_a_user_who_is_gone_leaves_nothing_behind(handler, commander, group):
    user = commander.resolve_user("cid-a")
    group.user_worker_map[user] = WORKER_NAME
    handler.read_envelope(
        envelope({"op": "new_page", "worker": WORKER_NAME, "page_id": "p1", "session_id": "cid-a"})
    )
    commander.user_map[user]["pending_dbevents"] = [{"table": "invoices"}]

    handler.read_envelope(envelope({"op": "drop_user", "worker": WORKER_NAME, "user": user}))

    assert commander.user_map == {}
    assert commander.connection_user_map == {}
    assert commander.page_connection_map == {}
    assert group.user_worker_map == {}
    assert commander.counters["pendings_lost"] == 1


async def test_the_photo_is_read_before_the_worker_events_of_its_own_envelope(
    handler, commander
):
    user = commander.resolve_user("cid-a")

    handler.read_envelope(
        envelope(
            {"op": "user_frozen", "worker": WORKER_NAME, "user": user, "placement": None},
            photo={"users": {user: {"transfer_flag": "T"}}},
        )
    )

    # One envelope, taken in the order it was shot: the photo parks him first,
    # the event that follows settles him — nobody is left waiting for ever.
    assert commander.user_map[user]["on_hold"] is None
    assert commander.user_is_frozen(user) is True


async def test_a_freeze_is_a_mark_above_and_a_placement_to_assign_below(handler, commander, group):
    user = commander.resolve_user("cid-a")
    group.user_worker_map[user] = WORKER_NAME
    # The estimate is COMPOSED by the bottom rung, never sent by the child: the
    # worker's abstract occupancy (the group's gauge reads this envelope's own
    # photo, filed first) split over everybody it held, the leaver included.
    group.urgent_snapshots = True  # the stub's gauge reads 100.0

    handler.read_envelope(
        envelope(
            {"op": "user_frozen", "worker": WORKER_NAME, "user": user, "placement": None},
            photo={"users": {"somebody-else": {}}},
        )
    )

    assert commander.user_is_frozen(user) is True
    assert commander.user_map[user]["occupancy_percent"] == 50.0
    assert group.user_worker_map == {user: None}


async def test_a_batch_of_freezes_shares_the_worker_they_left(handler, commander, group):
    first = commander.resolve_user("cid-a")
    second = commander.resolve_user("cid-b")
    group.urgent_snapshots = True  # the stub's gauge reads 100.0

    handler.read_envelope(
        envelope(
            {"op": "user_frozen", "worker": WORKER_NAME, "user": first, "placement": None},
            {"op": "user_frozen", "worker": WORKER_NAME, "user": second, "placement": None},
            photo={"users": {"somebody-else": {}}},
        )
    )

    # One photo excludes them BOTH: the divisor is its population plus every
    # leaver of this same envelope, or each would wear the worker whole.
    assert commander.user_map[first]["occupancy_percent"] == 100.0 / 3
    assert commander.user_map[second]["occupancy_percent"] == 100.0 / 3


async def test_an_adoption_turns_the_mark_off_and_drains_what_was_waiting(handler, commander):
    user = commander.resolve_user("cid-a")
    handler.read_envelope(
        envelope(
            {"op": "user_frozen", "worker": WORKER_NAME, "user": user, "placement": None}
        )
    )
    commander.user_map[user]["pending_datachanges"] = [{"path": "a.b"}]

    handler.read_envelope(
        envelope({"op": "user_adopted", "worker": WORKER_NAME, "user": user})
    )

    assert commander.user_is_frozen(user) is False
    assert commander.user_map[user]["pending_datachanges"] == []


async def test_a_hold_is_lifted_by_the_freeze_it_was_waiting_for(handler, commander):
    user = commander.resolve_user("cid-a")
    handler.read_envelope(envelope(photo=photo_of(**{user: "T"})))
    with pytest.raises(UserOnHold):
        commander.resolve_user("cid-a")

    handler.read_envelope(
        envelope({"op": "user_frozen", "worker": WORKER_NAME, "user": user, "placement": None})
    )

    assert commander.resolve_user("cid-a") == user


async def test_a_worker_event_no_layer_knows_is_ignored(handler, commander):
    handler.read_envelope(
        envelope({"op": "something_nobody_reads", "worker": WORKER_NAME, "user": "mario"})
    )

    assert commander.user_map == {}


async def test_the_ordered_death_freezes_the_flagged_and_discards_the_rest(
    handler, commander, group
):
    staying = commander.resolve_user("cid-a")
    leaving = commander.resolve_user("cid-b")
    handler.hosted_users.update({staying, leaving})
    group.user_worker_map[staying] = WORKER_NAME
    group.user_worker_map[leaving] = WORKER_NAME
    handler.read_envelope(envelope(photo=photo_of(**{staying: None, leaving: "T"})))
    handler.state = "quitted"

    handler.envelope_handler.report_death()

    assert commander.user_is_frozen(leaving) is True
    assert staying not in commander.user_map
    assert group.user_worker_map == {leaving: None}
    assert group.dropped_workers == [WORKER_NAME]


async def test_the_wild_death_saves_nobody_and_its_parcels_are_discarded(
    handler, commander, group, caplog
):
    caplog.set_level(logging.INFO)
    user = commander.resolve_user("cid-a")
    handler.hosted_users.add(user)
    # What a freeze leaves on disk, written the way a worker writes it: under the
    # semaphore of that user's own folder.
    commander.freeze_handler.take_lock(user, WORKER_NAME)
    commander.freeze_handler.write_user_register_item(
        user, {"store": "whatever"}, writer=WORKER_NAME, cause="freeze", group="standard"
    )
    commander.freeze_handler.release_lock(user, WORKER_NAME)
    handler.read_envelope(envelope(photo=photo_of(**{user: "T"})))
    handler.state = "aborted"

    handler.envelope_handler.report_death()

    assert commander.user_map == {}
    assert commander.freeze_handler.user_folders == set()
    assert commander.counters["frozen_users_discarded"] == 1
    assert group.dropped_workers == [WORKER_NAME]
    assert "order=drop_user" in caplog.text
    assert "outcome=process_aborted" in caplog.text


async def test_a_death_reported_for_a_living_process_is_refused(handler):
    handler.state = "running"

    with pytest.raises(ValueError, match="not dead"):
        handler.envelope_handler.report_death()


async def test_a_presentation_is_answered_with_the_whole_store(handler, commander):
    register = commander.global_register

    assert handler.read_envelope(presentation()) == {GLOBAL_STORE_KEY: to_tytx(register, "json")}

    register.set_item("counters.invoices", 3)
    answer = handler.read_envelope(presentation())

    assert answer == {GLOBAL_STORE_KEY: to_tytx(register, "json")}
    assert "invoices" in str(answer[GLOBAL_STORE_KEY])


async def test_an_answer_is_not_answered_and_carries_no_store(handler, commander):
    commander.global_register.set_item("counters.invoices", 3)

    assert handler.read_envelope(envelope()) == {}
    assert handler.read_envelope(envelope(photo=photo_of(mario=None))) == {}


async def test_a_real_child_announces_and_the_vertex_learns_it(
    handler, commander, group, repo_on_pythonpath, caplog
):
    caplog.set_level(logging.INFO)
    commander.global_register.set_item("counters.invoices", 3)
    user = commander.resolve_user("cid-a")

    # BORN. Its own first photo cannot know the store — it travels in the
    # presentation, and the store comes back in the answer to it, which is what
    # the chain composed: the whole thing, because a newborn holds nothing.
    await handler.launch_process()
    assert handler.worker_snapshot["global_store"] is None

    # IT ANNOUNCES. What happened in that process rides the answer to the order,
    # climbs the three layers inline, and lands in the indexes of the vertex.
    reply = await handler.connector.call(
        ANNOUNCE_OP,
        {
            "worker_events": [
                {"op": "new_page", "worker": WORKER_NAME, "page_id": "p1", "session_id": "cid-a"},
                {"op": "user_frozen", "worker": WORKER_NAME, "user": user, "placement": None},
            ]
        },
        timeout=CALL_TIMEOUT,
    )

    assert reply["result"] == {"announcing": 2}
    assert reply[WORKER_SNAPSHOT_KEY]["global_store"] == to_tytx(commander.global_register, "json")
    assert commander.page_connection_map == {"p1": "cid-a"}
    assert commander.user_is_frozen(user) is True
    # The estimate was composed on this side of the wire, off the last photo.
    assert commander.user_map[user]["occupancy_percent"] == 0.0
    assert group.user_worker_map == {user: None}

    # A CHANGE MADE NOW DOES NOT REACH IT. The store it holds is the one it was
    # answered at birth, and the beat carries no order of its own: how a change of
    # the master reaches a process already alive is not decided yet — the write
    # climbs, and the update is sent to everybody, in the phase that gives the
    # vertex its groups.
    born_with = handler.worker_snapshot["global_store"]
    commander.global_register.set_item("counters.orders", 7)
    beat = await handler.ping_process()

    assert beat[WORKER_SNAPSHOT_KEY]["global_store"] == born_with
    assert born_with != to_tytx(commander.global_register, "json")

    # A FOLD THAT REFUSES DOES NOT SEVER THE WIRE. An worker event about somebody
    # the vertex never wrote cannot be filed — and a bug one level up must not
    # take a whole process's users down with it: the refusal is denounced and the
    # caller is answered.
    refused = await handler.connector.call(
        ANNOUNCE_OP,
        {"worker_events": [{"op": "drop_page", "worker": WORKER_NAME, "page_id": "p1"}]},
        timeout=CALL_TIMEOUT,
    )
    assert refused["result"] == {"announcing": 1}

    stranger = await handler.connector.call(
        ANNOUNCE_OP,
        {
            "worker_events": [
                {"op": "user_frozen", "worker": WORKER_NAME, "user": "nobody", "placement": None}
            ]
        },
        timeout=CALL_TIMEOUT,
    )

    assert stranger["result"] == {"announcing": 1}
    assert "The fold refused the envelope" in caplog.text
    assert handler.connector.connected is True
    assert await handler.ping_process() is not None
