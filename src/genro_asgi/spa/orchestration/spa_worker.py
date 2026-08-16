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

"""SpaWorker: the three registers of one process, and the row a request lands on.

A worker holds the users it was given, and for each of them the connections and
the pages under them. That picture lives in three registers — ``user_register``,
``connection_register``, ``page_register`` — and one entry of a register is a
**register item**: the same word the deposit files under, so the thing in memory
and the thing on disk are never two words for one object.

**The tree lives in the items.** A page belongs to a CONNECTION and a connection
to a USER. Downwards the edge is a set the parent carries (a user item's
``connections``, a connection item's ``pages``); upwards it is the parent key the
child already holds (a connection item's ``user``, a page item's
``connection_id``). Both directions are written in the same gesture by ONE
mutator, so they cannot disagree, and a page stores no user label at all: the
owner is derived by walking up, and what is derived cannot go stale.

**The unified row.** A request for a user finds its row ``active`` and is served;
finds it ``frozen`` and the store is pulled back from the deposit first; finds no
row at all and one is added ``frozen``, then pulled the same way. The arrival of
somebody nobody has ever seen and the waking of a hibernated user are the SAME
line of code — the pull simply finds nothing for the first and a parcel for the
second. The three states are derived from what the worker holds, never oracle
booleans somebody has to remember to set.

**One trip to the freezer, and the sisters wait for it.** A page fires dozens of
calls at once, so a burst on a frozen user arrives as many coroutines together.
The FIRST marks the row ``unfreezing`` before it reads anything, and that mark is
what the others find: they await the transition — never the service, which stays
parallel per user — and then all go on together. So the disk is read once, by
one call, however wide the burst.

**What may be adopted, and what may not.** The user store comes home ONLY when
the envelope authorises it: the Commander, routing the request, attaches its own
verdict under ``user_frozen``, and without that verdict the parcel on disk is
residue and is never touched — the sweep's business, not the worker's. A
CONNECTION needs no verdict: a worker that does not hold the connection a request
names looks in the user's own folder by itself — found, it installs the
connection and its pages and serves; not found, it starts that connection empty.
One code path for both, which is why the stranger needs no special treatment.

**Adoption reads, empties, then announces.** Read the parcel, delete the file —
and the folder with it when that file was the last thing in it, so the deposit
holds the frozen and nothing else — and only then announce. The user store
announces ``user_adopted``, which is what turns the sleeping mark off at the
fold. An adopted CONNECTION announces nothing of its own: it is born through the
ordinary mutators and emits the ordinary ``new_connection``/``new_page`` — one
birth path in the machine, not two.

**Announcements ride the envelope out.** Every mutation queues its protocol name
in ``events``, the sub-envelope the reply carries up to the fold: the inherited
``new_user``/``new_connection``/``new_page`` and
``drop_user``/``drop_connection``/``drop_connections``/``drop_page``/
``drop_pages``, plus ``user_adopted``. A cascade speaks the plural: dropping a
connection announces its pages as one ``drop_pages``, dropping a user its
connections as one ``drop_connections``.

**A drop asks for absence.** Dropping something already gone is that same
outcome — no error, and nothing announced, because nothing happened.

**Three clocks, one climb.** ``last_refresh_ts`` is technical contact and every
call stamps it, the beat included; ``last_user_ts`` is a real human event and is
the prince; ``last_rpc_ts`` is a real call, the surrogate metre until the page
protocol carries the human event of its own. Whoever judges idleness or expiry
reads the real clocks and never ``last_refresh_ts``, which a beat alone can keep
warm forever. A stamp climbs the chain — page, its connection, its user — with an
instant the server takes itself: a client cannot buy immortality by claiming
activity.

**One lock.** Every mutation is serialized on ``dispatch_lock``; nothing awaits
while holding it. Finer grain was measured and refused: at a couple of kilobytes
per user, reading and unpickling a parcel costs microseconds.

**Leaving is the mirror of arriving.** ``freeze_user`` writes what the adoption
reads back — the store under the user, one parcel per connection carrying that
connection and its pages — DIRECTLY under the folder semaphore, which is the
deposit's only coherence mechanism, and then says ``user_frozen`` with the
placement: this worker's own name when the user wakes here, nothing at all when
the placement is still to be assigned. Only then do his rows leave memory, with
no drop announced: the freeze announcement already told the whole story, and the
wake tells it back through the ordinary births. A write that fails aborts the
departure whole — the semaphore goes back, the user stays alive exactly where he
is, nothing is announced, and the failure is logged and counted. Nobody here
kills what could not be saved.

**Nothing is parked while a call of its user runs.** Every call opens under its
user and closes there (``open_request`` / ``close_request``, WSGI stitching
included); a freeze happens only at empty pendings, because a store photographed
with live calls inside would take their work nowhere while the browser was told
it was done. The end of a call is therefore where a departure that had to wait
for it happens — one mechanism, whether the worker is being emptied or a single
user is being ceded.

**The departures are the worker's own initiative.** At photo time
``decide_departures`` pairs every user row with a ``transfer_flag``: ``None``
kept, ``'T'`` ceded, ``'X'`` expired. Expiry is judged on the REAL clocks and
only for ACTIVE rows — a frozen user is the vertex's business — while the choice
of whom to cede belongs to whoever holds the measures (the fattest by memory, the
costliest by load, preferring those with no call in flight) and is handed in.
Then THE GATE: the worker does not park anybody in the same turn it announced
them. It waits ``TRANSFER_START_DELAY``, the time the fold needs to park the
users just named, and only then lets them go — the expired dropped with their
announcements, the ceded written to the deposit one at a time, the loop breathing
between two.

**The valve and the exit.** ``freeze_idle_users`` parks whoever has been silent
past ``user_idle_freeze_delay``, placement this worker's own name: he comes back
where he left, on his own next call. ``quit`` is the whole departure applied to
everybody — flag, gate, park as the last calls end, leave. The worker has no
verb of rebirth: whoever wants a successor launches one.

Not here yet, and deliberately: the wire, the child process, the two thread pools
and the photo (they arrive with the process shell, which is also what makes the
exit real). The deposit IO runs inline on the loop for now; it moves onto the
service pool when that pool exists.
"""

from __future__ import annotations

import asyncio
import logging
import math
import threading
import time
from collections.abc import Iterable
from typing import Any

from genro_bag import Bag

from .freeze_handler import FreezeHandler

#: The reserved prefix that names an anonymous user — the daemon's own
#: convention, so the name itself carries the guest rule. Redefined here with
#: its ratified value rather than imported: the legacy machine dies at the
#: cutover, this one must outlive it.
GUEST_PREFIX = "guest_"

#: How often a wait for a busy deposit folder looks at it again, in seconds.
DEPOSIT_LOCK_RETRY_INTERVAL = 0.05

#: How long the worker waits between announcing its departures and starting to
#: park them, in seconds — the time the fold needs to park the users just named.
#: A technical time, not a grammar of configuration.
TRANSFER_START_DELAY = 2.0

__all__ = [
    "DEPOSIT_LOCK_RETRY_INTERVAL",
    "GUEST_PREFIX",
    "TRANSFER_START_DELAY",
    "SpaWorker",
]


class SpaWorker:
    """The users, connections and pages one worker process holds.

    Args:
        name: the worker's name, the one its handler minted; it stamps every
            announcement and holds the deposit semaphore.
        freeze_handler: the deposit surface — the only way to the parcels.
        group: the group this worker serves in; it goes in the diagnostic header
            of every parcel, which is read for counting and for the sysop.
        deposit_lock_retry_interval: how often a busy user folder is looked at
            again while waiting for its semaphore.
        transfer_start_delay: how long the gate stays shut between announcing
            the departures and parking them.
        user_idle_freeze_delay: the silence past which the valve parks a single
            user; with nothing said, the valve never fires.
    """

    def __init__(
        self,
        name: str,
        *,
        freeze_handler: FreezeHandler,
        group: str = "",
        deposit_lock_retry_interval: float = DEPOSIT_LOCK_RETRY_INTERVAL,
        transfer_start_delay: float = TRANSFER_START_DELAY,
        user_idle_freeze_delay: float = math.inf,
    ) -> None:
        self.name = name
        self.freeze_handler = freeze_handler
        self.group = group
        self.deposit_lock_retry_interval = deposit_lock_retry_interval
        self.transfer_start_delay = transfer_start_delay
        self.user_idle_freeze_delay = user_idle_freeze_delay
        self.dispatch_lock = threading.RLock()
        self._user_register: dict[str, dict[str, Any]] = {}
        self._connection_register: dict[str, dict[str, Any]] = {}
        self._page_register: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._unfreeze_waits: dict[str, asyncio.Event] = {}
        self._pendings: dict[str, int] = {}
        self._transfer_flags: dict[str, str] = {}
        self._departures_start_ts = 0.0
        self._departures_done = asyncio.Event()
        self._departures_done.set()
        self._freeze_failures = 0
        self._exited = False
        self._logger = logging.getLogger(__name__)

    @property
    def user_register(self) -> dict[str, dict[str, Any]]:
        """The users this worker holds, by identity.

        Returns:
            The live register — read it, and leave the writing to the mutators.
        """
        return self._user_register

    @property
    def connection_register(self) -> dict[str, dict[str, Any]]:
        """The connections this worker holds, by cid.

        Returns:
            The live register — read it, and leave the writing to the mutators.
        """
        return self._connection_register

    @property
    def page_register(self) -> dict[str, dict[str, Any]]:
        """The pages this worker holds, by page id.

        Returns:
            The live register — read it, and leave the writing to the mutators.
        """
        return self._page_register

    @property
    def events(self) -> list[dict[str, Any]]:
        """The announcements waiting for the next envelope out.

        Returns:
            The live list: whoever composes the envelope takes them from here.
        """
        return self._events

    @property
    def freeze_failures(self) -> int:
        """How many departures the deposit refused since this worker was born.

        Returns:
            The count. Every one of them left a user alive and a loud line in
            the log; a number that grows is a disk to look at.
        """
        return self._freeze_failures

    @property
    def exited(self) -> bool:
        """Whether this worker has already left.

        Returns:
            True once ``exit_process`` was reached.
        """
        return self._exited

    def offer_event(self, op: str, **payload: Any) -> dict[str, Any]:
        """Queue one announcement for the envelope out.

        Args:
            op: the protocol name of what happened.
            payload: the entity keys that name it.

        Returns:
            The announcement as it was queued.

        Appends to ``events``.
        """
        event = {"op": op, "worker": self.name, **payload}
        self._events.append(event)
        return event

    def add_user(self, user: str, **fields: Any) -> dict[str, Any]:
        """Bring a user into being on this worker and announce it.

        Args:
            user: the user identity.
            fields: anything else the item should carry, stored verbatim.

        Returns:
            The user register item.

        Adds the item and announces ``new_user``.
        """
        with self.dispatch_lock:
            item = self._add_user_item(user, **fields)
            self.offer_event("new_user", user=user)
            return item

    def add_connection(self, cid: str, user: str | None = None, **fields: Any) -> dict[str, Any]:
        """Bring a connection into being, born guest unless it is given a user.

        Args:
            cid: the connection identity.
            user: the user it belongs to; ``None`` is the anonymous reception,
                which names it ``GUEST_PREFIX`` + the cid.
            fields: anything else the item should carry, stored verbatim.

        Returns:
            The connection register item.

        Adds the item — with the user above it when that user is unseen — and
        announces the cascade in the order it happened.
        """
        with self.dispatch_lock:
            user = user or GUEST_PREFIX + cid
            if user not in self._user_register:
                self.add_user(user)
            item = self._add_connection_item(cid, user, **fields)
            self.offer_event("new_connection", user=user, session_id=cid)
            return item

    def add_page(
        self, page_id: str, cid: str, user: str | None = None, **fields: Any
    ) -> dict[str, Any]:
        """Bring a page into being under its connection and announce it.

        Args:
            page_id: the page identity.
            cid: the connection the page belongs to.
            user: the user to hang an unseen connection from; ignored when the
                connection is already here.
            fields: anything else the item should carry, stored verbatim.

        Returns:
            The page register item.

        Adds the item — with the connection and the user above it when they are
        unseen — and announces the cascade in the order it happened.
        """
        with self.dispatch_lock:
            if cid not in self._connection_register:
                self.add_connection(cid, user)
            item = self._add_page_item(page_id, cid, **fields)
            self.offer_event(
                "new_page", user=self._page_user(page_id), page_id=page_id, session_id=cid
            )
            return item

    def drop_page(self, page_id: str) -> None:
        """Take one page off this worker, and whatever it was the last of.

        Args:
            page_id: the page to be gone.

        Removes the item and announces ``drop_page``, then the
        ``drop_connection`` and ``drop_user`` its departure empties. A page
        already gone is the same outcome: nothing happens and nothing is said.
        """
        with self.dispatch_lock:
            if page_id not in self._page_register:
                return
            cid = self._page_register[page_id]["connection_id"]
            user = self._page_user(page_id)
            self._remove_page_item(page_id)
            self.offer_event("drop_page", user=user, page_id=page_id, session_id=cid)
            if not self._connection_register[cid]["pages"]:
                self._remove_connection_item(cid)
                self.offer_event("drop_connection", user=user, session_id=cid)
                self._drop_emptied_user(user)

    def drop_connection(self, cid: str) -> None:
        """Take a whole connection off this worker, its pages first.

        Args:
            cid: the connection to be gone.

        Removes the pages and the connection, announcing ``drop_pages`` (when it
        had any), ``drop_connection``, and ``drop_user`` if it was the user's
        last. A connection already gone is the same outcome.
        """
        with self.dispatch_lock:
            item = self._connection_register.get(cid)
            if item is None:
                return
            user = item["user"]
            page_ids = sorted(item["pages"])
            for page_id in page_ids:
                self._remove_page_item(page_id)
            if page_ids:
                self.offer_event("drop_pages", user=user, page_ids=page_ids, session_id=cid)
            self._remove_connection_item(cid)
            self.offer_event("drop_connection", user=user, session_id=cid)
            self._drop_emptied_user(user)

    def drop_user(self, user: str) -> None:
        """Take a user off this worker with everything under him.

        Args:
            user: the user to be gone.

        Removes the pages, the connections and the user, announcing
        ``drop_pages`` and ``drop_connections`` for what he had and ``drop_user``
        last. A user already gone is the same outcome.
        """
        with self.dispatch_lock:
            item = self._user_register.get(user)
            if item is None:
                return
            session_ids = sorted(item["connections"])
            page_ids = sorted(
                page_id
                for cid in session_ids
                for page_id in self._connection_register[cid]["pages"]
            )
            for page_id in page_ids:
                self._remove_page_item(page_id)
            if page_ids:
                self.offer_event("drop_pages", user=user, page_ids=page_ids)
            for cid in session_ids:
                self._remove_connection_item(cid)
            if session_ids:
                self.offer_event("drop_connections", user=user, session_ids=session_ids)
            del self._user_register[user]
            self._unfreeze_waits.pop(user, None)
            self.offer_event("drop_user", user=user)

    def refresh_chain(self, page_id: str, *clocks: str) -> float:
        """Stamp a page and the chain above it with the server's own instant.

        Args:
            page_id: the page the contact came in on.
            clocks: the clocks the contact deserves besides ``last_refresh_ts``,
                which every contact stamps — ``last_user_ts`` for a human event,
                ``last_rpc_ts`` for a real call.

        Returns:
            The instant written, the same on all three levels.

        Raises:
            KeyError: no such page here.

        Stamps the page item, its connection item and its user item.
        """
        now = time.time()
        with self.dispatch_lock:
            page = self._page_register[page_id]
            connection = self._connection_register[page["connection_id"]]
            user = self._user_register[connection["user"]]
            for item in (page, connection, user):
                item["last_refresh_ts"] = now
                for clock in clocks:
                    item[clock] = now
        return now

    async def adopt_user(self, user: str) -> dict[str, Any]:
        """Bring a user's store home from the deposit — the pull of the unified row.

        Args:
            user: the user the envelope authorised, under its ``user_frozen``
                verdict.

        Returns:
            The user register item, ``active``.

        Adds the item as ``frozen`` when the user is unknown, marks it
        ``unfreezing`` for the one call that makes the trip — the sisters of a
        burst await that transition and read nothing — installs the parcel,
        deletes it from the deposit and announces ``user_adopted``.
        """
        with self.dispatch_lock:
            item = self._user_register.get(user)
            if item is None:
                item = self._add_user_item(user, state="frozen")
            if item["state"] == "active":
                return item
            waiting = self._unfreeze_waits.get(user)
            if waiting is None:
                waiting = self._unfreeze_waits[user] = asyncio.Event()
                item["state"] = "unfreezing"
                mine = True
            else:
                mine = False
        if not mine:
            await waiting.wait()
            return self._user_register[user]
        try:
            store = await self._take_from_deposit(user, self._read_user_parcel)
            if store is None:
                self._logger.warning(
                    "Worker %s: %s was announced frozen but has no store in the deposit",
                    self.name,
                    user,
                )
            with self.dispatch_lock:
                if store is not None:
                    item["store"] = store
                item["state"] = "active"
                self.offer_event("user_adopted", user=user)
        finally:
            with self.dispatch_lock:
                del self._unfreeze_waits[user]
                if item["state"] == "unfreezing":
                    item["state"] = "frozen"
            waiting.set()
        return item

    async def adopt_connection(self, user: str, cid: str) -> dict[str, Any]:
        """Look for a connection of ``user`` in the deposit and install what is there.

        Args:
            user: the user the connection belongs to.
            cid: the connection the request names.

        Returns:
            The connection register item — carrying the pages the parcel had, or
            empty when the deposit had nothing.

        Reads the parcel by itself (no verdict authorises a connection), deletes
        it from the deposit and brings the connection and its pages into being
        through the ordinary mutators: the announcements are the natural
        ``new_connection``/``new_page``, never one of its own. A connection
        already held costs no trip at all; the question is asked again on the
        way back, because the trip is a handoff and a sister may have installed
        it meanwhile.
        """
        with self.dispatch_lock:
            item = self._connection_register.get(cid)
            if item is not None:
                return item
        parcel = await self._take_from_deposit(user, self._read_connection_parcel, cid) or {}
        with self.dispatch_lock:
            item = self._connection_register.get(cid)
            if item is None:
                item = self.add_connection(cid, user, **parcel.get("connection", {}))
                for page_id, fields in parcel.get("pages", {}).items():
                    self.add_page(page_id, cid, user, **fields)
            return item

    def open_request(self, user: str) -> None:
        """Write one live call under the user it is for.

        Args:
            user: the user the call belongs to.

        Adds to his pendings: nothing of his is parked while it is open.
        """
        with self.dispatch_lock:
            self._pendings[user] = self._pendings.get(user, 0) + 1

    async def close_request(self, user: str) -> None:
        """Close one live call, and execute the departure that was waiting for it.

        Args:
            user: the user the call belonged to.

        Raises:
            KeyError: no call of his is open.

        Takes the call out of his pendings and, when it was his last and a
        departure of his is past the gate, lets him go now — the closure of a
        whole worker and the cession of a single user hang on this same hook.
        """
        with self.dispatch_lock:
            self._pendings[user] -= 1
            if self._pendings[user]:
                return
            del self._pendings[user]
            flag = self._transfer_flags.get(user)
        if flag is not None and self._departures_open:
            await self._execute_departure(user, flag)

    async def freeze_user(self, user: str, *, placement: str | None = None) -> bool:
        """Park a user in the deposit and announce where he will wake.

        Args:
            user: the user leaving memory.
            placement: the worker he wakes on — this worker's own name when he
                stays here as ``frozen``, ``None`` when it is still to be
                assigned.

        Returns:
            True when he went to the deposit; False when he stayed — a row that
            is not ``active``, a call of his still in flight, or a deposit that
            refused the parcels.

        Writes his store and one parcel per connection under the folder
        semaphore, announces ``user_frozen`` with the placement and takes his
        rows out of memory. A failed write aborts the whole departure: the
        semaphore goes back, he stays alive where he is, nothing is announced,
        and the failure is logged and counted.
        """
        with self.dispatch_lock:
            item = self._user_register.get(user)
            if item is None or item["state"] != "active" or user in self._pendings:
                return False
        await self._take_folder_lock(user)
        try:
            with self.dispatch_lock:
                self._write_parcels(user, item)
        except Exception:
            self._freeze_failures += 1
            self._logger.exception(
                "Worker %s: the deposit refused the parcels of %s; he stays here",
                self.name,
                user,
            )
            return False
        finally:
            self.freeze_handler.release_lock(user, self.name)
        with self.dispatch_lock:
            self.offer_event("user_frozen", user=user, placement=placement)
            self._release_rows(user, placement)
        return True

    async def freeze_all_users(self) -> None:
        """Park every user this worker holds, one at a time.

        The loop breathes between two of them: a process that stopped answering
        its probes while emptying itself would be taken for dead. Whoever has a
        call in flight stays behind — the end of that call parks him.
        """
        for user in list(self._user_register):
            await self.freeze_user(user)
            await asyncio.sleep(0)

    async def freeze_idle_users(self) -> None:
        """Park whoever has gone silent past ``user_idle_freeze_delay``, waking here.

        Silence is measured on the real clocks: a page that only beats keeps
        nobody alive. The placement is this worker's own name — the user comes
        back where he left, on his own next call.
        """
        now = time.time()
        for user, item in list(self._user_register.items()):
            if item["state"] != "active":
                continue
            if now - self._last_real_activity(item) <= self.user_idle_freeze_delay:
                continue
            await self.freeze_user(user, placement=self.name)
            await asyncio.sleep(0)

    def decide_departures(
        self, *, transfer_users: Iterable[str] = (), expiry_delay: float = math.inf
    ) -> dict[str, tuple[dict[str, Any], str | None]]:
        """Pair every user with the flag the next photo carries, and shut the gate.

        Args:
            transfer_users: the users this round cedes, chosen by whoever holds
                the measures — the fattest by memory, the costliest by load,
                preferring those with no call in flight.
            expiry_delay: the silence past which an ACTIVE user is expired; his
                frozen namesakes are judged at the vertex, never here.

        Returns:
            Every user, mapped to his register item and his flag: ``None`` kept,
            ``'T'`` ceded, ``'X'`` expired.

        Remembers the flags that are not ``None`` and starts the clock of the
        gate: nothing departs before ``transfer_start_delay`` has passed.
        """
        now = time.time()
        ceded = set(transfer_users)
        departures: dict[str, tuple[dict[str, Any], str | None]] = {}
        with self.dispatch_lock:
            self._transfer_flags = {}
            for user, item in self._user_register.items():
                flag = None
                if item["state"] == "active":
                    if now - self._last_real_activity(item) > expiry_delay:
                        flag = "X"
                    elif user in ceded:
                        flag = "T"
                if flag is not None:
                    self._transfer_flags[user] = flag
                departures[user] = (item, flag)
            self._departures_start_ts = now + self.transfer_start_delay
            if self._transfer_flags:
                self._departures_done.clear()
            else:
                self._departures_done.set()
        return departures

    async def execute_departures(self) -> None:
        """Wait out the gate, then let the flagged users go, one at a time.

        The expired are dropped with their announcements — eliminating them
        everywhere else is the vertex's — and the ceded go to the deposit as
        soon as no call of theirs is in flight; whoever still has one is taken
        by the end of that call. The loop breathes between two users.
        """
        await asyncio.sleep(self._departures_start_ts - time.time())
        for user, flag in list(self._transfer_flags.items()):
            await self._execute_departure(user, flag)
            await asyncio.sleep(0)

    async def quit(self, *, expiry_delay: float = math.inf) -> None:
        """Leave: everybody departs, the last call is waited for, the process ends.

        Args:
            expiry_delay: the silence past which a user is expired and dropped
                instead of parked.

        Flags every user for cession, waits the gate, parks them as their calls
        end, and only then leaves the process. Rebirth is not the worker's:
        whoever wants a successor launches one.
        """
        self.decide_departures(
            transfer_users=list(self._user_register), expiry_delay=expiry_delay
        )
        await self.execute_departures()
        await self._departures_done.wait()
        self.exit_process()

    def exit_process(self) -> None:
        """Leave the process — the last act of ``quit``.

        The worker itself only records that the point was reached: it holds no
        process of its own, and the shell that runs it in one makes this real.
        """
        self._exited = True

    @property
    def _departures_open(self) -> bool:
        """Whether the gate opened on the departures last announced."""
        return time.time() >= self._departures_start_ts

    async def _execute_departure(self, user: str, flag: str) -> None:
        """Let one flagged user go: the expired dropped, the ceded to the deposit."""
        if flag == "X":
            self.drop_user(user)
        elif user in self._pendings:
            return
        else:
            await self.freeze_user(user)
        with self.dispatch_lock:
            self._transfer_flags.pop(user, None)
            if not self._transfer_flags:
                self._departures_done.set()

    def _write_parcels(self, user: str, item: dict[str, Any]) -> None:
        """Write the user's store and one parcel per connection, under the held lock."""
        self.freeze_handler.write_user_register_item(
            user, item["store"], writer=self.name, cause="freeze", group=self.group
        )
        for cid in sorted(item["connections"]):
            self.freeze_handler.write_connection_register_item(
                user,
                cid,
                self._connection_parcel(cid),
                writer=self.name,
                cause="freeze",
                group=self.group,
            )

    def _connection_parcel(self, cid: str) -> dict[str, Any]:
        """One connection with its pages, in the shape the adoption reads back.

        The edges of the tree are left out on purpose: the folder already says
        whose the connection is, and the pages half is what rebuilds the rest.
        """
        item = self._connection_register[cid]
        return {
            "connection": {
                key: value for key, value in item.items() if key not in ("user", "pages")
            },
            "pages": {
                page_id: {
                    key: value
                    for key, value in self._page_register[page_id].items()
                    if key != "connection_id"
                }
                for page_id in sorted(item["pages"])
            },
        }

    def _release_rows(self, user: str, placement: str | None) -> None:
        """Take a parked user's rows out of memory, saying nothing: the freeze said it.

        The connections and the pages go whatever the placement; the user row
        stays behind as ``frozen``, its store emptied, only when he wakes here.
        """
        item = self._user_register[user]
        for cid in sorted(item["connections"]):
            for page_id in sorted(self._connection_register[cid]["pages"]):
                self._remove_page_item(page_id)
            self._remove_connection_item(cid)
        if placement == self.name:
            item["state"] = "frozen"
            item["store"] = Bag()
            return
        del self._user_register[user]
        self._unfreeze_waits.pop(user, None)

    def _last_real_activity(self, item: dict[str, Any]) -> float:
        """The last of the two real clocks — the beat never counts as presence."""
        return max(item["last_user_ts"], item["last_rpc_ts"])

    def _add_user_item(self, user: str, **fields: Any) -> dict[str, Any]:
        """Put a user item in the register, born stamped and with a live store."""
        fields.setdefault("state", "active")
        fields.setdefault("store", Bag())
        item = self._user_register[user] = self._stamped(connections=set(), **fields)
        return item

    def _add_connection_item(self, cid: str, user: str, **fields: Any) -> dict[str, Any]:
        """Put a connection item in the register and join it to its user."""
        item = self._connection_register[cid] = self._stamped(user=user, pages=set(), **fields)
        self._user_register[user]["connections"].add(cid)
        return item

    def _add_page_item(self, page_id: str, cid: str, **fields: Any) -> dict[str, Any]:
        """Put a page item in the register and join it to its connection."""
        item = self._page_register[page_id] = self._stamped(connection_id=cid, **fields)
        self._connection_register[cid]["pages"].add(page_id)
        return item

    def _remove_page_item(self, page_id: str) -> None:
        """Take a page item out of the register and off its connection."""
        item = self._page_register.pop(page_id)
        self._connection_register[item["connection_id"]]["pages"].discard(page_id)

    def _remove_connection_item(self, cid: str) -> None:
        """Take a connection item out of the register and off its user."""
        item = self._connection_register.pop(cid)
        self._user_register[item["user"]]["connections"].discard(cid)

    def _drop_emptied_user(self, user: str) -> None:
        """Take the user away when the connection just removed was his last."""
        if not self._user_register[user]["connections"]:
            del self._user_register[user]
            self._unfreeze_waits.pop(user, None)
            self.offer_event("drop_user", user=user)

    def _stamped(self, **fields: Any) -> dict[str, Any]:
        """An item born with the three clocks on the server's own instant."""
        now = time.time()
        for clock in ("last_refresh_ts", "last_user_ts", "last_rpc_ts"):
            fields.setdefault(clock, now)
        return fields

    def _page_user(self, page_id: str) -> str:
        """The user a page belongs to, derived by walking up its chain."""
        cid = self._page_register[page_id]["connection_id"]
        return self._connection_register[cid]["user"]

    async def _take_folder_lock(self, user: str) -> None:
        """Wait on the loop until the semaphore of the user's folder is this worker's.

        The wait is a coroutine and never a thread: whoever holds the semaphore
        is working, and a thread parked here would be a thread not doing that
        work.
        """
        while not self.freeze_handler.take_lock(user, self.name):
            await asyncio.sleep(self.deposit_lock_retry_interval)

    async def _take_from_deposit(self, user: str, read: Any, *args: Any) -> Any:
        """Hold the user's folder, read one parcel and delete it, then let go.

        Releasing the semaphore takes the folder away when the parcel read was
        the last thing in it.
        """
        await self._take_folder_lock(user)
        try:
            return read(user, *args)
        finally:
            self.freeze_handler.release_lock(user, self.name)

    def _read_user_parcel(self, user: str) -> Any:
        """Read the user's store off the deposit and take the parcel away."""
        payload = self.freeze_handler.read_user_register_item(user)
        self.freeze_handler.drop_user_register_item(user)
        return payload

    def _read_connection_parcel(self, user: str, cid: str) -> Any:
        """Read one connection with its pages off the deposit and take it away."""
        payload = self.freeze_handler.read_connection_register_item(user, cid)
        self.freeze_handler.drop_connection_register_item(user, cid)
        return payload
