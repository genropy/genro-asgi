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

"""Live stores on the rows: capture, user views, drain and forwarded writes.

The rows are exercised through the registry's own lifecycle vocabulary, and
the drain through the worker's ``collect_page`` — no collector is built by
hand, because the point under test is precisely that the lifecycle builds and
tears them down. A write into the user store is asserted to reach exactly the
pages that subscribed to a prefix covering it: that reach IS the API of Q-A,
so it is asserted on the collectors' contents, never on a smear loop.
"""

from __future__ import annotations

from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector
from genro_tytx import to_tytx

from genro_asgi.spa.register_registry import RegisterRegistry
from genro_asgi.spa.worker import UserStickyWorker


def make_registry() -> RegisterRegistry:
    """A registry holding one user with two pages."""
    registry = RegisterRegistry()
    registry.new_page("p1", user="u1", session_id="s1")
    registry.new_page("p2", user="u1", session_id="s1")
    return registry


def test_rows_are_born_with_live_stores() -> None:
    registry = make_registry()
    user = registry.user_items.get("u1")
    page = registry.page_items.get("p1")
    assert isinstance(user["store"], Bag)
    assert isinstance(page["store"], Bag)
    assert page["collector"].bag is page["store"]
    assert page["user_view"] is None
    assert page["dbevents"] == []
    assert page["collector"].paths == set()
    assert page["subscribed_paths"] == set()
    assert page["store_subscriptions"] == set()


def test_a_moved_row_keeps_the_stamp_it_travelled_with() -> None:
    """The birth stamp is a default, not an imposition: a rebirth restores it."""
    registry = RegisterRegistry()
    registry.new_page("p1", user="u1", session_id="s1", last_refresh_ts=1000.0)
    assert registry.page_items.get("p1")["last_refresh_ts"] == 1000.0


def test_page_collector_captures_nothing_until_the_page_subscribes() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    page = worker.page_items.get("p1")
    page["store"]["form.name"] = "Ada"
    assert page["collector"].pending == 0
    assert page["subscribed_paths"] == set()


def test_page_collector_captures_its_own_store() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    page = worker.page_items.get("p1")
    assert page["subscribed_paths"] == {"form"}
    page["store"]["form.name"] = "Ada"
    changes = page["collector"].drain()
    # The intermediate node is a write of its own: genro-bag captures its
    # insert before the leaf's.
    assert [c["key"]["path"] for c in changes] == ["form", "form.name"]
    assert changes[-1]["value"] == "Ada"
    assert page["collector"].pending == 0


# ----------------------------------------------------------------------
# setStoreSubscription: the page declares what it wants to hear about
# ----------------------------------------------------------------------


def subscribed_worker() -> UserStickyWorker:
    """A worker holding one page of ``u1``, nothing subscribed yet."""
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    return worker


def test_the_page_subscription_opens_and_closes_its_own_store() -> None:
    worker = subscribed_worker()
    page = worker.page_items.get("p1")

    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    page["store"]["form.name"] = "Ada"
    assert [c["key"]["path"] for c in page["collector"].drain()] == ["form", "form.name"]

    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form", active=False)
    assert page["subscribed_paths"] == set()
    page["store"]["form.name"] = "Grace"
    assert page["collector"].pending == 0


def test_the_explicit_deposit_ignores_the_page_filter() -> None:
    """The ratified escape: ``set_datachange`` lands whatever the filter says."""
    worker = subscribed_worker()
    page = worker.page_items.get("p1")
    source = Bag()
    producer = DataChangeCollector(source)
    source["untold.x"] = 1
    change = producer.drain()[-1]

    worker.set_datachange("u1", change=to_tytx(change, "json"), target="p1")

    assert [c["key"]["path"] for c in page["collector"].drain()] == ["untold.x"]


def test_the_chat_pattern_opens_and_closes_the_user_store() -> None:
    """The legacy consumer's own shape: a prefix of the USER store, on and off."""
    worker = subscribed_worker()
    page = worker.page_items.get("p1")
    user_store = worker.user_items.get("u1")["store"]

    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="gnr.chat.msg")
    assert page["store_subscriptions"] == {"gnr.chat.msg"}
    user_store["gnr.chat.msg.m1"] = "ciao"
    # The intermediate nodes above the prefix are outside it: only the
    # subscribed node and its leaf are captured.
    assert [c["key"]["path"] for c in page["user_view"].drain()] == [
        "gnr.chat.msg",
        "gnr.chat.msg.m1",
    ]

    worker.setStoreSubscription(
        "u1", page_id="p1", storename="user", prefix="gnr.chat.msg", active=False
    )
    assert page["store_subscriptions"] == set()
    user_store["gnr.chat.msg.m2"] = "ancora"
    assert page["user_view"].pending == 0


def test_the_batch_pattern_widens_the_view_it_finds() -> None:
    worker = subscribed_worker()
    page = worker.page_items.get("p1")
    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="gnr.chat.msg")
    view = page["user_view"]

    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="gnr.batch")

    assert page["user_view"] is view
    assert view.paths == {"gnr.chat.msg", "gnr.batch"}
    worker.user_items.get("u1")["store"]["gnr.batch.b1.status"] = "running"
    assert [c["key"]["path"] for c in view.drain()] == [
        "gnr.batch",
        "gnr.batch.b1",
        "gnr.batch.b1.status",
    ]


def test_closing_a_user_subscription_a_page_never_took_is_a_no_op() -> None:
    worker = subscribed_worker()

    worker.setStoreSubscription("u1", page_id="p1", storename="user", prefix="prefs", active=False)

    assert worker.page_items.get("p1")["user_view"] is None


def test_an_unknown_storename_is_an_error() -> None:
    worker = subscribed_worker()
    try:
        worker.setStoreSubscription("u1", page_id="p1", storename="connection", prefix="x")
    except ValueError as exc:
        assert "connection" in str(exc)
    else:
        raise AssertionError("setStoreSubscription accepted an unknown storename")


def test_subscription_creates_the_view_then_widens_it() -> None:
    registry = make_registry()
    page = registry.subscribe_store_path("p1", "prefs")
    view = page["user_view"]
    assert view.bag is registry.user_items.get("u1")["store"]
    assert view.paths == {"prefs"}
    registry.subscribe_store_path("p1", "cart")
    assert page["user_view"] is view
    assert view.paths == {"prefs", "cart"}
    assert page["store_subscriptions"] == {"prefs", "cart"}


def test_user_store_write_reaches_only_the_subscribed_pages() -> None:
    registry = make_registry()
    registry.subscribe_store_path("p1", "prefs")
    user_store = registry.user_items.get("u1")["store"]
    user_store["prefs.theme"] = "dark"
    p1_changes = registry.page_items.get("p1")["user_view"].drain()
    assert [c["key"]["path"] for c in p1_changes] == ["prefs", "prefs.theme"]
    assert registry.page_items.get("p2")["user_view"] is None


def test_the_view_prefix_is_segment_bounded() -> None:
    registry = make_registry()
    registry.subscribe_store_path("p1", "prefs")
    user_store = registry.user_items.get("u1")["store"]
    user_store["prefsauto.theme"] = "dark"
    user_store["prefs.theme"] = "light"
    view = registry.page_items.get("p1")["user_view"]
    assert [c["key"]["path"] for c in view.drain()] == ["prefs", "prefs.theme"]


def test_two_pages_of_one_user_drain_independently() -> None:
    registry = make_registry()
    registry.subscribe_store_path("p1", "prefs")
    registry.subscribe_store_path("p2", "prefs")
    registry.user_items.get("u1")["store"]["prefs.theme"] = "dark"
    p1_view = registry.page_items.get("p1")["user_view"]
    p2_view = registry.page_items.get("p2")["user_view"]
    assert p1_view.pending == 2
    assert p2_view.pending == 2
    p1_view.drain()
    assert p1_view.pending == 0
    assert p2_view.pending == 2


def test_drop_page_detaches_both_collectors() -> None:
    registry = make_registry()
    page = registry.subscribe_store_path("p1", "prefs")
    store, view = page["store"], page["user_view"]
    registry.drop_page("p1")
    store["form.name"] = "Ada"
    registry.user_items.get("u1")["store"]["prefs.theme"] = "dark"
    assert page["collector"].pending == 0
    assert view.pending == 0


def test_drop_user_detaches_the_collectors_of_its_pages() -> None:
    registry = make_registry()
    registry.subscribe_store_path("p1", "prefs")
    page = registry.page_items.get("p1")
    store, view = page["store"], page["user_view"]
    user_store = registry.user_items.get("u1")["store"]
    registry.drop_user("u1")
    store["form.name"] = "Ada"
    user_store["prefs.theme"] = "dark"
    assert page["collector"].pending == 0
    assert view.pending == 0


def test_collect_page_merges_both_collectors_by_ts() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    worker.registry.subscribe_store_path("p1", "prefs")
    page = worker.page_items.get("p1")
    page["store"]["form.name"] = "Ada"
    worker.user_items.get("u1")["store"]["prefs.theme"] = "dark"
    page["store"]["form.age"] = 36
    collected = worker.collect_page("p1")
    assert [c["key"]["path"] for c in collected["datachanges"]] == [
        "form",
        "form.name",
        "prefs",
        "prefs.theme",
        "form.age",
    ]
    assert collected["dbevents"] == []
    assert worker.collect_page("p1")["datachanges"] == []


def test_collect_page_drains_the_dbevents_species_apart() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    page = worker.page_items.get("p1")
    page["dbevents"].append({"table": "adm.user"})
    collected = worker.collect_page("p1")
    assert collected["dbevents"] == [{"table": "adm.user"}]
    assert collected["datachanges"] == []
    assert worker.collect_page("p1")["dbevents"] == []


def test_collect_page_of_an_unknown_page_is_an_error() -> None:
    worker = UserStickyWorker("W:w1")
    try:
        worker.collect_page("nope")
    except KeyError as exc:
        assert "nope" in str(exc)
    else:
        raise AssertionError("collect_page accepted an unknown page")


def test_apply_forwarded_stamps_the_original_ts() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    source = Bag()
    source.set_item("form.name", "Ada", _attributes={"tag": "input"})
    producer = DataChangeCollector(source)
    source.set_item("form.name", "Grace", _attributes={"tag": "input"})
    change = producer.drain()[0]

    target = worker.page_items.get("p1")["store"]
    worker.apply_forwarded(target, change)
    node = target.get_node("form.name")
    assert node.value == "Grace"
    assert node.attr["tag"] == "input"
    assert node.attr["_original_ts"] == change["change_ts"]
    local = worker.collect_page("p1")["datachanges"][0]
    assert local["change_ts"] >= change["change_ts"]


def test_apply_forwarded_deletes_instead_of_nulling() -> None:
    worker = UserStickyWorker("W:w1")
    worker.registry.new_page("p1", user="u1", session_id="s1")
    worker.setStoreSubscription("u1", page_id="p1", storename="page", prefix="form")
    target = worker.page_items.get("p1")["store"]
    target["form.name"] = "Ada"
    worker.collect_page("p1")
    source = Bag()
    source["form.name"] = "Ada"
    producer = DataChangeCollector(source)
    del source["form.name"]
    change = producer.drain()[0]

    worker.apply_forwarded(target, change)
    assert target.get_node("form.name") is None
    assert worker.collect_page("p1")["datachanges"][0]["delete"] is True


# ----------------------------------------------------------------------
# The login is a mutation: keys, rows and live objects survive it
# ----------------------------------------------------------------------


def test_the_login_relabels_the_connection_and_its_pages_with_the_keys_intact() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="sess-1", session_id="sess-1")
    registry.new_page("p2", user="sess-1", session_id="sess-1")
    connection = registry.connection_items.get("sess-1")

    registry.change_connection_user("sess-1", "alice")

    # The same rows, re-labelled: nothing was dropped and re-created.
    assert registry.connection_items.get("sess-1") is connection
    assert connection["user"] == "alice"
    assert connection["pages"] == {"p1", "p2"}
    assert {registry.page_user(page_id) for page_id in ("p1", "p2")} == {"alice"}
    assert registry.page_items.get("p1")["connection_id"] == "sess-1"
    assert "sess-1" not in registry.user_items


def test_the_login_keeps_the_user_view_on_the_carried_store() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="guest_sess-1", session_id="sess-1")
    registry.subscribe_store_path("p1", "prefs")
    guest_store = registry.user_items.get("guest_sess-1")["store"]

    registry.change_connection_user("sess-1", "alice")

    page = registry.page_items.get("p1")
    # The Bag under the new key IS the guest's own, so the view never moved.
    assert registry.user_items.get("alice")["store"] is guest_store
    registry.user_items.get("alice")["store"]["prefs.lang"] = "it"
    assert [change["key"]["path"] for change in page["user_view"].changes] == [
        "prefs",
        "prefs.lang",
    ]


def test_the_login_re_attaches_the_user_view_without_draining_it() -> None:
    registry = RegisterRegistry()
    registry.new_user("alice")
    registry.new_page("p1", user="sess-1", session_id="sess-1")
    registry.subscribe_store_path("p1", "prefs")
    registry.user_items.get("sess-1")["store"]["prefs.theme"] = "dark"
    before = registry.page_items.get("p1")["user_view"]
    pending = list(before.changes)

    registry.change_connection_user("sess-1", "alice")

    view = registry.page_items.get("p1")["user_view"]
    # Alice already existed, so this is the re-attach branch: a fresh collector
    # on the RESIDENT store, re-deposited with everything still pending.
    assert view is not before
    assert [change["key"]["path"] for change in view.changes] == [
        change["key"]["path"] for change in pending
    ]
    assert [change["change_ts"] for change in view.changes] == [
        change["change_ts"] for change in pending
    ]
    assert view.paths == {"prefs"}
    # And from here on it captures on alice's own Bag.
    registry.user_items.get("alice")["store"]["prefs.size"] = "L"
    assert [change["key"]["path"] for change in view.changes][-1] == "prefs.size"


def test_the_guest_item_follows_its_first_real_identity() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="guest_sess-1", session_id="sess-1")
    guest = registry.user_items.get("guest_sess-1")
    guest_store, guest_connections = guest["store"], guest["connections"]
    guest_store["draft"] = "half typed"

    registry.change_connection_user("sess-1", "alice")

    entry = registry.user_items.get("alice")
    # Only the key changed: the same live objects arrived under the new one.
    assert registry.user_items.get("guest_sess-1") is None
    assert entry["store"] is guest_store
    assert entry["connections"] is guest_connections
    assert entry["connections"] == {"sess-1"}
    assert entry["register_item_id"] == "alice"
    assert entry["store"]["draft"] == "half typed"


def test_the_carried_store_keeps_capturing_with_no_re_attach() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="guest_sess-1", session_id="sess-1")
    registry.subscribe_store_path("p1", "prefs")
    view = registry.page_items.get("p1")["user_view"]

    registry.change_connection_user("sess-1", "alice")

    # The very same collector object, still capturing: nothing was re-attached.
    assert registry.page_items.get("p1")["user_view"] is view
    registry.user_items.get("alice")["store"]["prefs.lang"] = "it"
    assert [change["key"]["path"] for change in view.changes] == ["prefs", "prefs.lang"]


def test_a_login_onto_a_resident_user_leaves_the_guest_store_behind() -> None:
    registry = RegisterRegistry()
    registry.new_page("p0", user="alice", session_id="s0")
    resident_store = registry.user_items.get("alice")["store"]
    resident_store["prefs.theme"] = "dark"
    registry.new_page("p1", user="guest_sess-1", session_id="sess-1")
    registry.user_items.get("guest_sess-1")["store"]["draft"] = "half typed"

    registry.change_connection_user("sess-1", "alice")

    # Boundary 1: the resident wins — its store is the truth, the guest's data
    # is not merged, and the orphaned guest dies with it.
    entry = registry.user_items.get("alice")
    assert entry["store"] is resident_store
    assert entry["store"]["prefs.theme"] == "dark"
    assert entry["store"]["draft"] is None
    assert registry.user_items.get("guest_sess-1") is None
    assert entry["connections"] == {"s0", "sess-1"}


def test_a_real_users_connection_logging_in_elsewhere_gets_a_fresh_store() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="alice", session_id="s1")
    registry.new_page("p2", user="alice", session_id="s2")
    registry.user_items.get("alice")["store"]["draft"] = "half typed"

    registry.change_connection_user("s1", "bob")

    # Boundary 2: a real user's item never transfers — bob is born fresh and
    # alice survives while a connection is still hers.
    assert registry.user_items.get("bob")["store"]["draft"] is None
    assert registry.user_items.get("alice")["connections"] == {"s2"}

    registry.change_connection_user("s2", "carol")

    # Orphaned at last, alice dies with her data.
    assert registry.user_items.get("alice") is None
    assert registry.user_items.get("carol")["store"]["draft"] is None


def test_a_second_connection_logging_in_leaves_the_first_untouched() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="sess-1", session_id="sess-1")
    registry.change_connection_user("sess-1", "alice")
    first = registry.connection_items.get("sess-1")
    alice_store = registry.user_items.get("alice")["store"]
    registry.new_page("p2", user="sess-2", session_id="sess-2")

    registry.change_connection_user("sess-2", "alice")

    # Two connections of one user, and the resident one never moved.
    assert registry.user_items.get("alice")["connections"] == {"sess-1", "sess-2"}
    assert registry.connection_items.get("sess-1") is first
    assert registry.user_items.get("alice")["store"] is alice_store
    assert registry.page_items.get("p1")["connection_id"] == "sess-1"
    assert registry.page_items.get("p2")["connection_id"] == "sess-2"


def test_the_login_fields_describe_the_user_and_its_connection() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="sess-1", session_id="sess-1")

    registry.change_connection_user("sess-1", "alice", user_name="Ada")

    assert registry.user_items.get("alice")["user_name"] == "Ada"
    assert registry.connection_items.get("sess-1")["user_name"] == "Ada"


def test_the_login_fields_on_a_resident_stay_on_the_connection() -> None:
    """Resident wins: the entry keeps its own fields, the arriving ones land on the connection."""
    registry = RegisterRegistry()
    registry.new_user("alice", user_name="Ada")
    resident_store = registry.user_items.get("alice")["store"]
    registry.new_page("p1", user="sess-1", session_id="sess-1")

    registry.change_connection_user("sess-1", "alice", user_name="Lovelace")

    entry = registry.user_items.get("alice")
    assert entry["user_name"] == "Ada"
    assert entry["store"] is resident_store
    assert entry["connections"] == {"sess-1"}
    assert registry.connection_items.get("sess-1")["user_name"] == "Lovelace"
    assert "sess-1" not in registry.user_items


def test_a_login_on_an_unknown_connection_is_an_explicit_error() -> None:
    registry = RegisterRegistry()
    try:
        registry.change_connection_user("ghost", "alice")
    except KeyError as error:
        assert "ghost" in str(error)
    else:
        raise AssertionError("an unknown connection must raise")
