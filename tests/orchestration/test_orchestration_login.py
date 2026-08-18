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

"""The login: what the site's call changes at once, and what the call's tail does.

The story in one line: a visitor browses as a guest and his store fills up; he
logs in and the connection changes owner IN THAT INSTANT, because the caller
reads the row back in the same breath; the request goes on being served under the
new identity; and only when the call is over does the connection travel to the
deposit, carrying what the guest had accumulated. His next request — wherever the
pool puts him — finds it.

The deposit is a real ``FreezeHandler`` on a real directory: what a login leaves
on disk is the whole point, and a fake filesystem would judge nothing.
"""

from __future__ import annotations

import time

import pytest
from genro_bag import Bag

from genro_asgi.spa.orchestration import FreezeHandler, SpaCommander, SpaWorker
from genro_asgi.spa.orchestration.spa_worker import GUEST_PREFIX

WORKER_NAME = "standard_0001"


@pytest.fixture
def deposit(tmp_path):
    return FreezeHandler(tmp_path / "frozen_users")


@pytest.fixture
def worker(deposit):
    return SpaWorker(WORKER_NAME, freeze_handler=deposit, deposit_lock_retry_interval=0.01)


def browsing_guest(worker: SpaWorker, cid: str = "a1b2", pages: int = 1) -> str:
    """A visitor who arrived anonymous, opened a page and filled his store a little."""
    worker.add_connection(cid)
    guest = f"{GUEST_PREFIX}{cid}"
    for index in range(pages):
        worker.add_page(f"page-{index}", cid)
    worker.user_register[guest]["store"]["cart.item"] = "a lamp"
    return guest


def events_of(worker: SpaWorker, op: str) -> list[dict]:
    """The announcements of one kind this worker has ready to send."""
    return [event for event in worker.worker_events if event["op"] == op]


# -- what the call sees, in the instant of the login --


async def test_the_connection_changes_owner_in_the_same_breath(worker):
    guest = browsing_guest(worker)

    worker.relabel_connection("a1b2", "mario", user_tags="admin")

    # The caller reads the row back at once and must see the new identity.
    assert worker.connection_register["a1b2"]["user"] == "mario"
    assert worker.connection_register["a1b2"]["user_tags"] == "admin"
    assert worker.user_register["mario"]["connections"] == {"a1b2"}
    assert worker.user_register[guest]["connections"] == set()
    # The pages were not touched: their owner is derived through the connection.
    assert worker.page_register["page-0"]["connection_id"] == "a1b2"
    assert worker._page_user("page-0") == "mario"


async def test_the_new_identity_is_born_empty(worker):
    browsing_guest(worker)

    worker.relabel_connection("a1b2", "mario")

    assert worker.user_register["mario"]["store"] == Bag()


async def test_nobody_logs_in_as_a_guest(worker):
    browsing_guest(worker)

    with pytest.raises(ValueError):
        worker.relabel_connection("a1b2", "guest_somebody")


async def test_a_connection_this_worker_never_saw_is_loud(worker):
    with pytest.raises(KeyError):
        worker.relabel_connection("nobody", "mario")


async def test_the_departure_promised_to_the_guest_is_dropped(worker):
    """A guest that is ceasing to exist is not carried to the deposit."""
    guest = browsing_guest(worker)
    worker.plan_transfers(transfer_users=[guest])

    worker.relabel_connection("a1b2", "mario")

    assert worker._transfer_flags == {}


async def test_the_login_travels_on_the_reply(worker):
    guest = browsing_guest(worker)

    worker.relabel_connection("a1b2", "mario")

    assert events_of(worker, "connection_relabeled") == [
        {
            "op": "connection_relabeled",
            "worker": WORKER_NAME,
            "user": "mario",
            "previous_user": guest,
            "session_id": "a1b2",
        }
    ]


async def test_a_login_makes_the_photo_due(worker):
    """The population is a list of NAMES, and the login changes which names.

    The count does not move — a guest goes, a person arrives — but a stale photo
    would name somebody who no longer exists and miss somebody who does, and every
    reader of that photo hangs on the names: the flagged are held by name, a death
    is settled by intersecting names, the estimate is divided over them.
    """
    browsing_guest(worker)
    # A photo just sent and nothing changed since: the ONLY thing that can make
    # one due now is the population, which is what this test is about.
    worker._population_changed = False
    worker._snapshot_sent_ts = time.time()
    assert worker._snapshot_due is False

    worker.relabel_connection("a1b2", "mario")

    assert worker._snapshot_due is True


# -- what the tail of the call does --


async def test_nothing_leaves_before_the_call_is_over(worker, deposit):
    browsing_guest(worker)
    worker.open_request("guest_a1b2")

    worker.relabel_connection("a1b2", "mario")

    # Mid-call the rows are all still here: the site goes on serving under the
    # new identity, and the deposit has seen nothing.
    assert "a1b2" in worker.connection_register
    assert deposit.user_folders == set()


async def test_the_tail_carries_the_connection_and_the_guests_store(worker, deposit):
    guest = browsing_guest(worker)

    worker.relabel_connection("a1b2", "mario")
    assert await worker.freeze_connection("a1b2") is True

    # On disk, under the identity he logged in as.
    parcel = deposit.read_connection_register_item("mario", "a1b2")
    assert parcel["store"]["cart.item"] == "a lamp"
    assert set(parcel["pages"]) == {"page-0"}
    # And nothing of them is left in memory — the guest included.
    assert "a1b2" not in worker.connection_register
    assert "page-0" not in worker.page_register
    assert guest not in worker.user_register
    assert "mario" not in worker.user_register


async def test_an_avatar_switch_carries_no_store(worker, deposit):
    """A real identity is not a guest: what is his stays his."""
    worker.add_connection("a1b2", "mario")
    worker.add_page("page-0", "a1b2")
    worker.add_connection("c3d4", "mario")
    worker.user_register["mario"]["store"]["cart.item"] = "a lamp"

    worker.relabel_connection("a1b2", "carlo")
    assert await worker.freeze_connection("a1b2") is True

    parcel = deposit.read_connection_register_item("carlo", "a1b2")
    assert "store" not in parcel
    # He kept his other connection, so he is still here with his store.
    assert worker.user_register["mario"]["store"]["cart.item"] == "a lamp"


async def test_a_deposit_that_refuses_leaves_everything_alive(worker, monkeypatch):
    guest = browsing_guest(worker)
    worker.relabel_connection("a1b2", "mario")

    def refuse(*args, **kwargs):
        raise OSError("the disk is full")

    monkeypatch.setattr(worker.freeze_handler, "write_connection_register_item", refuse)

    assert await worker.freeze_connection("a1b2") is False

    # The legitimate degraded shape: he is resident here with his connection.
    assert worker.connection_register["a1b2"]["user"] == "mario"
    assert "mario" in worker.user_register
    assert guest in worker.user_register
    assert worker.freeze_failures == 1
    assert events_of(worker, "user_frozen") == []


# -- what the next request finds, wherever the pool puts him --


async def test_the_guests_store_becomes_his_own_on_a_row_just_born(worker, deposit):
    browsing_guest(worker)
    worker.relabel_connection("a1b2", "mario")
    await worker.freeze_connection("a1b2")

    await worker.adopt_connection("mario", "a1b2")

    assert worker.user_register["mario"]["store"]["cart.item"] == "a lamp"
    assert "page-0" in worker.page_register


async def test_a_resident_keeps_his_own_store_and_the_guests_dies(worker, deposit):
    """The RESIDENT wins, applied where the resident is."""
    browsing_guest(worker)
    worker.relabel_connection("a1b2", "mario")
    await worker.freeze_connection("a1b2")
    # He is already living here under another connection of his own.
    worker.add_connection("c3d4", "mario")
    worker.user_register["mario"]["store"]["cart.item"] = "his own lamp"

    await worker.adopt_connection("mario", "a1b2")

    assert worker.user_register["mario"]["store"]["cart.item"] == "his own lamp"


async def test_the_user_parcel_is_installed_before_the_connection_one(worker, deposit):
    """THE RATIFIED INVARIANT — it is what makes the resident win on a wake.

    A user whose own state was in the freezer comes home FIRST; only then is the
    connection installed, and the store it carries meets a row that is already
    full and dies. Inverting the two would let a login's leftovers overwrite days
    of hibernated state. A failure here is a STOP, never a test to adapt.
    """
    browsing_guest(worker)
    worker.relabel_connection("a1b2", "mario")
    await worker.freeze_connection("a1b2")
    deposit.take_lock("mario", "standard_0002")
    hibernated = Bag()
    hibernated["cart.item"] = "what he had before"
    deposit.write_user_register_item(
        "mario", hibernated, writer="standard_0002", cause="freeze", group="standard"
    )
    deposit.release_lock("mario", "standard_0002")

    await worker._resolve_row("mario", "a1b2", {"user_frozen": True, "http": {}})

    assert worker.user_register["mario"]["store"]["cart.item"] == "what he had before"


# -- what the vertex folds --


async def test_the_fold_repoints_the_cookie_and_forgets_the_guest(tmp_path):
    vertex = SpaCommander(tmp_path / "frozen_users")
    guest = vertex.resolve_user("a1b2")

    vertex.relabel_connection("a1b2", "mario", guest)

    assert vertex.connection_user_map["a1b2"] == "mario"
    assert "mario" in vertex.user_map
    assert guest not in vertex.user_map


async def test_the_fold_keeps_a_real_previous_identity(tmp_path):
    vertex = SpaCommander(tmp_path / "frozen_users")
    vertex.connection_user_map["a1b2"] = "mario"
    vertex.resolve_user("a1b2")

    vertex.relabel_connection("a1b2", "carlo", "mario")

    assert vertex.connection_user_map["a1b2"] == "carlo"
    assert "mario" in vertex.user_map


async def test_the_handler_swaps_who_it_holds(tmp_path):
    """A death between the login and the tail must not report a guest nobody knows."""
    from genro_asgi.spa.orchestration import GroupHandler
    from genro_asgi.spa.orchestration.worker_handler import WorkerHandler

    vertex = SpaCommander(tmp_path / "frozen_users")
    group = GroupHandler(
        vertex,
        "standard",
        memory_concession_bytes=1_000_000,
        instance_dir=tmp_path / "i",
        frozen_users_path=tmp_path / "frozen_users",
        entry_module="never.launched",
    )
    worker_handler = WorkerHandler(group, "standard_0001", **group.worker_settings)
    worker_handler.read_envelope(
        {"worker_events": [{"op": "new_user", "worker": "standard_0001", "user": "guest_a1b2"}]}
    )

    worker_handler.read_envelope(
        {
            "worker_events": [
                {
                    "op": "connection_relabeled",
                    "worker": "standard_0001",
                    "user": "mario",
                    "previous_user": "guest_a1b2",
                    "session_id": "a1b2",
                }
            ]
        }
    )

    assert worker_handler.hosted_users == {"mario"}
