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

"""RegisterRegistry tests: generic registers, the extension seam, lifecycle."""

from __future__ import annotations

import pytest

from genro_asgi.spa import Register, RegisterRegistry


def test_generic_registers_exist_with_ratified_indexes() -> None:
    registry = RegisterRegistry()
    assert isinstance(registry.user_items, Register)
    assert registry.user_items.name == "user_items"
    assert registry.user_items.index_attrs == ()
    assert registry.page_items.name == "page_items"
    assert registry.page_items.index_attrs == ("user", "session_id", "root_page_id")


def test_generic_registers_are_stable_references() -> None:
    registry = RegisterRegistry()
    registry.user_items.create("alice")
    assert registry.user_items.get("alice") == {"register_item_id": "alice"}
    assert len(registry.user_items) == 1


def test_new_register_returns_a_hosted_working_register() -> None:
    registry = RegisterRegistry()
    connections = registry.new_register("connections", index_attrs=("user", "session_id"))
    assert isinstance(connections, Register)
    assert connections.name == "connections"
    connections.create("c1", user="alice", session_id="s1")
    assert connections.keys_by("user", "alice") == ["c1"]
    registry.add_index("connections", "root_page_id")
    assert connections.index_attrs == ("user", "session_id", "root_page_id")


def test_new_register_duplicate_name_raises_value_error() -> None:
    registry = RegisterRegistry()
    registry.new_register("connections")
    with pytest.raises(ValueError, match="connections"):
        registry.new_register("connections")


def test_new_register_cannot_shadow_a_generic_register() -> None:
    registry = RegisterRegistry()
    with pytest.raises(ValueError, match="page_items"):
        registry.new_register("page_items")


def test_add_index_on_pages_indexes_a_passthrough_field() -> None:
    registry = RegisterRegistry()
    registry.page_items.create("p1", user="alice", session_id="s1", connection_id="c1")
    registry.page_items.create("p2", user="bob", session_id="s2", connection_id="c2")
    registry.add_index("page_items", "connection_id")
    assert registry.page_items.keys_by("connection_id", "c1") == ["p1"]
    assert registry.page_items.keys_by("connection_id", "c2") == ["p2"]


def test_add_index_unknown_register_raises_key_error() -> None:
    registry = RegisterRegistry()
    with pytest.raises(KeyError):
        registry.add_index("connections", "user")


def test_new_user_duplicate_raises_value_error() -> None:
    registry = RegisterRegistry()
    registry.new_user("alice")
    with pytest.raises(ValueError, match="alice"):
        registry.new_user("alice")


def test_drop_page_cascade_destroys_an_explicit_user_entry() -> None:
    registry = RegisterRegistry()
    registry.new_user("alice", role="admin")
    registry.new_page("p1", user="alice", session_id="s1")
    registry.drop_page("p1")
    assert "alice" not in registry.user_items


def test_new_page_creates_the_user_entry_when_unseen() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="alice", session_id="s1")
    assert "alice" in registry.user_items
    registry.new_page("p2", user="alice", session_id="s1")
    assert len(registry.user_items) == 1


def test_new_page_root_defaults_and_tree_lookup() -> None:
    registry = RegisterRegistry()
    root_a = registry.new_page("a", user="alice", session_id="s1")
    assert root_a["root_page_id"] == "a"
    assert root_a["parent_page_id"] is None
    registry.new_page("a1", user="alice", session_id="s1", root_page_id="a", parent_page_id="a")
    registry.new_page("b", user="alice", session_id="s1")
    assert sorted(registry.page_items.keys_by("root_page_id", "a")) == ["a", "a1"]
    assert registry.page_items.keys_by("root_page_id", "b") == ["b"]
    assert sorted(registry.page_items.keys_by("session_id", "s1")) == ["a", "a1", "b"]


def test_new_page_child_without_root_raises_value_error() -> None:
    registry = RegisterRegistry()
    registry.new_page("a", user="alice", session_id="s1")
    with pytest.raises(ValueError, match="a1"):
        registry.new_page("a1", user="alice", session_id="s1", parent_page_id="a")


def test_new_page_born_fields_and_passthrough() -> None:
    registry = RegisterRegistry()
    page = registry.new_page("p1", user="alice", session_id="s1", connection_id="c1")
    assert page["avatar_key"] == "root"
    assert page["data"] is None
    assert page["pending_changes"] == []
    assert page["store_subscriptions"] == set()
    assert page["table_subscriptions"] == set()
    assert page["connection_id"] == "c1"
    page["pending_changes"].append("x")
    other = registry.new_page("p2", user="bob", session_id="s2")
    assert other["pending_changes"] == []
    registry.add_index("page_items", "connection_id")
    assert registry.page_items.keys_by("connection_id", "c1") == ["p1"]


def test_new_page_avatar_key_is_explicit_when_given() -> None:
    registry = RegisterRegistry()
    page = registry.new_page("p1", user="alice", session_id="s1", avatar_key="admin")
    assert page["avatar_key"] == "admin"


def test_update_page_merges_and_reindexes() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="alice", session_id="s1")
    page = registry.update_page("p1", session_id="s2", label="home")
    assert page["label"] == "home"
    assert registry.page_items.keys_by("session_id", "s2") == ["p1"]
    assert registry.page_items.keys_by("session_id", "s1") == []


def test_drop_page_cascades_only_on_the_last_page() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="alice", session_id="s1")
    registry.new_page("p2", user="alice", session_id="s1")
    dropped = registry.drop_page("p1")
    assert dropped["user"] == "alice"
    assert "alice" in registry.user_items
    registry.drop_page("p2")
    assert "alice" not in registry.user_items
    assert len(registry.page_items) == 0


def test_drop_user_removes_every_page_of_that_user() -> None:
    registry = RegisterRegistry()
    registry.new_page("p1", user="alice", session_id="s1")
    registry.new_page("p2", user="alice", session_id="s1")
    registry.new_page("p3", user="bob", session_id="s2")
    registry.drop_user("alice")
    assert "alice" not in registry.user_items
    assert registry.page_items.keys_by("user", "alice") == []
    assert registry.page_items.keys_by("user", "bob") == ["p3"]
    assert "bob" in registry.user_items


def test_drop_user_unknown_raises_key_error() -> None:
    registry = RegisterRegistry()
    with pytest.raises(KeyError):
        registry.drop_user("alice")
