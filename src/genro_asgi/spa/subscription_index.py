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

"""SubscriptionIndex: table subscriptions, both directions, one mutator each.

The dual of "which pages want this table" and "which tables does this page
want" lives in ONE object holding BOTH maps:

- ``table_pages: {table -> set(page_id)}`` — the fan-out direction. A dbevent
  on a table nobody subscribed costs a dict lookup that misses: zero pages,
  zero iteration, zero scan.
- ``page_tables: {page_id -> set(table)}`` — the cleanup and move direction.
  Dropping a page, or packaging it for a move, needs its tables without
  walking every table set.

**The house pattern for a link.** Both directions held together and mutated
only through the named primitives is the shape the surface links take (owner's
decision, 2026-08-06): a derived form would make every commit pay a full scan
of the pages even with zero subscriptions.

**Atomicity by construction.** Nothing outside this class touches the maps;
they mutate only through ``subscribe``, ``unsubscribe`` and ``drop_page``, and
each of the three updates both sides together — there is no window in which
one map knows something the other does not. An empty set is deleted rather
than left behind, so a missing key and an empty set are never both possible.

**The lock is the owner's.** ``lock`` is injected: the worker passes the lock
that already serializes its registry mutations, so an index change and the
row change it belongs to are one critical section. That lock is REENTRANT for
exactly this reason — the caller holds it already when it reaches a primitive.
The commander passes none — its mutations are sync methods on the event loop,
and the invariant that keeps them safe is that the index primitives never
await.

**Readers get copies.** ``pages_for`` and ``tables_for`` hand back a new set:
a fan-out iterating the live set while a subscriber arrives would raise, and
the caller must be free to hold its answer across an await.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Any


class SubscriptionIndex:
    """Bidirectional page/table subscription index with an injectable lock."""

    def __init__(self, lock: AbstractContextManager[Any] | None = None) -> None:
        self.lock = lock
        self.table_pages: dict[str, set[str]] = {}
        self.page_tables: dict[str, set[str]] = {}

    @contextlib.contextmanager
    def guard(self) -> Iterator[None]:
        """The owner's lock if one was injected, otherwise nothing at all."""
        if self.lock is None:
            yield
        else:
            with self.lock:
                yield

    def subscribe(self, page_id: str, table: str) -> None:
        """Add the pair to both maps. Idempotent: sets, not counters."""
        with self.guard():
            self.table_pages.setdefault(table, set()).add(page_id)
            self.page_tables.setdefault(page_id, set()).add(table)

    def unsubscribe(self, page_id: str, table: str) -> None:
        """Remove the pair from both maps. Unknown pair: nothing happens."""
        with self.guard():
            self._forget(page_id, table)

    def drop_page(self, page_id: str) -> None:
        """Forget a page everywhere: its own entry and every table set it sat in."""
        with self.guard():
            for table in list(self.page_tables.get(page_id, ())):
                self._forget(page_id, table)

    def pages_for(self, table: str) -> set[str]:
        """The pages subscribed to a table, as a copy. Unknown table: empty."""
        with self.guard():
            return set(self.table_pages.get(table, ()))

    def tables_for(self, page_id: str) -> set[str]:
        """The tables a page subscribed to, as a copy. Unknown page: empty."""
        with self.guard():
            return set(self.page_tables.get(page_id, ()))

    def _forget(self, page_id: str, table: str) -> None:
        """Drop one pair from both maps, under the caller's guard.

        The only place that empties a set, so the only place that has to keep
        the "no empty set survives" rule.
        """
        pages = self.table_pages.get(table)
        if pages is not None:
            pages.discard(page_id)
            if not pages:
                del self.table_pages[table]
        tables = self.page_tables.get(page_id)
        if tables is not None:
            tables.discard(table)
            if not tables:
                del self.page_tables[page_id]
