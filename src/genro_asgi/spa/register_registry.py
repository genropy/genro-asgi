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

One host holding named :class:`Register` instances. The core creates the two
primary registers of the worker world (legacy origin, the rich-content ones)
and nothing else: ``user_items`` (keyed by user, no secondary index) and
``page_items`` (keyed by page_id, indexed by ``user``, ``session_id`` and
``root_page_id``). The ``_items`` suffix is the ratified naming rule: the
name says the map and the level — naked ``users``/``pages`` are banned
because the commander world will host its own thin routing registers
(``user_worker_map``, ``worker_roster``, ...) and the word alone must tell
them apart.

**Semantic minimum vs passthrough.** The core assigns meaning to exactly the
fields it indexes and cascades on; every other field a caller passes is stored
verbatim and never interpreted. A downstream layer can therefore enrich a page
row with its own data (``connection_id``, a socket handle, whatever it owns)
without the core learning about it.

**The extension seam.** ``new_register(name, index_attrs=())`` creates, hosts
and *returns* the register: the caller keeps the reference — the same graft
pattern as the site grammar, no magic attribute access, no by-name getter.
Only ``user_items`` and ``page_items`` are exposed as properties, because only
they are stable core API. A consumer that needs an index the core did not
declare calls ``add_index(register_name, attr)`` and the register rebuilds.

**Lifecycle vocabulary.** ``new_user``/``new_page``/``update_page``/
``drop_page``/``drop_user`` are the only supported way to move the two
generic registers through their life: they hold the root conventions of a
page forest and the cascades between users and pages. The cascades live in
code, never in a declarative table — there are two of them and they read
better as the two lines they are.

Impossible cases are explicit errors: a duplicate register name raises
ValueError, an unknown register name raises KeyError.
"""

from __future__ import annotations

from typing import Any

from ..session.session import Session
from .register import Register

__all__ = ["RegisterRegistry"]


class RegisterRegistry:
    """A host of named registers, with the two generic ones built in."""

    def __init__(self) -> None:
        """Create the host with the ``user_items`` and ``page_items`` registers."""
        self._registers: dict[str, Register] = {
            "user_items": Register("user_items"),
            "page_items": Register(
                "page_items", index_attrs=("user", "session_id", "root_page_id")
            ),
        }

    @property
    def user_items(self) -> Register:
        """The primary register of users, keyed by user."""
        return self._registers["user_items"]

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

    def new_user(self, user: str, **fields: Any) -> dict[str, Any]:
        """Create the entry of ``user`` in the ``user_items`` register.

        Raises ``ValueError`` if the user already has an entry — page
        creation calls this only for a user it has not seen.
        """
        return self.user_items.create(user, **fields)

    def new_page(
        self,
        page_id: str,
        *,
        user: str,
        session_id: str,
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

        The user entry is created here when unseen. Rows are born with an
        empty ``pending_changes`` list and empty subscription sets; every
        other keyword passes through verbatim (schemaless).
        """
        if parent_page_id is not None and root_page_id is None:
            raise ValueError(f"page {page_id!r} has a parent but no root_page_id")
        if root_page_id is None:
            root_page_id = page_id
        if user not in self.user_items:
            self.new_user(user)
        return self.page_items.create(
            page_id,
            user=user,
            session_id=session_id,
            root_page_id=root_page_id,
            parent_page_id=parent_page_id,
            avatar_key=avatar_key,
            data=data,
            pending_changes=[],
            store_subscriptions=set(),
            table_subscriptions=set(),
            **fields,
        )

    def update_page(self, page_id: str, **fields: Any) -> dict[str, Any]:
        """Merge ``fields`` into a page row; ``KeyError`` if it is not there."""
        return self.page_items.update(page_id, **fields)

    def drop_page(self, page_id: str) -> dict[str, Any]:
        """Drop a page row, and its user entry with it if it was the last page.

        Returns the dropped page row; raises ``KeyError`` if ``page_id`` is
        not registered.
        """
        page = self.page_items.drop(page_id)
        user = page["user"]
        if not self.page_items.keys_by("user", user):
            self.user_items.drop(user)
        return page

    def drop_user(self, user: str) -> dict[str, Any]:
        """Drop a user entry and every page of that user.

        Returns the dropped user entry; raises ``KeyError`` if ``user`` has
        no entry.
        """
        for page_id in self.page_items.keys_by("user", user):
            self.page_items.drop(page_id)
        return self.user_items.drop(user)
