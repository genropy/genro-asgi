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

"""The commander's page surface: one map, fed by the lifecycle fold alone.

Two halves, the shape of the commander's own suite. First the fold on real
REPLY envelopes — a worker really answering ``/op/new_page`` and ``/op/drop_page``
over a channel, so what is folded here is what a page really causes. Then the
surface rules that need two workers and no process at all: the owner check, the
pages following their user through ``assign_user``, the cascades.
"""

from __future__ import annotations

from typing import Any

import pytest

from genro_asgi.spa.commander import LOGIN_OP, UserStickyCommander


def event(op: str, seq: int, **payload: Any) -> dict[str, Any]:
    """One shaped lifecycle event as a worker would offer it."""
    return {"op": op, "seq": seq, **payload}


@pytest.fixture
def commander(tmp_path: Any) -> UserStickyCommander:
    """A commander with two enrolled workers and a hub that is never started."""
    running = UserStickyCommander(workers=0, path=str(tmp_path / "hub.sock"))
    for name in ("W:w-1", "W:w-2"):
        running.worker_roster[name] = running.new_roster_row(0, None)
        running.worker_roster[name]["status"] = "active"
    return running


@pytest.fixture
async def single() -> Any:
    """A commander in the single role: its own worker, in this very process."""
    running = UserStickyCommander(workers=0, local_worker=True)
    await running.start()
    try:
        yield running
    finally:
        await running.stop()


# ----------------------------------------------------------------------
# The fold on real REPLY envelopes
# ----------------------------------------------------------------------


async def test_a_new_page_call_puts_the_page_on_the_surface(single: UserStickyCommander) -> None:
    row = await single.forward_call("alice", "/op/new_page", {"page_id": "p1", "session_id": "s1"})

    assert row["connection_id"] == "s1" and row["session_id"] == "s1"
    assert single.page_connection == {"p1": "s1"}
    assert single.page_worker("p1") == single.worker.name


async def test_the_wire_view_of_a_page_row_carries_its_subscriptions_as_lists(
    single: UserStickyCommander,
) -> None:
    row = await single.forward_call("alice", "/op/new_page", {"page_id": "p1", "session_id": "s1"})

    # The live objects stayed on the worker; the sets travelled as JSON can.
    assert "store" not in row and "collector" not in row and "user_view" not in row
    assert row["store_subscriptions"] == [] and row["table_subscriptions"] == []


async def test_dropping_the_last_page_takes_the_page_and_its_user_off_the_surface(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("alice", "/op/new_page", {"page_id": "p1", "session_id": "s1"})
    await single.forward_call("alice", "/op/drop_page", {"page_id": "p1"})

    # The worker's own registry cascaded the user away, and the event said so.
    assert single.page_connection == {}
    assert single.user_worker_map == {}


async def test_a_second_page_survives_its_sibling_being_dropped(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("alice", "/op/new_page", {"page_id": "p1", "session_id": "s1"})
    await single.forward_call("alice", "/op/new_page", {"page_id": "p2", "session_id": "s1"})
    await single.forward_call("alice", "/op/drop_page", {"page_id": "p1"})

    assert list(single.page_connection) == ["p2"]
    assert single.user_worker_map == {"alice": single.worker.name}


async def test_dropping_the_user_takes_every_page_of_it(single: UserStickyCommander) -> None:
    await single.forward_call("alice", "/op/new_page", {"page_id": "p1", "session_id": "s1"})
    await single.forward_call("alice", "/op/new_page", {"page_id": "p2", "session_id": "s1"})
    await single.forward_call("bob", "/op/new_page", {"page_id": "p3", "session_id": "s2"})

    await single.forward_call("alice", "/op/drop_user", {})

    assert list(single.page_connection) == ["p3"]


async def test_a_login_keeps_the_pages_and_their_owner_follows_the_connection(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("s1", "/op/new_page", {"page_id": "p1", "session_id": "s1"})
    await single.forward_call("s1", "/op/change_connection_user", {"user": "alice"})

    # S1: the page survived the login on its own connection, and its owner
    # changed with that connection — nothing about the page itself was touched.
    assert single.page_connection == {"p1": "s1"}
    assert single.page_worker("p1") == single.worker.name
    assert single.connection_user == {"s1": "alice"}
    assert single.user_worker_map == {"alice": single.worker.name}


async def test_the_guest_leaves_the_surface_once_it_has_no_connection_left(
    single: UserStickyCommander,
) -> None:
    await single.forward_call("s1", "/op/new_page", {"page_id": "p1", "session_id": "s1"})
    await single.forward_call("s1", "/op/change_connection_user", {"user": "alice"})

    # Its only connection joined alice, so the guest entry went — and it took
    # nothing with it: the page hangs under a connection alice now owns.
    assert "s1" not in single.user_worker_map
    assert single.connection_user[single.page_connection["p1"]] == "alice"


# ----------------------------------------------------------------------
# The surface rules, two workers and no process
# ----------------------------------------------------------------------


def test_an_unknown_page_resolves_to_none(commander: UserStickyCommander) -> None:
    assert commander.page_worker("nobody-knows-me") is None


def test_the_broadcast_filter_matches_on_the_fields_the_walk_derives(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
        ],
    )
    # Only the connection edge is written; user and worker come off the chain.
    assert commander.page_connection == {"p1": "s1"}
    assert commander.matching_pages("connection:s1") == [("p1", "W:w-1")]
    assert commander.matching_pages("user:alice") == [("p1", "W:w-1")]
    assert commander.matching_pages("worker:W:w-1") == [("p1", "W:w-1")]


def test_a_new_page_naming_an_unknown_connection_self_heals_it(
    commander: UserStickyCommander,
) -> None:
    """The event's ``user`` owns its ``session_id``: the middle link is rebuilt."""
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_page", 2, user="alice", page_id="p1", session_id="s1"),
        ],
    )

    assert commander.connection_user == {"s1": "alice"}
    assert commander.connections_of("alice") == ["s1"]
    assert commander.page_worker("p1") == "W:w-1"


def test_a_late_claim_never_re_places_a_page(
    commander: UserStickyCommander, caplog: Any
) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
        ],
    )
    with caplog.at_level("WARNING"):
        commander.fold_events(
            "W:w-2", [event("new_page", 1, user="alice", page_id="p1", session_id="s1")]
        )
    assert commander.page_worker("p1") == "W:w-1"
    assert caplog.records == []


def test_a_foreign_drop_leaves_the_holder_alone(commander: UserStickyCommander) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_page", 2, user="alice", page_id="p1", session_id="s1"),
        ],
    )
    commander.fold_events("W:w-2", [event("drop_page", 1, user="alice", page_id="p1")])
    assert commander.page_worker("p1") == "W:w-1"


def test_dropping_an_unknown_page_is_a_no_op(commander: UserStickyCommander) -> None:
    commander.fold_events("W:w-1", [event("drop_page", 1, user="alice", page_id="ghost")])
    assert commander.page_connection == {}


def test_pages_follow_their_user_when_it_is_re_pointed(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
            event("new_page", 4, user="alice", page_id="p2", session_id="s1"),
        ],
    )
    commander.fold_events(
        "W:w-2",
        [
            event("new_user", 1, user="bob"),
            event("new_connection", 2, user="bob", session_id="s2"),
            event("new_page", 3, user="bob", page_id="p3", session_id="s2"),
        ],
    )

    before = dict(commander.page_connection)

    commander.assign_user("alice", "W:w-2")

    assert commander.page_worker("p1") == "W:w-2"
    assert commander.page_worker("p2") == "W:w-2"
    assert commander.page_worker("p3") == "W:w-2"
    # Nothing per page was written: the answer moved because the user's did.
    assert commander.page_connection == before


def test_a_placement_in_flight_leaves_the_pages_unplaced(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
        ],
    )
    commander.assign_user("alice", None)
    assert commander.page_worker("p1") is None
    assert "p1" in commander.page_connection


def test_sweeping_a_dead_worker_forgets_its_pages(commander: UserStickyCommander) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
        ],
    )
    commander.fold_events(
        "W:w-2",
        [
            event("new_user", 1, user="bob"),
            event("new_connection", 2, user="bob", session_id="s2"),
            event("new_page", 3, user="bob", page_id="p2", session_id="s2"),
        ],
    )
    commander.sweep_worker("W:w-1")
    assert list(commander.page_connection) == ["p2"]


# ----------------------------------------------------------------------
# The chain: two connections of one user, and the login of the second
# ----------------------------------------------------------------------


def two_connections(commander: UserStickyCommander, worker: str = "W:w-1") -> None:
    """Alice on ``worker`` with two connections, one page each."""
    commander.fold_events(
        worker,
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
            event("new_connection", 4, user="alice", session_id="s2"),
            event("new_page", 5, user="alice", page_id="p2", session_id="s2"),
        ],
    )


def test_the_connections_of_a_user_are_read_off_the_one_map(
    commander: UserStickyCommander,
) -> None:
    two_connections(commander)

    assert commander.connections_of("alice") == ["s1", "s2"]
    assert commander.pages_of_connection("s2") == ["p2"]


def test_dropping_one_connection_leaves_the_user_and_its_sibling_alone(
    commander: UserStickyCommander,
) -> None:
    two_connections(commander)

    commander.fold_events(
        "W:w-1",
        [
            event("drop_page", 6, user="alice", page_id="p2"),
            event("drop_connection", 7, user="alice", session_id="s2"),
        ],
    )

    assert commander.connection_user == {"s1": "alice"}
    assert list(commander.page_connection) == ["p1"]
    assert commander.user_worker_map == {"alice": "W:w-1"}


def test_removing_a_two_connection_user_clears_the_whole_chain(
    commander: UserStickyCommander,
) -> None:
    two_connections(commander)
    commander.page_subscriptions.subscribe("p1", "glbl.user")

    commander.remove_user("alice")

    assert commander.page_connection == {}
    assert commander.connection_user == {}
    assert commander.user_worker_map == {}
    assert commander.page_subscriptions.pages_for("glbl.user") == set()


def test_a_login_leaves_the_page_subscriptions_where_they_are(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="s1"),
            event("new_connection", 2, user="s1", session_id="s1"),
            event("new_page", 3, user="s1", page_id="p1", session_id="s1"),
        ],
    )
    commander.page_subscriptions.subscribe("p1", "glbl.user")

    commander.fold_events(
        "W:w-1",
        [event(LOGIN_OP, 4, user="alice", previous_user="s1", session_id="s1", encoded="")],
    )

    assert commander.page_subscriptions.pages_for("glbl.user") == {"p1"}
    assert commander.connection_user[commander.page_connection["p1"]] == "alice"


def test_the_login_of_a_second_connection_never_flags_a_resident_user(
    commander: UserStickyCommander,
) -> None:
    commander.fold_events(
        "W:w-1",
        [
            event("new_user", 1, user="alice"),
            event("new_connection", 2, user="alice", session_id="s1"),
            event("new_page", 3, user="alice", page_id="p1", session_id="s1"),
        ],
    )
    commander.fold_events(
        "W:w-2",
        [
            event("new_user", 1, user="s2"),
            event("new_connection", 2, user="s2", session_id="s2"),
            event("new_page", 3, user="s2", page_id="p2", session_id="s2"),
        ],
    )

    commander.fold_events(
        "W:w-2",
        [event(LOGIN_OP, 4, user="alice", previous_user="s2", session_id="s2", encoded="")],
    )

    # S2: alice is at home, not in flight, and her first connection never moved.
    assert commander.user_worker_map == {"alice": "W:w-1"}
    assert commander.connections_of("alice") == ["s1", "s2"]
    assert commander.page_connection == {"p1": "s1", "p2": "s2"}
    assert commander.page_worker("p1") == "W:w-1"
    # p2 came over with its connection: its owner derives to alice, its worker
    # to the one alice was already on.
    assert commander.connection_user["s2"] == "alice"
    assert commander.page_worker("p2") == "W:w-1"


def test_a_re_registered_page_leaves_no_edge_on_its_old_connection(
    commander: UserStickyCommander,
) -> None:
    """The same worker moving a page to another connection moves the edge with it."""
    two_connections(commander)

    commander.register_page("p1", "alice", "W:w-1", "s2")

    assert commander.pages_of_connection("s1") == []
    assert commander.pages_of_connection("s2") == ["p1", "p2"]
    assert commander.page_connection["p1"] == "s2"


def test_dropping_a_page_clears_the_edge_on_both_sides(
    commander: UserStickyCommander,
) -> None:
    two_connections(commander)

    assert commander.page_connection == {"p1": "s1", "p2": "s2"}

    commander.fold_events("W:w-1", [event("drop_page", 6, user="alice", page_id="p1")])
    assert commander.page_connection == {"p2": "s2"}
    assert commander.pages_of_connection("s1") == []
