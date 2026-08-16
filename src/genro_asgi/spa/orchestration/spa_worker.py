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
``plan_transfers`` pairs every user row with a ``transfer_flag``: ``None``
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

**The wire is handed in, never opened here.** Whoever runs this worker in a
process connects to the handler's socket and hands the stream over
(``attach_stream``); the worker presents itself on it — its pid and the
configuration it was built from — and the answer brings the whole global store
down. Then it reads envelopes until the wire ends. A REPLY is resolved inline,
because that is O(1) and the loop belongs on the wire; a CALL is served on its
own task, so a long one cannot make this worker deaf to the next; an EVENT has
no consumer here yet.

**Two pools, and what runs where.** The TRAFFIC pool takes the WSGI stitching
and the long calls, the SERVICE pool — much smaller — takes the deposit IO;
their sizes come down in the spawn payload. Neither ever takes a wait: waiting
for a busy folder is a coroutine on the loop, because whoever holds that
semaphore is working, and a thread parked here would be a thread not doing that
work.

**One op, and one form.** ``/op/ping`` answers the health beat and nothing else
— are you alive. The http CALL form (an ``http`` dict beside the ``identity``
and the ``user_frozen`` verdict) is a request the front packed whole: it lands
on the unified row FIRST — the store adopted when the verdict authorises it, the
connection looked up in the deposit by itself, the clocks stamped — and only
then goes to the ``WsgiSeam`` on the traffic pool. That seam's ``wsgi_app`` is
``None`` here: this class hosts no site, and says so explicitly. A subclass
assigns it, which is the whole contract with the bridge.

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
announcements stay unsaid: whoever finds the parcels needs no telling.
"""

from __future__ import annotations

import asyncio
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
    EVENT_METHOD,
    GLOBAL_STORE_KEY,
    REPLY_METHOD,
    WORKER_SNAPSHOT_KEY,
)
from .worker_handler import PING_OP_PATH

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

#: How long a photo already sent stays fresh enough, in seconds: past it, the
#: next envelope out carries a new one.
WORKER_SNAPSHOT_TTL = 0.5

#: The three clocks every register item carries, in the order of their rank.
CLOCK_NAMES = ("last_refresh_ts", "last_user_ts", "last_rpc_ts")

# The announcements that mean the population changed — a user entering or
# leaving — and therefore that the next envelope out owes a fresh photo.
POPULATION_EVENTS = frozenset({"new_user", "drop_user", "user_frozen", "user_adopted"})

__all__ = [
    "CLOCK_NAMES",
    "DEPOSIT_LOCK_RETRY_INTERVAL",
    "GUEST_PREFIX",
    "TRANSFER_START_DELAY",
    "WORKER_SNAPSHOT_TTL",
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
        transfer_start_delay: float = TRANSFER_START_DELAY,
        user_idle_freeze_delay: float = math.inf,
        main_threadpool_size: int | None = None,
        aux_threadpool_size: int | None = None,
        worker_snapshot_ttl: float = WORKER_SNAPSHOT_TTL,
    ) -> None:
        self.name = name
        self.freeze_handler = freeze_handler
        self.group = group
        self.deposit_lock_retry_interval = deposit_lock_retry_interval
        self.transfer_start_delay = transfer_start_delay
        self.user_idle_freeze_delay = user_idle_freeze_delay
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
        self._events: list[dict[str, Any]] = []
        self._unfreeze_waits: dict[str, asyncio.Event] = {}
        self._pendings: dict[str, int] = {}
        self._transfer_flags: dict[str, str] = {}
        self._transfers_start_ts = 0.0
        self._transfers_done = asyncio.Event()
        self._transfers_done.set()
        self._freeze_failures = 0
        self._exited = False
        self._pending: dict[str, asyncio.Future[Any]] = {}
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

    def offer_event(self, op: str, **payload: Any) -> dict[str, Any]:
        """Queue one announcement for the envelope out.

        Args:
            op: the protocol name of what happened.
            payload: the entity keys that name it.

        Returns:
            The announcement as it was queued.

        Appends to ``events``, and marks the photo due when what happened is a
        user entering or leaving.
        """
        event = {"op": op, "worker": self.name, **payload}
        self._events.append(event)
        if op in POPULATION_EVENTS:
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

        Sets ``global_register_item_tytx``. The presentation carries the first
        photo: a live process is never without one.
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
        does is not decided here: the caller asks for ``on_wire_lost``. Whatever
        this worker had asked upward fails on the way out: nobody is going to
        answer it now.
        """
        try:
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
        finally:
            self._fail_pending()

    def handle_frame(self, frame: Frame) -> None:
        """Route one envelope from the handler, the global store taken off it first.

        Args:
            frame: the envelope as it came off the wire.

        A REPLY is resolved inline — O(1), and the loop belongs on the wire; a
        CALL is served on its own task, so a long op cannot make this worker
        deaf to the next one. An EVENT has no consumer here yet: the descending
        pipes are the Commander's, and the one thing that travels down today —
        the store — was taken off this envelope before anything looked at it.
        """
        self._take_global_store(frame)
        if frame.method == REPLY_METHOD:
            self._resolve_reply(frame)
        elif frame.method == CALL_METHOD:
            task = asyncio.create_task(self._guarded_call(frame))
            self._service_tasks.add(task)
            task.add_done_callback(self._service_tasks.discard)
        elif frame.method == EVENT_METHOD:
            self._logger.info(
                "Worker %s: EVENT %s from its handler, not consumed yet", self.name, frame.path
            )
        else:
            self._logger.warning(
                "Worker %s: unexpected envelope %s from its handler", self.name, frame.method
            )

    async def answer_call(self, frame: Frame) -> None:
        """Answer one CALL: the beat, the http form, or an op nobody here knows.

        Args:
            frame: the CALL as it came off the wire.

        Sends exactly one REPLY, whatever the outcome. The beat asks aliveness
        and gets an empty answer — what it proves is that the answer came.
        """
        payload = frame.data or {}
        if frame.path == PING_OP_PATH:
            await self.send_reply(frame, result={})
        elif "http" in payload:
            await self.serve_http(frame, payload)
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

        Empties ``events`` onto the envelope — the announcements are delivered
        once, and the send IS the delivery — and attaches the photo when it is
        due.
        """
        with self.dispatch_lock:
            events = self._events
            self._events = []
        data: dict[str, Any] = {"events": events}
        if error is not None:
            data["error"] = error
        else:
            data["result"] = result
        await self.stream.write(
            Frame(id=frame.id, method=REPLY_METHOD, path=frame.path, data=self._outbound(data))
        )

    async def call(self, path: str, data: dict[str, Any] | None = None) -> Any:
        """CALL the handler and await its REPLY.

        Args:
            path: the routing key of the call.
            data: the payload; an envelope out of here is always a mapping,
                because any of them may carry the photo.

        Returns:
            The handler's payload, untouched — reading it is the caller's job.

        Raises:
            ConnectionError: the wire died while the answer was awaited.
        """
        frame = Frame(method=CALL_METHOD, path=path, data=self._outbound(dict(data or {})))
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[frame.id] = future
        try:
            await self.stream.write(frame)
            return await future
        finally:
            self._pending.pop(frame.id, None)

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
        if flag is not None and self._transfers_open:
            await self._execute_transfer(user, flag)

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
            await self._run_in_pool(
                self.service_pool, functools.partial(self._write_parcels, user, item)
            )
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
        gate: nothing departs before ``transfer_start_delay`` has passed.
        """
        now = time.time()
        ceded = set(transfer_users)
        transfers: dict[str, tuple[dict[str, Any], str | None]] = {}
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
                transfers[user] = (item, flag)
            self._transfers_start_ts = now + self.transfer_start_delay
            if self._transfer_flags:
                self._transfers_done.clear()
            else:
                self._transfers_done.set()
        return transfers

    async def execute_transfers(self) -> None:
        """Wait out the gate, then let the flagged users go, one at a time.

        The expired are dropped with their announcements — eliminating them
        everywhere else is the vertex's — and the ceded go to the deposit as
        soon as no call of theirs is in flight; whoever still has one is taken
        by the end of that call. The loop breathes between two users.
        """
        await asyncio.sleep(self._transfers_start_ts - time.time())
        for user, flag in list(self._transfer_flags.items()):
            await self._execute_transfer(user, flag)
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
        self.plan_transfers(
            transfer_users=list(self._user_register), expiry_delay=expiry_delay
        )
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
        """Attach the photo to an envelope going out, when it is due.

        One road for the three moments the design names — the presentation, a
        population that changed, a photo gone stale — because there is one slot.
        """
        if not self._snapshot_due:
            return data
        data[WORKER_SNAPSHOT_KEY] = self.worker_snapshot
        self._snapshot_sent_ts = time.time()
        self._population_changed = False
        return data

    def _take_global_store(self, frame: Frame) -> None:
        """Take the whole global store off an inbound envelope and replace the replica.

        The mirror of what the wire does with the photo in the other direction:
        the slot is read before anything asks what kind of envelope this is.
        """
        if isinstance(frame.data, dict) and GLOBAL_STORE_KEY in frame.data:
            self.global_register_item_tytx = frame.data[GLOBAL_STORE_KEY]

    def _resolve_reply(self, frame: Frame) -> None:
        """Hand a REPLY to the parked caller; a caller already gone drops it."""
        future = self._pending.get(frame.id)
        if future is None or future.done():
            self._logger.debug("Worker %s: REPLY %s has no parked caller", self.name, frame.id)
            return
        future.set_result(frame.data or {})

    def _fail_pending(self) -> None:
        """Fail every CALL still waiting: the wire that would have answered is gone."""
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(f"the wire of {self.name} is down"))

    async def _guarded_call(self, frame: Frame) -> None:
        """Serve one CALL with the guard inside the task, so nothing dies unretrieved."""
        try:
            await self.answer_call(frame)
        except Exception:
            self._logger.exception("Worker %s: service of CALL %s failed", self.name, frame.path)

    async def _serve_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """The row, the pendings and the stitching — everything that can fail as one.

        The row comes first (the store adopted when the verdict authorises it,
        the connection found by itself, the clocks stamped), the call is written
        in the user's pendings for as long as it runs, and the stitching happens
        on the traffic pool: WSGI is synchronous, and neither the loop nor the
        service pool may be held behind it. The end of the call is where a
        departure that had to wait for it happens.
        """
        user = await self._resolve_row(payload)
        seam = WsgiSeam(self.wsgi_app)
        work = functools.partial(seam.serve, payload["http"], payload.get("identity"))
        self.open_request(user)
        try:
            return await self._run_in_pool(self.traffic_pool, work)
        finally:
            await self.close_request(user)

    async def _resolve_row(self, payload: dict[str, Any]) -> str:
        """Put the row of an incoming request in order, and say whose it is.

        The identity the front routed on IS the user, except while it is still
        the bare cid of somebody anonymous — that one is a guest by this
        worker's own naming. The store comes home only if the envelope
        authorises it; the connection is looked for in the deposit with no
        authorisation at all, and is born empty when there is nothing there.
        """
        cid = payload["http"]["cid"]
        identity = payload.get("identity")
        user = identity if identity and identity != cid else GUEST_PREFIX + cid
        if payload.get("user_frozen"):
            await self.adopt_user(user)
        await self.adopt_connection(user, cid)
        self._stamp_request(cid)
        return user

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
                self._transfers_done.set()

    def _write_parcels(self, user: str, item: dict[str, Any]) -> None:
        """Write the user's store and one parcel per connection, under the held lock.

        Runs on the service pool — this is real disk work — and takes the
        dispatch lock itself, because the registers it photographs are the
        loop's and must not change under its hands.
        """
        with self.dispatch_lock:
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
        for clock in CLOCK_NAMES:
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

        The reading is real disk work and runs on the service pool; the wait for
        the semaphore is not, and stays a coroutine on the loop. Releasing the
        semaphore takes the folder away when the parcel read was the last thing
        in it.
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
