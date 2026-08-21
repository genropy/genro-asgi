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

"""RegisterRegistry: the register of registers.

One host holding named :class:`Register` instances. The core creates the three
primary registers of the worker world (legacy origin, the rich-content ones)
and nothing else: ``user_items`` (keyed by user, no secondary index),
``connection_items`` (keyed by the connection id, no secondary index) and
``page_items`` (keyed by page_id, indexed by ``connection_id`` and
``root_page_id`` — query dimensions of the page forest, not edges of the
ownership tree). The ``_items`` suffix is the ratified
naming rule: the name says the map and the level — naked ``users``/``pages``
are banned
because the commander world will host its own thin routing registers
(``user_worker_map``, ``worker_roster``, ...) and the word alone must tell
them apart.

**Semantic minimum vs passthrough.** The core assigns meaning to exactly the
fields it indexes and cascades on; every other field a caller passes is stored
verbatim and never interpreted. A downstream layer can therefore enrich a page
row with its own data (``connection_id``, a socket handle, whatever it owns)
without the core learning about it.

**The ownership chain — the tree LIVES IN THE ITEMS.** A page belongs to a
CONNECTION, and a connection belongs to a user: page → connection → user.
Downwards the edges are sets carried by the items themselves — a user entry
carries ``connections``, a connection row carries ``pages``; upwards they are
the parent key each child already holds — a page row's ``connection_id``, a
connection row's ``user``. Every lifecycle mutator writes both directions in
the same gesture, so the two can never disagree. A page row stores NO ``user``
label: the owner is DERIVED by walking up (``page_user``), and what is
derived cannot diverge. The connection row is born GUEST — its ``user`` is
``GUEST_PREFIX`` + the connection id, the name itself carrying the guest rule —
and the login is a label mutation on that live row, never a re-key.

**The extension seam.** ``new_register(name, index_attrs=())`` creates, hosts
and *returns* the register: the caller keeps the reference — the same graft
pattern as the site grammar, no magic attribute access, no by-name getter.
Only ``user_items``, ``connection_items`` and ``page_items`` are exposed as
properties, because only they are stable core API. A consumer that needs an
index the core did not declare calls ``add_index(register_name, attr)`` and the
register rebuilds.

**Lifecycle vocabulary.** ``new_user``/``new_connection``/``new_page``/
``update_page``/``change_connection_user``/``drop_page``/``drop_connection``/
``drop_user`` are the only supported way to move the three generic registers
through their life: they hold the root conventions of a page forest and the
cascades along the chain. The cascades live in code, never in a declarative
table.

**The login is a mutation.** ``change_connection_user`` re-labels a live
connection onto the logged-in user and moves its id between the two users'
``connections`` sets, re-attaching each page's ``user_view`` to the new
owner's store. The pages need no re-labelling — their owner was never written
down. Nothing is re-keyed and nothing is re-born: keys, live stores and
collectors survive the login. The old user is dropped only once its
``connections`` set is empty. The one exception is the anonymous entry claiming
its first real identity: there the user item itself is TRANSFERRED onto the new
key, store included — see ``change_connection_user`` for the rule and its two
boundaries.

**The cascade discipline, legacy verbatim.** Bringing into being climbs the
chain: ``new_page`` creates the connection when unseen and the user when
unseen. Demolition climbs it only ONCE, from the originating drop —
``drop_page`` takes the connection with the last page of it, ``drop_connection``
takes the user with its last connection — and every descending drop passes
``cascade=False``, so the demolition never climbs back up the branch it is
already tearing down. Both "last one" checks read the emptied set on the parent
item; the descending walks iterate a COPY of it, since each drop discards from
the very set being walked.

**The live stores.** A user row carries ``store``, a live Bag; a page row
carries its own ``store`` plus ``collector``, a :class:`DataChangeCollector`
on that store born FILTERED AND EMPTY: a write is captured only under a prefix
the page has subscribed, mirrored on the row's ``subscribed_paths``. The
explicit deposit (``collector.append``) bypasses the filter and always lands.
A page interested in part of its
user's store gets ``user_view``: a second collector attached to the OWNER
USER's Bag and filtered on ``store_subscriptions``, created lazily at the
first ``subscribe_store_path`` and widened by the next ones. That view IS the
API — a write into the user store is found by every interested page in its own
collector, with no smear loop and no offset machinery. What makes it possible
is usersticky: all the pages of a user live in the same process as the user's
store.

Collectors are attached and detached by the lifecycle: ``drop_page`` detaches
both of a page's collectors, and ``drop_connection``/``drop_user`` detach those
of every page they cascade over. A detached collector keeps its pending changes
— dropping the row is what discards them.

Impossible cases are explicit errors: a duplicate register name raises
ValueError, an unknown register name raises KeyError.
"""

from __future__ import annotations

import time
from typing import Any

from genro_bag import Bag
from genro_bag.datachange import DataChangeCollector

from ..session.session import Session
from .register import Register

__all__ = ["GUEST_PREFIX", "RegisterRegistry"]

#: The reserved prefix that names an anonymous user — the daemon's own
#: convention (siteregister.py:716-717), restored so the NAME carries the
#: guest rule and a consumer minting its own ``guest_<id>`` needs no
#: translation layer. ``change_connection_user`` refuses a target carrying it:
#: nobody can log in as a guest.
GUEST_PREFIX = "guest_"


class RegisterRegistry:
    """A host of named registers, with the two generic ones built in."""

    def __init__(self) -> None:
        """Create the host with the three primary registers of the chain."""
        self._registers: dict[str, Register] = {
            "user_items": Register("user_items"),
            "connection_items": Register("connection_items"),
            "page_items": Register(
                "page_items",
                index_attrs=("connection_id", "root_page_id"),
            ),
        }

    @property
    def user_items(self) -> Register:
        """The primary register of users, keyed by user."""
        return self._registers["user_items"]

    @property
    def connection_items(self) -> Register:
        """The primary register of connections, keyed by the connection id."""
        return self._registers["connection_items"]

    @property
    def page_items(self) -> Register:
        """The primary register of pages, keyed by page_id."""
        return self._registers["page_items"]

    def new_register(self, name: str, index_attrs: tuple[str, ...] = ()) -> Register:
        """Create a register named ``name``, host it and return it.

        The returned reference is how the caller reaches its own register:
        there is no by-name getter. Raises ``ValueError`` if ``name`` is
        already hosted.
        """
        if name in self._registers:
            raise ValueError(f"register already exists: {name!r}")
        register = Register(name, index_attrs=index_attrs)
        self._registers[name] = register
        return register

    def add_index(self, register_name: str, attr: str) -> None:
        """Add a secondary index on ``attr`` to a hosted register.

        Delegates to the register's own ``add_index`` (idempotent, rebuilds
        from the existing rows). Raises ``KeyError`` if ``register_name`` is
        not hosted.
        """
        self._registers[register_name].add_index(attr)

    def new_store(self) -> Any:
        """The store factory: the birth of every row's live store.

        A consumer whose rows hold its own store type overrides this alone —
        nothing else in the machinery names the concrete class, and a store
        travels the move pickled, whole.
        """
        return Bag()

    def new_collector(self, store: Any, paths: set[str] | None = None) -> Any:
        """The collector factory: the capture attached to a row's store.

        One seam for the three attach points — a page's own collector, born
        filtered on an empty prefix set, the ``user_view`` born of the first
        subscription, the re-attach of the login — so a consumer pairing its
        own store type overrides the capture with it.
        """
        return DataChangeCollector(store, paths=paths)

    def new_user(self, user: str, **fields: Any) -> dict[str, Any]:
        """Create the entry of ``user`` in the ``user_items`` register.

        The entry is born with a live ``store`` Bag unless the caller supplies
        one — a moved user arrives with its own, already hydrated — and with an
        empty ``connections`` set, the downward edge of the tree, which callers
        never supply: it is filled by ``new_connection``.

        It is born STAMPED: ``last_refresh_ts`` carries the server's own clock
        from birth, so the expiry sweep needs no fallback to a start time. A
        supplied value is honoured — a moved row keeps the stamp it travelled
        with.

        Raises ``ValueError`` if the user already has an entry — page
        creation calls this only for a user it has not seen.
        """
        if "store" not in fields:
            fields["store"] = self.new_store()
        fields.setdefault("last_refresh_ts", time.time())
        return self.user_items.create(user, connections=set(), **fields)

    def new_connection(
        self, connection_id: str, user: str | None = None, **fields: Any
    ) -> dict[str, Any]:
        """Create the connection row of ``connection_id``, born guest by default.

        ``user is None`` means the anonymous reception: the row takes
        ``GUEST_PREFIX`` + the connection id as its user — the daemon's own
        naming, so the name itself says guest — and the guest user entry is
        brought into being with it, a user entry like any other, with its own
        live store. A consumer that mints its own ``guest_<id>`` passes it
        explicitly and falls under the same rule with no translation.

        The row is born with a live ``store`` Bag unless the caller supplies one
        — a moved connection arrives with its own, already hydrated — like every
        other row of the tree. That store is SERVER-SIDE ONLY: no view, no
        collector, nothing of it is ever replicated with the browser.

        The row is born with an empty ``pages`` set and its id joins the owner
        entry's ``connections``: both directions of the edge in one gesture. It
        is born STAMPED with the server's clock, like every row of the chain.

        Raises ``ValueError`` if the connection already has a row.
        """
        if user is None:
            user = GUEST_PREFIX + connection_id
        if "store" not in fields:
            fields["store"] = self.new_store()
        fields.setdefault("last_refresh_ts", time.time())
        if user not in self.user_items:
            self.new_user(user)
        connection = self.connection_items.create(connection_id, user=user, pages=set(), **fields)
        self.user_items.get(user)["connections"].add(connection_id)
        return connection

    def new_page(
        self,
        page_id: str,
        *,
        user: str,
        connection_id: str,
        root_page_id: str | None = None,
        parent_page_id: str | None = None,
        avatar_key: str = Session.ROOT_AVATAR_KEY,
        data: Any = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Create a page row, defaulting the root conventions of its tree.

        ``parent_page_id is None`` means the page is a root, and a root's
        ``root_page_id`` defaults to its own ``page_id`` — so
        ``keys_by("root_page_id", X)`` returns the whole tree, root included.
        A child (``parent_page_id`` set) without a ``root_page_id`` is an
        impossible case and raises ``ValueError``.

        ``connection_id`` names the connection the page hangs from — the
        daemon's own word for it. The chain is brought into being from the
        bottom up: the connection row when unseen, and with it the user
        entry when unseen. ``user`` drives that cascade ONLY — it is never
        stored on the page row, whose owner is derived by ``page_user``.
        The new page id joins its connection row's ``pages``.

        Rows are born with a live ``store`` Bag under a collector FILTERED AND
        EMPTY — nothing of the page's own store is captured until the page
        subscribes a prefix — an empty ``dbevents`` list and empty subscription
        sets, ``subscribed_paths`` among them: the mirror of that collector's
        prefix set, the value a move packages. ``user_view`` stays None until
        the first ``subscribe_store_path``. The row is born STAMPED with the
        server's clock, like the connection and the user above it. Every other
        keyword passes through verbatim (schemaless).

        The store may carry a SECOND subscription this registry neither creates
        nor removes: the worker's table-cache observer, which needs the worker's
        own index and is therefore attached — and unsubscribed — up there.
        """
        if parent_page_id is not None and root_page_id is None:
            raise ValueError(f"page {page_id!r} has a parent but no root_page_id")
        if root_page_id is None:
            root_page_id = page_id
        if user not in self.user_items:
            self.new_user(user)
        if connection_id not in self.connection_items:
            self.new_connection(connection_id, user=user)
        store = fields.pop("store", None)
        if store is None:
            store = self.new_store()
        fields.setdefault("last_refresh_ts", time.time())
        page = self.page_items.create(
            page_id,
            connection_id=connection_id,
            root_page_id=root_page_id,
            parent_page_id=parent_page_id,
            avatar_key=avatar_key,
            data=data,
            store=store,
            collector=self.new_collector(store, paths=set()),
            user_view=None,
            dbevents=[],
            subscribed_paths=set(),
            store_subscriptions=set(),
            table_subscriptions=set(),
            **fields,
        )
        self.connection_items.get(connection_id)["pages"].add(page_id)
        return page

    def page_user(self, page_id: str) -> str:
        """The user a page belongs to, derived by walking up its chain.

        Page row → ``connection_id`` → connection row → ``user``. Nothing is
        stored twice, so nothing can go stale. Raises ``KeyError`` if the page
        is not registered.
        """
        page = self.page_items.get(page_id)
        if page is None:
            raise KeyError(f"page_user: unknown page {page_id!r}")
        return self.connection_items.get(page["connection_id"])["user"]

    def change_connection_user(
        self, connection_id: str, user: str, **fields: Any
    ) -> dict[str, Any]:
        """Move a live connection from its current user to ``user`` — a mutation.

        The login re-labels; it never re-keys. The connection row and every page
        row of it keep their keys and their live objects: only the ``user``
        label changes, on the connection alone — the pages have none to change,
        their owner being derived through this very row.

        **The guest item follows its first real identity.** This is a
        declared divergence from the daemon, which built the new user fresh
        and let the guest die with its data. When the connection is still
        anonymous (its user name carries ``GUEST_PREFIX``, the born-guest rule)
        and the target user has no
        entry yet, the entry is TRANSFERRED: only the key changes, the values —
        the live store above all — are conserved. The store being the same Bag
        object, every attached ``user_view`` keeps capturing with nothing to
        re-attach, and the ``connections`` set travels inside the entry already
        naming this connection. Two boundaries hold it in place: a RESIDENT wins
        — a login onto a user that already exists leaves that entry and its
        store the truth, and the orphaned guest still dies with its data — and
        only an ANONYMOUS item transfers: a real user's entry never changes key.

        On the non-transfer paths the connection id moves between the two users'
        ``connections`` sets in the same gesture, the destination user entry is
        brought into being when unseen with its own live store, and each page
        that watches its owner's store has its ``user_view`` re-attached: the
        old collector is detached and a new one is created on the NEW owner's
        Bag with the very same ``store_subscriptions`` prefixes, then
        re-deposited with everything the old one still held. The view is
        re-attached, never drained — a change captured before the login is still
        pending after it. The previous user leaves only when its ``connections``
        set came out empty: this was its last connection, and its store dies
        with it.

        ``GUEST_PREFIX`` is RESERVED: a login target carrying it raises
        ``ValueError`` — nobody can log in as a guest. The ban lives here and
        not at ``new_connection``, which legitimately receives an explicit
        ``guest_<id>`` from a consumer declaring its own anonymous connection.

        Returns the mutated connection row; raises ``KeyError`` if
        ``connection_id`` is not registered.
        """
        if user.startswith(GUEST_PREFIX):
            raise ValueError(
                f"change_connection_user: {user!r} — "
                f"{GUEST_PREFIX!r} is reserved, nobody logs in as a guest"
            )
        connection = self.connection_items.get(connection_id)
        if connection is None:
            raise KeyError(f"change_connection_user: unknown connection {connection_id!r}")
        previous_user = connection["user"]
        if user not in self.user_items and previous_user.startswith(GUEST_PREFIX):
            entry = self.user_items.drop(previous_user)
            del entry["register_item_id"]
            self.user_items.create(user, **{**entry, **fields})
            return self.connection_items.update(connection_id, user=user, **fields)
        if user not in self.user_items:
            self.new_user(user, **fields)
        user_store = self.user_items.get(user)["store"]
        connection = self.connection_items.update(connection_id, user=user, **fields)
        self.user_items.get(previous_user)["connections"].discard(connection_id)
        self.user_items.get(user)["connections"].add(connection_id)
        for page_id in connection["pages"]:
            page = self.page_items.get(page_id)
            view = page["user_view"]
            if view is not None:
                view.detach()
                fresh = self.new_collector(user_store, paths=set(page["store_subscriptions"]))
                for change in view.changes:
                    fresh.append(change)
                page["user_view"] = fresh
        if not self.user_items.get(previous_user)["connections"]:
            self.user_items.drop(previous_user)
        return connection

    def subscribe_store_path(self, page_id: str, prefix: str) -> dict[str, Any]:
        """Subscribe a page to a prefix of its user's store, returning its row.

        The first subscription creates ``user_view`` — a collector on the
        owner user's store Bag filtered on that prefix; the next ones widen it
        through ``subscribe_path``. Raises ``KeyError`` if the page is unknown.
        """
        page = self.page_items.get(page_id)
        if page is None:
            raise KeyError(f"subscribe_store_path: unknown page {page_id!r}")
        page["store_subscriptions"].add(prefix)
        view = page["user_view"]
        if view is None:
            user_store = self.user_items.get(self.page_user(page_id))["store"]
            page["user_view"] = self.new_collector(user_store, paths={prefix})
        else:
            view.subscribe_path(prefix)
        return page

    def update_page(self, page_id: str, **fields: Any) -> dict[str, Any]:
        """Merge ``fields`` into a page row; ``KeyError`` if it is not there."""
        return self.page_items.update(page_id, **fields)

    def detach_page(self, page: dict[str, Any]) -> None:
        """Stop the capture of a page row: its own collector and its user view.

        The two collectors are all this knows about: a worker watching the store
        for its own purposes unsubscribes its own observer.
        """
        page["collector"].detach()
        if page["user_view"] is not None:
            page["user_view"].detach()

    def drop_page(self, page_id: str, cascade: bool = True) -> dict[str, Any]:
        """Drop a page row, taking its connection with it if it was the last one.

        Both collectors of the page are detached first: the row leaves the
        register with nothing still capturing into it, and its id leaves its
        connection's ``pages`` — the edge dies with the row. ``cascade=False``
        is how a descending demolition drops a page without climbing back up
        the branch it is already tearing down.

        Returns the dropped page row; raises ``KeyError`` if ``page_id`` is
        not registered.
        """
        page = self.page_items.drop(page_id)
        self.detach_page(page)
        connection = self.connection_items.get(page["connection_id"])
        connection["pages"].discard(page_id)
        if cascade and not connection["pages"]:
            self.drop_connection(connection["register_item_id"])
        return page

    def drop_connection(self, connection_id: str, cascade: bool = True) -> dict[str, Any]:
        """Drop a connection row and every page of it, up to the user.

        The pages go down first — a copy of ``pages`` is walked, since each drop
        discards from that very set — each with ``cascade=False``: they must not
        try to take this connection away a second time. The connection then
        leaves its user's ``connections`` and, with ``cascade``, takes the user
        along when that set comes out empty.

        Returns the dropped connection row; raises ``KeyError`` if
        ``connection_id`` is not registered.
        """
        connection = self.connection_items.get(connection_id)
        if connection is None:
            raise KeyError(f"drop_connection: unknown connection {connection_id!r}")
        for page_id in list(connection["pages"]):
            self.drop_page(page_id, cascade=False)
        self.connection_items.drop(connection_id)
        user_entry = self.user_items.get(connection["user"])
        user_entry["connections"].discard(connection_id)
        if cascade and not user_entry["connections"]:
            self.user_items.drop(connection["user"])
        return connection

    def drop_user(self, user: str) -> dict[str, Any]:
        """Drop a user entry and every connection of that user, pages included.

        A copy of ``connections`` is walked — each drop discards from that very
        set — and every connection goes down with ``cascade=False``: this user
        is already being demolished and must not be dropped twice. The pages
        travel with their collectors detached — the user view of each dies with
        the store it was watching.

        Returns the dropped user entry; raises ``KeyError`` if ``user`` has
        no entry.
        """
        entry = self.user_items.get(user)
        if entry is None:
            raise KeyError(f"drop_user: unknown user {user!r}")
        for connection_id in list(entry["connections"]):
            self.drop_connection(connection_id, cascade=False)
        return self.user_items.drop(user)
