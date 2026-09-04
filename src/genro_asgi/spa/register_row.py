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

"""The three register rows as classes: a ``dict`` each, carrying what it knows of itself.

A row is still a dict — ``row["field"]`` reads and writes as it always did,
the parcel pickles a plain dict built from it, the census serialises it, the
hosted site receives it as the daemon's item — but the class says what the
worker used to hard-code about the row (#59, block 3):

- ``default_fields``: what the row is born with beside what the caller passes
  (the row's own ``item_lock`` for every kind);
- ``fields_left_behind``: what the parcel does NOT carry — the reserved id, the
  edges the folder already says, the lock, and the live objects bound to the
  Bags of the process the row lives in, which the birth on the other side
  makes anew;
- ``fields_replayed``: what travels in the parcel but cannot be passed to the
  birth, and ``replay_fields`` puts it back on the row once it exists;
- ``announcement_fields``: what the ``new_page`` worker event carries beside
  the identities.

A consumer subclasses a row and names it on its registry
(``RegisterRegistry.page_row_class`` and siblings); the worker asks the row and
knows nothing of the fields. ``PageRow`` still seeds the genropy fields —
the queue and its index, the user view, the deposits, the three subscription
sets — for as long as that machinery stays in the core.
"""

from __future__ import annotations

import threading
from typing import Any

__all__ = ["ConnectionRow", "PageRow", "RegisterRow", "UserRow"]


class RegisterRow(dict):
    """One register row: a dict born with its defaults, then the caller's fields.

    Args:
        fields: what the caller passes; wins over ``default_fields``.
    """

    #: What the parcel leaves behind: the reserved id and the row's own lock.
    fields_left_behind: frozenset[str] = frozenset({"register_item_id", "item_lock"})
    #: What travels but is put back after the birth, in order.
    fields_replayed: tuple[str, ...] = ()

    def __init__(self, fields: dict[str, Any] | None = None) -> None:
        super().__init__(self.default_fields())
        if fields:
            self.update(fields)

    def default_fields(self) -> dict[str, Any]:
        """The fields the row is born with: a fresh lock, exclusive and re-entrant."""
        return {"item_lock": threading.RLock()}

    def replay_fields(self, registry: Any, fields: dict[str, Any]) -> None:
        """Put back what travelled and could not be passed to the birth: nothing here."""

    def announcement_fields(self) -> dict[str, Any]:
        """What the birth announces beside the identities: nothing here."""
        return {}


class UserRow(RegisterRow):
    """The user's row: the top of the chain. Its parcel is the store alone."""


class ConnectionRow(RegisterRow):
    """The connection's row: the parcel leaves its two edges behind, the folder says them."""

    fields_left_behind = RegisterRow.fields_left_behind | {"user", "pages"}


class PageRow(RegisterRow):
    """The page's row, with the genropy fields for as long as they stay in the core.

    Born with an empty ``datachanges`` queue and its ``datachanges_idx`` at
    zero, ``user_view`` None until the first ``subscribe_store_path``, an empty
    ``dbevents`` list and the three empty subscription sets. The parcel leaves
    behind the edge to the connection and the two live objects; the three sets
    travel and are subscribed again on the woken row, so the page wakes
    capturing what it captured before it went to the deposit.
    """

    fields_left_behind = RegisterRow.fields_left_behind | {"connection_id", "user_view", "dbevents"}
    fields_replayed = ("subscribed_paths", "store_subscriptions", "table_subscriptions")

    def default_fields(self) -> dict[str, Any]:
        return {
            **super().default_fields(),
            "datachanges": [],
            "datachanges_idx": 0,
            "user_view": None,
            "dbevents": [],
            "subscribed_paths": set(),
            "store_subscriptions": set(),
            "table_subscriptions": set(),
        }

    def replay_fields(self, registry: Any, fields: dict[str, Any]) -> None:
        """Subscribe again what the parcel carried: tables, store prefixes, user-store prefixes.

        Args:
            registry: the registry the row lives in — the user-store prefixes
                go through its ``subscribe_store_path``, which builds the view.
            fields: the replayed fields as the parcel carried them.
        """
        for table in fields.get("table_subscriptions", ()):
            self["table_subscriptions"].add(table)
        for prefix in fields.get("subscribed_paths", ()):
            self["subscribed_paths"].add(prefix)
        for prefix in fields.get("store_subscriptions", ()):
            registry.subscribe_store_path(self["register_item_id"], prefix)

    def announcement_fields(self) -> dict[str, Any]:
        """The tables this page subscribes: what the vertex rebuilds its index from."""
        return {"table_subscriptions": sorted(self["table_subscriptions"])}
