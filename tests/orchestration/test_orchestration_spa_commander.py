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

"""The vertex on its own: who it writes, what it answers, what it discards.

The chain's tests look at the fold from above — an envelope arrives and the
indexes move. These look at the same object from the front: the reception desk
that mints whoever shows up, the predicates the rest of the machine reads it
through, the waiting room that is a raised exception and not a field, and the two
things the vertex does that nobody below it can — discarding what a dead process
left on disk, and writing the account of every order.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

import pytest

from genro_bag import Bag

from genro_asgi.spa.orchestration import SpaCommander, UserOnHold
from genro_asgi.spa.orchestration.spa_commander import GUEST_PREFIX

WORKER_NAME = "standard_0001"


@pytest.fixture
def vertex_root():
    """A root holding the deposit and, where a test asks for it, the log."""
    root = Path(tempfile.mkdtemp(prefix="gnrvertex_"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def commander(vertex_root):
    return SpaCommander(vertex_root / "frozen_users")


def parked_state(commander: SpaCommander, user: str) -> None:
    """What a freeze leaves on disk, written the way a worker writes it."""
    commander.freeze_handler.take_lock(user, WORKER_NAME)
    commander.freeze_handler.write_user_register_item(
        user, {"store": "whatever"}, writer=WORKER_NAME, cause="freeze", group="standard"
    )
    commander.freeze_handler.release_lock(user, WORKER_NAME)


def test_whoever_shows_up_is_minted_before_anything_descends(commander):
    user = commander.resolve_user("cid-a")

    assert user == f"{GUEST_PREFIX}cid-a"
    assert commander.connection_user_map == {"cid-a": user}
    assert commander.user_map[user] == {
        "group": None,
        "frozen": False,
        "on_hold": None,
        "occupancy_percent": None,
        "pending_dbevents": [],
        "pending_datachanges": [],
    }


def test_a_cid_already_known_is_answered_and_nothing_is_written_twice(commander):
    first = commander.resolve_user("cid-a")
    commander.user_map[first]["occupancy_percent"] = 9.0

    assert commander.resolve_user("cid-a") == first
    assert commander.user_map[first]["occupancy_percent"] == 9.0


def test_a_cookie_that_outlived_its_row_is_still_that_person(commander):
    commander.connection_user_map["cid-a"] = "mario"

    assert commander.resolve_user("cid-a") == "mario"
    assert commander.user_map["mario"]["frozen"] is False


def test_a_user_on_his_way_out_is_not_routed_but_raised(commander):
    user = commander.resolve_user("cid-a")
    commander.hold_user(user, "transfer_flag T")

    with pytest.raises(UserOnHold) as refusal:
        commander.resolve_user("cid-a")

    assert refusal.value.user == user
    assert refusal.value.cause == "transfer_flag T"
    assert str(refusal.value) == f"{user} is on hold: transfer_flag T"


def test_the_cause_of_a_hold_is_the_one_that_explains_the_wait(commander):
    user = commander.resolve_user("cid-a")
    commander.hold_user(user, "transfer_flag T")
    commander.hold_user(user, "transfer_flag X")

    assert commander.user_map[user]["on_hold"] == "transfer_flag T"


def test_nobody_is_frozen_until_it_is_written_down(commander):
    user = commander.resolve_user("cid-a")

    assert commander.user_is_frozen("somebody nobody knows") is False
    assert commander.user_is_frozen(user) is False

    commander.mark_user_frozen(user, 6.0)

    assert commander.user_is_frozen(user) is True


def test_a_freeze_that_carries_no_estimate_leaves_the_last_one_alone(commander):
    user = commander.resolve_user("cid-a")
    commander.mark_user_frozen(user, 6.0)

    commander.mark_user_frozen(user, None)

    assert commander.user_map[user]["occupancy_percent"] == 6.0


def test_a_freeze_ends_the_wait_it_was_the_reason_for(commander):
    user = commander.resolve_user("cid-a")
    commander.hold_user(user, "transfer_flag T")

    commander.mark_user_frozen(user, 6.0)

    assert commander.resolve_user("cid-a") == user


def test_an_adoption_empties_the_row_of_what_was_waiting(commander):
    user = commander.resolve_user("cid-a")
    commander.mark_user_frozen(user, 6.0)
    commander.user_map[user]["pending_dbevents"] = [{"table": "invoices"}]

    commander.mark_user_adopted(user)

    assert commander.user_map[user]["pending_dbevents"] == []
    assert commander.user_map[user]["pending_datachanges"] == []
    assert commander.user_is_frozen(user) is False


def test_dropping_what_is_already_gone_is_that_same_outcome(commander):
    commander.drop_page("never-existed")
    commander.drop_connection("never-existed")
    commander.drop_user("never-existed")

    assert commander.page_connection_map == {}
    assert commander.user_map == {}


def test_a_user_who_is_gone_takes_his_connections_and_pages_with_him(commander):
    user = commander.resolve_user("cid-a")
    commander.connection_user_map["cid-b"] = user
    commander.page_connection_map["p1"] = "cid-a"
    commander.page_connection_map["p2"] = "cid-b"
    commander.user_map[user]["pending_datachanges"] = [{"path": "a.b"}, {"path": "a.c"}]

    commander.drop_user(user)

    assert commander.user_map == {}
    assert commander.connection_user_map == {}
    assert commander.page_connection_map == {}
    assert commander.counters["pendings_lost"] == 2


def test_what_a_dead_process_left_on_disk_is_discarded_and_counted(commander, caplog):
    caplog.set_level(logging.INFO)
    user = commander.resolve_user("cid-a")
    parked_state(commander, user)
    without_state = commander.resolve_user("cid-b")

    commander.drop_users([user, without_state], cause="process_aborted")

    assert commander.freeze_handler.user_folders == set()
    assert commander.user_map == {}
    assert commander.counters["frozen_users_discarded"] == 1
    assert caplog.text.count("order=purge_user") == 2


def test_every_order_leaves_its_row_on_the_file_of_the_orders(vertex_root):
    log_path = vertex_root / "orchestration.log"
    commander = SpaCommander(vertex_root / "frozen_users", orchestration_log_path=log_path)

    commander.log_order(
        "standard",
        "quit_process",
        WORKER_NAME,
        numbers={"occupancy_percent": 12.0},
        outcome="quitted",
    )

    row = log_path.read_text().strip()
    assert "decided_by=standard" in row
    assert "order=quit_process" in row
    assert f"subject={WORKER_NAME}" in row
    assert "numbers={'occupancy_percent': 12.0}" in row
    assert "outcome=quitted" in row


def test_one_process_has_one_vertex_and_the_log_is_its_own(vertex_root):
    first_path = vertex_root / "first.log"
    second_path = vertex_root / "second.log"
    SpaCommander(vertex_root / "frozen_users", orchestration_log_path=first_path)
    second = SpaCommander(vertex_root / "frozen_users", orchestration_log_path=second_path)

    second.log_order("standard", "quit_process", WORKER_NAME, outcome="quitted")

    assert len(logging.getLogger("genro_asgi.orchestration.orders").handlers) == 1
    assert "order=quit_process" in second_path.read_text()
    assert first_path.read_text() == ""


def test_the_machine_starts_running_and_holds_the_master_of_the_store(commander):
    assert commander.state == "running"
    assert isinstance(commander.global_register, Bag)
    assert commander.global_register.keys() == []
