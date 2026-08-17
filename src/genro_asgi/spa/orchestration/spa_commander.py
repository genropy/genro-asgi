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

"""SpaCommander: the vertex — who exists, where he is, and what was decided about him.

The one object that knows the whole picture. It owns three indexes and nothing
below it owns a copy of them: a group knows where ITS users live, a worker knows
who is in ITS memory, and only here is there an answer to "who is this cid" or
"is this user in the freezer".

**The three indexes.** ``connection_user_map`` says whose a cid is — and it is
ETERNAL, because the cookie is: a browser that comes back a week later is the
same person, whatever happened to the process it used to talk to.
``page_connection_map`` says which connection a page belongs to, and that never
changes for the life of the page. ``user_map`` is the anagraph, one row per
identity:

    user_map[user] = {group, frozen, on_hold, occupancy_percent,
                      pending_dbevents, pending_datachanges}

Reading a row's meaning goes through the predicates (``user_is_frozen``), and
``on_hold`` is not read at all: it is RAISED, as ``UserOnHold``, by the one step
that resolves an identity. So a caller cannot forget to look at it.

**Whoever shows up is a user in full.** The front mints the cookie and keeps no
state; the vertex mints the ROWS. At the first request of a cid never seen, and
BEFORE anything descends, ``resolve_user`` writes the identity (``guest_<cid>``)
and its row: routing somebody the indexes do not carry is exactly what cannot be
done, so the writing comes first. The announcements the reception then sends
upward (``new_user``, ``new_connection``) find the work already done, and are
idempotent no-ops by design.

**Two writers, both here.** The minting above is one; the other is the fold — the
chain of the envelope, which turns what the processes announce into these
indexes, one announcement at a time, synchronously. The mutators live on this
class because the data does, and the chain calls them by name.

**The freezer is not on the ladder.** A worker parks a user's state on disk
itself and announces it; the vertex only writes the mark. The one time the vertex
touches the deposit is when nobody below can: pruning the traces of a wild death
(what a dead process left behind is not to be trusted, so it is discarded and
counted) and reaping what expired. Both go through the ``FreezeHandler``, which
is the only thing in the project that talks to the filesystem.

**Every order leaves a row.** ``log_order`` writes who decided, what, on whom,
with which numbers in front of them, and how it ended — one line per order, on a
file of its own, because the day something goes wrong that file is the only
account of what the machine chose to do. A wild death gets a row too, and it is
nobody's decision.

**The counters are aggregate, so they are here.** How many parcels were
discarded, how much was waiting for somebody who is gone: numbers the level below
cannot know because each of them sees only its own share.
"""

from __future__ import annotations

import logging
from collections import Counter
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from .envelope_handler import CommanderEnvelopeHandler
from .exceptions import UserOnHold
from .freeze_handler import FreezeHandler
from .global_register import GlobalRegister

#: What a user with no name of his own is called: the prefix plus his cid. The
#: name itself carries the rule — whoever reads it knows nobody logged in here.
#: Redefined with its ratified value rather than imported: the machine it is
#: shared with dies at the cutover.
GUEST_PREFIX = "guest_"

#: The logger the orchestration log is written on, whether or not a file is
#: attached to it.
ORDERS_LOGGER_NAME = "genro_asgi.orchestration.orders"

__all__ = ["GUEST_PREFIX", "ORDERS_LOGGER_NAME", "SpaCommander"]


class SpaCommander:
    """The vertex of the pool: the indexes, the minting, the master store, the log.

    Args:
        frozen_users_path: the deposit root — the same one the workers are given,
            since a parcel written on one side is read on the other.
        orchestration_log_path: where the log of the orders goes; None keeps them
            on the logger alone, which is what a test wants.
        orchestration_log_max_bytes: the size at which that file rotates.
        orchestration_log_backup_count: how many rotations are kept.
    """

    def __init__(
        self,
        frozen_users_path: str | Path,
        *,
        orchestration_log_path: str | Path | None = None,
        orchestration_log_max_bytes: int = 10 * 1024 * 1024,
        orchestration_log_backup_count: int = 5,
    ) -> None:
        self.freeze_handler = FreezeHandler(frozen_users_path)
        self.global_register = GlobalRegister()
        self.envelope_handler = CommanderEnvelopeHandler(self)
        #: Where the whole machine stands: ``running``, ``saturated`` (no room
        #: for a newcomer anywhere) or ``broken``. Written by the check of the
        #: resources, which arrives with the heartbeat.
        self.state = "running"
        self.counters: Counter[str] = Counter()
        self._user_map: dict[str, dict[str, Any]] = {}
        self._connection_user_map: dict[str, str] = {}
        self._page_connection_map: dict[str, str] = {}
        self._logger = logging.getLogger(__name__)
        self._orders_logger = self._build_orders_logger(
            orchestration_log_path,
            orchestration_log_max_bytes,
            orchestration_log_backup_count,
        )

    @property
    def user_map(self) -> dict[str, dict[str, Any]]:
        """The anagraph: one row per identity the machine knows.

        Returns:
            The live index — read it through the predicates, and leave the
            writing to the mutators.
        """
        return self._user_map

    @property
    def connection_user_map(self) -> dict[str, str]:
        """Whose each cid is.

        Returns:
            The live index. A cid stays here once written: the cookie outlives
            the process, the placement and the freezer.
        """
        return self._connection_user_map

    @property
    def page_connection_map(self) -> dict[str, str]:
        """Which connection each page belongs to.

        Returns:
            The live index. A page's connection never changes, so a row here is
            written once and only ever removed.
        """
        return self._page_connection_map

    def resolve_user(self, cid: str) -> str:
        """The reception desk: whose cid this is, minting him if he is new.

        Args:
            cid: the identity the cookie carries.

        Returns:
            The user this connection belongs to — an existing identity, or the
            guest just minted for a cid never seen before.

        Raises:
            UserOnHold: the row says this user is between two homes; whoever
                asked for him waits rather than being routed to an address that
                is being emptied.

        Acts on the indexes when the cid or the row is missing: the rows of a
        newcomer are written HERE, before anything descends, because routing
        somebody the indexes do not carry cannot be done. A cid whose row is gone
        — a cookie that outlived it — is minted again, empty: the browser is
        still known, its state is not.
        """
        user = self._connection_user_map.get(cid)
        if user is None:
            user = f"{GUEST_PREFIX}{cid}"
            self._connection_user_map[cid] = user
            self._logger.info("Vertex: cid %s is new — minted as %s", cid, user)
        if user not in self._user_map:
            self._user_map[user] = self._new_row()
        row = self._user_map[user]
        if row["on_hold"] is not None:
            raise UserOnHold(user, row["on_hold"])
        return user

    def user_is_frozen(self, user: str) -> bool:
        """Whether this user's state is in the freezer rather than in a process.

        Args:
            user: the identity to judge.

        Returns:
            True when the mark is on. An identity with no row at all is not
            frozen — there is nothing of his anywhere.
        """
        row = self._user_map.get(user)
        return bool(row and row["frozen"])

    def hold_user_TBD(self, user: str, cause: str) -> None:
        """Put a user in the waiting room: his next request waits instead of routing.

        Args:
            user: the identity on his way out of the process he lives on.
            cause: what put him there, kept for the log.

        Acts on his row. Setting a hold that is already there is that same state,
        and the cause of the first one stays: it is the one that explains the
        wait.
        """
        row = self._user_map[user]
        if row["on_hold"] is None:
            row["on_hold"] = cause

    def add_page(self, page_id: str, cid: str) -> None:
        """Write which connection a newborn page belongs to.

        Args:
            page_id: the page that was born.
            cid: the connection that asked for it.

        Acts on ``page_connection_map``.
        """
        self._page_connection_map[page_id] = cid

    def drop_page(self, page_id: str) -> None:
        """Forget a page.

        Args:
            page_id: the page that is gone; one already forgotten is that same
                outcome.

        Acts on ``page_connection_map``.
        """
        self._page_connection_map.pop(page_id, None)

    def drop_connection(self, cid: str) -> None:
        """Forget a connection's pages, and keep the connection's identity.

        Args:
            cid: the connection that is gone.

        Acts on ``page_connection_map`` only: the cid stays in
        ``connection_user_map``, because the cookie is eternal and the browser
        that comes back on it is the same person.
        """
        for page_id in self.get_connection_pages_TBD(cid):
            del self._page_connection_map[page_id]

    def drop_user(self, user: str) -> None:
        """Forget an identity whole: his row, his connections, his pages, his waiting.

        Args:
            user: the identity that is gone; one already forgotten is that same
                outcome.

        Acts on all three indexes, and counts what was waiting for him and will
        now never be delivered.
        """
        row = self._user_map.pop(user, None) or {}
        for cid in self.get_user_connections_TBD(user):
            self.drop_connection(cid)
            del self._connection_user_map[cid]
        waiting = len(row.get("pending_dbevents") or ()) + len(
            row.get("pending_datachanges") or ()
        )
        self.record_count_TBD("pendings_lost", waiting)

    def record_user_frozen_TBD(self, user: str, occupancy_percent: float | None) -> None:
        """Write down that a user's state is on disk, and what it is expected to cost.

        Args:
            user: the identity that left his process.
            occupancy_percent: what he occupied where he was, normalised — the
                estimate whoever places him next reads. None leaves the estimate
                as it was, which is the case of a user whose own announcement
                died with the wire.

        Acts on his row: the mark goes on and the wait he may have been in is
        over — his next request is routed by the mark itself.
        """
        row = self._user_map[user]
        row["frozen"] = True
        row["on_hold"] = None
        if occupancy_percent is not None:
            row["occupancy_percent"] = occupancy_percent

    def record_user_adopted_TBD(self, user: str) -> dict[str, list[Any]]:
        """Write down that a user came home from the freezer, and take his waiting off the row.

        Args:
            user: the identity now living in a process again.

        Returns:
            What was waiting for him while he was away, drained from the row —
            its DELIVERY belongs to whoever answers his requests, and arrives
            with the data plane. Nothing fills these slots yet.

        Acts on his row: the mark goes off, the wait is over, the slots are
        emptied.
        """
        row = self._user_map[user]
        row["frozen"] = False
        row["on_hold"] = None
        waiting = {
            "pending_dbevents": row["pending_dbevents"],
            "pending_datachanges": row["pending_datachanges"],
        }
        row["pending_dbevents"] = []
        row["pending_datachanges"] = []
        return waiting

    def purge_users_TBD(self, users: list[str], *, cause: str) -> None:
        """Take these users out of the machine and discard whatever they left on disk.

        Args:
            users: the identities to forget.
            cause: why, for the log — a wild death, or a departure that lost
                somebody on the way.

        Acts on all three indexes and on the deposit: what a process nobody can
        question left behind cannot be trusted, so it goes, counted. Their next
        request finds nothing of them and is a re-login, which is the declared
        price of a death nobody ordered.
        """
        folders = self.freeze_handler.user_folders
        for user in users:
            had_state = self.freeze_handler.user_to_userkey(user) in folders
            if had_state:
                self.freeze_handler.drop_user_folder(user)
                self.record_count_TBD("frozen_users_discarded")
            self.drop_user(user)
            self.log_order(
                "vertex",
                "purge_user",
                user,
                numbers={"had_state": had_state},
                outcome=cause,
            )

    def record_count_TBD(self, name: str, amount: int = 1) -> None:
        """Add to one of the aggregate counters.

        Args:
            name: what is being counted.
            amount: how much to add.

        Acts on ``counters``.
        """
        self.counters[name] += amount

    def log_order(
        self,
        decided_by: str,
        order: str,
        subject: str | None = None,
        *,
        numbers: dict[str, Any] | None = None,
        outcome: str | None = None,
    ) -> None:
        """Write one row of the orchestration log: an order, and what came of it.

        Args:
            decided_by: who decided — a group, a handler, the vertex itself.
            order: what was decided.
            subject: on whom or on what.
            numbers: what the decider had in front of it when it decided.
            outcome: how it ended.

        The row is the account of a decision, and a wild death is written like an
        order nobody gave: whoever reads this file must find every fact that
        changed the shape of the pool.
        """
        self._orders_logger.info(
            "decided_by=%s order=%s subject=%s numbers=%s outcome=%s",
            decided_by,
            order,
            subject,
            numbers,
            outcome,
        )

    def get_user_connections_TBD(self, user: str) -> list[str]:
        """The cids of one user.

        Args:
            user: the identity to look up.

        Returns:
            His connections, as a list taken now: the caller usually goes on to
            drop them, and a view would change under it.
        """
        return [cid for cid, owner in self._connection_user_map.items() if owner == user]

    def get_connection_pages_TBD(self, cid: str) -> list[str]:
        """The pages of one connection.

        Args:
            cid: the connection to look up.

        Returns:
            Its pages, as a list taken now. The index is page → connection, so
            this walks it: pages are few per connection and the walk happens
            when one goes away, never on the way in.
        """
        return [page for page, owner in self._page_connection_map.items() if owner == cid]

    def _new_row(self) -> dict[str, Any]:
        """The row of an identity nobody knows anything about yet."""
        return {
            "group": None,
            "frozen": False,
            "on_hold": None,
            "occupancy_percent": None,
            "pending_dbevents": [],
            "pending_datachanges": [],
        }

    def _build_orders_logger(
        self, path: str | Path | None, max_bytes: int, backup_count: int
    ) -> logging.Logger:
        """The dedicated logger of the orders, with its own file when there is one.

        The file is attached in place of whatever was there: a process has ONE
        vertex, so this logger is this object's, and a second commander in the
        same process — which only a test builds — replaces the first rather than
        writing every row twice.
        """
        logger = logging.getLogger(ORDERS_LOGGER_NAME)
        if path is None:
            return logger
        for attached in list(logger.handlers):
            logger.removeHandler(attached)
            attached.close()
        handler = RotatingFileHandler(
            Path(path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        return logger
