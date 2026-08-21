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

"""Macro 3 end to end: a pool written in a config file, living its whole day.

Everything here is the real thing. The policies are read from a **config file on
disk** through the server's own read door, the vertex and the group are built
from what it says, and every worker is a REAL child process running the package's
own ``WorkerEntry`` over a real Unix socket, freezing real users onto a real disk.
Nothing is doubled: what plays a part it does not own is only the DRIVER — the
test — standing in for the request chain of Macro 4, which is the layer that will
turn an HTTP request into "resolve the identity, place him, forward".

The worker in the children is ``X_SpaWorker_m3``, which takes the shared
instrumentation of ``X_SpaWorker`` — the declared memory and the
driver's two orders — and fills the ``wsgi_app`` seam with a tiny site of its
own, the way the genropy-asgi bridge fills it with a whole one.

The day, in order:

1. **The reception is born.** The group's first worker is a role and not a count:
   nothing in the grammar says how many processes there are.
2. **Two people arrive** and are placed on it, and the site answers them through
   the WSGI seam. The rows are born in the vertex's indexes.
3. **One of them goes quiet** past the ``user_idle_freeze_minutes`` the CONFIG
   FILE declared, so the shot flags her for the freezer: the vertex parks her, and
   past the gate her state is on disk and her placement is nobody's.
4. **Her next request wakes her**, lazily: the vertex says frozen, the group says
   where, and the call carries the verdict that authorises the trip home.
5. **The pool grows on demand.** The machine's concession is measured at last and
   the reception reads full: a newcomer nobody admits rings the wake, the round
   brings a second process into being, and his retry lands on it — the reception
   refuses him with the reserve it keeps for the trade only it has.
6. **The pool shrinks by waste.** The machine grew, so what the second one holds
   the reception can absorb and still admit: the closure runs its six steps over
   the real child, and the round that reads its ended state takes it out.
7. **A process dies wild**, with two people on board, while the real clock is
   running: the end of its wire rings the wake, the round reads ``aborted``, the
   two on board are purged whole — the freezer state of a process nobody can
   question is not to be trusted — the frozen woman who was on nobody's board is
   untouched, and the group, left with no worker at all, brings a fresh reception
   into being. Nobody drove any of it: the machine did.

And the ACCOUNT of the day: the orchestration log the config file named, read at
the end, one row per order — who decided, what, on whom, with which numbers, how
it ended.

The sockets, the freezer and the config file live under a short ``mkdtemp`` root:
the system caps a UDS path at about a hundred characters and pytest's own
directory is already past it, which is the very reason worker names are short.
"""

from __future__ import annotations

import asyncio
import base64
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from genro_asgi.config import ConfigurationHandler
from genro_asgi.spa.orchestration import (
    AssignmentRefused,
    FreezeHandler,
    GroupHandler,
    SpaCommander,
    UserOnHold,
)

from .conftest import wait_for
from .x_spa_worker import EXECUTE_ORDER, PLAN_ORDER, X_SpaWorker

#: The front that owns the pool of this story: a pool hangs under its own app.
APP_CODE = "shop"

GROUP = "std"
ENTRY_MODULE = "genro_asgi.spa.orchestration.worker_entry"
STORY_WORKER = f"{__name__}:X_SpaWorker_m3"

#: The silence past which a worker parks a user, as the CONFIG FILE declares it —
#: in minutes, because it is a policy of the installation — and the gate the
#: departures wait out. Both shrunk so the day is told in fractions of a second.
IDLE_SECONDS = 0.5
IDLE_MINUTES = IDLE_SECONDS / 60
GATE_DELAY = 0.3

#: What every child of this story declares it holds. The concession it is read
#: against is the machine's, and the story measures it when it wants the pool to
#: feel full: 70 MB in 100 MB is 70% of a worker's ceiling.
STORY_RSS_BYTES = 70_000_000
TIGHT_CONCESSION_BYTES = 100_000_000
ROOMY_CONCESSION_BYTES = 1_000_000_000

CALL_TIMEOUT = 10.0
DEATH_TIMEOUT = 15.0

POOL_CONFIG = '''
"""The pool of the story, as an installation writes it."""

from genro_asgi.applications.spa_app_new import SpaApplicationNew
from genro_asgi.config import AsgiConfigBuilder


class ServerConfiguration(AsgiConfigBuilder):
    """One front, its commander, one group, and the child that runs in it."""

    default_config = False

    def main(self, root):
        cfg = root.configuration()
        front = cfg.applications().application(
            code="{app_code}", mount="", app_class=SpaApplicationNew
        )
        commander = front.commander(
            frozen_users_path="{root}/frozen_users",
            instance_dir="{root}/i",
            orchestration_log_path="{root}/orchestration.log",
            orchestration_log_max_bytes=1000000,
            orchestration_log_backup_count=2,
            memory_max_percent=90.0,
            machine_memory_alarm_percent=95.0,
            user_expiry_hours=240.0,
            guest_expiry_hours=6.0,
        )
        commander.groups().group(
            name="{group}",
            worker_memory_max_percent=100.0,
            occupancy_max_percent=80.0,
            restart_occupancy_max_percent=95.0,
            reception_reserved_percent=20.0,
            new_user_occupancy_percent=5.0,
            user_idle_freeze_minutes={idle_minutes},
            entry_module="{entry_module}",
            worker_class="{worker_class}",
            main_threadpool_size=4,
            aux_threadpool_size=1,
            worker_kwargs={{
                "declared_rss_bytes": {rss_bytes},
                "transfer_start_delay": {gate_delay},
                "worker_snapshot_ttl": 0,
            }},
        )
'''


class X_SpaWorker_m3(X_SpaWorker):
    """The worker of the story: the shared instrumentation, and a tiny site.

    The site is the real seam — ``wsgi_app``, what the genropy-asgi bridge
    assigns — and it says back who asked and for what, which is how the parent
    reads that the request really crossed the process boundary.
    """

    def site(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        """The WSGI callable: say back who asked, for what, and which process served it."""
        identity = environ["genro.identity"]
        cid = self.request_slot.cid
        if identity is not None and self._connection_for_cid(cid) is None:
            # A real site registers its connection while serving (doctrine of
            # 2026-08-21: the rows are the site's) — keyed by the cookie, the
            # core-only world where no site renames it.
            self.new_connection(cid, user=identity)
        start_response("200 OK", [("Content-Type", "text/plain"), ("X-Worker", self.name)])
        return [f"{environ['REQUEST_METHOD']} {environ['PATH_INFO']} "
                f"for {identity}".encode()]


def http_call(cid: str, identity: str, *, path: str, **payload: Any) -> dict[str, Any]:
    """The http CALL form as the front packs it: the request, and who it is for."""
    return {
        "http": {
            "method": "GET",
            "path": path,
            "query_string": "",
            "headers": [["host", "site.example:8080"]],
            "body": "",
            "cid": cid,
        },
        "identity": identity,
        **payload,
    }


def body_of(reply: dict[str, Any]) -> str:
    """The site's answer, decoded out of the wire form."""
    return base64.b64decode(reply["result"]["body"]).decode()


def announced(reply: dict[str, Any]) -> list[str]:
    """The protocol names the reply carried up, in order."""
    return [event["op"] for event in reply["worker_events"]]


def known_at_the_vertex(vertex: SpaCommander, cid: str, user: str) -> str:
    """What the login will do in Macro 4: this cid is that person's, and he has a row."""
    vertex.connection_user_map[cid] = user
    return vertex.resolve_user(cid)


async def serve(group: GroupHandler, user: str, cid: str, path: str, **payload: Any) -> Any:
    """One request, the way the chain of Macro 4 will do it: where he lives, then there.

    The driver's whole part in this story: it never decides anything the machine
    decides — the placement is the group's, the identity is the vertex's — it only
    carries the request to the process the pool named.
    """
    worker_name = group.user_worker_map.get(user) or group.assign_user(user)
    handler = group.worker_handler_map[worker_name]
    return await handler.connector.call(
        f"/site{path}", http_call(cid, user, path=path, **payload), timeout=CALL_TIMEOUT
    )


def orders_text(story_root: Path) -> str:
    """The orchestration log the config file named, as it stands on disk."""
    return (story_root / "orchestration.log").read_text()


def orders_of(story_root: Path) -> list[str]:
    """The orchestration log as the sysop reads it: the order rows, in order."""
    return [row.partition("decided_by=")[2] for row in orders_text(story_root).splitlines()]


@pytest.fixture
def story_root(repo_on_pythonpath):
    """The short root holding the config file, the sockets and the freezer."""
    root = Path(tempfile.mkdtemp(prefix="gnrm3_"))
    (root / "pool_config.py").write_text(
        POOL_CONFIG.format(
            root=root,
            app_code=APP_CODE,
            group=GROUP,
            idle_minutes=IDLE_MINUTES,
            entry_module=ENTRY_MODULE,
            worker_class=STORY_WORKER,
            rss_bytes=STORY_RSS_BYTES,
            gate_delay=GATE_DELAY,
        )
    )
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def pool_config(story_root):
    """The server's own read door over the config FILE of this installation."""
    return ConfigurationHandler(story_root / "pool_config.py")


@pytest.fixture
async def group(pool_config):
    """The vertex and the group, built from nothing but what the config file says."""
    vertex = SpaCommander(**pool_config.commander_kwargs(APP_CODE))
    group_handler = GroupHandler(
        vertex,
        GROUP,
        memory_concession_bytes=vertex.memory_concession_bytes,
        **pool_config.group_kwargs(APP_CODE)[GROUP],
    )
    yield group_handler
    for worker_handler in list(group_handler.worker_handler_map.values()):
        if worker_handler.process is not None and worker_handler.process.poll() is None:
            worker_handler.process.kill()
            worker_handler.process.wait()
        await worker_handler.connector.stop()


async def test_the_pool_of_a_config_file_lives_its_whole_day(group, story_root):
    vertex = group.spa_commander
    freezer = FreezeHandler(story_root / "frozen_users")
    # What the file said, where it had to arrive: the vertex's policies, the
    # group's, and the ones that belong to the child.
    assert vertex.user_expiry_hours == 240.0
    assert vertex.machine_memory_alarm_percent == 95.0
    assert group.occupancy_max_percent == 80.0
    assert group.reception_reserved_percent == 20.0
    assert group.worker_settings["worker_kwargs"]["user_idle_freeze_minutes"] == IDLE_MINUTES

    # 1. THE RECEPTION IS BORN. One worker, which is a role and not a count: the
    # grammar never said how many.
    reception = await group.start_worker()

    assert list(group.worker_handler_map) == [f"{GROUP}_0001"]
    assert group.reception is reception
    assert reception.state == "running"
    assert reception.worker_snapshot["pid"] == reception.process.pid

    # 2. TWO PEOPLE ARRIVE. The vertex knows them (the login of Macro 4), the
    # group places them, and the site answers through the seam.
    mario = known_at_the_vertex(vertex, "cid-a", "mario")
    anna = known_at_the_vertex(vertex, "cid-b", "anna")
    first = await serve(group, mario, "cid-a", "/invoices")
    await serve(group, anna, "cid-b", "/orders")

    assert body_of(first) == "GET /invoices for mario"
    assert announced(first) == ["new_user", "new_connection"]
    assert group.user_worker_map == {mario: reception.name, anna: reception.name}
    # And the process's own layer of the chain kept the list a death is settled
    # on: who is in there is what the process announced.
    assert reception.hosted_users == {mario, anna}

    # 3. ONE GOES QUIET. Past the silence the config file declared, the shot flags
    # her — the valve is one more reason for a 'T' — while the one who has just
    # spoken is kept; the vertex parks whoever is on his way out.
    await asyncio.sleep(2 * IDLE_SECONDS)
    await serve(group, mario, "cid-a", "/invoices")
    planned = await reception.connector.call(PLAN_ORDER, timeout=CALL_TIMEOUT)

    flags = planned["worker_snapshot"]["users"]
    assert {user: row["transfer_flag"] for user, row in flags.items()} == {mario: None, anna: "T"}
    with pytest.raises(UserOnHold):
        vertex.resolve_user("cid-b")

    # Past the gate her state is on disk, her row has left the process, and her
    # placement is nobody's: where she wakes is the vertex's to say.
    parked = await reception.connector.call(EXECUTE_ORDER, timeout=CALL_TIMEOUT)

    assert announced(parked) == ["user_frozen"]
    assert vertex.user_is_frozen(anna) is True
    assert group.user_worker_map[anna] is None
    assert reception.hosted_users == {mario}
    assert freezer.read_user_register_item(anna) is not None

    # 4. HER NEXT REQUEST WAKES HER, lazily: nothing woke her while she was away.
    woken = await serve(group, anna, "cid-b", "/orders", user_frozen=True)

    assert announced(woken) == ["user_adopted", "new_connection"]
    assert body_of(woken) == "GET /orders for anna"
    assert vertex.user_is_frozen(anna) is False
    assert freezer.read_user_register_item(anna) is None
    assert group.user_worker_map[anna] == reception.name
    assert reception.hosted_users == {mario, anna}

    # 5. THE POOL GROWS ON DEMAND. The machine's concession is measured at last,
    # and against it the reception reads 70% full — over what it may take with the
    # reserve it keeps for receiving whoever arrives unplaced. So a newcomer
    # nobody admits is refused, and the refusal rings the wake.
    group.memory_concession_bytes = TIGHT_CONCESSION_BYTES
    # The newcomer is a person the site has already baptised: reception-first
    # keeps a guest at the reception, so the one who takes the capacity walk is
    # an identity (doctrine of 2026-08-21).
    carla = known_at_the_vertex(vertex, "cid-c", "carla")
    assert group.get_occupancy_percent(reception.worker_snapshot) == 70.0
    with pytest.raises(AssignmentRefused, match="no worker of std admits him"):
        group.assign_user(carla)
    assert group.ping_now_event.is_set() is True

    await group.ping()

    assert sorted(group.worker_handler_map) == [f"{GROUP}_0001", f"{GROUP}_0002"]
    # His retry lands on the new one: same reading, different setpoint — the
    # reception has a reserve and the other has not.
    spare = group.worker_handler_map[f"{GROUP}_0002"]
    assert group.assign_user(carla) == spare.name
    served = await serve(group, carla, "cid-c", "/catalog")
    assert body_of(served) == f"GET /catalog for {carla}"
    assert spare.hosted_users == {carla}

    # 6. THE POOL SHRINKS BY WASTE. The machine grew — what ``need_resources``
    # asks the world for — so the share of the second one is capacity the
    # reception can absorb and still admit. The closure runs its six steps: the
    # order, the reply that carries everybody flagged, the drain, the process
    # ending BY ITSELF, the awaited end of its wire.
    group.memory_concession_bytes = ROOMY_CONCESSION_BYTES

    await group.check_occupancy(now=True)

    assert spare.state == "quitted"
    await wait_for(lambda: spare.process.poll() is not None, timeout=DEATH_TIMEOUT)
    assert spare.process.poll() == 0
    assert freezer.read_user_register_item(carla) is not None

    # And the round that reads that ended state takes it out of the group, with
    # the placements that pointed at it: her state is in the freezer, and her
    # next request will be told where to wake.
    await group.ping()

    assert list(group.worker_handler_map) == [f"{GROUP}_0001"]
    assert vertex.user_is_frozen(carla) is True
    assert group.user_worker_map[carla] is None

    # 7. A PROCESS DIES WILD, with two people on board, and the real clock is
    # running: nobody drives what follows.
    clock = asyncio.get_running_loop().create_task(vertex.heartbeat_loop())
    reception.process.kill()

    await wait_for(lambda: reception.state == "aborted", timeout=DEATH_TIMEOUT)
    # The end of the wire rang the wake, the round read the state, and the two on
    # board are purged whole — a process that went for reasons of its own leaves
    # nothing that can be trusted — while the frozen woman, who was on nobody's
    # board, is untouched. Left with no worker at all, the group brings a fresh
    # reception into being.
    await wait_for(
        lambda: f"order=start_worker subject={GROUP}_0003" in orders_text(story_root),
        timeout=DEATH_TIMEOUT,
    )
    clock.cancel()

    assert list(group.worker_handler_map) == [f"{GROUP}_0003"]

    assert mario not in vertex.user_map
    assert anna not in vertex.user_map
    assert vertex.connection_user_map == {"cid-c": carla}
    assert group.user_worker_map == {carla: None}
    assert vertex.user_is_frozen(carla) is True
    assert freezer.user_folders == {freezer.user_to_userkey(carla)}
    assert group.reception is group.worker_handler_map[f"{GROUP}_0003"]
    assert group.state == "running"

    # THE ACCOUNT OF THE DAY. One row per order, on the file the config file
    # named: who decided, what, on whom, with which numbers, how it ended.
    orders = orders_of(story_root)
    # The share each of the two read when the closure was decided, as the group
    # itself computes it: the row carries the number, not a rounding of it.
    closed_occupancy = group.get_occupancy_percent({"rss_bytes": STORY_RSS_BYTES})

    assert [row for row in orders if "order=start_worker" in row] == [
        f"std order=start_worker subject={GROUP}_0001 numbers={{'workers': 1}} outcome=None",
        f"std order=start_worker subject={GROUP}_0002 numbers={{'workers': 2}} outcome=None",
        f"std order=start_worker subject={GROUP}_0003 numbers={{'workers': 1}} outcome=None",
    ]
    assert [row for row in orders if "order=close_worker" in row] == [
        f"std order=close_worker subject={GROUP}_0002 "
        f"numbers={{'occupancy_percent': {closed_occupancy}, 'workers': 2}} outcome=None"
    ]
    assert [row for row in orders if "order=drop_worker" in row] == [
        f"std order=drop_worker subject={GROUP}_0002 numbers=None outcome=quitted",
        f"std order=drop_worker subject={GROUP}_0001 numbers=None outcome=aborted",
    ]
    assert sorted(row for row in orders if "order=drop_user" in row) == [
        f"vertex order=drop_user subject={anna} numbers={{'had_state': False}} "
        "outcome=process_aborted",
        f"vertex order=drop_user subject={mario} numbers={{'had_state': False}} "
        "outcome=process_aborted",
    ]
