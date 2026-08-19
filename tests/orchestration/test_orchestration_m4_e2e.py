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

"""Macro 4 end to end: a whole day of a site, entered through the front.

The story of Macro 3 told the pool's day from the inside, with the test standing
in for the request chain that did not exist yet. This one is the same day one rung
up: NOTHING stands in for the chain any more. A recipe on disk builds a real
``AsgiServer``; its lifespan builds the pool and starts the reception; and every
click of this story is an ASGI request through the server's own door, answered by
a REAL child process running a REAL WSGI site over a real Unix socket.

**What the story looks at is the site's own answer.** The store lives inside the
child and no assertion can reach it, so the site writes the trail of the paths it
has served into ``user_register[identity]["store"]`` and renders it back —
identity and content, in the body. Proving the store that way proves the whole
road it travelled (``freeze_connection`` → the parcel on disk → ``adopt_user`` /
``adopt_connection`` → the install at the destination), not that a dictionary has
a key.

The day, in order:

1. **The server starts from the recipe.** Two groups are declared and the base
   one is ELECTED — it is not the first declared, so the election is proved by the
   file and not by the order of writing. Only the elected group has a reception.
2. **A visitor arrives with no cookie.** He is served, the front coins his cookie,
   and every click adds to the store of the guest he was minted as.
3. **He logs in.** The site calls the login verb in-process, the way the
   genropy-asgi bridge does, and the request goes on being served.
4. **His next click finds his store**, under his real name now: what he
   accumulated as a guest travelled inside the connection's parcel and was
   installed where the pool put him. (R3/R5, proved AT THE DESTINATION.)
5. **Somebody goes quiet and is parked.** The driver's two orders flag her and
   let her go — no clock calls them yet — and her own next click wakes her, with
   the trail she left behind her.
6. **The pool grows, and stickiness is proved on two workers.** The concession
   shrinks until the reception refuses, a shape step brings a second process into
   being, and a SECOND browser of the same person lands on it as a guest. When he
   logs in, his next click is answered by the FIRST worker, where that person
   lives, carrying that person's trail and not the guest's — the connection
   travelled, and the carried store lost to the resident, which is the invariant
   of R5.
7. **An avatar switch keeps the two apart.** The same connection logs in as
   another real identity: the new one starts with an empty store, while the other
   browser of the first identity still renders his.
8. **A pool with no room is a polite 503.** The concession shrinks past what the
   two processes hold, so nobody admits AND the growth is refused: a newcomer gets
   a 503 with the ``Retry-After`` the vertex composed, and the residents keep being
   served.

The clock stays alive — the beat keeps the processes answered, the frozen swept
and the expired dropped — but the SHAPE steps are driven where the story wants
them, by raising the cadence of ``GroupHandler.check_occupancy`` and asking for it
by hand. Its wake still overrides the cadence, which is why the refusal of the
last chapter rests on the memory gate: a pool that cannot grow, and not a round
that has not arrived.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any

import pytest

from genro_asgi import AsgiServer
from genro_asgi.applications.spa_app_new import STICKY_CID_COOKIE
from genro_asgi.spa.orchestration import GroupHandler
from genro_asgi.spa.orchestration.spa_commander import GUEST_PREFIX

from ..conftest import LifespanRunner, ask_app, get_answer_header
from .x_spa_worker import EXECUTE_ORDER, PLAN_ORDER, X_SpaWorker

#: The front that owns the pool of this story, and its two groups: the one the
#: recipe ELECTS, and one declared before it so the election says something.
APP_CODE = "shop"
BASE_GROUP = "std"
OTHER_GROUP = "alt"

ENTRY_MODULE = "genro_asgi.spa.orchestration.worker_entry"
STORY_WORKER = f"{__name__}:X_SpaWorker_m4"

#: The path the site reads as a login; what follows it is the identity.
LOGIN_PATH = "/login/"

#: The silence past which a worker parks a user, as the recipe declares it, and
#: the gate the departures wait out — both shrunk to fractions of a second.
IDLE_SECONDS = 0.5
IDLE_MINUTES = IDLE_SECONDS / 60
GATE_DELAY = 0.3

#: What every child of this story declares it holds, and the three concessions the
#: story reads it against: roomy while the day is ordinary; 100 MB, where the
#: reception stands at 70% against a cap of 30 and the growth is still afforded;
#: 85 MB, where two processes hold 164% of the concession and nothing can grow.
STORY_RSS_BYTES = 70_000_000
GROWTH_CONCESSION_BYTES = 100_000_000
FULL_CONCESSION_BYTES = 85_000_000

#: What the vertex tells a refused browser to wait: the beat times the beats
#: between two readings of the shape.
RETRY_AFTER = "30"

CALL_TIMEOUT = 10.0

#: Mario's whole day by the sixth chapter, in the order he lived it: two pages as
#: a guest, the login that was still served under that guest, then everything he
#: did once the store had come home to his own name.
MARIO_TRAIL = f"/catalog /catalog/lamps {LOGIN_PATH}mario /orders /orders /orders/9"

POOL_CONFIG = '''
"""The pool of the story, as an installation writes it."""

from genro_asgi.applications.spa_app_new import SpaApplicationNew
from genro_asgi.config import AsgiConfigBuilder


class ServerConfiguration(AsgiConfigBuilder):
    """One front, its commander, two groups, and the child that runs in them."""

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
            user_expiry_hours=240.0,
            guest_expiry_hours=6.0,
        )
        groups = commander.groups(default="{base_group}")
        for name in ("{other_group}", "{base_group}"):
            groups.group(
                name=name,
                occupancy_max_percent=80.0,
                restart_occupancy_max_percent=95.0,
                reception_reserved_percent=50.0,
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


class X_SpaWorker_m4(X_SpaWorker):
    """The worker of the story: the shared instrumentation, and a site that remembers.

    The site keeps a TRAIL in the store of whoever it is serving — one word per
    path — and renders it with the identity it was served under. That is the only
    window this test has on what lives inside the process, and it is the same
    window a browser has.

    ``/login/<identity>`` is the login of this site: it calls the verb the
    genropy-asgi bridge calls, in-process and in the middle of the request, and
    reads the connection out of the cookie exactly where a real site reads it.
    """

    def site(self, environ: dict[str, Any], start_response: Any) -> list[bytes]:
        """Serve one page: log in when asked, add to the trail, render it back."""
        identity = environ["genro.identity"]
        path = environ["PATH_INFO"]
        if path.startswith(LOGIN_PATH):
            self.relabel_connection(cid_of(environ), path[len(LOGIN_PATH) :])
        with self.dispatch_lock:
            store = self.user_register[identity]["store"]
            store["trail"] = f"{store['trail'] or ''}{path} "
            trail = store["trail"]
        start_response("200 OK", [("Content-Type", "text/plain"), ("X-Worker", self.name)])
        return [f"{identity}|{trail}".encode()]


def cid_of(environ: dict[str, Any]) -> str:
    """The connection a request belongs to, read where a real site reads it."""
    return SimpleCookie(environ.get("HTTP_COOKIE", ""))[STICKY_CID_COOKIE].value


async def browse(server: AsgiServer, path: str, cid: str | None = None) -> dict[str, Any]:
    """One click of a browser: the cookie it carries, and the answer it gets."""
    return await ask_app(server, path, cookies={STICKY_CID_COOKIE: cid} if cid else None)


def minted_cid(answer: dict[str, Any]) -> str:
    """The cid the front has just coined, out of the cookie it stamped.

    Args:
        answer: what a click got back.

    Returns:
        The value of the ``sticky_cid`` the front minted.

    Raises:
        AssertionError: this answer stamped none.
    """
    for name, value in answer["headers"]:
        if name.lower() == "set-cookie" and value.startswith(f"{STICKY_CID_COOKIE}="):
            return str(SimpleCookie(value)[STICKY_CID_COOKIE].value)
    raise AssertionError("the answer carries no sticky cid")


def served_by(answer: dict[str, Any]) -> str | None:
    """Which process answered, as the site itself declares it."""
    return get_answer_header(answer, "x-worker")


def identity_of(answer: dict[str, Any]) -> str:
    """The identity the site was serving when it answered."""
    return answer["body"].decode().partition("|")[0]


def trail_of(answer: dict[str, Any]) -> str:
    """The paths the store of that identity remembers, oldest first."""
    return answer["body"].decode().partition("|")[2].strip()


@pytest.fixture
def story_root(repo_on_pythonpath):
    """The short root holding the recipe, the sockets and the freezer."""
    root = Path(tempfile.mkdtemp(prefix="gnrm4_"))
    (root / "pool_config.py").write_text(
        POOL_CONFIG.format(
            root=root,
            app_code=APP_CODE,
            base_group=BASE_GROUP,
            other_group=OTHER_GROUP,
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
async def server(story_root, monkeypatch):
    """The server of the recipe, up through its own lifespan and down after."""
    # The beat stays alive; only the reading of the SHAPE is taken out of its
    # hands, so the two chapters that need a shape step ask for it themselves.
    monkeypatch.setattr(GroupHandler.check_occupancy, "every_beats", 10_000)
    asgi_server = AsgiServer(config=story_root / "pool_config.py")
    runner = LifespanRunner(asgi_server)
    await runner.startup()
    yield asgi_server
    await runner.shutdown()


async def test_a_day_of_the_site_from_the_front_to_the_child(server):
    front = server.applications[APP_CODE]
    vertex = front.commander
    group = vertex.group_map[BASE_GROUP]

    # 1. THE SERVER STARTS FROM THE RECIPE. The elected group is not the first
    # declared, and it is the only one with a reception: the other exists, empty.
    assert list(vertex.group_map) == [OTHER_GROUP, BASE_GROUP]
    assert vertex.default_group == BASE_GROUP
    assert list(group.worker_handler_map) == [f"{BASE_GROUP}_0001"]
    assert vertex.group_map[OTHER_GROUP].worker_handler_map == {}
    reception = group.reception

    # 2. A VISITOR ARRIVES WITH NO COOKIE. The front coins one, the vertex mints
    # him a guest, and his store grows click by click.
    first = await browse(server, "/catalog")
    cid = minted_cid(first)
    guest = f"{GUEST_PREFIX}{cid}"

    assert identity_of(first) == guest
    assert vertex.connection_user_map[cid] == guest
    assert group.user_worker_map[guest] == reception.name
    assert trail_of(await browse(server, "/catalog/lamps", cid)) == "/catalog /catalog/lamps"

    # 3. HE LOGS IN, in the middle of a request the site is serving.
    logged = await browse(server, f"{LOGIN_PATH}mario", cid)

    assert logged["status"] == 200
    assert vertex.connection_user_map[cid] == "mario"
    assert guest not in vertex.user_map

    # 4. HIS NEXT CLICK FINDS HIS STORE, under his real name: what he gathered as
    # a guest travelled in the connection's parcel and was installed at the
    # destination, which is the only place R5 can be proved.
    back = await browse(server, "/orders", cid)

    assert identity_of(back) == "mario"
    assert trail_of(back) == f"/catalog /catalog/lamps {LOGIN_PATH}mario /orders"

    # 5. SOMEBODY GOES QUIET AND IS PARKED. Anna arrives, logs in, clicks once so
    # she is resident, and then falls silent past the recipe's own silence.
    anna_first = await browse(server, "/invoices")
    anna_cid = minted_cid(anna_first)
    await browse(server, f"{LOGIN_PATH}anna", anna_cid)
    await browse(server, "/invoices/7", anna_cid)

    await asyncio.sleep(2 * IDLE_SECONDS)
    await browse(server, "/orders", cid)            # mario has just spoken
    planned = await reception.connector.call(PLAN_ORDER, timeout=CALL_TIMEOUT)
    flags = planned["worker_snapshot"]["users"]

    assert {user: row["transfer_flag"] for user, row in flags.items()} == {
        "mario": None,
        "anna": "T",
    }

    await reception.connector.call(EXECUTE_ORDER, timeout=CALL_TIMEOUT)

    assert vertex.user_is_frozen("anna") is True
    assert group.user_worker_map["anna"] is None

    # Her own next click wakes her, and the trail is where she left it.
    woken = await browse(server, "/invoices/8", anna_cid)

    assert vertex.user_is_frozen("anna") is False
    assert trail_of(woken) == f"/invoices {LOGIN_PATH}anna /invoices/7 /invoices/8"

    # 6. THE POOL GROWS, AND STICKINESS IS PROVED ON TWO WORKERS. Against a
    # hundred megabytes the reception stands at 70% with a cap of 30 and takes
    # nobody, while the memory still affords one more process.
    group.memory_concession_bytes = GROWTH_CONCESSION_BYTES

    await group.check_occupancy(now=True)
    spare = group.worker_handler_map[f"{BASE_GROUP}_0002"]

    assert group.get_occupancy_percent(reception.worker_snapshot) == 70.0
    assert group.get_worker_cap(reception) == 30.0

    # A second browser of the same person arrives as a stranger and lands on the
    # new process, because the reception has no room for him.
    joining = await browse(server, "/joining")
    second_cid = minted_cid(joining)

    assert served_by(joining) == spare.name
    assert trail_of(joining) == "/joining"

    await browse(server, f"{LOGIN_PATH}mario", second_cid)
    joined = await browse(server, "/orders/9", second_cid)

    # His connection travelled to where mario lives, and the store it carried lost
    # to the resident: the trail is mario's whole day, and the guest of this second
    # browser left no trace in it — the install of a carried store happens only on
    # a row just born, which is the invariant of R5.
    assert served_by(joined) == reception.name
    assert identity_of(joined) == "mario"
    assert trail_of(joined) == MARIO_TRAIL
    assert "/joining" not in trail_of(joined)
    assert group.user_worker_map["mario"] == reception.name

    # 7. AN AVATAR SWITCH KEEPS THE TWO APART. The first browser logs in again, as
    # another real person. The login itself is still served under mario — the site
    # was called for him — and it is the identity BORN of it that starts empty.
    await browse(server, f"{LOGIN_PATH}mario_admin", cid)
    switched = await browse(server, "/admin", cid)
    unmoved = await browse(server, "/orders/10", second_cid)

    assert identity_of(switched) == "mario_admin"
    assert trail_of(switched) == "/admin"
    assert served_by(switched) == spare.name        # a new identity, placed anew
    assert identity_of(unmoved) == "mario"
    assert trail_of(unmoved) == f"{MARIO_TRAIL} {LOGIN_PATH}mario_admin /orders/10"

    # 8. A POOL WITH NO ROOM IS A POLITE 503. Against eighty-five megabytes the
    # two processes hold more than the whole concession: nobody admits, and the
    # growth is refused instead of ordered.
    group.memory_concession_bytes = FULL_CONCESSION_BYTES

    await group.check_occupancy(now=True)
    refused = await browse(server, "/catalog")
    resident = await browse(server, "/orders/11", second_cid)

    assert group.state == "saturated"
    assert list(group.worker_handler_map) == [reception.name, spare.name]
    assert refused["status"] == 503
    assert get_answer_header(refused, "retry-after") == RETRY_AFTER
    assert STICKY_CID_COOKIE in (get_answer_header(refused, "set-cookie") or "")
    assert vertex.counters["requests_refused"] == 1
    assert resident["status"] == 200
    assert identity_of(resident) == "mario"
