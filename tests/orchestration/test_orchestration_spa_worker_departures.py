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

"""SpaWorker tests: how a user leaves — the flags, the gate, the valve, the quit.

The deposit is a real ``FreezeHandler`` on a real directory here too: a departure
is judged by what is on disk when it is over, and by the fact that the adoption
can read it back. The gate is watched with a delay shrunk to a tenth of a second
— the point being that it is waited for, not how long it is — and the clocks are
pushed into the past by hand, because idleness measured by really waiting would
make the suite sleep for the age it is meant to prove.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

WORKER_NAME = "standard_0001"
GROUP = "standard"
CLOCKS = ("last_refresh_ts", "last_user_ts", "last_rpc_ts")


class RefusingDeposit(FreezeHandler):
    """A real deposit whose disk has stopped taking writes."""

    def write_user_register_item(self, user, payload, **header):
        raise OSError("no space left on device")


@pytest.fixture
def deposit(tmp_path):
    return FreezeHandler(tmp_path / "frozen_users")


def build_worker(deposit, **kwargs):
    """A worker whose gate is short enough to watch inside a test."""
    kwargs.setdefault("transfer_start_delay", 0.1)
    return SpaWorker(
        WORKER_NAME,
        freeze_handler=deposit,
        group=GROUP,
        deposit_lock_retry_interval=0.01,
        **kwargs,
    )


@pytest.fixture
def worker(deposit):
    return build_worker(deposit)


def announced(worker):
    """The protocol names queued for the envelope out, in order."""
    return [event["op"] for event in worker.events]


def age_user(worker, user, seconds):
    """Push a user and everything under him that many seconds into the past."""
    item = worker.user_register[user]
    items = [item]
    for cid in item["connections"]:
        connection = worker.connection_register[cid]
        items.append(connection)
        items.extend(worker.page_register[page_id] for page_id in connection["pages"])
    for one in items:
        for clock in CLOCKS:
            one[clock] -= seconds


# ----------------------------------------------------------------------
# The flags: who is kept, who is ceded, who is expired
# ----------------------------------------------------------------------


def test_the_photo_pairs_every_user_with_his_flag(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.add_page("page-2", "cid-b", "anna")
    worker.add_page("page-3", "cid-c", "ugo")
    age_user(worker, "ugo", 3600)

    departures = worker.decide_departures(transfer_users=["mario"], expiry_delay=600)

    assert departures["mario"] == (worker.user_register["mario"], "T")
    assert departures["anna"] == (worker.user_register["anna"], None)
    assert departures["ugo"] == (worker.user_register["ugo"], "X")


def test_a_beat_does_not_save_an_expired_user(worker):
    worker.add_page("page-1", "cid-a", "mario")
    age_user(worker, "mario", 3600)
    worker.refresh_chain("page-1")

    departures = worker.decide_departures(expiry_delay=600)

    assert worker.user_register["mario"]["last_refresh_ts"] > time.time() - 1
    assert departures["mario"][1] == "X"


def test_a_real_call_saves_the_user_the_beat_could_not(worker):
    worker.add_page("page-1", "cid-a", "mario")
    age_user(worker, "mario", 3600)
    worker.refresh_chain("page-1", "last_rpc_ts")

    departures = worker.decide_departures(transfer_users=[], expiry_delay=600)

    assert departures["mario"][1] is None


async def test_a_frozen_row_is_left_to_the_vertex(worker):
    worker.add_page("page-1", "cid-a", "mario")
    await worker.freeze_user("mario", placement=WORKER_NAME)
    age_user(worker, "mario", 3600)

    departures = worker.decide_departures(transfer_users=["mario"], expiry_delay=600)

    assert worker.user_register["mario"]["state"] == "frozen"
    assert departures["mario"][1] is None


# ----------------------------------------------------------------------
# The gate: nothing departs in the turn it was announced
# ----------------------------------------------------------------------


async def test_the_gate_holds_the_departure_until_its_delay_has_passed(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.decide_departures(transfer_users=["mario"])
    departure = asyncio.ensure_future(worker.execute_departures())

    await asyncio.sleep(worker.transfer_start_delay / 4)
    still_here = "mario" in worker.user_register
    await departure

    assert still_here
    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None


async def test_a_ceded_user_leaves_with_his_placement_to_be_assigned(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    worker.decide_departures(transfer_users=["mario"])

    await worker.execute_departures()

    assert announced(worker) == ["user_frozen"]
    assert worker.events[0] == {
        "op": "user_frozen",
        "worker": WORKER_NAME,
        "user": "mario",
        "placement": None,
    }
    assert worker.connection_register == {}
    assert worker.page_register == {}


async def test_the_expired_are_dropped_with_their_announcements(worker, deposit):
    worker.add_page("page-1", "cid-a", "ugo")
    age_user(worker, "ugo", 3600)
    worker.events.clear()
    worker.decide_departures(expiry_delay=600)

    await worker.execute_departures()

    assert announced(worker) == ["drop_pages", "drop_connections", "drop_user"]
    assert "ugo" not in worker.user_register
    assert deposit.user_folders == set()


# ----------------------------------------------------------------------
# The end of a call is where a deferred departure happens
# ----------------------------------------------------------------------


async def test_a_call_in_flight_defers_the_departure_to_its_end(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    worker.decide_departures(transfer_users=["mario"])

    await worker.execute_departures()

    assert "mario" in worker.user_register
    assert deposit.read_user_register_item("mario") is None

    await worker.close_request("mario")

    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None
    assert "user_frozen" in announced(worker)


async def test_the_departure_waits_for_the_last_of_several_calls(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    worker.open_request("mario")
    worker.decide_departures(transfer_users=["mario"])
    await worker.execute_departures()

    await worker.close_request("mario")
    assert "mario" in worker.user_register

    await worker.close_request("mario")
    assert "mario" not in worker.user_register


async def test_a_call_closing_before_the_gate_takes_nobody_away(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    worker.decide_departures(transfer_users=["mario"])

    await worker.close_request("mario")

    assert "mario" in worker.user_register
    assert "user_frozen" not in announced(worker)


async def test_a_call_closing_on_a_user_nobody_asked_for_changes_nothing(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    worker.events.clear()

    await worker.close_request("mario")

    assert worker.user_register["mario"]["state"] == "active"
    assert announced(worker) == []


# ----------------------------------------------------------------------
# The valve: whoever only beats goes to sleep, and wakes where he left
# ----------------------------------------------------------------------


async def test_the_valve_parks_whoever_only_beats_and_spares_the_active(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-idle", "cid-idle", "mario")
    worker.add_page("page-live", "cid-live", "anna")
    age_user(worker, "mario", 60)
    worker.refresh_chain("page-idle")
    worker.events.clear()

    await worker.freeze_idle_users()

    assert worker.user_register["mario"]["state"] == "frozen"
    assert worker.user_register["anna"]["state"] == "active"
    assert worker.connection_register.keys() == {"cid-live"}
    assert worker.events == [
        {
            "op": "user_frozen",
            "worker": WORKER_NAME,
            "user": "mario",
            "placement": WORKER_NAME,
        }
    ]

    await worker.freeze_idle_users()

    assert len(worker.events) == 1


async def test_the_valve_leaves_the_row_ready_to_wake_in_place(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-1", "cid-a", "mario")
    worker.user_register["mario"]["store"]["cart.total"] = 12
    age_user(worker, "mario", 60)

    await worker.freeze_idle_users()
    assert len(worker.user_register["mario"]["store"]) == 0

    item = await worker.adopt_user("mario")
    connection = await worker.adopt_connection("mario", "cid-a")

    assert item["state"] == "active"
    assert item["store"]["cart.total"] == 12
    assert connection["pages"] == {"page-1"}
    assert deposit.user_folders == set()


async def test_the_valve_leaves_alone_whoever_has_a_call_in_flight(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-1", "cid-a", "mario")
    age_user(worker, "mario", 60)
    worker.open_request("mario")

    await worker.freeze_idle_users()

    assert worker.user_register["mario"]["state"] == "active"


# ----------------------------------------------------------------------
# What the freeze writes, the adoption reads back
# ----------------------------------------------------------------------


async def test_what_the_freeze_writes_the_adoption_reads_back(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.add_page("page-2", "cid-a")
    worker.user_register["mario"]["store"]["cart.total"] = 12
    human_event = worker.refresh_chain("page-1", "last_user_ts")

    assert await worker.freeze_user("mario")
    assert (worker.user_register, worker.connection_register, worker.page_register) == (
        {},
        {},
        {},
    )

    item = await worker.adopt_user("mario")
    connection = await worker.adopt_connection("mario", "cid-a")

    assert item["store"]["cart.total"] == 12
    assert connection["user"] == "mario"
    assert connection["pages"] == {"page-1", "page-2"}
    assert connection["last_user_ts"] == human_event
    assert worker.page_register["page-1"]["last_user_ts"] == human_event
    assert worker.page_register["page-2"]["connection_id"] == "cid-a"
    assert deposit.user_folders == set()


# ----------------------------------------------------------------------
# The deposit that refuses: nobody is killed who could not be saved
# ----------------------------------------------------------------------


async def test_a_deposit_that_refuses_leaves_the_user_alive(tmp_path):
    deposit = RefusingDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()

    frozen = await worker.freeze_user("mario")

    assert frozen is False
    assert worker.user_register["mario"]["state"] == "active"
    assert worker.connection_register["cid-a"]["pages"] == {"page-1"}
    assert announced(worker) == []
    assert worker.freeze_failures == 1
    assert deposit.lock_holder("mario") is None
    assert deposit.user_folders == set()


async def test_a_refused_departure_does_not_keep_coming_back(tmp_path):
    deposit = RefusingDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.decide_departures(transfer_users=["mario"])

    await worker.execute_departures()
    worker.open_request("mario")
    await worker.close_request("mario")

    assert worker.user_register["mario"]["state"] == "active"
    assert worker.freeze_failures == 1


# ----------------------------------------------------------------------
# The mass cycle and the quit
# ----------------------------------------------------------------------


async def test_the_mass_cycle_gives_the_loop_back_between_two_users(worker, deposit):
    for number in range(4):
        worker.add_page(f"page-{number}", f"cid-{number}", f"user-{number}")
    ticks = 0

    async def watch():
        nonlocal ticks
        while True:
            await asyncio.sleep(0)
            ticks += 1

    watcher = asyncio.ensure_future(watch())
    await worker.freeze_all_users()
    watcher.cancel()

    assert worker.user_register == {}
    assert len(deposit.user_folders) == 4
    assert ticks >= 3


async def test_quit_parks_everybody_and_reaches_the_exit(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.add_page("page-2", "cid-b", "anna")
    worker.events.clear()

    await worker.quit()

    assert worker.exited
    assert worker.user_register == {}
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_user_register_item("anna") is not None
    assert announced(worker) == ["user_frozen", "user_frozen"]
    assert all(event["placement"] is None for event in worker.events)


async def test_quit_drops_the_expired_instead_of_parking_them(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.add_page("page-2", "cid-b", "ugo")
    age_user(worker, "ugo", 3600)

    await worker.quit(expiry_delay=600)

    assert worker.exited
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.user_folders == {deposit.user_to_userkey("mario")}


async def test_quit_does_not_leave_while_a_call_is_in_flight(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    leaving = asyncio.ensure_future(worker.quit())

    await asyncio.sleep(worker.transfer_start_delay * 3)
    still_here = not worker.exited
    await worker.close_request("mario")
    await leaving

    assert still_here
    assert worker.exited
    assert worker.user_register == {}
