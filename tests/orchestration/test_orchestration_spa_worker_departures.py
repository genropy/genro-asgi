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

Three deposits are played against here besides the plain one: one that refuses
every write, one whose disk takes a visible half second to answer, and — through
a semaphore taken by a name that is not this worker's — one whose folder is
simply not available. What they are for is what happens on the loop MEANWHILE.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

import pytest

from genro_asgi.spa.orchestration import FreezeHandler, SpaWorker

WORKER_NAME = "standard_0001"
OTHER_WORKER = "standard_0002"
GROUP = "standard"
CLOCKS = ("last_refresh_ts", "last_user_ts", "last_rpc_ts")


class RefusingDeposit(FreezeHandler):
    """A real deposit whose disk has stopped taking writes."""

    def write_user_register_item(self, user, payload, **header):
        raise OSError("no space left on device")


class BreakingDeposit(FreezeHandler):
    """A deposit that goes wrong where the departure catches nothing: on the way out."""

    def release_lock(self, user, holder):
        raise RuntimeError("the semaphore file vanished under us")


class SlowDeposit(FreezeHandler):
    """A real deposit whose disk takes a visible moment to take a store.

    ``STALL`` is long enough that anything waiting behind it is unmistakable in
    a measurement, and ``writing`` says when the wait has really begun — the
    write runs on the service pool, so the flag is read from the loop.
    """

    STALL = 0.5

    def __init__(self, root_path):
        super().__init__(root_path)
        self.writing = threading.Event()

    def write_user_register_item(self, user, payload, **header):
        self.writing.set()
        time.sleep(self.STALL)
        super().write_user_register_item(user, payload, **header)


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


async def wait_until(condition, timeout=5.0):
    """Give the loop back until something else has happened, or give up."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() >= deadline:
            raise TimeoutError("the departure never reached the awaited state")
        await asyncio.sleep(0.005)


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

    transfers = worker.plan_transfers(transfer_users=["mario"], expiry_delay=600)

    assert transfers["mario"] == (worker.user_register["mario"], "T")
    assert transfers["anna"] == (worker.user_register["anna"], None)
    assert transfers["ugo"] == (worker.user_register["ugo"], "X")


def test_a_beat_does_not_save_an_expired_user(worker):
    worker.add_page("page-1", "cid-a", "mario")
    age_user(worker, "mario", 3600)
    worker.refresh_chain("page-1")

    transfers = worker.plan_transfers(expiry_delay=600)

    assert worker.user_register["mario"]["last_refresh_ts"] > time.time() - 1
    assert transfers["mario"][1] == "X"


def test_a_real_call_saves_the_user_the_beat_could_not(worker):
    worker.add_page("page-1", "cid-a", "mario")
    age_user(worker, "mario", 3600)
    worker.refresh_chain("page-1", "last_rpc_ts")

    transfers = worker.plan_transfers(transfer_users=[], expiry_delay=600)

    assert transfers["mario"][1] is None


async def test_a_row_that_is_not_active_is_left_to_the_vertex(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.user_register["mario"]["state"] = "unfreezing"
    age_user(worker, "mario", 3600)

    transfers = worker.plan_transfers(transfer_users=["mario"], expiry_delay=600)

    assert transfers["mario"][1] is None
    assert worker.worker_snapshot["users"]["mario"]["transfer_flag"] is None


async def test_the_valve_is_one_more_reason_for_a_cession(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-idle", "cid-idle", "mario")
    worker.add_page("page-live", "cid-live", "anna")
    age_user(worker, "mario", 60)
    worker.refresh_chain("page-idle")

    transfers = worker.plan_transfers()

    assert transfers["mario"][1] == "T"
    assert transfers["anna"][1] is None


async def test_the_expiry_wins_over_the_valve_on_the_same_user(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-1", "cid-a", "mario")
    age_user(worker, "mario", 3600)

    transfers = worker.plan_transfers(expiry_delay=600)

    assert transfers["mario"][1] == "X"


# ----------------------------------------------------------------------
# The gate: nothing departs in the turn it was announced
# ----------------------------------------------------------------------


async def test_the_gate_holds_the_departure_until_its_delay_has_passed(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.plan_transfers(transfer_users=["mario"])
    transfer = asyncio.ensure_future(worker.execute_transfers())

    await asyncio.sleep(worker.transfer_start_delay / 4)
    still_here = "mario" in worker.user_register
    await transfer

    assert still_here
    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None


async def test_a_ceded_user_leaves_with_his_placement_to_be_assigned(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    worker.plan_transfers(transfer_users=["mario"])

    await worker.execute_transfers()

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
    worker.plan_transfers(expiry_delay=600)

    await worker.execute_transfers()

    assert announced(worker) == ["drop_pages", "drop_connections", "drop_user"]
    assert "ugo" not in worker.user_register
    assert deposit.user_folders == set()


# ----------------------------------------------------------------------
# The end of a call is where a deferred departure happens
# ----------------------------------------------------------------------


async def test_a_call_in_flight_defers_the_departure_to_its_end(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    worker.plan_transfers(transfer_users=["mario"])

    await worker.execute_transfers()

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
    worker.plan_transfers(transfer_users=["mario"])
    await worker.execute_transfers()

    await worker.close_request("mario")
    assert "mario" in worker.user_register

    await worker.close_request("mario")
    assert "mario" not in worker.user_register


async def test_a_call_closing_before_the_gate_takes_nobody_away(worker):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    worker.plan_transfers(transfer_users=["mario"])

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
# The valve: whoever only beats leaves by the common road
# ----------------------------------------------------------------------


async def test_the_valve_parks_whoever_only_beats_and_spares_the_active(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-idle", "cid-idle", "mario")
    worker.add_page("page-live", "cid-live", "anna")
    age_user(worker, "mario", 60)
    worker.refresh_chain("page-idle")
    worker.events.clear()

    worker.plan_transfers()
    await worker.execute_transfers()

    assert "mario" not in worker.user_register
    assert worker.user_register["anna"]["state"] == "active"
    assert worker.connection_register.keys() == {"cid-live"}
    assert worker.events == [
        {"op": "user_frozen", "worker": WORKER_NAME, "user": "mario", "placement": None}
    ]

    worker.plan_transfers()
    await worker.execute_transfers()

    assert len(worker.events) == 1


async def test_the_valve_leaves_nothing_of_him_behind(deposit):
    worker = build_worker(deposit, user_idle_freeze_delay=10)
    worker.add_page("page-1", "cid-a", "mario")
    worker.user_register["mario"]["store"]["cart.total"] = 12
    age_user(worker, "mario", 60)

    worker.plan_transfers()
    await worker.execute_transfers()
    assert worker.user_register == {}

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

    worker.plan_transfers()
    await worker.execute_transfers()

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
    worker.plan_transfers(transfer_users=["mario"])

    await worker.execute_transfers()
    worker.open_request("mario")
    await worker.close_request("mario")

    assert worker.user_register["mario"]["state"] == "active"
    assert worker.freeze_failures == 1


# ----------------------------------------------------------------------
# A row mid-adoption is nobody's to park
# ----------------------------------------------------------------------


async def test_a_row_being_adopted_is_not_parked_under_the_adoption(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    worker.user_register["mario"]["state"] = "unfreezing"

    assert await worker.freeze_user("mario") is False
    assert worker.user_register["mario"]["state"] == "unfreezing"
    assert announced(worker) == []
    assert deposit.read_user_register_item("mario") is None
    assert deposit.user_folders == set()


# ----------------------------------------------------------------------
# One departure at a time, and the disk held by nobody
# ----------------------------------------------------------------------


async def test_the_cycle_and_the_hook_never_park_the_same_user_twice(tmp_path):
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    worker.plan_transfers(transfer_users=["mario"])
    cycle = asyncio.ensure_future(worker.execute_transfers())
    await wait_until(deposit.writing.is_set)

    # A call opens and closes while his departure is already on the disk: the
    # hook finds it claimed and comes straight back, instead of queueing behind
    # a semaphore this worker itself is holding.
    worker.open_request("mario")
    await asyncio.wait_for(worker.close_request("mario"), SlowDeposit.STALL / 2)
    await cycle

    assert announced(worker) == ["user_frozen"]
    assert "mario" not in worker.user_register
    assert deposit.lock_holder("mario") is None


async def test_a_call_born_while_the_parcels_were_written_keeps_the_user(tmp_path):
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    worker.plan_transfers(transfer_users=["mario"])
    cycle = asyncio.ensure_future(worker.execute_transfers())
    await wait_until(deposit.writing.is_set)

    # His parcels are already going onto the disk when a call of his is born.
    # The question asked again when the write comes back is what takes them off
    # again and leaves him exactly as he was, flag included.
    worker.open_request("mario")
    await cycle

    assert worker.user_register["mario"]["state"] == "active"
    assert worker.connection_register["cid-a"]["pages"] == {"page-1"}
    assert worker.page_register.keys() == {"page-1"}
    assert announced(worker) == []
    assert deposit.read_user_register_item("mario") is None
    assert deposit.read_connection_register_item("mario", "cid-a") is None
    assert worker.worker_snapshot["users"]["mario"]["transfer_flag"] == "T"

    # And the tail of that very call is what parks him.
    await worker.close_request("mario")

    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None
    assert announced(worker) == ["user_frozen"]


async def test_the_parcels_are_photographed_before_the_disk_takes_them(tmp_path):
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.user_register["mario"]["store"]["cart.total"] = 12
    freezing = asyncio.ensure_future(worker.freeze_user("mario"))
    await wait_until(deposit.writing.is_set)

    # The disk is slow and the store is live. What a mutation writes now must
    # NOT reach the parcel: the deposit pickles on the service pool, with no
    # lock of the worker's, so what crosses over has to be a photograph.
    worker.user_register["mario"]["store"]["cart.total"] = 99

    assert await freezing is True
    assert deposit.read_user_register_item("mario")["cart.total"] == 12


async def test_the_mass_cycle_leaves_a_departure_already_under_way_to_whoever_has_it(
    tmp_path, caplog
):
    caplog.set_level(logging.WARNING)
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit, deposit_lock_wait_limit=SlowDeposit.STALL / 10)
    worker.add_page("page-1", "cid-a", "mario")
    worker.add_page("page-2", "cid-b", "anna")
    worker.plan_transfers(transfer_users=["mario"])
    cycle = asyncio.ensure_future(worker.execute_transfers())
    await wait_until(deposit.writing.is_set)

    # The wire dies while mario's parcels are being written. The D8 road goes
    # through the same claim as every other departure, so mario is left to the
    # cycle that has him instead of being queued behind a folder semaphore THIS
    # worker itself is holding — a wait that would only ever end in a timeout.
    await worker.freeze_all_users()
    await cycle

    assert worker.user_register == {}
    assert worker.freeze_failures == 0
    assert [record.getMessage() for record in caplog.records] == []
    assert deposit.lock_holder("mario") is None
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_user_register_item("anna") is not None


async def test_a_slow_write_does_not_stall_the_loop(tmp_path):
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    freezing = asyncio.ensure_future(worker.freeze_user("mario"))
    await wait_until(deposit.writing.is_set)

    started = time.monotonic()
    worker.add_page("page-2", "cid-b", "anna")
    elapsed = time.monotonic() - started

    assert elapsed < SlowDeposit.STALL / 2
    assert await freezing is True
    assert "anna" in worker.user_register


# ----------------------------------------------------------------------
# The semaphore: a voice on the first miss, and a floor under the wait
# ----------------------------------------------------------------------


async def test_a_held_folder_says_once_who_is_holding_it(worker, deposit, caplog):
    caplog.set_level(logging.WARNING)
    worker.add_page("page-1", "cid-a", "mario")
    deposit.take_lock("mario", OTHER_WORKER)
    freezing = asyncio.ensure_future(worker.freeze_user("mario"))

    await asyncio.sleep(worker.deposit_lock_retry_interval * 10)
    deposit.release_lock("mario", OTHER_WORKER)

    assert await freezing is True
    warnings = [record.getMessage() for record in caplog.records if record.levelno >= logging.WARNING]
    assert len(warnings) == 1
    assert "mario" in warnings[0]
    assert OTHER_WORKER in warnings[0]


async def test_a_folder_nobody_gives_back_ends_the_departure_loud(deposit):
    worker = build_worker(deposit, deposit_lock_wait_limit=0.05)
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    deposit.take_lock("mario", OTHER_WORKER)

    assert await asyncio.wait_for(worker.freeze_user("mario"), 2.0) is False
    assert worker.user_register["mario"]["state"] == "active"
    assert worker.freeze_failures == 1
    assert announced(worker) == []
    assert deposit.lock_holder("mario") == OTHER_WORKER


async def test_a_folder_nobody_gives_back_makes_the_adoption_raise(deposit):
    worker = build_worker(deposit, deposit_lock_wait_limit=0.05)
    deposit.take_lock("mario", OTHER_WORKER)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(worker.adopt_user("mario"), 2.0)

    # The wait limit is one more failed pull: no row of his stays behind, and
    # the verdict on his next request is what tries the folder again.
    assert "mario" not in worker.user_register
    assert deposit.lock_holder("mario") == OTHER_WORKER


# ----------------------------------------------------------------------
# The window of the wait: a call born inside it keeps its user
# ----------------------------------------------------------------------


async def test_a_call_born_while_the_semaphore_was_waited_for_keeps_the_user(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.events.clear()
    deposit.take_lock("mario", OTHER_WORKER)
    worker.plan_transfers(transfer_users=["mario"])
    cycle = asyncio.ensure_future(worker.execute_transfers())
    await asyncio.sleep(worker.transfer_start_delay * 2)

    worker.open_request("mario")
    deposit.release_lock("mario", OTHER_WORKER)
    await cycle

    assert worker.user_register["mario"]["state"] == "active"
    assert deposit.read_user_register_item("mario") is None
    assert announced(worker) == []

    await worker.close_request("mario")

    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None
    assert announced(worker) == ["user_frozen"]


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


async def test_a_shot_taken_during_the_quit_does_not_free_the_straggler(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    leaving = asyncio.ensure_future(worker.quit())
    await asyncio.sleep(worker.transfer_start_delay * 3)

    # An ordinary shot, naming nobody for cession: once the quit has begun the
    # plan is its own, and this one may not take the straggler off it.
    transfers = worker.plan_transfers()

    assert transfers["mario"][1] == "T"
    assert not worker.exited

    # The cycle is given its turn on the shot and goes back to sleep on him,
    # and only THEN does his call end — inside what a restarted gate would
    # cost. So the hook is the only thing that can free him, and a gate the
    # shot had shut again would leave the quit with nobody to wake it.
    await asyncio.sleep(worker.transfer_start_delay / 4)
    await worker.close_request("mario")
    await asyncio.wait_for(leaving, 5.0)

    assert worker.exited
    assert worker.user_register == {}
    assert deposit.read_user_register_item("mario") is not None


async def test_a_user_born_during_the_quit_is_added_to_the_departing(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    leaving = asyncio.ensure_future(worker.quit())
    await asyncio.sleep(worker.transfer_start_delay * 3)

    # Somebody arrives while the worker is leaving: his own call is what puts
    # him on the registers, and the shot that answers it flags him too.
    worker.add_page("page-2", "cid-b", "anna")
    worker.open_request("anna")
    transfers = worker.plan_transfers()

    assert transfers["anna"][1] == "T"

    await worker.close_request("anna")
    await worker.close_request("mario")
    await asyncio.wait_for(leaving, 5.0)

    assert worker.exited
    assert worker.user_register == {}
    assert deposit.read_user_register_item("anna") is not None


async def test_a_user_flagged_after_the_first_pass_leaves_with_the_quit_all_the_same(
    worker, deposit
):
    worker.add_page("page-1", "cid-a", "mario")
    worker.open_request("mario")
    leaving = asyncio.ensure_future(worker.quit())
    await asyncio.sleep(worker.transfer_start_delay * 3)

    # Somebody arrives while the worker is leaving, is served, and his call is
    # already CLOSED by the time the shot names him: no hook of his will ever
    # fire again, so the cycle itself is what has to come back for him.
    worker.add_page("page-2", "cid-b", "anna")
    worker.open_request("anna")
    await worker.close_request("anna")
    transfers = worker.plan_transfers()

    assert transfers["anna"][1] == "T"

    await worker.close_request("mario")
    await asyncio.wait_for(leaving, 5.0)

    assert worker.exited
    assert worker.user_register == {}
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_user_register_item("anna") is not None


async def test_the_quit_waits_for_a_pull_still_on_its_way(worker, deposit):
    worker.add_page("page-1", "cid-a", "mario")

    # anna's store is still travelling: her pull is parked on a folder somebody
    # else is holding, so her row is neither active nor gone — she is a
    # straggler like the man with a call open, and a quit that left now would
    # shut the pool her own trip is running on.
    deposit.take_lock("anna", OTHER_WORKER)
    pull = asyncio.ensure_future(worker.adopt_user("anna"))
    await wait_until(lambda: worker.user_register.get("anna", {}).get("state") == "unfreezing")

    leaving = asyncio.ensure_future(worker.quit())
    await asyncio.sleep(worker.transfer_start_delay * 3)

    assert not worker.exited

    deposit.release_lock("anna", OTHER_WORKER)
    await asyncio.wait_for(pull, 5.0)
    await asyncio.wait_for(leaving, 5.0)

    assert worker.exited
    assert worker.user_register == {}
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_user_register_item("anna") is not None


async def test_a_departure_that_falls_over_does_not_keep_the_worker_alive(tmp_path):
    deposit = BreakingDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.add_page("page-2", "cid-b", "anna")

    await asyncio.wait_for(worker.quit(), 5.0)

    # What breaks here breaks on the way OUT — the parcels are already written
    # and the rows already released under the semaphore — so both men really
    # left; what the containment buys is the exit being reached anyway, with
    # the two falls counted and shouted rather than raised at the quit.
    assert worker.exited
    assert worker.freeze_failures == 2
    assert worker.user_register == {}
    assert deposit.read_user_register_item("mario") is not None
    assert deposit.read_user_register_item("anna") is not None


# ----------------------------------------------------------------------
# The flag is the promise (owner, 2026-08-16): only a departure that
# happened, a counted failure or the man's own absence consumes it
# ----------------------------------------------------------------------

class SlowReadDeposit(FreezeHandler):
    """A real deposit whose disk takes a visible moment to give a store back."""

    STALL = 0.3

    def __init__(self, root_path):
        super().__init__(root_path)
        self.reading = threading.Event()

    def read_user_register_item(self, user):
        self.reading.set()
        time.sleep(self.STALL)
        return super().read_user_register_item(user)


async def test_a_bounced_hook_drops_no_flag_between_two_hands(worker, deposit):
    # The two-porters race: the hook fires while somebody else still holds the
    # claim; it bounces — and the bounce must consume NOTHING, because the flag
    # is the promise and only a completed departure takes it away.
    worker.add_page("page-1", "cid-a", "mario")
    worker.plan_transfers(transfer_users=["mario"])
    worker.open_request("mario")

    worker._departing_users.add("mario")
    await worker.close_request("mario")
    assert "mario" in worker._transfer_flags

    worker._release_departure("mario")
    await asyncio.sleep(worker.transfer_start_delay + 0.05)
    await worker.execute_transfers()
    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None
    assert "mario" not in worker._transfer_flags


async def test_a_write_window_deferral_keeps_the_flag_standing(tmp_path):
    # A call born while the disk writes defers the freeze (None, not False):
    # the flag stays, and the tail of that very call is what parks him.
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.plan_transfers(transfer_users=["mario"])
    await asyncio.sleep(worker.transfer_start_delay + 0.05)

    cycle = asyncio.ensure_future(worker.execute_transfers())
    await asyncio.get_running_loop().run_in_executor(None, deposit.writing.wait)
    worker.open_request("mario")
    await asyncio.wait_for(cycle, 5.0)

    assert "mario" in worker.user_register
    assert worker.user_register["mario"]["state"] == "active"
    assert "mario" in worker._transfer_flags
    await worker.close_request("mario")
    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None
    assert "mario" not in worker._transfer_flags


async def test_the_quit_survives_a_departure_deferred_at_its_edge(tmp_path):
    # Inside a quit the kept flag is found again by the chewing cycle: the
    # process leaves only after the man is parked, never with him on board.
    deposit = SlowDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")

    leaving = asyncio.ensure_future(worker.quit())
    await asyncio.get_running_loop().run_in_executor(None, deposit.writing.wait)
    worker.open_request("mario")
    await wait_until(lambda: "mario" not in worker._departing_users)
    assert "mario" in worker._transfer_flags
    await worker.close_request("mario")
    await asyncio.wait_for(leaving, 5.0)

    assert worker.exited
    assert worker.user_register == {}
    assert deposit.read_user_register_item("mario") is not None


async def test_the_pendings_cover_the_adoption_itself(tmp_path):
    # open_request comes before the row is put in order: while the store is
    # still travelling up from the deposit, the call is already visible in the
    # pendings, so no departure can wake in the gap between the loading and
    # the serving of the same call.
    deposit = SlowReadDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    def tiny_site(environ, start_response):
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]

    worker.wsgi_app = tiny_site
    deposit.take_lock("mario", "test")
    deposit.write_user_register_item("mario", {"cart": 1}, writer="t", cause="t", group="g")
    deposit.release_lock("mario", "test")

    payload = {
        "http": {
            "method": "GET",
            "path": "/",
            "query_string": "",
            "headers": [["host", "site.example:8080"]],
            "body": "",
            "cid": "cid-a",
        },
        "identity": "mario",
        "user_frozen": True,
    }
    serving = asyncio.ensure_future(worker._serve_request(payload))
    await asyncio.get_running_loop().run_in_executor(None, deposit.reading.wait)
    assert worker._pendings.get("mario")
    await asyncio.wait_for(serving, 5.0)
    assert not worker._pendings


class TwoPorterDeposit(SlowDeposit):
    """A deposit that can hold the give-back road open: the drop of the parcels
    written by an interrupted freeze waits until the test says go — the exact
    window in which the interrupting call can close and the hook can bounce."""

    def __init__(self, root_path):
        super().__init__(root_path)
        self.dropping = threading.Event()
        self.release_drop = threading.Event()

    def drop_user_register_item(self, user):
        self.dropping.set()
        self.release_drop.wait(5)
        super().drop_user_register_item(user)


async def test_a_call_closing_inside_the_give_back_drops_no_flag(tmp_path):
    # THE two-porters instant: the freeze was deferred to the call's tail, and
    # that very call closes while the executor is still giving the parcels
    # back — the hook bounces off the claim, the executor's own epilogue runs
    # with the pendings already empty. Only a completed departure may consume
    # the flag: whoever pops it here leaves mario between two hands.
    deposit = TwoPorterDeposit(tmp_path / "frozen_users")
    worker = build_worker(deposit)
    worker.add_page("page-1", "cid-a", "mario")
    worker.plan_transfers(transfer_users=["mario"])
    await asyncio.sleep(worker.transfer_start_delay + 0.05)

    cycle = asyncio.ensure_future(worker.execute_transfers())
    await asyncio.get_running_loop().run_in_executor(None, deposit.writing.wait)
    worker.open_request("mario")
    await asyncio.get_running_loop().run_in_executor(None, deposit.dropping.wait)
    await worker.close_request("mario")
    deposit.release_drop.set()
    await asyncio.wait_for(cycle, 5.0)

    assert "mario" in worker._transfer_flags
    await worker.execute_transfers()
    assert "mario" not in worker.user_register
    assert deposit.read_user_register_item("mario") is not None
