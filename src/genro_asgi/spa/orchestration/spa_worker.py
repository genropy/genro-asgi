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
one call, however wide the burst. A pull that fails takes the row away instead
of leaving it half-born: the parcel is still on disk and the mark still on at
the vertex, so the next request of his carries the verdict again and the trip
is retried by the unified row's own shape, with nothing to reconcile.

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
connection and its pages — under the folder semaphore, which is the deposit's
only coherence mechanism, and then says ``user_frozen``. WHERE he wakes is not
this worker's business: the worker event keeps a ``placement`` slot for the
vertex that will decide it and this worker never fills it, so every departure
leaves with the placement to be assigned and the row leaves memory WHOLE. No
drop is announced beside it: the freeze worker event already told the story, and
the wake tells it back through the ordinary births. A write that fails aborts
the departure whole — the semaphore goes back, the user stays alive exactly
where he is, nothing is announced, and the failure is logged and counted. Nobody
here kills what could not be saved.

**The semaphore is waited for, never forever.** A folder somebody else holds is
waited on with a coroutine, and the first miss says out loud whose it is; past
``DEPOSIT_LOCK_WAIT_LIMIT`` the wait gives up rather than hang silently — an
adoption raises, and the caller's own REPLY carries the failure; a freeze takes
the shape of any other refused departure. That bound is a floor against a
semaphore nobody gives back, not a budget: how long a REQUEST may wait before
the vertex answers it something else is the Commander's parking budget, and
arrives with the fold.

**Nothing is parked while a call of its user runs.** Every call opens under its
user and closes there (``open_request`` / ``close_request``, WSGI stitching
included); a freeze happens only at empty pendings, because a store photographed
with live calls inside would take their work nowhere while the browser was told
it was done. The question is asked TWICE — before the semaphore and again under
it — because a check taken before the window it decides about decides nothing: a
call born while the folder was being waited for finds the departure abandoned
and takes it over at its own tail. The end of a call is therefore where a
departure that had to wait for it happens — one mechanism, whether the worker is
being emptied or a single user is being ceded — and a departure is CLAIMED
before the first await of its path, so the cycle and the hook can never park the
same user twice.

**The departures are the worker's own initiative.** At photo time
``plan_transfers`` pairs every user row with a ``transfer_flag``: ``None``
kept, ``'T'`` ceded, ``'X'`` expired. Expiry is judged on the REAL clocks and
only for ACTIVE rows — a frozen user is the vertex's business — while the choice
of whom to cede belongs to whoever holds the measures (the fattest by memory, the
costliest by load, preferring those with no call in flight) and is handed in.
THE VALVE IS ONE MORE REASON FOR A ``'T'``: whoever has been silent past
``user_idle_freeze_minutes`` — silence read on the real clocks, since a beat
alone proves nobody — is ceded by the same decision, on the same road, with no
verb of his own. Then THE GATE: the worker does not park anybody in the same turn
it announced them. It waits ``TRANSFER_START_DELAY``, the time the fold needs to
park the users just named, and only then lets them go — the expired dropped with
their worker events, the ceded written to the deposit one at a time, the loop
breathing between two. So there is ONE departure scheme and no special case: the
window in which somebody could come back to a row that was already emptied
cannot open, because whoever comes back either is already in the pendings and
his freeze waits for him, or arrives after the fold parked him and starts again
from the vertex with the verdict in hand.

**The exit.** ``quit`` is that same departure applied to everybody — flag, gate,
park as the last calls end, leave — and once it starts the plan is TERMINAL: a
later shot may add a newborn to the departing, never take anybody off them. A
single user's failure is contained where it happens, so one refused parcel
cannot keep the process from ending. The worker has no verb of rebirth: whoever
wants a successor launches one.

**The wire is handed in, never opened here.** Whoever runs this worker in a
process connects to the handler's socket and hands the stream over
(``attach_stream``); the worker presents itself on it — its pid and the
configuration it was built from — and the answer brings the whole global store
down. Then it reads envelopes until the wire ends. What comes down is a CALL and
nothing else, served on its own task so a long one cannot make this worker deaf
to the next; the protocol is asymmetric, so this worker never asks anything
upward — what it has to say rides the answer to what was asked of it, and any
other kind of envelope arriving here is denounced.

**Two pools, and what runs where.** The TRAFFIC pool takes the WSGI stitching
and the long calls, the SERVICE pool — much smaller — takes the deposit IO;
their sizes come down in the spawn payload. Neither ever takes a wait: waiting
for a busy folder is a coroutine on the loop, because whoever holds that
semaphore is working, and a thread parked here would be a thread not doing that
work.

**Four ops, and one form.** ``/op/ping`` answers the health beat and nothing else
— are you alive. The other three are named after the verb of this class that
serves them and carry that verb's own argument: ``/op/quit``, answered AT ONCE
with the photo that shows every user flagged for cession, the departures running
after the answer because the process ends with them; ``/op/drop_user`` and
``/op/drop_connection``, answered when the drop is done, so the worker events it
made ride that same reply. The http CALL form (an ``http`` dict beside the
``identity`` and the ``user_frozen`` verdict) is a request the front packed
whole: it lands on the unified row FIRST — the store adopted when the verdict
authorises it, the connection looked up in the deposit by itself, the clocks
stamped — and only then goes to the ``WsgiSeam`` on the traffic pool. That
seam's ``wsgi_app`` is ``None`` here: this class hosts no site, and says so
explicitly. A subclass assigns it, which is the whole contract with the bridge.

**The photo rides out.** ``worker_snapshot`` is a slot ANY envelope leaving here
may carry beside its own payload: the presentation carries it (a live process is
never without a photo), every population change carries it (a user entering or
leaving is when the thing the photo describes really changes), and any reply
carries it once ``worker_snapshot_ttl`` has run out on the last one. So there is
one road instead of three, and the beat keeps the only question its name asks.

**The store comes down the same slot, mirrored.** ``global_register_item_tytx``
is taken off every inbound envelope before anything else looks at it, and the
replica is replaced WHOLE — no delta, no version, no dedicated event. The
newborn is not a special case, and nothing can arrive out of order.

**When the wire dies.** The handler watches the process and the process watches
the wire: two guardians converging on the same safe state. A wire gone means
nobody can be told anything, so the worker parks everybody in the deposit — the
road to safety does not pass through the channel — and leaves. The
worker events stay unsaid: whoever finds the parcels needs no telling.
"""

from __future__ import annotations

import asyncio
import copy
import functools
import logging
import math
import os
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from genro_bag import Bag

from ...channel.frame import REGISTER_METHOD, REGISTER_PATH, Frame, FrameStream
from ..environ import WsgiSeam
from .freeze_handler import FreezeHandler
from .worker_connector import (
    CALL_METHOD,
    GLOBAL_STORE_KEY,
    REPLY_METHOD,
    WORKER_SNAPSHOT_KEY,
)
from .worker_handler import (
    DROP_CONNECTION_OP_PATH,
    DROP_USER_OP_PATH,
    PING_OP_PATH,
    QUIT_OP_PATH,
)

#: The reserved prefix that names an anonymous user — the daemon's own
#: convention, so the name itself carries the guest rule. Redefined here with
#: its ratified value rather than imported: the legacy machine dies at the
#: cutover, this one must outlive it.
GUEST_PREFIX = "guest_"

#: How often a wait for a busy deposit folder looks at it again, in seconds.
DEPOSIT_LOCK_RETRY_INTERVAL = 0.05

#: How long a wait for a busy deposit folder goes on before it gives up, in
#: seconds. A technical floor against a semaphore nobody gives back — never a
#: budget for how long a request may wait, which is the vertex's to spend.
DEPOSIT_LOCK_WAIT_LIMIT = 30.0

#: How long the worker waits between announcing its departures and starting to
#: park them, in seconds — the time the fold needs to park the users just named.
#: A technical time, not a grammar of configuration.
TRANSFER_START_DELAY = 2.0

#: How long a photo already sent stays fresh enough, in seconds: past it, the
#: next envelope out carries a new one.
WORKER_SNAPSHOT_TTL = 0.5

#: The conversion the valve makes: its silence is a policy and comes in minutes,
#: the clocks it reads are seconds.
SECONDS_PER_MINUTE = 60.0

#: The three clocks every register item carries, in the order of their rank.
CLOCK_NAMES = ("last_refresh_ts", "last_user_ts", "last_rpc_ts")

# The worker events that mean the population changed — a user entering or
# leaving — and therefore that the next envelope out owes a fresh photo.
POPULATION_WORKER_EVENTS = frozenset(
    {
        "new_user",
        "drop_user",
        "user_frozen",
        "user_adopted",
        "connection_relabeled",
        "user_rows_released",
    }
)

__all__ = [
    "CLOCK_NAMES",
    "DEPOSIT_LOCK_RETRY_INTERVAL",
    "DEPOSIT_LOCK_WAIT_LIMIT",
    "GUEST_PREFIX",
    "SECONDS_PER_MINUTE",
    "TRANSFER_START_DELAY",
    "WORKER_SNAPSHOT_TTL",
    "SpaWorker",
]


class SpaWorker:
    """The users, connections and pages one worker process holds.

    Args:
        name: the worker's name, the one its handler minted; it stamps every
            worker event and holds the deposit semaphore.
        freeze_handler: the deposit surface — the only way to the parcels.
        group: the group this worker serves in; it goes in the diagnostic header
            of every parcel, which is read for counting and for the sysop.
        deposit_lock_retry_interval: how often a busy user folder is looked at
            again while waiting for its semaphore.
        deposit_lock_wait_limit: how long that wait goes on before it gives up
            loud.
        transfer_start_delay: how long the gate stays shut between announcing
            the departures and parking them.
        user_idle_freeze_minutes: the silence, IN MINUTES, past which the valve
            flags a user for the deposit; with nothing said, the valve never
            fires. Minutes because it is a policy of the installation, and the
            comparison against the clocks converts where it is made.
        main_threadpool_size: the traffic pool's size — the WSGI stitching and
            the long calls; ``None`` leaves the interpreter's own default.
        aux_threadpool_size: the service pool's size — the deposit IO, and much
            smaller.
        worker_snapshot_ttl: how long a photo already sent stays fresh enough.
    """

    def __init__(
        self,
        name: str,
        *,
        freeze_handler: FreezeHandler,
        group: str = "",
        deposit_lock_retry_interval: float = DEPOSIT_LOCK_RETRY_INTERVAL,
        deposit_lock_wait_limit: float = DEPOSIT_LOCK_WAIT_LIMIT,
        transfer_start_delay: float = TRANSFER_START_DELAY,
        user_idle_freeze_minutes: float = math.inf,
        main_threadpool_size: int | None = None,
        aux_threadpool_size: int | None = None,
        worker_snapshot_ttl: float = WORKER_SNAPSHOT_TTL,
    ) -> None:
        self.name = name
        self.freeze_handler = freeze_handler
        self.group = group
        self.deposit_lock_retry_interval = deposit_lock_retry_interval
        self.deposit_lock_wait_limit = deposit_lock_wait_limit
        self.transfer_start_delay = transfer_start_delay
        self.user_idle_freeze_minutes = user_idle_freeze_minutes
        self.worker_snapshot_ttl = worker_snapshot_ttl
        self.traffic_pool = ThreadPoolExecutor(
            max_workers=main_threadpool_size, thread_name_prefix=f"{name}-traffic"
        )
        self.service_pool = ThreadPoolExecutor(
            max_workers=aux_threadpool_size, thread_name_prefix=f"{name}-service"
        )
        #: The wire this worker speaks on, handed in by whoever runs it.
        self.stream: FrameStream | None = None
        #: The global store as it came down, in the form it travels: the master
        #: is the Commander's, and this replica is replaced whole.
        self.global_register_item_tytx: str | None = None
        #: The consumer seam of the http CALL form: a WSGI callable a subclass
        #: assigns. None here — this class hosts no site of its own.
        self.wsgi_app: Callable[..., Any] | None = None
        self.dispatch_lock = threading.RLock()
        self._user_register: dict[str, dict[str, Any]] = {}
        self._connection_register: dict[str, dict[str, Any]] = {}
        self._page_register: dict[str, dict[str, Any]] = {}
        self._worker_events: list[dict[str, Any]] = []
        self._unfreeze_waits: dict[str, asyncio.Event] = {}
        self._pendings: dict[str, int] = {}
        self._transfer_flags: dict[str, str] = {}
        #: One entry per connection that logged in during a call and is
        #: waiting for that call's tail to carry it away: the identity it
        #: belonged to BEFORE, which is the only fact the tail needs.
        self._login_previous_user_map: dict[str, str] = {}
        self._departing_users: set[str] = set()
        self._transfers_start_ts = 0.0
        self._transfers_done = asyncio.Event()
        self._transfers_done.set()
        self._transfers_changed = asyncio.Event()
        self._quitting = False
        self._freeze_failures = 0
        self._exited = False
        self._service_tasks: set[asyncio.Task[None]] = set()
        self._snapshot_sent_ts = 0.0
        self._population_changed = False
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
    def worker_events(self) -> list[dict[str, Any]]:
        """The worker events waiting for the next envelope out.

        Returns:
            The live list: whoever composes the envelope takes them from here.
        """
        return self._worker_events

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

    @property
    def rss_bytes(self) -> int | None:
        """The resident set size of this process, in bytes.

        Returns:
            What ``/proc/self/status`` says, or None where there is no ``/proc``
            (macOS) — the photo carries the counts either way, and no dependency
            is taken for a gauge that the platform may simply not have.
        """
        try:
            with open("/proc/self/status", encoding="ascii") as status:
                for line in status:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except OSError:
            return None
        return None

    @property
    def worker_snapshot(self) -> dict[str, Any]:
        """What this process honestly knows of itself, ready for the wire.

        Returns:
            The aggregates of the process, one row per connection with its three
            clocks, and one pair per user — his projected item and the
            ``transfer_flag`` the last photo decided, ``None`` when he is going
            nowhere. Scalars only: the stores and the working fields are the
            application's business, never the observer's.
        """
        with self.dispatch_lock:
            return {
                "pid": os.getpid(),
                "name": self.name,
                "group": self.group,
                "rss_bytes": self.rss_bytes,
                "user_count": len(self._user_register),
                "connection_count": len(self._connection_register),
                "page_count": len(self._page_register),
                "connections": {
                    cid: {"user": item["user"], **{clock: item[clock] for clock in CLOCK_NAMES}}
                    for cid, item in self._connection_register.items()
                },
                "users": {
                    user: {
                        "item": self._user_row(item),
                        "transfer_flag": self._transfer_flags.get(user),
                    }
                    for user, item in self._user_register.items()
                },
            }

    def add_worker_event(self, op: str, **payload: Any) -> dict[str, Any]:
        """Queue one worker event for the envelope out.

        Args:
            op: the protocol name of what happened.
            payload: the entity keys that name it.

        Returns:
            The worker event as it was queued.

        Appends to ``events``, and marks the photo due when what happened is a
        user entering or leaving.
        """
        event = {"op": op, "worker": self.name, **payload}
        self._worker_events.append(event)
        if op in POPULATION_WORKER_EVENTS:
            self._population_changed = True
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
            self.add_worker_event("new_user", user=user)
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
            self.add_worker_event("new_connection", user=user, session_id=cid)
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
            self.add_worker_event(
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
            self.add_worker_event("drop_page", user=user, page_id=page_id, session_id=cid)
            if not self._connection_register[cid]["pages"]:
                self._remove_connection_item(cid)
                self.add_worker_event("drop_connection", user=user, session_id=cid)
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
                self.add_worker_event("drop_pages", user=user, page_ids=page_ids, session_id=cid)
            self._remove_connection_item(cid)
            self.add_worker_event("drop_connection", user=user, session_id=cid)
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
                self.add_worker_event("drop_pages", user=user, page_ids=page_ids)
            for cid in session_ids:
                self._remove_connection_item(cid)
            if session_ids:
                self.add_worker_event("drop_connections", user=user, session_ids=session_ids)
            del self._user_register[user]
            self._unfreeze_waits.pop(user, None)
            self.add_worker_event("drop_user", user=user)

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
        with self.dispatch_lock:
            page = self._page_register[page_id]
            connection = self._connection_register[page["connection_id"]]
            user = self._user_register[connection["user"]]
            return self._stamp_items((page, connection, user), clocks)

    def attach_stream(self, stream: FrameStream) -> None:
        """Take the wire this worker speaks on.

        Args:
            stream: the frame codec over the connection to the handler.

        Sets ``stream``. The worker never opens it: whoever runs this worker in
        a process connects, and hands the connection over.
        """
        self.stream = stream

    async def send_presentation(self, config: dict[str, Any]) -> None:
        """Present this process on the wire and install the store that answers.

        Args:
            config: the spawn payload this process was built from, echoed back
                so the handler sees what its child understood of it.

        Sets ``global_register_item_tytx``.
        """
        await self.stream.write(
            Frame(
                method=REGISTER_METHOD,
                path=REGISTER_PATH,
                data=self._outbound({"pid": os.getpid(), "config": config}),
            )
        )
        self._take_global_store(await self.stream.read())

    async def receive_frames(self) -> None:
        """Read the handler's envelopes until the wire ends.

        Returns when the wire is gone — EOF, the death signal on a same-host
        socket — or a protocol violation closed it. What a worker without a wire
        does is not decided here: the caller asks for ``on_wire_lost``.
        """
        while True:
            try:
                frame = await self.stream.read()
            except ValueError:
                self._logger.exception(
                    "Worker %s: protocol violation from its handler; leaving the wire",
                    self.name,
                )
                return
            if frame is None:
                return
            self.handle_frame(frame)

    def handle_frame(self, frame: Frame) -> None:
        """Route one envelope from the handler, the global store taken off it first.

        Args:
            frame: the envelope as it came off the wire.

        A CALL is served on its own task, so a long op cannot make this worker
        deaf to the next one, and it is the ONLY envelope that comes down this
        wire; anything else is denounced. The store is taken off the envelope
        before anything looks at its kind.
        """
        self._take_global_store(frame)
        if frame.method == CALL_METHOD:
            task = asyncio.create_task(self._guarded_call(frame))
            self._service_tasks.add(task)
            task.add_done_callback(self._service_tasks.discard)
        else:
            self._logger.warning(
                "Worker %s: unexpected envelope %s from its handler", self.name, frame.method
            )

    async def answer_call(self, frame: Frame) -> None:
        """Answer one CALL: the beat, the http form, one of the three ops, or nothing known.

        Args:
            frame: the CALL as it came off the wire.

        Sends exactly one REPLY, whatever the outcome.
        """
        payload = frame.data or {}
        if frame.path == PING_OP_PATH:
            await self.send_reply(frame, result={})
        elif "http" in payload:
            await self.serve_http(frame, payload)
        elif frame.path == QUIT_OP_PATH:
            await self._answer_then_quit(frame, payload)
        elif frame.path == DROP_USER_OP_PATH:
            self.drop_user(payload["user"])
            await self.send_reply(frame, result={})
        elif frame.path == DROP_CONNECTION_OP_PATH:
            self.drop_connection(payload["cid"])
            await self.send_reply(frame, result={})
        else:
            await self.send_reply(frame, error=f"unknown op: {frame.path!r}")

    async def serve_http(self, frame: Frame, payload: dict[str, Any]) -> None:
        """Serve the http CALL form through the WSGI seam, or refuse it.

        Args:
            frame: the CALL being answered.
            payload: its whole payload — the ``http`` dict the front packed, the
                ``identity`` to route on and the ``user_frozen`` verdict, which
                belong together because the row is resolved from all three.

        No ``wsgi_app`` means this worker hosts no site: the form is understood
        and the explicit error says the seam is empty — and nothing is born on
        the registers for a request that was never served. Anything that goes
        wrong afterwards comes back as that same REPLY: a caller is answered
        once, always, and a deposit that refuses a parcel must not leave a
        browser waiting for a timeout.
        """
        if self.wsgi_app is None:
            await self.send_reply(
                frame, error="http CALL form refused: this worker hosts no WSGI site"
            )
            return
        try:
            result: Any = await self._serve_request(payload)
            error: Any = None
        except Exception as exc:
            self._logger.exception("Worker %s: http CALL %s failed", self.name, frame.path)
            result, error = None, f"{type(exc).__name__}: {exc}"
        await self.send_reply(frame, result=result, error=error)

    async def send_reply(self, frame: Frame, *, result: Any = None, error: Any = None) -> None:
        """Answer a CALL, carrying what happened here while it was being served.

        Args:
            frame: the CALL being answered; its id is what makes this a REPLY.
            result: the answer, when there is one.
            error: what went wrong instead.

        Empties ``events`` onto the envelope — the worker events are delivered
        once, and the send IS the delivery — and attaches the photo when it is
        due.
        """
        with self.dispatch_lock:
            events = self._worker_events
            self._worker_events = []
        data: dict[str, Any] = {"worker_events": events}
        if error is not None:
            data["error"] = error
        else:
            data["result"] = result
        await self.stream.write(
            Frame(id=frame.id, method=REPLY_METHOD, path=frame.path, data=self._outbound(data))
        )

    async def on_wire_lost(self) -> None:
        """The wire is gone: park everybody in the deposit and leave.

        The mirror of the handler's own ``on_child_lost``, and the second of the
        two guardians. A process nobody can speak to any more saves its users
        the one way that does not need the wire — the deposit — and then ends.
        What it would have announced stays unsaid: nothing could carry it now,
        and whoever finds the parcels needs no telling.
        """
        self._logger.warning(
            "Worker %s: its wire is gone — freezing everybody and leaving", self.name
        )
        await self.freeze_all_users()
        self.exit_process()

    async def adopt_user(self, user: str) -> dict[str, Any]:
        """Bring a user's store home from the deposit — the pull of the unified row.

        Args:
            user: the user the envelope authorised, under its ``user_frozen``
                verdict.

        Returns:
            The user register item, ``active``.

        Raises:
            Whatever the deposit raised, to the call that made the trip; the
            sisters of that burst are woken with a failure of their own.

        Adds the item as ``frozen`` when the user is unknown, marks it
        ``unfreezing`` for the one call that makes the trip — the sisters of a
        burst await that transition and read nothing — installs the parcel,
        deletes it from the deposit and announces ``user_adopted``. A pull that
        fails leaves NO row behind: his parcel is still in the deposit and the
        mark is still on at the vertex, so the next request of his carries the
        verdict again and the adoption is retried by construction. A resident
        row would have to be reconciled with that verdict; an absent one is
        already the truth.
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
            item = self._user_register.get(user)
            if item is None:
                raise RuntimeError(
                    f"the adoption of {user} failed in the call that made the trip; "
                    "his parcel is still in the deposit"
                )
            return item
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
                self.add_worker_event("user_adopted", user=user)
        finally:
            with self.dispatch_lock:
                del self._unfreeze_waits[user]
                if item["state"] == "unfreezing":
                    self._release_rows(user)
                    self._logger.error(
                        "Worker %s: the deposit would not give %s back; his row goes "
                        "and the verdict on his next request retries the adoption",
                        self.name,
                        user,
                    )
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
        through the ordinary mutators: the worker events are the natural
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
                resident = user in self._user_register
                item = self.add_connection(cid, user, **parcel.get("connection", {}))
                for page_id, fields in parcel.get("pages", {}).items():
                    self.add_page(page_id, cid, user, **fields)
                self._install_carried_store(user, parcel.get("store"), resident)
            return item

    def _install_carried_store(self, user: str, store: Any, resident: bool) -> None:
        """Give a login's store to the row it belongs to, or let it die out loud.

        A connection that logged in carries what its guest had accumulated. It
        becomes the user's own store when the row was born a moment ago with
        this very connection; when a row of his was already here — his own state
        came home first, or he is living on this worker already — the RESIDENT
        wins and what the guest did before logging in dies, said out loud rather
        than silently dropped. The caller holds the lock.
        """
        if store is None:
            return
        if resident:
            self._logger.info(
                "Worker %s: %s was already here, so what his guest accumulated is dropped",
                self.name,
                user,
            )
            return
        self._user_register[user]["store"] = store

    def relabel_connection(self, cid: str, user: str, **fields: Any) -> None:
        """The login: this connection stops being anonymous and becomes his.

        Args:
            cid: the connection that logged in.
            user: the identity it belongs to from now on.
            fields: whatever else the site puts on the connection row, stored
                verbatim.

        Raises:
            ValueError: the target carries ``GUEST_PREFIX`` — nobody logs in as a
                guest, and the value crosses a border of trust to get here.
            KeyError: this worker holds no such connection.

        Acts on the registers AT ONCE — the row changes owner, the user is born
        here if he was unknown, and the pages follow their connection without
        being touched, their owner being derived through it — on the flag the
        tail of this call reads, and on the departure the previous identity may
        have been promised: a guest that is ceasing to exist is not carried to
        the deposit, so that flag is dropped in this same breath. Announces the
        login, which is what the vertex folds.
        """
        if user.startswith(GUEST_PREFIX):
            raise ValueError(f"{user!r} is reserved: nobody logs in as a guest")
        with self.dispatch_lock:
            item = self._connection_register[cid]
            previous_user = item["user"]
            if user not in self._user_register:
                self._add_user_item(user)
            self._user_register[previous_user]["connections"].discard(cid)
            self._user_register[user]["connections"].add(cid)
            item.update(user=user, **fields)
            self._login_previous_user_map[cid] = previous_user
            self._transfer_flags.pop(previous_user, None)
            self.add_worker_event(
                "connection_relabeled", user=user, previous_user=previous_user, session_id=cid
            )

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
        if flag is not None and self._transfers_open:
            await self._execute_transfer(user, flag)

    async def freeze_user(self, user: str) -> bool | None:
        """Park a user in the deposit and announce that he left.

        Args:
            user: the user leaving memory.

        Returns:
            True when he went to the deposit; None when a call of his is what
            holds him — DEFERRED: that call's own end is where his departure
            happens, and the flag that sent him here must stay untouched;
            False when he STAYED for good as far as this attempt goes — a row
            that is not ``active``, a semaphore that never came free, or a
            deposit that refused the parcels (both failures counted, B1).

        Writes his store and one parcel per connection under the folder
        semaphore, announces ``user_frozen`` — placement always ``None``, the
        vertex's to decide — and takes his rows out of memory whole. The row is
        judged THREE times: before the semaphore, under it, and once more when
        the write is over, each time because the wait just ended could have
        brought a call of his into being. That last question is asked in the
        same locked breath as the worker event, so nothing is photographed
        mid-flight: a call born while the disk was writing takes his parcels
        back off the deposit, leaves him active with his flag, and the tail of
        that very call is what parks him. A failed write aborts the whole
        departure: the semaphore goes back, he stays alive where he is, nothing
        is announced, and the failure is logged and counted.
        """
        with self.dispatch_lock:
            first_look = self._user_register.get(user)
            if first_look is None or first_look["state"] != "active":
                return False
            if user in self._pendings:
                return None
        try:
            await self._take_folder_lock(user)
        except TimeoutError:
            self._freeze_failures += 1
            self._logger.error(
                "Worker %s: the folder of %s never came free; he stays here", self.name, user
            )
            return False
        try:
            with self.dispatch_lock:
                item = self._user_register.get(user)
                if item is None or item["state"] != "active":
                    return False
                if user in self._pendings:
                    return None
            store, connection_parcels = self._get_user_parcels(item)
            await self._run_in_pool(
                self.service_pool,
                functools.partial(self._write_parcels, user, store, connection_parcels),
            )
            with self.dispatch_lock:
                leaving = self._get_freezable_item(user) is not None
                if leaving:
                    self.add_worker_event("user_frozen", user=user, placement=None)
                    self._release_rows(user)
                deferred = not leaving and user in self._pendings
            if not leaving:
                self._logger.warning(
                    "Worker %s: a call of %s was born while his parcels were written; "
                    "they go back off the deposit and he stays here",
                    self.name,
                    user,
                )
                await self._run_in_pool(
                    self.service_pool,
                    functools.partial(self._drop_parcels, user, connection_parcels),
                )
                return None if deferred else False
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
        return True

    async def freeze_connection(self, cid: str) -> bool | None:
        """Carry one logged-in connection to the deposit, under its new identity.

        Args:
            cid: the connection whose call has just ended.

        Returns:
            None when this connection did not log in — the ordinary tail of an
            ordinary call; True when it went to the deposit; False when it stayed
            (somebody else is already taking the previous identity away, or the
            deposit refused the parcel, which is counted).

        Writes ONE parcel under the identity the connection now belongs to — the
        connection, its pages, and the store the previous identity accumulated
        when that identity was a guest, which is the only thing that makes an
        anonymous visit survive its own login — then takes the rows out of memory:
        the connection, its pages, the guest left behind, and the new identity
        too when this was all it had here, so that his own next request finds a
        row just born and installs the carried store instead of discarding it.
        A refused write leaves EVERYTHING alive and announces nothing: the
        identity stays resident on this worker with its connection attached,
        which is a legitimate shape of the machine, and the failure is counted.
        """
        with self.dispatch_lock:
            previous_user = self._login_previous_user_map.get(cid)
            if previous_user is None:
                return None
            user = self._connection_register[cid]["user"]
        if not self._claim_departure(previous_user):
            return False
        try:
            await self._take_folder_lock(user)
        except TimeoutError:
            self._freeze_failures += 1
            self._logger.error(
                "Worker %s: the folder of %s never came free; the connection of his "
                "login stays here",
                self.name,
                user,
            )
            return False
        try:
            with self.dispatch_lock:
                parcel = self._connection_parcel(cid)
                if previous_user.startswith(GUEST_PREFIX):
                    parcel["store"] = self._user_register[previous_user]["store"]
                parcel = copy.deepcopy(parcel)
            await self._run_in_pool(
                self.service_pool,
                functools.partial(
                    self.freeze_handler.write_connection_register_item,
                    user,
                    cid,
                    parcel,
                    writer=self.name,
                    cause="login",
                    group=self.group,
                ),
            )
        except Exception:
            self._freeze_failures += 1
            self._logger.exception(
                "Worker %s: the deposit refused the connection of %s; he stays here",
                self.name,
                user,
            )
            return False
        finally:
            self.freeze_handler.release_lock(user, self.name)
            with self.dispatch_lock:
                del self._login_previous_user_map[cid]
            self._release_departure(previous_user)
        with self.dispatch_lock:
            self._release_login_rows(cid, user, previous_user)
        return True

    async def freeze_all_users(self) -> None:
        """Park every user this worker holds, one at a time.

        Every departure is CLAIMED through the one claim the transfer cycle and
        the end-of-call hook go through as well: a user somebody is already
        taking away is left to whoever has him, instead of being queued behind a
        folder semaphore this same worker is holding. The loop breathes between
        two of them: a process that stopped answering its probes while emptying
        itself would be taken for dead. Whoever has a call in flight stays
        behind — the end of that call parks him.
        """
        for user in list(self._user_register):
            if self._claim_departure(user):
                try:
                    await self.freeze_user(user)
                finally:
                    self._release_departure(user)
            await asyncio.sleep(0)

    def plan_transfers(
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
        gate: nothing departs before ``transfer_start_delay`` has passed. A user
        idle past ``user_idle_freeze_minutes`` is ceded like any other — the valve
        is a reason for a ``'T'``, not a road of its own — unless expiry already
        claimed him. Once ``quit`` has begun the plan is terminal: everybody is
        ceded, a row still mid-adoption included (he is a straggler, ceded as
        soon as his pull lands), no flag already given is taken back, and the
        gate already open is not shut again. Every plan that leaves flags
        behind wakes the cycle, so a man named here while the quit waits for a
        straggler leaves with the others.
        """
        now = time.time()
        ceded = set(transfer_users)
        transfers: dict[str, tuple[dict[str, Any], str | None]] = {}
        with self.dispatch_lock:
            if not self._quitting:
                self._transfer_flags = {}
            for user, item in self._user_register.items():
                flag = self._transfer_flags.get(user)
                if flag is None:
                    if item["state"] == "active":
                        idle = now - self._last_real_activity(item)
                        if idle > expiry_delay:
                            flag = "X"
                        elif (
                            self._quitting
                            or user in ceded
                            or idle > self.user_idle_freeze_minutes * SECONDS_PER_MINUTE
                        ):
                            flag = "T"
                    elif self._quitting:
                        flag = "T"
                if flag is not None:
                    self._transfer_flags[user] = flag
                transfers[user] = (item, flag)
            if not self._quitting:
                self._transfers_start_ts = now + self.transfer_start_delay
            if self._transfer_flags:
                # A flag is a promise the vertex must read: the photo that
                # carries it is due whatever the throttle says.
                self._population_changed = True
                self._transfers_done.clear()
                self._transfers_changed.set()
            elif not self._quitting:
                self._transfers_done.set()
        return transfers

    async def execute_transfers(self) -> None:
        """Wait out the gate, then let the flagged users go, one at a time.

        The expired are dropped with their worker events — eliminating them
        everywhere else is the vertex's — and the ceded go to the deposit as
        soon as no call of theirs is in flight; whoever still has one is taken
        by the end of that call. The loop breathes between two users.

        An ordinary cycle passes over the flags it found and comes back. The
        cycle of a ``quit`` does not: it re-reads the flag map at every pass —
        so a man a later shot names, or one whose adoption has only just landed,
        leaves with the others — and returns only when the departures are over,
        which is no flag left and nobody on his way out. Between two passes it
        sleeps on the changes, never on a clock: a flag added, a departure
        ended, and it looks again.
        """
        await asyncio.sleep(self._transfers_start_ts - time.time())
        while True:
            self._transfers_changed.clear()
            for user, flag in list(self._transfer_flags.items()):
                await self._execute_transfer(user, flag)
                await asyncio.sleep(0)
            if not self._quitting:
                return
            self._settle_transfers()
            if self._transfers_done.is_set():
                return
            await self._transfers_changed.wait()

    async def quit(self, *, expiry_delay: float = math.inf) -> None:
        """Leave: everybody departs, the last call is waited for, the process ends.

        Args:
            expiry_delay: the silence past which a user is expired and dropped
                instead of parked.

        Flags every user for cession, waits the gate, parks them as their calls
        end, and only then leaves the process. From here the plan is this
        routine's: a shot taken while it waits for a straggler may name a
        newborn among the departing, but can take nobody off them, and the
        cycle picks that newborn up itself. A straggler is whoever is not gone
        yet — a call of his in flight, or a pull of his still on the way — and
        the exit is behind the last of them, because a process that left with
        an adoption in flight would shut the pool it is running on. A departure
        that fails is counted where it fails, so the exit is reached whatever
        the disk says. Rebirth is not the worker's: whoever wants a successor
        launches one.
        """
        self._flag_everybody_for_departure(expiry_delay)
        await self.execute_transfers()
        await self._transfers_done.wait()
        self.exit_process()

    def exit_process(self) -> None:
        """Leave the process — the last act of ``quit`` and of ``on_wire_lost``.

        Closes the wire, which is what ends the read the shell is parked on, and
        stops the two pools. Nothing here kills a process: the shell returns
        from its run and the process ends with it.
        """
        self._exited = True
        if self.stream is not None:
            self.stream.writer.close()
        self.traffic_pool.shutdown(wait=False)
        self.service_pool.shutdown(wait=False)

    @property
    def _snapshot_due(self) -> bool:
        """Whether the next envelope out owes a photo: a change, or a stale one."""
        return (
            self._population_changed
            or time.time() - self._snapshot_sent_ts >= self.worker_snapshot_ttl
        )

    @property
    def _transfers_open(self) -> bool:
        """Whether the gate opened on the departures last announced."""
        return time.time() >= self._transfers_start_ts

    def _outbound(self, data: dict[str, Any]) -> dict[str, Any]:
        """Attach the photo to an envelope going out, when it is due."""
        if not self._snapshot_due:
            return data
        data[WORKER_SNAPSHOT_KEY] = self.worker_snapshot
        self._snapshot_sent_ts = time.time()
        self._population_changed = False
        return data

    def _take_global_store(self, frame: Frame) -> None:
        """Take the whole global store off an inbound envelope and replace the replica."""
        if isinstance(frame.data, dict) and GLOBAL_STORE_KEY in frame.data:
            self.global_register_item_tytx = frame.data[GLOBAL_STORE_KEY]

    async def _answer_then_quit(self, frame: Frame, payload: dict[str, Any]) -> None:
        """Answer the order to leave with everybody already flagged, then leave.

        Args:
            frame: the CALL being answered.
            payload: its payload; ``expiry_delay`` is the silence past which a
                user is dropped instead of parked.

        Acts on the flags before the answer, so the photo riding it shows every
        user ceded and the level above parks them all in one read.
        """
        expiry_delay = payload.get("expiry_delay", math.inf)
        self._flag_everybody_for_departure(expiry_delay)
        await self.send_reply(frame, result={})
        await self.quit(expiry_delay=expiry_delay)

    def _flag_everybody_for_departure(self, expiry_delay: float) -> None:
        """Cede every user and make the plan terminal: sets ``_quitting`` and the flags."""
        self._quitting = True
        self.plan_transfers(transfer_users=list(self._user_register), expiry_delay=expiry_delay)

    async def _guarded_call(self, frame: Frame) -> None:
        """Serve one CALL with the guard inside the task, so nothing dies unretrieved."""
        try:
            await self.answer_call(frame)
        except Exception:
            self._logger.exception("Worker %s: service of CALL %s failed", self.name, frame.path)

    async def _serve_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The pendings, the row and the stitching — everything that can fail as one.

        The call is written in the user's pendings FIRST, before the row is put
        in order: the pendings cover the adoption too, so no departure can wake
        in the gap between the loading and the serving of the same call. Then
        the row (the store adopted when the verdict authorises it, the
        connection found by itself, the clocks stamped), and the stitching on
        the traffic pool: WSGI is synchronous, and neither the loop nor the
        service pool may be held behind it. The end of the call is where a
        departure that had to wait for it happens.
        """
        cid = payload["http"]["cid"]
        identity = payload.get("identity")
        user = identity if identity and identity != cid else GUEST_PREFIX + cid
        self.open_request(user)
        try:
            await self._resolve_row(user, cid, payload)
            seam = WsgiSeam(self.wsgi_app)
            work = functools.partial(seam.serve, payload["http"], payload.get("identity"))
            return await self._run_in_pool(self.traffic_pool, work)
        finally:
            await self.close_request(user)
            await self.freeze_connection(cid)

    async def _resolve_row(self, user: str, cid: str, payload: dict[str, Any]) -> None:
        """Put the row of an incoming request in order.

        Who the user IS was decided by the caller — the identity the front
        routed on, or a guest named after his own cid. The store comes home
        only if the envelope authorises it; the connection is looked for in
        the deposit with no authorisation at all, and is born empty when
        there is nothing there.
        """
        if payload.get("user_frozen"):
            await self.adopt_user(user)
        await self.adopt_connection(user, cid)
        self._stamp_request(cid)

    def _stamp_request(self, cid: str) -> None:
        """Stamp the connection a request came in on, and the user above it.

        The http form names no page: what it proves is a real call on that
        connection, which is the clock the valve and the expiry read.
        """
        with self.dispatch_lock:
            connection = self._connection_register[cid]
            user = self._user_register[connection["user"]]
            self._stamp_items((connection, user), ("last_rpc_ts",))

    def _stamp_items(self, items: Iterable[dict[str, Any]], clocks: Iterable[str]) -> float:
        """Write the server's own instant on the items given.

        ``last_refresh_ts`` always, the clocks named besides it: a client cannot
        buy immortality by claiming activity, so the instant is taken here.
        """
        now = time.time()
        for item in items:
            item["last_refresh_ts"] = now
            for clock in clocks:
                item[clock] = now
        return now

    def _user_row(self, item: dict[str, Any]) -> dict[str, Any]:
        """One user item projected for the photo: his state, his clocks, his size."""
        row: dict[str, Any] = {
            "state": item["state"],
            "connection_count": len(item["connections"]),
        }
        row.update({clock: item[clock] for clock in CLOCK_NAMES})
        return row

    async def _run_in_pool(self, pool: ThreadPoolExecutor, work: Callable[[], Any]) -> Any:
        """Run one piece of synchronous work on the pool it belongs to."""
        return await asyncio.get_running_loop().run_in_executor(pool, work)

    async def _execute_transfer(self, user: str, flag: str) -> None:
        """Let one flagged user go: the expired dropped, the ceded to the deposit.

        The departure is CLAIMED before the first await — the transfer cycle,
        the end-of-call hook and the mass cycle all come through the same claim,
        and whoever arrives second finds it taken and nothing to do. A row still
        mid-adoption is WAITED for and never parked under its own pull: that is
        how the quit keeps a straggler whose store is still travelling. What
        goes wrong for one user is counted here and goes no further: a whole
        worker leaving must not be stopped by one refused parcel. The flag is
        the promise (owner, 2026-08-16): only a departure that HAPPENED, a
        counted failure or the man's own absence consumes it — a freeze
        deferred to a call's tail keeps it, and the wakeup set below lets the
        quit's cycle find it again, so no instant between a closing call and a
        releasing claim can drop a man between two hands.
        """
        with self.dispatch_lock:
            if self._transfer_flags.get(user) != flag:
                return
            if flag != "X" and user in self._pendings:
                return
            if not self._claim_departure(user):
                return
            adopting = self._unfreeze_waits.get(user)
        settled = True
        try:
            if adopting is not None:
                await adopting.wait()
            if flag == "X":
                self.drop_user(user)
            else:
                settled = await self.freeze_user(user) is not None
        except Exception:
            settled = True
            self._freeze_failures += 1
            self._logger.exception(
                "Worker %s: the departure of %s fell over; the others go on", self.name, user
            )
        finally:
            with self.dispatch_lock:
                if settled or user not in self._user_register:
                    self._transfer_flags.pop(user, None)
                self._release_departure(user)
                self._transfers_changed.set()

    def _claim_departure(self, user: str) -> bool:
        """Take the one departure a user is allowed at a time.

        Args:
            user: the user about to leave.

        Returns:
            True when the claim is the caller's; False when somebody is already
            taking him away.

        Marks him departing. Three roads reach a freeze — the transfer cycle,
        the end-of-call hook, the mass cycle of a lost wire — and the second to
        arrive must find the door shut, or it would queue on a folder semaphore
        this same worker is holding.
        """
        with self.dispatch_lock:
            if user in self._departing_users:
                return False
            self._departing_users.add(user)
            return True

    def _release_departure(self, user: str) -> None:
        """Give the claim back, and say so if that was the last departure."""
        with self.dispatch_lock:
            self._departing_users.discard(user)
            self._settle_transfers()

    def _settle_transfers(self) -> None:
        """Declare the departures over: no flag left, and nobody on his way out.

        Both halves are asked, because a flag popped by the man who is at that
        instant writing his parcels would otherwise let a ``quit`` leave from
        under him.
        """
        with self.dispatch_lock:
            if not self._transfer_flags and not self._departing_users:
                self._transfers_done.set()

    def _get_freezable_item(self, user: str) -> dict[str, Any] | None:
        """The user's row if he may leave right now, None if he may not.

        Args:
            user: the user asked about.

        Returns:
            His register item when it is here and ``active`` and no call of his
            is open; None otherwise — a row mid-adoption is nobody's to park,
            and a store photographed with live calls inside would take their
            work nowhere.
        """
        with self.dispatch_lock:
            item = self._user_register.get(user)
            if item is None or item["state"] != "active" or user in self._pendings:
                return None
            return item

    def _get_user_parcels(self, item: dict[str, Any]) -> tuple[Any, dict[str, dict[str, Any]]]:
        """The store payload and the connection parcels, photographed off the registers.

        Args:
            item: the user register item leaving memory.

        Returns:
            Two things: the payload of his store, and one parcel per connection
            in the shape the adoption reads back, in the order they are written.

        The photograph is DEEP and is taken under the dispatch lock: at the
        scale of these parcels the copy is memory work of microseconds, and
        nothing live then crosses onto the service pool, where the deposit
        pickles what it is handed with no lock of ours at all. The write itself
        is disk and runs with the lock let go, because a loop-side mutation must
        never wait on a spinning disk.
        """
        with self.dispatch_lock:
            parcels = (
                item["store"],
                {cid: self._connection_parcel(cid) for cid in sorted(item["connections"])},
            )
            return copy.deepcopy(parcels)

    def _write_parcels(
        self, user: str, store: Any, connection_parcels: dict[str, dict[str, Any]]
    ) -> None:
        """Write the store and the connection parcels already copied out of the registers.

        Runs on the service pool — this is real disk work — and holds NO lock of
        the dispatch: what it writes was photographed before it was handed over,
        so nothing here reads a register a mutation could be changing.
        """
        self.freeze_handler.write_user_register_item(
            user, store, writer=self.name, cause="freeze", group=self.group
        )
        for cid, parcel in connection_parcels.items():
            self.freeze_handler.write_connection_register_item(
                user, cid, parcel, writer=self.name, cause="freeze", group=self.group
            )

    def _drop_parcels(
        self, user: str, connection_parcels: dict[str, dict[str, Any]]
    ) -> None:
        """Take back off the deposit the parcels of a departure that did not happen.

        Runs on the service pool, under the folder semaphore its caller is still
        holding. Dropping what is not there is the same outcome as dropping what
        is, so a departure abandoned halfway leaves the folder as it found it.
        """
        self.freeze_handler.drop_user_register_item(user)
        for cid in connection_parcels:
            self.freeze_handler.drop_connection_register_item(user, cid)

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

    def _release_login_rows(self, cid: str, user: str, previous_user: str) -> None:
        """Take out of memory what the login left here: the caller holds the lock.

        The connection and its pages are gone to the deposit; the guest that used
        to own it has nothing left anywhere and goes with them; and the identity
        that received it goes too when this connection was all he had here — a
        row left empty would make his own next request look like a resident and
        throw away the store his connection is carrying. A previous identity that
        is NOT a guest STAYS, empty if this was his last connection: he is a
        person the machine knows, and the idleness sweep is what parks him.

        Losing that row is ANNOUNCED, and with a word of its own: he has not gone
        to the deposit and he has not left the machine — he lives wherever he
        lived before this login, and the only rung that has to hear it is the
        handler of this process, whose list of who is on board is what a wild
        death is settled on. A death reading a name whose rows are gone would
        report the loss of somebody who is perfectly well somewhere else.
        """
        item = self._connection_register.pop(cid)
        for page_id in item["pages"]:
            del self._page_register[page_id]
        if previous_user.startswith(GUEST_PREFIX):
            self._user_register.pop(previous_user, None)
        resident = self._user_register.get(user)
        if resident is not None:
            resident["connections"].discard(cid)
            if not resident["connections"]:
                del self._user_register[user]
                self.add_worker_event("user_rows_released", user=user)

    def _release_rows(self, user: str) -> None:
        """Take a user's rows out of memory, saying nothing: his departure said it.

        Everything of his goes — pages, connections, the user row itself. No
        emptied row is left resident: he is the vertex's to place now, and
        whatever comes back for him starts from the parcel in the deposit. Two
        departures end here — the freeze that parked him, and the pull that
        failed to bring him home.
        """
        item = self._user_register[user]
        for cid in sorted(item["connections"]):
            for page_id in sorted(self._connection_register[cid]["pages"]):
                self._remove_page_item(page_id)
            self._remove_connection_item(cid)
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
            self.add_worker_event("drop_user", user=user)

    def _stamped(self, **fields: Any) -> dict[str, Any]:
        """An item born with the three clocks on the server's own instant."""
        now = time.time()
        for clock in CLOCK_NAMES:
            fields.setdefault(clock, now)
        return fields

    def _page_user(self, page_id: str) -> str:
        """The user a page belongs to, derived by walking up its chain."""
        cid = self._page_register[page_id]["connection_id"]
        return self._connection_register[cid]["user"]

    async def _take_folder_lock(self, user: str) -> None:
        """Wait on the loop until the semaphore of the user's folder is this worker's.

        Args:
            user: the user whose folder is being entered.

        Raises:
            TimeoutError: ``deposit_lock_wait_limit`` passed and it never came
                free — a folder nobody gave back, which is a disk to look at and
                never something to go on waiting for in silence.

        The wait is a coroutine and never a thread: whoever holds the semaphore
        is working, and a thread parked here would be a thread not doing that
        work. The FIRST miss says out loud who is holding it, once for this
        wait and not once per look. The limit is a technical floor, not a
        budget: how long a REQUEST may wait before the vertex answers it
        something else is the Commander's parking budget, and arrives with the
        fold.
        """
        if self.freeze_handler.take_lock(user, self.name):
            return
        self._logger.warning(
            "Worker %s: the deposit folder of %s is held by %s; waiting for it",
            self.name,
            user,
            self.freeze_handler.lock_holder(user),
        )
        deadline = time.time() + self.deposit_lock_wait_limit
        while not self.freeze_handler.take_lock(user, self.name):
            if time.time() >= deadline:
                raise TimeoutError(
                    f"the deposit folder of {user} was held by "
                    f"{self.freeze_handler.lock_holder(user)!r} for "
                    f"{self.deposit_lock_wait_limit}s"
                )
            await asyncio.sleep(self.deposit_lock_retry_interval)

    async def _take_from_deposit(self, user: str, read: Any, *args: Any) -> Any:
        """Hold the user's folder, read one parcel and delete it, then let go.

        The reading is real disk work and runs on the service pool; the wait for
        the semaphore is not, and stays a coroutine on the loop. Releasing the
        semaphore takes the folder away when the parcel read was the last thing
        in it. A semaphore that never comes free raises out of here and travels
        to the caller, whose REPLY says so: an adoption nobody can make is an
        answered failure, never a request left hanging.
        """
        await self._take_folder_lock(user)
        try:
            return await self._run_in_pool(
                self.service_pool, functools.partial(read, user, *args)
            )
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
