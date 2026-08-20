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

"""The group's own life: it is born, it grows, it restarts, it closes, it breaks.

Every worker here is a REAL child process: a scripted one written to disk at test
time, started by the group itself through its own ``WorkerHandler``, configured by
the very payload the handler puts in ``GENRO_ASGI_WORKER``. The child answers
every order with a photo it was told to carry — how much memory it holds, and who
is flagged for the freezer — leaves when it is asked to, or never shows up at all,
which is the group's ``broken`` crisis.

The vertex above the group is real too, so the marks a departure leaves are read
where they are really written. What no test doubles is the group: it is the
subject.

The sockets live under a short ``mkdtemp`` root: the system caps a UDS path at
about a hundred characters and pytest's own directory is already past it, which is
the very reason worker names are short.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.spa.orchestration import AssignmentRefused, GroupHandler, SpaCommander
from genro_asgi.spa.orchestration.worker_connector import ENVELOPE_SLOT_WORKER_SNAPSHOT
from genro_asgi.spa.orchestration.worker_handler import QUIT_OP_PATH, WORKER_ENV_VAR

from .conftest import wait_for

CHILD_SCRIPT = '''
"""A scripted worker of a group: one photo, one answer, one departure."""

import asyncio
import json
import os

from genro_asgi.channel.frame import REGISTER_METHOD, REGISTER_PATH, Frame, FrameStream


async def live() -> None:
    payload = json.loads(os.environ["{env_var}"])
    kwargs = payload["kwargs"]
    if kwargs["behaviour"] == "absent":
        await asyncio.sleep(60)
        return
    photo = {{
        "pid": os.getpid(),
        "rss_bytes": kwargs["rss_bytes"],
        "users": {{user: {{"transfer_flag": "T"}} for user in kwargs["users"]}},
    }}
    reader, writer = await asyncio.open_unix_connection(payload["uds_url"].removeprefix("uds:"))
    stream = FrameStream(reader, writer)
    await stream.write(
        Frame(
            method=REGISTER_METHOD,
            path=REGISTER_PATH,
            data={{"pid": os.getpid(), "{snapshot_key}": photo}},
        )
    )
    await stream.read()
    while True:
        frame = await stream.read()
        if frame is None:
            return
        if frame.method == "CALL":
            data = {{"result": {{}}}}
            # A real worker attaches its photo only when one is DUE, so an
            # answer — the one to the order to leave included — may carry none.
            if frame.path != "{quit_path}" or kwargs["photo_on_quit"]:
                data["{snapshot_key}"] = photo
            await stream.write(
                Frame(id=frame.id, method="REPLY", path=frame.path, data=data)
            )
            # Asked to leave it leaves, after answering: the answer is what
            # carries the photo of everybody it is about to park.
            if frame.path == "{quit_path}":
                await stream.close()
                return


asyncio.run(live())
'''.format(
    env_var=WORKER_ENV_VAR, snapshot_key=ENVELOPE_SLOT_WORKER_SNAPSHOT, quit_path=QUIT_OP_PATH
)

CHILD_MODULE = "scripted_group_child"

#: What the machine concedes these groups. Their quota and what one worker of
#: theirs may hold are both the whole of it by default, so this is also the
#: ceiling every photo below is read against.
MEMORY_CEILING = 1_000_000


@pytest.fixture
def instance_root(monkeypatch):
    """A short root holding the sockets, the deposit and the scripted child."""
    root = Path(tempfile.mkdtemp(prefix="gnrgh_"))
    (root / f"{CHILD_MODULE}.py").write_text(CHILD_SCRIPT)
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(root), inherited]).rstrip(os.pathsep))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def commander(instance_root):
    return SpaCommander(instance_root / "frozen_users")


@pytest.fixture
def group_settings(instance_root):
    """What a group of this file is built with: the child's identity and the paths."""
    return {
        "instance_dir": instance_root / "i",
        "frozen_users_path": instance_root / "frozen_users",
        "entry_module": CHILD_MODULE,
        "worker_kwargs": {
            "behaviour": "answer",
            "users": [],
            "rss_bytes": 0,
            "photo_on_quit": True,
        },
        "process_ping_timeout": 2.0,
    }


@pytest.fixture
async def make_group(commander, group_settings):
    """Build groups, and let no process or socket of theirs outlive the test."""
    groups: list[GroupHandler] = []

    def build(
        *,
        behaviour: str = "answer",
        users: list[str] | None = None,
        rss_bytes: int = 0,
        photo_on_quit: bool = True,
        **policies: Any,
    ) -> GroupHandler:
        settings = dict(group_settings)
        settings["worker_kwargs"] = {
            "behaviour": behaviour,
            "users": users or [],
            "rss_bytes": rss_bytes,
            "photo_on_quit": photo_on_quit,
        }
        group = GroupHandler(
            commander,
            "standard",
            memory_concession_bytes=MEMORY_CEILING,
            **settings,
            **policies,
        )
        groups.append(group)
        return group

    yield build
    for group in groups:
        for worker_handler in list(group.worker_handler_map.values()):
            if worker_handler.process is not None and worker_handler.process.poll() is None:
                worker_handler.process.kill()
                worker_handler.process.wait()
            await worker_handler.connector.stop()


def known_at_the_vertex(commander, cid: str, user: str) -> None:
    """What the login will do in Macro 4: this cid is that person's, and he has a row."""
    commander.connection_user_map[cid] = user
    commander.resolve_user(cid)


async def test_the_first_worker_of_a_group_is_its_reception(make_group):
    group = make_group()
    assert group.reception is None

    worker_handler = await group.start_worker()

    assert group.worker_handler_map == {"standard_0001": worker_handler}
    assert group.reception is worker_handler
    assert worker_handler.state == "running"
    assert worker_handler.worker_snapshot["pid"] == worker_handler.process.pid
    assert group.state == "running"


async def test_a_group_where_nobody_admits_anybody_grows_at_its_check(make_group):
    group = make_group(rss_bytes=int(0.79 * MEMORY_CEILING))
    await group.start_worker()

    await group.check_occupancy(now=True)

    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]
    assert group.state == "running"


async def test_a_group_of_one_closes_nobody(make_group):
    group = make_group()
    reception = await group.start_worker()

    await group.check_occupancy(now=True)

    # Empty as it is, the reception is still the one that receives whoever
    # arrives unplaced: it is nobody's spare capacity.
    assert list(group.worker_handler_map) == ["standard_0001"]
    assert reception.state == "running"


async def test_a_growth_the_quota_refuses_saturates_the_group_until_there_is_room(make_group):
    # Half the concession is this group's, and one worker of it may hold that
    # half whole: two of them at 79% of what they may hold stand together at 79%
    # of the concession, which is over the group's own share of it.
    quota = MEMORY_CEILING // 2
    group = make_group(rss_bytes=int(0.79 * quota), memory_max_percent=50.0)
    reception = await group.start_worker()
    spare = await group.start_worker()

    await group.check_occupancy(now=True)

    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]
    assert group.memory_occupied_percent == 79.0
    assert group.state == "saturated"

    # Somebody left: the same reading admits again, and the crisis is over
    # without anybody having to say so.
    reception.worker_snapshot = {"rss_bytes": quota // 5}
    spare.worker_snapshot = {"rss_bytes": 3 * quota // 5}
    await group.check_occupancy(now=True)

    assert group.memory_occupied_percent == 40.0
    assert group.state == "running"
    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]


async def test_a_process_that_never_starts_breaks_the_group_until_one_does(make_group, caplog):
    group = make_group(behaviour="absent")

    with caplog.at_level("ERROR"):
        assert await group.start_worker() is None

    assert group.state == "broken"
    assert group.worker_handler_map == {}
    assert "could not be started" in caplog.text

    # The first process that starts closes the crisis — nothing else does.
    group.worker_settings["worker_kwargs"]["behaviour"] = "answer"
    assert await group.start_worker() is not None
    assert group.state == "running"


async def test_a_worker_past_the_restart_setpoint_is_replaced_by_a_fresh_one(
    make_group, commander
):
    group = make_group(rss_bytes=int(0.99 * MEMORY_CEILING), users=["mario"])
    known_at_the_vertex(commander, "cid-a", "mario")
    doomed = await group.start_worker()
    doomed.hosted_users.add("mario")
    group.user_worker_map["mario"] = doomed.name

    await group.check_occupancy(now=True)

    assert list(group.worker_handler_map) == ["standard_0002"]
    await wait_for(lambda: doomed.process.poll() is not None)
    assert doomed.state == "quitted"
    # His state went to the freezer with the process that held it, and his
    # placement is to be assigned: his next request decides where he wakes.
    assert commander.user_is_frozen("mario") is True
    assert group.user_worker_map == {"mario": None}
    assert group.state == "running"


async def test_a_closure_that_would_eat_the_reserve_is_not_ordered(make_group):
    # Both at 30%: the spare's share would put the reception at 60, past its own
    # cap (80 less the 50 it reserves) — the flat-average reading would close it,
    # the per-worker question keeps it.
    group = make_group(rss_bytes=int(0.30 * MEMORY_CEILING))
    await group.start_worker()
    await group.start_worker()

    await group.check_occupancy(now=True)

    # The map alone is blind here — an ordered quit leaves the map to the next
    # round — so the states say whether a closure was ordered at all.
    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]
    assert [wh.state for wh in group.worker_handler_map.values()] == ["running", "running"]


async def test_a_worker_on_its_way_out_counts_no_room(make_group):
    group = make_group()
    worker_handler = await group.start_worker()
    worker_handler.state = "quitting"

    await group.check_occupancy(now=True)

    # Empty as it reads, a quitting worker refuses everybody: the reserve is
    # gone and the group grows at its own round.
    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]


async def test_a_death_that_outruns_the_close_order_leaves_no_zombie(make_group, commander):
    group = make_group()
    known_at_the_vertex(commander, "cid-a", "mario")
    doomed = await group.start_worker()
    doomed.hosted_users.add("mario")
    group.user_worker_map["mario"] = doomed.name
    await wait_for(lambda: doomed.worker_snapshot is not None)
    doomed.process.kill()
    await wait_for(lambda: doomed.state == "aborted")

    fresh = await group.restart_worker(doomed)

    # The order found the death already written and ordered nothing: the wild
    # death was not overwritten into a departure nobody would ever settle, the
    # dead one is buried with the users it held, and the fresh one serves.
    assert doomed.state == "aborted"
    assert list(group.worker_handler_map) == [fresh.name]
    assert group.reception is fresh
    assert group.user_worker_map == {}


async def test_a_dead_worker_never_photographed_is_ordered_nothing(make_group):
    group = make_group()
    doomed = await group.start_worker()
    doomed.process.kill()
    await wait_for(lambda: doomed.state == "aborted")
    doomed.worker_snapshot = None

    # The state is read BEFORE the photo beat: no beat is thrown at a dead wire.
    fresh = await group.restart_worker(doomed)

    assert doomed.state == "aborted"
    assert list(group.worker_handler_map) == [fresh.name]


async def test_a_worker_on_its_way_out_is_nobodys_spare(make_group):
    group = make_group()
    await group.start_worker()
    leaving = await group.start_worker()
    leaving.state = "quitting"

    await group.check_occupancy(now=True)

    # Its closure is already somebody's order: it is not a candidate for a
    # second one, and its room counts for nobody.
    assert leaving.state == "quitting"


async def test_the_closure_of_a_spare_worker_goes_through_its_six_steps(make_group, commander):
    group = make_group(users=["mario"])
    known_at_the_vertex(commander, "cid-a", "mario")
    reception = await group.start_worker()
    spare = await group.start_worker()
    spare.hosted_users.add("mario")
    group.user_worker_map["mario"] = spare.name

    # 1. the group decides on one reading: what the spare one holds, the others
    # can hold and still admit.
    await group.check_occupancy(now=True)

    # 2-4. it answered the order at once, with the photo of everybody flagged for
    # the freezer; then it drained and ENDED BY ITSELF, and that end was awaited.
    assert spare.worker_snapshot["users"]["mario"]["transfer_flag"] == "T"
    assert spare.state == "quitted"
    await wait_for(lambda: spare.process.poll() is not None)
    assert reception.state == "running"

    # 5. at the round that reads the ended state, the group takes it out: out of
    # the list, its wire away, its placements released — and the vertex marks the
    # user whose own worker event died with the wire.
    spare.envelope_handler.report_death()

    assert list(group.worker_handler_map) == ["standard_0001"]
    assert group.reception is reception
    assert commander.user_is_frozen("mario") is True
    assert group.user_worker_map == {"mario": None}
    await wait_for(lambda: not spare.connector.socket_path.exists())


async def test_a_closure_that_would_undo_a_growth_is_not_made(make_group):
    group = make_group()
    reception = await group.start_worker()
    spare = await group.start_worker()
    reception.worker_snapshot = {"rss_bytes": int(0.78 * MEMORY_CEILING)}
    spare.worker_snapshot = {"rss_bytes": 0}

    await group.check_occupancy(now=True)

    # Alone, the reception would stand at 78 and take nobody: closing the other
    # one now would only have the next round bring it back.
    assert sorted(group.worker_handler_map) == ["standard_0001", "standard_0002"]
    assert spare.state == "running"


async def test_a_placement_pointing_at_a_worker_that_died_goes_with_it(make_group, commander):
    group = make_group()
    worker_handler = await group.start_worker()
    user = commander.resolve_user("cid-a")
    assert group.assign_user(user) == worker_handler.name

    # The process dies before it ever said the user had arrived in it: nobody
    # names him at the death, so his placement goes with the worker holding it.
    worker_handler.process.kill()
    await wait_for(lambda: worker_handler.state == "aborted")
    worker_handler.envelope_handler.report_death()

    assert group.worker_handler_map == {}
    assert group.user_worker_map == {}


async def test_a_death_reported_for_a_worker_this_group_does_not_have_is_loud(make_group):
    group = make_group()
    await group.start_worker()

    with pytest.raises(KeyError):
        group.drop_worker("standard_9999")

    assert list(group.worker_handler_map) == ["standard_0001"]


async def test_an_ordered_quit_photographs_the_worker_first_so_nobody_is_lost(
    make_group, commander
):
    # A worker whose answer to the order carries no photo — which is what the
    # throttle of a real one does when none is due.
    group = make_group(users=["mario"], photo_on_quit=False)
    known_at_the_vertex(commander, "cid-a", "mario")
    worker_handler = await group.start_worker()
    worker_handler.hosted_users.add("mario")
    # And of which there is no photo at all: a departure is settled on the last
    # one, so without the beat the order takes first, this user would be purged
    # as lost instead of parked in the freezer.
    worker_handler.worker_snapshot = None

    await group.restart_worker(worker_handler)

    assert commander.user_is_frozen("mario") is True
    assert "mario" in commander.user_map
    assert list(group.worker_handler_map) == ["standard_0002"]


async def test_a_photo_past_the_restart_setpoint_brings_the_round_forward(make_group):
    group = make_group()
    worker_handler = await group.start_worker()
    group.ping_now_event.clear()

    worker_handler.read_envelope(
        {ENVELOPE_SLOT_WORKER_SNAPSHOT: {"rss_bytes": MEMORY_CEILING // 2}}
    )
    assert group.ping_now_event.is_set() is False

    worker_handler.read_envelope({ENVELOPE_SLOT_WORKER_SNAPSHOT: {"rss_bytes": MEMORY_CEILING}})

    assert group.ping_now_event.is_set() is True


async def test_every_order_of_the_group_leaves_its_row_in_the_orchestration_log(
    make_group, commander, caplog
):
    group = make_group()
    with caplog.at_level("INFO", logger="genro_asgi.orchestration.orders"):
        worker_handler = await group.start_worker()
        await group.restart_worker(worker_handler)

    rows = [record.getMessage() for record in caplog.records]
    assert any("order=start_worker subject=standard_0001" in row for row in rows)
    assert any("order=restart_worker subject=standard_0001" in row for row in rows)
    assert any("order=drop_worker subject=standard_0001 numbers=None outcome=quitted" in row
               for row in rows)
    assert any("order=start_worker subject=standard_0002" in row for row in rows)


async def test_the_vertex_builds_its_groups_with_the_concession_already_inside(
    instance_root, group_settings
):
    vertex = SpaCommander(instance_root / "frozen_users", groups={"standard": group_settings})

    group = vertex.group_map["standard"]
    assert isinstance(group, GroupHandler)
    assert group.spa_commander is vertex
    assert group.memory_concession_bytes == vertex.memory_concession_bytes
    assert vertex.default_group == "standard"


async def test_a_group_built_without_the_concession_says_so_at_once(commander, group_settings):
    with pytest.raises(TypeError):
        GroupHandler(commander, "standard", **group_settings)


async def test_start_brings_the_reception_up_and_stop_leaves_no_child_alive(
    instance_root, group_settings
):
    vertex = SpaCommander(instance_root / "frozen_users", groups={"standard": group_settings})
    group = vertex.group_map["standard"]
    try:
        await vertex.start()

        # READY is the reception having presented itself: start returns there.
        reception = group.reception
        assert reception is not None
        assert reception.state == "running"
        process = reception.process
        assert process.poll() is None
    finally:
        await vertex.stop()

    assert process.poll() is not None
    assert not reception.connector.connected
    # The death of a shutdown is ORDERED: no alarm is owed for it, and the log
    # of a clean stop must not read like N processes died on their own.
    assert reception.state == "quitted"


async def test_the_group_of_a_user_is_written_where_he_is_placed(make_group, commander):
    group = make_group()
    await group.start_worker()
    known_at_the_vertex(commander, "cid-a", "mario")

    group.assign_user("mario")

    assert group.user_worker_map["mario"] == "standard_0001"
    assert commander.user_map["mario"]["group"] == "standard"


async def test_a_placement_nobody_took_writes_no_group(make_group, commander):
    group = make_group()
    known_at_the_vertex(commander, "cid-a", "mario")

    with pytest.raises(AssignmentRefused):
        group.assign_user("mario")

    assert "mario" not in group.user_worker_map
    assert commander.user_map["mario"]["group"] is None
