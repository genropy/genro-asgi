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

**The registers are the shared registry's.** They are built by
``build_registry`` — the seam a consumer replaces to pair its own row types with
the tree — and the three names above are properties onto its ``user_items`` /
``connection_items`` / ``page_items``. So a row is born with the whole data
plane already on it (the live store, the filtered collector, the deposit
container, the subscription sets) and the worker's own fields — ``state``, the
transfer flag, the three clocks — ride that same row: one object, whichever
half of the machine is reading it. Reading goes through the register idioms
(``get``, ``keys``, ``keys_by``, ``in``); writing stays where it already was, in
the single-writer mutators, which speak the registry's own lifecycle vocabulary.

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
it was done. The question is asked ONCE, at the door: what holds that window
shut is the BLOCK whoever orders the departure raises at the vertex before
ordering it, so nothing of his can be born while his parcels are written and no
check under the semaphore would have anything left to decide. The end of a call
is therefore where a
departure that had to wait for it happens — one mechanism, whether the worker is
being emptied or a single user is being ceded — and a departure is CLAIMED
before the first await of its path, so the cycle and the hook can never park the
same user twice.

**The departures are decided above.** At photo time ``plan_transfers`` pairs
every user row with a ``transfer_flag``: ``None`` kept, ``'T'`` ceded. WHO is
ceded is handed in — by the group, which reads the clocks the photo carries and
judges the silence, or by the quit, which cedes everybody. No user is named here
by a policy of this process: silence and expiry are the group's judgment, and
this rung has no gauge of its own. Then THE GATE: the worker does not park
anybody in the same turn it announced them. It waits ``TRANSFER_START_DELAY``,
the time the fold needs to park the users just named, and only then lets them
go, one at a time, the loop breathing between two. So there is ONE departure
scheme and no special case: the
window in which somebody could come back to a row that was already emptied
cannot open, because whoever comes back either is already in the pendings and
his freeze waits for him, or arrives after the fold parked him and starts again
from the vertex with the verdict in hand.

**The ordered freeze.** ``/op/freeze_user`` parks ONE user on the parent's
order. The worker only executes: it waits for whatever holds him — a pull
bringing him home, his calls in flight — parks him through the same departure
every road uses, and only then answers, so the REPLY IS the confirmation and
``user_frozen`` rides it as always. A user this worker does not host is
refused out loud in that same REPLY. The waits are serialization, not
policy: the judgment of WHO sleeps is the caller's alone, and so is the block
that keeps new work of his from arriving while he leaves.

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
down. Then it reads envelopes until the wire ends. A CALL coming down is served
on its own task, so a long one cannot make this worker deaf to the next; a REPLY
coming down is the answer to a call this worker placed UPWARD and is resolved
inline, on the frame id the future was parked under. Any other kind of envelope
is denounced.

**The lane upward.** ``call`` places a CALL of this worker's own on the same
wire and awaits the answer: the id makes the conversations independent, so calls
placed without awaiting the first resolve each with its own REPLY in whatever
order the parent gives them, and an answer carrying an ``error`` raises
``CommanderCallFailed`` rather than returning a result nobody made. What the
site's verbs need is the sync door onto it: they run on a traffic-pool thread,
and ``run_on_loop`` hops the coroutine onto the loop the wire lives on.

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

**The global store is NOT here at all.** There is no replica: the one copy lives
on the commander, and every access is a CALL on the lane. ``store_set`` and
``store_del`` are answered once the store holds the write, so the site's own next
read sees it. ``global_store_lock`` is the read-modify-write form and it is the
protocol of ``GlobalStoreLease``: the grant carries the store itself, the body
mutates a captured working copy nobody else can see, and the release carries the
drained changes up in full shape. A body that raises releases with nothing
applied, and a process that dies holding the grant has the desk give it back.

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
import os
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from genro_bag import Bag
from genro_tytx import from_tytx, to_tytx

from ...channel.frame import REGISTER_METHOD, REGISTER_PATH, Frame, FrameStream
from ..environ import WsgiSeam
from ..global_store import CapturingGlobalStore, GlobalStoreLease
from ..register import Register
from ..register_registry import RegisterRegistry
from .freeze_handler import FreezeHandler
from .worker_connector import (
    CALL_METHOD,
    ENVELOPE_SLOT_PRESENTATION,
    ENVELOPE_SLOT_WORKER_EVENTS,
    ENVELOPE_SLOT_WORKER_SNAPSHOT,
    REPLY_METHOD,
    CommanderCallFailed,
)
from .worker_handler import (
    CENSUS_OP_PATH,
    DROP_CONNECTION_OP_PATH,
    DROP_USER_OP_PATH,
    EVAL_OP_PATH,
    FREEZE_USER_OP_PATH,
    OBSERVE_OP_PATH,
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

#: How long a quit waits for a user whose call is still in flight, in seconds.
#: Past it the wait is dropped and he is parked without that call.
PENDING_CALL_GRACE_SECONDS = 5.0

#: The three clocks every register item carries, in the order of their rank.
CLOCK_NAMES = ("last_refresh_ts", "last_user_ts", "last_rpc_ts")

#: The routing key of the lane call that files a page's table subscription at
#: the desk: it goes up at once and synchronously, so the index is already
#: right when the request that subscribed commits in the same breath.
DESK_SUBSCRIBE_TABLE_PATH = "/desk/subscribe_table"

#: The routing key of the end-of-request exchange: what this request produced
#: goes up, what waits for its page comes back.
DESK_EXCHANGE_PATH = "/desk/exchange"

#: The routing keys of the global store, which lives on the commander and
#: nowhere else: two blind writes, and the two halves of one grant.
DESK_STORE_SET_PATH = "/desk/store_set"
DESK_STORE_DEL_PATH = "/desk/store_del"
DESK_STORE_GET_PATH = "/desk/store_get"
DESK_STORE_LOCK_PATH = "/desk/store_lock"
DESK_STORE_UNLOCK_PATH = "/desk/store_unlock"

#: The routing key one observation climbs: a mutation of this process's
#: registers, as it happens, for whoever is watching at the vertex.
DESK_OBSERVATION_PATH = "/desk/observation"

#: The address kind that names a page itself: the change is a SIGNAL and lands
#: as a deposit on that page's collector — no Bag write, no residue.
SIGNAL_KIND = "page"

#: The address kinds that name a STORE instead of a page. They exist in the
#: addressing vocabulary because a change born on another worker arrives as a
#: real Bag write; nothing on this worker produces one, the site writing its
#: own stores through the Bag it holds.
STATE_KINDS = frozenset({"page_store", "user_store", "connection_store"})

# What the census puts in place of a field it cannot carry as JSON: the field is
# left out of the reading entirely, and a sentinel says so without colliding
# with a legitimate None.
_NOT_JSON_SAFE = object()

# The connection-row fields a parcel leaves behind: the edges of the ownership
# tree, which the adoption rebuilds from the rows it lands, and the reserved key
# the register seeds itself and refuses as a keyword.
PARCEL_CONNECTION_REBUILT_FIELDS = frozenset({"register_item_id", "user", "pages"})

# The page-row fields a parcel leaves behind: the reserved key, the two edges to
# its connection, and the live objects bound to THIS process's Bags — the two
# collectors and the deposit container — which the rebirth builds itself.
PARCEL_PAGE_REBUILT_FIELDS = frozenset(
    {
        "register_item_id",
        "connection_id",
        "collector",
        "user_view",
        "dbevents",
    }
)

# The page-row fields the birth seeds itself and would refuse as keywords: they
# travel in the parcel and are put back on the row once it exists.
PARCEL_PAGE_REPLAYED_FIELDS = ("subscribed_paths", "store_subscriptions", "table_subscriptions")

# The worker events that mean the population changed — a user entering or
# leaving — and therefore that the next envelope out owes a fresh photo.
POPULATION_WORKER_EVENTS = frozenset(
    {
        "new_user",
        "drop_user",
        "user_frozen",
        "user_adopted",
        "connection_user_changed",
        "user_rows_released",
    }
)

__all__ = [
    "CLOCK_NAMES",
    "DEPOSIT_LOCK_RETRY_INTERVAL",
    "DEPOSIT_LOCK_WAIT_LIMIT",
    "DESK_EXCHANGE_PATH",
    "DESK_STORE_DEL_PATH",
    "DESK_STORE_GET_PATH",
    "DESK_STORE_LOCK_PATH",
    "DESK_STORE_SET_PATH",
    "DESK_STORE_UNLOCK_PATH",
    "DESK_SUBSCRIBE_TABLE_PATH",
    "GUEST_PREFIX",
    "PARCEL_CONNECTION_REBUILT_FIELDS",
    "PARCEL_PAGE_REBUILT_FIELDS",
    "PARCEL_PAGE_REPLAYED_FIELDS",
    "SIGNAL_KIND",
    "STATE_KINDS",
    "TRANSFER_START_DELAY",
    "WORKER_SNAPSHOT_TTL",
    "RequestSlot",
    "SpaWorker",
]


class RequestSlot:
    """What one request has produced so far, waiting for its own exchange.

    The events of a request belong to THAT request: they accumulate here and
    leave together at its end. ``datachanges`` are the addressed writes and
    ``dbevents`` the table-event deposits that go up the lane; ``own_dbevents``
    are the ``local_only`` deposits of the hidden transaction, which never
    leave this process and reach the origin page's own collect alone.
    ``connection_id`` is the one field that travels back OUT: the front reads
    it off the reply to write its cookie with.
    """

    def __init__(self) -> None:
        self.datachanges: list[dict[str, Any]] = []
        self.dbevents: list[dict[str, Any]] = []
        self.own_dbevents: list[dict[str, Any]] = []
        #: The connection the site named while serving this request — born, or
        #: changed owner. None when it named none, which is every request that
        #: reused the connection its cookie already carried.
        self.connection_id: str | None = None


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
        self.worker_snapshot_ttl = worker_snapshot_ttl
        self.traffic_pool = ThreadPoolExecutor(
            max_workers=main_threadpool_size, thread_name_prefix=f"{name}-traffic"
        )
        self.service_pool = ThreadPoolExecutor(
            max_workers=aux_threadpool_size, thread_name_prefix=f"{name}-service"
        )
        #: The wire this worker speaks on, handed in by whoever runs it.
        self.stream: FrameStream | None = None
        #: The loop the wire lives on, taken with the wire: what a pool thread
        #: hops onto to place a call of its own.
        self.loop: asyncio.AbstractEventLoop | None = None
        #: One future per CALL this worker placed upward, by frame id: the read
        #: loop resolves them as the answers land, in whatever order they do.
        self._parent_calls: dict[str, asyncio.Future[Any]] = {}
        #: The consumer seam of the http CALL form: a WSGI callable a subclass
        #: assigns. None here — this class hosts no site of its own.
        self.wsgi_app: Callable[..., Any] | None = None
        self.dispatch_lock = threading.RLock()
        #: The rows of the three registers, and the lifecycle vocabulary that
        #: moves them: the shared registry, built through its own hook.
        self.registry = self.build_registry()
        #: The tables somebody subscribes somewhere, as the last exchange reply
        #: told it: the source filter of this worker, at most one exchange out
        #: of date, which is the price of asking nobody.
        self.subscribed_tables: set[str] = set()
        #: Whether every register mutation of this process is reported up the
        #: lane as it happens. Off until somebody watches, and switched only by
        #: the vertex: a debug surface must not cost anything when unobserved.
        self.observation_on = False
        #: One slot per traffic-pool thread. A request is served on one thread
        #: from end to end, so the thread IS the request and two of them served
        #: at once never see each other's events.
        self._request_slots = threading.local()
        self._worker_events: list[dict[str, Any]] = []
        self._observation_tasks: set[asyncio.Task[None]] = set()
        self._unfreeze_waits: dict[str, asyncio.Event] = {}
        self._pendings: dict[str, int] = {}
        #: One event per user a freeze order is waiting on: set by the end of
        #: his last call, which is the instant the order may park him.
        self._freeze_order_waits: dict[str, asyncio.Event] = {}
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

    def build_registry(self) -> RegisterRegistry:
        """Build the registry this worker holds its rows in.

        Returns:
            A fresh ``RegisterRegistry``.

        The seam a consumer replaces to pair its own row types with the tree:
        whoever hosts a site subclasses this and returns its own registry, and
        nothing else in this class names the concrete class.
        """
        return RegisterRegistry()

    @property
    def user_register(self) -> Register:
        """The users this worker holds, by identity.

        Returns:
            The live register — read it, and leave the writing to the mutators.
        """
        return self.registry.user_items

    @property
    def connection_register(self) -> Register:
        """The connections this worker holds, by cid.

        Returns:
            The live register — read it, and leave the writing to the mutators.
        """
        return self.registry.connection_items

    @property
    def page_register(self) -> Register:
        """The pages this worker holds, by page id.

        Returns:
            The live register — read it, and leave the writing to the mutators.
        """
        return self.registry.page_items

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
    def pss_bytes(self) -> int | None:
        """The proportional set size of this process, in bytes.

        Returns:
            The ``Pss`` total from Linux ``smaps_rollup``. Shared pages are
            divided among the processes mapping them, unlike RSS, so summing
            this gauge across prefork workers does not charge the template's
            pages once per child. ``None`` is the honest answer on platforms
            without the rollup file or when the kernel refuses the reading.
        """
        try:
            with open("/proc/self/smaps_rollup", encoding="ascii") as rollup:
                for line in rollup:
                    if not line.startswith("Pss:"):
                        continue
                    fields = line.split()
                    if len(fields) != 3 or fields[2] != "kB":
                        return None
                    kilobytes = int(fields[1])
                    return kilobytes * 1024 if kilobytes >= 0 else None
        except (OSError, ValueError):
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
            application's business, never the observer's. Each user row carries
            his cumulative service counters — ``served_call_count``,
            ``service_seconds``, ``pending_call_count`` — raw readings the
            envelope layer turns into per-interval deltas. The CPU is measured
            by the commander through psutil, never by this photo. The counters live in
            the register item and never reach a frozen parcel: the freeze
            persists the store and the connections, not the row itself.
        """
        with self.dispatch_lock:
            return {
                "pid": os.getpid(),
                "name": self.name,
                "group": self.group,
                "rss_bytes": self.rss_bytes,
                "pss_bytes": self.pss_bytes,
                "user_count": len(self.user_register),
                "connection_count": len(self.connection_register),
                "page_count": len(self.page_register),
                "connections": {
                    cid: {
                        "user": item["user"],
                        **{clock: item[clock] for clock in CLOCK_NAMES},
                    }
                    for cid, item in self._get_register_rows(self.connection_register)
                },
                "users": {
                    user: {
                        "item": self._user_row(user, item),
                        "transfer_flag": self._transfer_flags.get(user),
                    }
                    for user, item in self._get_register_rows(self.user_register)
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
        if self.observation_on:
            self.report_observation(op, payload)
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
            if user not in self.user_register:
                self.add_user(user)
            item = self._add_connection_item(cid, user, **fields)
            self.request_slot.connection_id = cid
            self.add_worker_event("new_connection", user=user, connection_id=cid)
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
            if cid not in self.connection_register:
                self.add_connection(cid, user)
            item = self._add_page_item(page_id, cid, **fields)
            self.add_worker_event(
                "new_page",
                user=self.registry.page_user(page_id),
                page_id=page_id,
                connection_id=cid,
                table_subscriptions=sorted(item["table_subscriptions"]),
            )
            return item

    def new_connection(self, identity: str, **fields: Any) -> dict[str, Any]:
        """Open a connection in the form the site calls it, identity first.

        Args:
            identity: the connection identity — the session id.
            fields: anything else the row should carry; ``user`` names the owner
                and its absence is the anonymous reception.

        Returns:
            The connection register item.

        Acts on the registers through ``add_connection``, so the announcements
        rise exactly as they do for the reception.
        """
        return self.add_connection(identity, fields.pop("user", None), **fields)

    def new_page(
        self, identity: str, page_id: str, **fields: Any
    ) -> dict[str, Any]:
        """Open a page under its user in the form the site calls it.

        Args:
            identity: the user the page belongs to.
            page_id: the page identity.
            fields: anything else the row should carry; ``connection_id``
                names the connection it hangs from.

        Returns:
            The page register item.

        Acts on the registers through ``add_page``, which brings the connection
        and the user above it into being when they are unseen and announces the
        cascade in the order it happened.
        """
        cid = fields.pop("connection_id", None)
        return self.add_page(page_id, cid, identity, **fields)

    def drop_page(self, identity: str, page_id: str) -> None:
        """Take one page off this worker, and whatever it was the last of.

        Args:
            identity: the user the site names as the page's owner; the owner
                this worker acts on is derived through the chain.
            page_id: the page to be gone.

        Removes the item and announces ``drop_page``, then the
        ``drop_connection`` and ``drop_user`` its departure empties. A page
        already gone is the same outcome: nothing happens and nothing is said.
        """
        with self.dispatch_lock:
            page = self.page_register.get(page_id)
            if page is None:
                return
            cid = page["connection_id"]
            user = self.registry.page_user(page_id)
            self._remove_page_item(page_id)
            self.add_worker_event("drop_page", user=user, page_id=page_id)
            if not self.connection_register.get(cid)["pages"]:
                self._remove_connection_item(cid)
                self.add_worker_event("drop_connection", user=user, connection_id=cid)
                self._drop_emptied_user(user)

    def drop_connection(self, identity: str, connection_id: str) -> None:
        """Take a whole connection off this worker, its pages first.

        Args:
            identity: the user the site names as the connection's owner; the
                owner this worker acts on is read off the row.
            connection_id: the connection to be gone.

        Raises:
            KeyError: this worker holds no such connection.

        Removes the pages and the connection, announcing ``drop_pages`` (when it
        had any), ``drop_connection``, and ``drop_user`` if it was the user's
        last.
        """
        cid = connection_id
        with self.dispatch_lock:
            item = self.connection_register.get(cid)
            if item is None:
                raise KeyError(f"drop_connection: no connection {cid!r} here")
            user = item["user"]
            page_ids = sorted(item["pages"])
            for page_id in page_ids:
                self._remove_page_item(page_id)
            if page_ids:
                self.add_worker_event("drop_pages", user=user, page_ids=page_ids)
            self._remove_connection_item(cid)
            self.add_worker_event("drop_connection", user=user, connection_id=cid)
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
            item = self.user_register.get(user)
            if item is None:
                return
            connection_ids = sorted(item["connections"])
            page_ids = sorted(
                page_id
                for cid in connection_ids
                for page_id in self.connection_register.get(cid)["pages"]
            )
            for page_id in page_ids:
                self._remove_page_item(page_id)
            if page_ids:
                self.add_worker_event("drop_pages", user=user, page_ids=page_ids)
            for cid in connection_ids:
                self._remove_connection_item(cid)
            if connection_ids:
                self.add_worker_event(
                    "drop_connections", user=user, connection_ids=connection_ids
                )
            self._remove_user_item(user)
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
            owner = self.registry.page_user(page_id)
            page = self.page_register.get(page_id)
            connection = self.connection_register.get(page["connection_id"])
            user = self.user_register.get(owner)
            return self._stamp_items((page, connection, user), clocks)

    # ------------------------------------------------------------------
    # The local data plane: what a page hears about, what it collects, and
    # the drain that hands both species over. Every write addressed here is
    # LOCAL by stickiness — the target page lives on this worker of fact —
    # so nothing ascends, while the addressing the second pass will route
    # already rides in the signatures.
    # ------------------------------------------------------------------

    @property
    def request_slot(self) -> RequestSlot:
        """The slot of the request being served on this thread, born on first touch."""
        slot = getattr(self._request_slots, "slot", None)
        if slot is None:
            slot = RequestSlot()
            self._request_slots.slot = slot
        return slot

    def open_request_slot(self) -> None:
        """Put a fresh slot on this thread, so no request inherits another's events.

        Called on the traffic-pool thread the request is about to be served on:
        whatever the previous one left there — a request that never collected —
        goes with it instead of leaking into this one.
        """
        self._request_slots.slot = RequestSlot()

    def apply_forwarded(self, bag: Bag, change: dict[str, Any]) -> None:
        """Apply a change born elsewhere to a local Bag (a STATE delivery).

        Args:
            bag: the store the change belongs to — the user's own.
            change: the change as the desk handed it back.

        The write is a real write, so the local collectors capture it with a
        local ``change_ts``: ordering stays on local time. What the producer
        knew travels as ``_original_ts``, an attribute added to the ones the
        change carried. A delete removes the node: setting None would be a
        different state from *gone*.
        """
        path = change["key"]["path"]
        reason = change["key"]["reason"]
        if change["delete"]:
            bag.pop(path, _reason=reason)
            return
        attributes = dict(change["attributes"] or {})
        attributes["_original_ts"] = change["change_ts"]
        bag.set_item(
            path,
            change["value"],
            _attributes=attributes,
            _reason=reason,
            _fired=change["key"]["fired"],
        )

    def setStoreSubscription(  # noqa: N802 - reserved protocol name
        self,
        identity: str,
        page_id: str,
        storename: str,
        prefix: str,
        active: bool = True,
    ) -> dict[str, Any]:
        """Open (or close) a page's window onto a store, by path prefix.

        Args:
            identity: the user the calling site speaks for.
            page_id: the page whose window moves.
            storename: ``'page'`` for the page's own store, ``'user'`` for the
                view onto its owner's.
            prefix: the path prefix the window covers.
            active: opening it, or closing it.

        Returns:
            The page register item.

        Raises:
            KeyError: no such page here.
            ValueError: any other storename — an impossible address.

        Moves the row's subscription set and the collector's prefix set
        together: the set is what a move packages, the collector what the
        drain reads.
        """
        with self.dispatch_lock:
            page = self.page_register.get(page_id)
            if page is None:
                raise KeyError(f"setStoreSubscription: unknown page {page_id!r}")
            if storename == "page":
                if active:
                    page["subscribed_paths"].add(prefix)
                    page["collector"].subscribe_path(prefix)
                else:
                    page["subscribed_paths"].discard(prefix)
                    page["collector"].unsubscribe_path(prefix)
            elif storename == "user":
                if active:
                    self.registry.subscribe_store_path(page_id, prefix)
                elif page["user_view"] is not None:
                    page["store_subscriptions"].discard(prefix)
                    page["user_view"].unsubscribe_path(prefix)
            else:
                raise ValueError(f"setStoreSubscription: no store named {storename!r}")
            return page

    def collect_page(self, page_id: str) -> dict[str, Any]:
        """End the request: exchange with the desk, then drain everything for one page.

        Args:
            page_id: the page the delivery is for.

        Returns:
            ``{"datachanges": [...], "dbevents": [...]}`` — the page's own
            collector and its ``user_view`` merged with the changes the desk
            handed back, sorted by ``change_ts`` with a stable sort; the
            deposits are their own species in their own key, never dressed as
            datachanges.

        Raises:
            KeyError: no such page here.
            CommanderCallFailed: the desk refused the exchange.

        Empties the request slot, both collectors and — through the exchange —
        the page's queues at the desk. The exchange happens on EVERY request,
        empty-handed included: retiring what waits is the reason it exists. The
        STATE writes it brings back are applied to the user's own Bag BEFORE
        the drain, so the page that retired them reads them in this very
        delivery and its siblings capture them on their own ``user_view``.
        """
        with self.dispatch_lock:
            if self.page_register.get(page_id) is None:
                raise KeyError(f"collect_page: unknown page {page_id!r}")
            user = self.registry.page_user(page_id)
        slot = self.request_slot
        reply = self.run_on_loop(
            self.call(
                DESK_EXCHANGE_PATH,
                {
                    "page_id": page_id,
                    "user": user,
                    "datachanges": slot.datachanges,
                    "dbevents": slot.dbevents,
                },
            )
        )
        slot.datachanges = []
        slot.dbevents = []
        self.subscribed_tables = set(reply["tables"])
        with self.dispatch_lock:
            page = self.page_register.get(page_id)
            if page is None:
                raise KeyError(f"collect_page: unknown page {page_id!r}")
            store = self.user_register.get(user)["store"]
            for change in from_tytx(reply["store_changes"], "json"):
                self.apply_forwarded(store, change)
            datachanges = page["collector"].drain()
            if page["user_view"] is not None:
                datachanges.extend(page["user_view"].drain())
            datachanges.extend(from_tytx(reply["datachanges"], "json"))
            dbevents = reply["dbevents"] + slot.own_dbevents
            slot.own_dbevents = []
        datachanges.sort(key=lambda change: change["change_ts"])
        return {"datachanges": datachanges, "dbevents": dbevents}

    def _refuse_unservable_address(
        self, op: str, kind: str, target: str | None, filters: str | None
    ) -> None:
        """Refuse at the verb what this pass does not deliver: the bad call fails alone.

        Args:
            op: the refusing verb, named in the error.
            kind: what ``target`` names.
            target: the addressed page, or the addressed user's own store.
            filters: the broadcast address, whose delivery is the second pass's.

        Raises:
            NotImplementedError: a ``filters`` broadcast, or a STATE kind other
                than ``user_store`` — nothing local can serve them yet, and a
                silent success would be a write into nowhere.
            KeyError: a target this worker does not hold — with one worker of
                fact, a target not held does not exist.
        """
        if filters is not None:
            raise NotImplementedError(f"{op}: filtered addresses are not delivered by this pass")
        if kind in STATE_KINDS and kind != "user_store":
            raise NotImplementedError(f"{op}: kind {kind!r} is not delivered by this pass")
        register = self.user_register if kind == "user_store" else self.page_register
        with self.dispatch_lock:
            if target not in register:
                raise KeyError(f"{op}: no target {target!r} here")

    def set_datachange(
        self,
        identity: str,
        change: str,
        kind: str = SIGNAL_KIND,
        target: str | None = None,
        filters: str | None = None,
        replace: bool = False,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Write a change toward an addressed target, bypassing its filter.

        Args:
            identity: the user the calling site speaks for.
            change: the TYTX-encoded change dict.
            kind: what ``target`` names — a page (the SIGNAL address) or a
                store.
            target: the addressed page.
            filters: the alternative address, a broadcast over the pages a
                filter selects.
            replace: coalesce with the pending change of the same key — same
                path, same reason, same fired — so a value written over and
                over reaches the browser once.
            addressing: the caller's own ``page_id``, the pull cycle of the
                call and never the target of the write.

        Returns:
            The address the write took, as it was resolved.

        Raises:
            NotImplementedError: a ``filters`` broadcast, or a STATE kind other
                than ``user_store`` — addresses this pass does not deliver.
            KeyError: a target this worker does not hold.

        Lays the message on the request slot: the desk resolves every address,
        the own page included — there is no local shortcut, because the exchange
        that carries it happens at the end of the request anyway. The address is
        validated HERE, before the slot: an unservable write fails alone, in the
        caller's own call, and never poisons the request's exchange.
        """
        self._refuse_unservable_address("set_datachange", kind, target, filters)
        self.request_slot.datachanges.append(
            {
                "op": "set_datachange",
                "kind": kind,
                "target": target,
                "filters": filters,
                "replace": replace,
                "change": change,
            }
        )
        return {"kind": kind, "target": target, "filters": filters, "replace": replace}

    def reset_datachanges(
        self,
        identity: str,
        target: str | None = None,
        filters: str | None = None,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Empty the pending changes of the addressed page without reading them.

        Args:
            identity: the user the calling site speaks for.
            target: the addressed page.
            filters: the alternative address.
            addressing: the caller's own ``page_id``.

        Returns:
            The address the reset took.

        Raises:
            NotImplementedError: a ``filters`` address, undelivered by this pass.
            KeyError: a target this worker does not hold.

        Lays the message on the request slot: the desk empties the queue it
        keeps for that page.
        """
        self._refuse_unservable_address("reset_datachanges", SIGNAL_KIND, target, filters)
        self.request_slot.datachanges.append(
            {
                "op": "reset_datachanges",
                "kind": SIGNAL_KIND,
                "target": target,
                "filters": filters,
            }
        )
        return {"target": target, "filters": filters}

    def drop_datachanges(
        self,
        identity: str,
        path: str,
        target: str | None = None,
        filters: str | None = None,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Discard the pending changes under one path of the addressed page.

        Args:
            identity: the user the calling site speaks for.
            path: the prefix whose pending changes go.
            target: the addressed page.
            filters: the alternative address.
            addressing: the caller's own ``page_id``.

        Returns:
            The address the drop took, and the path it named.

        Raises:
            NotImplementedError: a ``filters`` address, undelivered by this pass.
            KeyError: a target this worker does not hold.

        Lays the message on the request slot: the desk drops that prefix from
        the queue it keeps for that page.
        """
        self._refuse_unservable_address("drop_datachanges", SIGNAL_KIND, target, filters)
        self.request_slot.datachanges.append(
            {
                "op": "drop_datachanges",
                "kind": SIGNAL_KIND,
                "target": target,
                "filters": filters,
                "path": path,
            }
        )
        return {"target": target, "filters": filters, "path": path}

    # ------------------------------------------------------------------
    # The table events: their own ops, their own index, their own species in
    # the drain. With one worker of fact «announce locally» is the whole
    # announcement — nothing ascends — while the signatures are the full ones,
    # so the delivery between workers will not have to reopen them.
    # ------------------------------------------------------------------

    def subscribeTable(  # noqa: N802 - reserved protocol name
        self,
        identity: str,
        table: str,
        page_id: str,
        subscribe: bool = True,
        subscribeMode: str | None = None,  # noqa: N803 - reserved protocol name
    ) -> dict[str, Any]:
        """Subscribe (or unsubscribe) the calling page to a table's events.

        Args:
            identity: the user the calling site speaks for.
            table: the table whose events the page wants.
            page_id: the caller's own page — the subscriber is whoever asks, so
                there is no target to address.
            subscribe: opening the subscription, or closing it.
            subscribeMode: vestigial, accepted and ignored exactly as the daemon
                does: callers still pass it, and refusing it would break them at
                mount time.

        Returns:
            The subscription as it was taken.

        Raises:
            KeyError: no such page here.

        Moves the row's ``table_subscriptions`` set — what a move packages —
        and then files the interest at the desk, which is the only index there
        is. The call is synchronous: when this request goes on to commit, the
        index it just changed is already right, so the window «I subscribe and
        commit in the same breath» is closed by construction. The reply's table
        list refreshes the source filter.
        """
        with self.dispatch_lock:
            page = self.page_register.get(page_id)
            if page is None:
                raise KeyError(f"subscribeTable: unknown page {page_id!r}")
            if subscribe:
                page["table_subscriptions"].add(table)
            else:
                page["table_subscriptions"].discard(table)
        reply = self.run_on_loop(
            self.call(
                DESK_SUBSCRIBE_TABLE_PATH,
                {"page_id": page_id, "table": table, "subscribe": subscribe},
            )
        )
        self.subscribed_tables = set(reply["tables"])
        return {"page_id": page_id, "table": table, "subscribe": subscribe}

    def notifyDbEvents(  # noqa: N802 - reserved protocol name
        self,
        identity: str,
        dbevents: dict[str, Any],
        reason: str | None = None,
        page_id: str | None = None,
        local_only: bool = False,
        **addressing: Any,
    ) -> dict[str, Any]:
        """Announce a commit's table events to the pages that subscribed them.

        Args:
            identity: the user the calling site speaks for.
            dbevents: ``{table: batch}`` as the commit produced it.
            reason: what the commit was, carried through to the subscribers.
            page_id: the origin page — the caller's own — travelling as
                ``from_page_id`` so a subscriber can tell its own commit from
                somebody else's.
            local_only: the hidden transaction, whose events belong to the page
                that made them and to nobody else: the deposits stay on the
                slot for the origin page's own collect and never reach the wire.
            addressing: what the desk would read of the address; nothing reads
                it while every deposit is announced by its table alone.

        Returns:
            The tables actually announced.

        Lays the deposits on the request slot, whence the end-of-request
        exchange carries them to the desk. Filtered at the source: a table no
        page anywhere subscribes is not announced at all — a thousand events
        nobody wants die here rather than on the wire — and neither is a table
        whose batch is empty. The deposits are shaped once, so every subscriber
        reads the very same object and the origin's own ``ts``.
        """
        deposits = [
            self.dbevent_deposit(table, batch, page_id, reason)
            for table, batch in (dbevents or {}).items()
            if batch and (local_only or table in self.subscribed_tables)
        ]
        slot = self.request_slot
        if local_only:
            slot.own_dbevents.extend(deposits)
        else:
            slot.dbevents.extend(deposits)
        return {"tables": [deposit["table"] for deposit in deposits]}

    def dbevent_deposit(
        self,
        table: str,
        batch: Any,
        from_page_id: str | None,
        reason: str | None,
    ) -> dict[str, Any]:
        """The deposit one table's batch becomes in a page's ``dbevents`` list.

        Args:
            table: the table the batch belongs to.
            batch: the events as the commit produced them.
            from_page_id: the origin page.
            reason: what the commit was.

        Returns:
            The shaped deposit, JSON by construction — ``ts`` an epoch float,
            the batch what the caller handed over — so it rides the rail as it
            is.
        """
        return {
            "table": table,
            "batch": batch,
            "from_page_id": from_page_id,
            "reason": reason,
            "ts": time.time(),
        }

    def store_set(self, identity: str, path: str, value: Any = None, **addressing: Any) -> Any:
        """Write one path of the global store: a CALL on the lane, answered once it landed.

        Args:
            identity: whose request this is — the site's own first positional.
            path: the path of the store to write.
            value: what to write there.
            addressing: the addressing the site passes and the store ignores.

        Returns:
            The path written, as the site's protocol expects. The answer means
            the store already holds the value: there is no replica to catch up.

        Raises:
            CommanderCallFailed: the desk refused the write.
        """
        return self.run_on_loop(self.call(DESK_STORE_SET_PATH, {"path": path, "value": value}))

    def store_del(self, identity: str, path: str, **addressing: Any) -> Any:
        """Remove one path of the global store — it travels exactly like a write.

        Args:
            identity: whose request this is.
            path: the path to remove.
            addressing: the addressing the site passes and the store ignores.

        Returns:
            The path removed. The node is GONE when the answer lands, not None.

        Raises:
            CommanderCallFailed: the desk refused the removal.
        """
        return self.run_on_loop(self.call(DESK_STORE_DEL_PATH, {"path": path}))

    def store_get(self, identity: str, path: str, **addressing: Any) -> Any:
        """Read one path of the global store: a CALL on the lane, the current value back.

        Args:
            identity: whose request this is — the site's own first positional.
            path: the path of the store to read.
            addressing: the addressing the site passes and the store ignores.

        Returns:
            The value the master holds at that path — decoded whole, datetimes
            and nested Bags included; None when the store holds nothing there,
            the Bag's own read semantics. A read pays its round trip on the
            lane and never holds a stale copy: what it answers is the master
            at the moment it was asked.

        Raises:
            CommanderCallFailed: the desk refused the read.
        """
        reply = self.run_on_loop(self.call(DESK_STORE_GET_PATH, {"path": path}))
        return from_tytx(reply["value"], "json")

    def global_store_lock(self) -> GlobalStoreLease:
        """One read-modify-write hold of the global store: ``with`` or ``async with``.

        Returns:
            The lease, which yields the working copy's Bag to its body. The
            vehicle follows the caller — a pool thread blocks on the loop, a
            coroutine stays on it — and both are the same protocol.

        NEVER open a lease while holding ``dispatch_lock``: both halves place a
        lane call, and a holder would park on its own lock.
        """
        return GlobalStoreLease(self)

    async def acquire_global_lock(self, request_id: str) -> CapturingGlobalStore:
        """Ask the desk for the store and mount what comes back as a working copy.

        Args:
            request_id: the hold's own id, which the release quotes back.

        Returns:
            The working copy, hydrated BEFORE its collector attaches — a captured
            hydration would ship the whole store back as changes at the release.

        Raises:
            CommanderCallFailed: the desk refused the grant.
        """
        grant = await self.call(
            DESK_STORE_LOCK_PATH, {"worker": self.name, "request_id": request_id}
        )
        return CapturingGlobalStore(from_tytx(grant["store"], "json"))

    async def release_global_lock(
        self, request_id: str, copy: CapturingGlobalStore, apply: bool = True
    ) -> None:
        """Give the grant back, carrying the drained changes when the body succeeded.

        Args:
            request_id: the grant being given back.
            copy: the working copy the body mutated.
            apply: False when the body raised — the release carries nothing, and
                the store is left exactly as the grant found it.

        Raises:
            CommanderCallFailed: the desk refused the release.

        The copy stops capturing either way: a released hold is thrown away.
        """
        changes = copy.drain() if apply else []
        copy.detach()
        await self.call(
            DESK_STORE_UNLOCK_PATH,
            {"request_id": request_id, "changes": to_tytx(changes, "json")},
        )

    def attach_stream(self, stream: FrameStream) -> None:
        """Take the wire this worker speaks on.

        Args:
            stream: the frame codec over the connection to the handler.

        Sets ``stream`` and ``loop``. The worker never opens the wire: whoever
        runs this worker in a process connects, and hands the connection over —
        from that process's own loop, which is the one the lane then lives on.
        """
        self.stream = stream
        self.loop = asyncio.get_running_loop()

    async def send_presentation(self, config: dict[str, Any]) -> None:
        """Present this process on the wire and install the store that answers.

        Args:
            config: the spawn payload this process was built from, echoed back
                so the handler sees what its child understood of it.

        Returns once the handler has answered, which is what tells this process
        it is on the wire.
        """
        await self.stream.write(
            Frame(
                method=REGISTER_METHOD,
                path=REGISTER_PATH,
                data=self._outbound({ENVELOPE_SLOT_PRESENTATION: os.getpid(), "config": config}),
            )
        )
        await self.stream.read()

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
        """Route one envelope from the handler: a CALL to serve, a REPLY to resolve.

        Args:
            frame: the envelope as it came off the wire.

        A CALL is served on its own task, so a long op cannot make this worker
        deaf to the next one; a REPLY is the answer to a call this worker placed
        upward and is resolved inline, on the frame id it was parked under.
        """
        if frame.method == CALL_METHOD:
            task = asyncio.create_task(self._guarded_call(frame))
            self._service_tasks.add(task)
            task.add_done_callback(self._service_tasks.discard)
        elif frame.method == REPLY_METHOD:
            self._resolve_parent_reply(frame)
        else:
            self._logger.warning(
                "Worker %s: unexpected envelope %s from its handler", self.name, frame.method
            )

    def eval_expression(self, expr: str) -> str:
        """Evaluate one debug expression against this process, repr back.

        Args:
            expr: a Python expression; ``worker`` names this instance.

        Returns:
            The ``repr`` of the value — the debug door's whole answer, so
            anything unforeseen is readable without a tool having predicted it.

        Evaluates under ``dispatch_lock``, so the rows it reads are coherent.
        Full eval power by construction: the door exists only where the
        console surface was mounted on purpose, never in production.
        """
        with self.dispatch_lock:
            return repr(eval(expr, {"worker": self}))

    def report_observation(self, kind: str, data: dict[str, Any]) -> None:
        """Send one observation up the lane, and forget about it.

        Args:
            kind: the mutation it reports, named as the worker event is.
            data: the keys that name what moved, JSON-safe as they travel.

        Best-effort by design: the answer is never read and a failure is logged
        and dropped. Nothing here may raise into the traffic path — an observer
        that changes what it observes is worse than no observer.
        """
        payload = {"kind": kind, "source": self.name, "data": data}
        try:
            self.loop.call_soon_threadsafe(self._start_observation_call, payload)
        except (AttributeError, RuntimeError) as exc:
            self._logger.debug("Worker %s: observation %s dropped (%s)", self.name, kind, exc)

    def _start_observation_call(self, payload: dict[str, Any]) -> None:
        """Put one observation on the lane as a detached task, on the loop."""
        task = asyncio.create_task(self._deliver_observation(payload))
        self._observation_tasks.add(task)
        task.add_done_callback(self._observation_tasks.discard)

    async def _deliver_observation(self, payload: dict[str, Any]) -> None:
        """Await the observation's own answer, so a failure is logged and no more."""
        try:
            await self.call(DESK_OBSERVATION_PATH, payload)
        except Exception as exc:
            self._logger.debug(
                "Worker %s: observation %s lost (%s)", self.name, payload["kind"], exc
            )

    def census(self) -> dict[str, Any]:
        """The whole process read out for a human: every register, JSON-safe.

        Returns:
            The three registers key by key with their scalar fields, the
            subscribed tables and how many table-event deposits wait per table. Live objects are left out by construction — only what
            survives ``json.dumps`` is in here.
        """
        with self.dispatch_lock:
            deposit_counts: dict[str, int] = {}
            for page_id in self.page_register.keys():
                for deposit in self.page_register.get(page_id)["dbevents"]:
                    table = deposit["table"]
                    deposit_counts[table] = deposit_counts.get(table, 0) + 1
            return {
                "name": self.name,
                "group": self.group,
                "pid": os.getpid(),
                "user_register": self._census_register(self.user_register),
                "connection_register": self._census_register(self.connection_register),
                "page_register": self._census_register(self.page_register),
                "subscribed_tables": sorted(self.subscribed_tables),
                "dbevent_deposit": deposit_counts,
            }

    def _census_register(self, register: Register) -> dict[str, Any]:
        """One register key by key, each item reduced to its JSON-safe fields."""
        return {
            key: {
                field: self._census_field(value)
                for field, value in register.get(key).items()
                if self._census_field(value) is not _NOT_JSON_SAFE
            }
            for key in register.keys()
        }

    def _census_field(self, value: Any) -> Any:
        """One field as the census carries it, or ``_NOT_JSON_SAFE`` to leave it out.

        Args:
            value: whatever the item holds under that name.

        Returns:
            The value itself when it is a scalar, the sorted elements of a
            container of scalars (the keys, for a dict), the count when those
            elements are objects — never the objects themselves.
        """
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            value = list(value)
        if isinstance(value, (set, frozenset, list, tuple)):
            if all(
                element is None or isinstance(element, (str, int, float, bool))
                for element in value
            ):
                return sorted(str(element) for element in value)
            return len(value)
        return _NOT_JSON_SAFE

    async def answer_call(self, frame: Frame) -> None:
        """Answer one CALL: the beat, the http form, one of the four ops, or nothing known.

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
            connection = self.connection_register.get(payload["cid"])
            if connection is not None:
                self.drop_connection(connection["user"], payload["cid"])
            await self.send_reply(frame, result={})
        elif frame.path == FREEZE_USER_OP_PATH:
            try:
                result = await self.freeze_designated_user(payload["user"])
            except Exception as exc:
                await self.send_reply(frame, error=f"{type(exc).__name__}: {exc}")
            else:
                await self.send_reply(frame, result=result)
        elif frame.path == OBSERVE_OP_PATH:
            self.observation_on = bool(payload["on"])
            await self.send_reply(frame, result={})
        elif frame.path == CENSUS_OP_PATH:
            await self.send_reply(frame, result=self.census())
        elif frame.path == EVAL_OP_PATH:
            try:
                result = {"repr": self.eval_expression(payload["expr"])}
            except Exception as exc:
                await self.send_reply(frame, error=f"{type(exc).__name__}: {exc}")
            else:
                await self.send_reply(frame, result=result)
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
        data: dict[str, Any] = {ENVELOPE_SLOT_WORKER_EVENTS: events}
        if error is not None:
            data["error"] = error
        else:
            data["result"] = result
        await self.stream.write(
            Frame(id=frame.id, method=REPLY_METHOD, path=frame.path, data=self._outbound(data))
        )

    async def call(
        self, path: str, data: Any = None, timeout: float | None = None
    ) -> Any:
        """CALL the commander on the lane and await its answer.

        Args:
            path: the routing key of the call, which is what the parent serves.
            data: the payload, JSON-serializable.
            timeout: the caller's own deadline; None waits until the answer lands.

        Returns:
            The ``result`` the parent put in its REPLY.

        Raises:
            CommanderCallFailed: the answer carried an ``error`` instead.

        The frame carries its own id and the future is parked under it, so calls
        placed without awaiting the first resolve each with its own answer, in
        whatever order the parent gives them. Reachable from a pool thread
        through ``run_on_loop``.
        """
        frame = Frame(method=CALL_METHOD, path=path, data=data)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._parent_calls[frame.id] = future
        try:
            await self.stream.write(frame)
            reply = await (future if timeout is None else asyncio.wait_for(future, timeout))
        finally:
            self._parent_calls.pop(frame.id, None)
        if "error" in reply:
            raise CommanderCallFailed(path, str(reply["error"]))
        return reply.get("result")

    def run_on_loop(self, coro: Any) -> Any:
        """Run a coroutine on this worker's loop from a pool thread, and wait.

        Args:
            coro: what to run there — a ``call`` of this worker's, in practice.

        Returns:
            Whatever the coroutine returned, on the calling thread.

        The bridge the site's own verbs need: they are served on a traffic-pool
        thread, where blocking costs nothing, and the lane lives on the loop.
        """
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()

    def _resolve_parent_reply(self, frame: Frame) -> None:
        """Hand the answer to the parked call; a caller already gone drops it."""
        future = self._parent_calls.get(frame.id)
        if future is None or future.done():
            self._logger.debug("Worker %s: the REPLY %s has no parked call", self.name, frame.id)
            return
        future.set_result(frame.data or {})

    async def on_wire_lost(self) -> None:
        """The wire is gone: leave, and save nothing.

        A process that lost its wire is unhealthy, so what it holds is not
        vouched for: it writes no parcel to the deposit. Its users are lost at
        the vertex, which drops what such a worker leaves and counts them in
        ``frozen_users_discarded``.
        """
        self._logger.warning("Worker %s: its wire is gone — leaving, saving nothing", self.name)
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
            item = self.user_register.get(user)
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
            item = self.user_register.get(user)
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

    async def adopt_connection(self, user: str, cid: str) -> dict[str, Any] | None:
        """Look for this connection of ``user`` in the deposit, install it if it is there.

        Args:
            user: the user the connection belongs to.
            cid: the connection the request carries.

        Returns:
            The connection register item — or None when nothing is held and
            nothing is parked: the rows are the site's to bear, and it baptises
            again while being served.

        Reads the parcel by itself (no verdict authorises a connection), deletes
        it from the deposit and brings the connection and its pages into being
        through the ordinary mutators: the worker events are the natural
        ``new_connection``/``new_page``, never one of its own. ONE key is looked
        up, because there is one identity: the deposit files the parcel under
        the very id the cookie carries. A connection already held is already
        home and spares the trip — a living row and a parked parcel of the same
        connection cannot both exist.
        """
        with self.dispatch_lock:
            item = self.connection_register.get(cid)
        if item is not None:
            return item
        parcel = await self._take_from_deposit(user, self._read_connection_parcel, cid)
        if parcel is None:
            return None
        with self.dispatch_lock:
            resident = user in self.user_register
            self.add_connection(cid, user, **parcel.get("connection", {}))
            for page_id, fields in parcel.get("pages", {}).items():
                replayed = {
                    key: fields.pop(key) for key in PARCEL_PAGE_REPLAYED_FIELDS if key in fields
                }
                page = self._add_page_item(page_id, cid, **fields)
                self._install_page_subscriptions(page_id, replayed)
                # Announced AFTER the replay, so the event carries the
                # subscriptions the vertex rebuilds its index from.
                self.add_worker_event(
                    "new_page",
                    user=self.registry.page_user(page_id),
                    page_id=page_id,
                    connection_id=cid,
                    table_subscriptions=sorted(page["table_subscriptions"]),
                )
            self._install_carried_store(user, parcel.get("store"), resident)
            return self.connection_register.get(cid)

    def _install_carried_store(self, user: str, store: Any, resident: bool) -> None:
        """Give a login's store to the row it belongs to, or let it die out loud.

        A connection that logged in carries what its guest had accumulated. It
        becomes the user's own store when the row was born a moment ago with
        this very connection; when a row of his was already here — his own state
        came home first, or he is living on this worker already — the RESIDENT
        wins and what the guest did before logging in dies, said out loud rather
        than silently dropped. Every page already watching the row's Bag is
        re-attached on the carried one — a fresh collector with the same
        prefixes, re-fed with everything the old one still held — so no window
        goes deaf and no captured change is lost in the swap. The caller holds
        the lock.
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
        entry = self.user_register.get(user)
        entry["store"] = store
        for connection_id in entry["connections"]:
            for page_id in self.connection_register.get(connection_id)["pages"]:
                page = self.page_register.get(page_id)
                view = page["user_view"]
                if view is None:
                    continue
                view.detach()
                fresh = self.registry.new_collector(store, paths=set(page["store_subscriptions"]))
                for change in view.changes:
                    fresh.append(change)
                page["user_view"] = fresh

    def change_connection_user(self, cid: str, user: str, **fields: Any) -> None:
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
        tail of this call reads, and on the departure a GUEST may have been
        promised: one that is ceasing to exist is not carried to the deposit, so
        his flag is dropped in this same breath. A previous identity that is no
        guest KEEPS his: he stays here with whatever else he holds, the round
        that promised his departure still means it, and cancelling it would leave
        the wait on him at the vertex with nothing to release it. Announces the
        login, which is what the vertex folds. The connection is written in this
        request's slot as well: the login is the second way a request settles on
        a connection the browser does not carry yet, and the cookie the front
        writes on the way out is whatever the slot ends up holding.
        """
        if user.startswith(GUEST_PREFIX):
            raise ValueError(f"{user!r} is reserved: nobody logs in as a guest")
        with self.dispatch_lock:
            connection = self.connection_register.get(cid)
            if connection is None:
                raise KeyError(f"change_connection_user: no connection {cid!r} here")
            previous_user = connection["user"]
            self.registry.change_connection_user(cid, user, **fields)
            self._login_previous_user_map[cid] = previous_user
            if previous_user.startswith(GUEST_PREFIX):
                self._transfer_flags.pop(previous_user, None)
            self.request_slot.connection_id = cid
            self.add_worker_event(
                "connection_user_changed",
                user=user,
                previous_user=previous_user,
                connection_id=cid,
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

        Takes the call out of his pendings and, when it was his last and a
        departure of his is past the gate, lets him go now — the closure of a
        whole worker and the cession of a single user hang on this same hook.
        A user with nothing open was CUT by a quit that would not wait for this
        call any longer: he is already parked, and there is nothing to close.
        """
        with self.dispatch_lock:
            if user not in self._pendings:
                return
            self._pendings[user] -= 1
            if self._pendings[user]:
                return
            del self._pendings[user]
            flag = self._transfer_flags.get(user)
            waiting_order = self._freeze_order_waits.pop(user, None)
        if waiting_order is not None:
            waiting_order.set()
        if flag is not None and self._transfers_open:
            await self._execute_transfer(user, flag)

    async def freeze_designated_user(self, user: str) -> dict[str, Any]:
        """Park one user on the parent's order, waiting for whatever holds him.

        Args:
            user: the user the order names.

        Returns:
            ``{"frozen": user}`` — sent only once he is in the deposit, so the
            REPLY that carries it IS the confirmation.

        Raises:
            KeyError: this worker does not host him.
            RuntimeError: he stayed here for good — a departure already under
                way (a state the caller's own serialization makes impossible),
                or a deposit that refused his parcels.

        The waits are serialization, never policy: a pull bringing him home is
        awaited on its own event, a call of his in flight on the event the end
        of that call sets — and a call born while the parcels were on the disk
        sends the order back to that same wait. The judgment of WHO sleeps is
        the caller's alone; this verb only executes.
        """
        while True:
            with self.dispatch_lock:
                if user not in self.user_register:
                    raise KeyError(f"freeze order refused: no user {user!r} here")
                adopting = self._unfreeze_waits.get(user)
                drained = None
                if adopting is None and user in self._pendings:
                    drained = self._freeze_order_waits.get(user)
                    if drained is None:
                        drained = self._freeze_order_waits[user] = asyncio.Event()
            if adopting is not None:
                await adopting.wait()
                continue
            if drained is not None:
                await drained.wait()
                continue
            if not self._claim_departure(user):
                raise RuntimeError(
                    f"freeze order refused: a departure of {user!r} is already under way"
                )
            try:
                parked = await self.freeze_user(user)
            finally:
                self._release_departure(user)
            if parked:
                return {"frozen": user}
            if parked is False:
                raise RuntimeError(f"freeze order failed: {user!r} stayed here")

    async def freeze_user(self, user: str) -> bool | None:
        """Park a user in the deposit and announce that he left.

        Args:
            user: the user leaving memory.

        Returns:
            True when he went to the deposit; None when a call of his is what
            holds him at the door — DEFERRED: that call's own end is where his
            departure happens, and the flag that sent him here must stay
            untouched; False when he STAYED for good as far as this attempt
            goes — a row that is not ``active``, a semaphore that never came
            free, or a deposit that refused the parcels (both failures counted,
            B1).

        Writes his store and one parcel per connection under the folder
        semaphore, announces ``user_frozen`` — placement always ``None``, the
        vertex's to decide — and takes his rows out of memory whole. The row is
        judged ONCE, at the door: whoever orders a departure BLOCKS him at the
        vertex first (``GroupHandler.freeze_hosted_user``), so no work of his
        can be born while the parcels are being written and nothing is ever
        taken back off the deposit. A failed write aborts the whole departure:
        the semaphore goes back, he stays alive where he is, nothing is
        announced, and the failure is logged and counted.
        """
        with self.dispatch_lock:
            item = self.user_register.get(user)
            if item is None or item["state"] != "active":
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
            store, connection_parcels = self._get_user_parcels(item)
            await self._run_in_pool(
                self.service_pool,
                functools.partial(self._write_parcels, user, store, connection_parcels),
            )
            with self.dispatch_lock:
                self.add_worker_event("user_frozen", user=user, placement=None)
                self._release_rows(user)
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
        A departure that does not happen leaves EVERYTHING alive and announces
        nothing: the identity stays resident on this worker with its connection
        attached, which is a legitimate shape of the machine, and the failure is
        counted. BOTH ways of not happening end there — a folder that never comes
        free and a deposit that refuses the parcel — so the claim taken on the
        previous identity and the flag of this login are given back on every road
        out. A claim kept by a departure that gave up would be held forever, and
        the whole worker could never finish leaving.
        """
        with self.dispatch_lock:
            previous_user = self._login_previous_user_map.get(cid)
            if previous_user is None:
                return None
            user = self.connection_register.get(cid)["user"]
        if not self._claim_departure(previous_user):
            return False
        try:
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
                        parcel["store"] = self.user_register.get(user)["store"]
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
        finally:
            with self.dispatch_lock:
                del self._login_previous_user_map[cid]
            self._release_departure(previous_user)
        with self.dispatch_lock:
            self._release_login_rows(cid, user, previous_user)
        return True

    def plan_transfers(
        self, *, transfer_users: Iterable[str] = ()
    ) -> dict[str, tuple[dict[str, Any], str | None]]:
        """Pair every user with the flag the next photo carries, and shut the gate.

        Args:
            transfer_users: the users this round cedes, named by whoever judged
                them — the group reading the silence off the photo's clocks, or
                the quit ceding everybody. This rung names nobody.

        Returns:
            Every user, mapped to his register item and his flag: ``None`` kept,
            ``'T'`` ceded.

        Remembers the flags that are not ``None`` and starts the clock of the
        gate: nothing departs before ``transfer_start_delay`` has passed. A row
        that is not active is left to the vertex. Once ``quit`` has begun the
        plan is terminal: everybody is ceded, a row still mid-adoption included
        (he is a straggler, ceded as soon as his pull lands), no flag already
        given is taken back, and the gate already open is not shut again. Every
        plan that leaves flags behind wakes the cycle, so a man named here while
        the quit waits for a straggler leaves with the others.
        """
        now = time.time()
        ceded = set(transfer_users)
        transfers: dict[str, tuple[dict[str, Any], str | None]] = {}
        with self.dispatch_lock:
            if not self._quitting:
                self._transfer_flags = {}
            for user, item in self._get_register_rows(self.user_register):
                flag = self._transfer_flags.get(user)
                if flag is None and (self._quitting or user in ceded):
                    if item["state"] == "active" or self._quitting:
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

        The ceded go to the deposit as soon as no call of theirs is in flight;
        whoever still has one is taken by the end of that call. The loop
        breathes between two users.

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

    async def quit(self, *, freezer_path: str | None = None) -> None:
        """Leave: everybody departs, the last call is waited for, the process ends.

        Args:
            freezer_path: where the parcels of THIS departure go, when they must
                not go to the working deposit — the reboot directory of a soft
                quit. The handler is replaced for good: nothing else will use
                this process's deposit.

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
        if freezer_path is not None:
            self.freeze_handler = FreezeHandler(freezer_path)
        self._flag_everybody_for_departure()
        departures = asyncio.ensure_future(self.execute_transfers())
        done, _ = await asyncio.wait({departures}, timeout=PENDING_CALL_GRACE_SECONDS)
        if not done:
            self._cut_stragglers()
            await departures
        self.exit_process()

    def _cut_stragglers(self) -> None:
        """Give up on the calls still in flight so their users can be parked.

        A call is not interrupted — the site runs it on a thread of the traffic
        pool and a thread cannot be killed. What is dropped is the WAIT: the
        users are taken out of the pendings, which is the one thing keeping
        ``freeze_user`` from parking them, and the cycle is woken to take them.
        An ordered freeze parked on the end of one of those calls is woken with
        them: the wait it is on would otherwise never be set, since the call it
        was waiting for is the one being given up on.
        The call finishes into a process that is leaving and its answer is lost;
        the front turns that into the same 503 a refusal gets, because the wire
        died on a server that is quitting.

        Accepted, and weighed: a call stuck this long is waiting on something,
        not writing, so the parcel it photographs is almost always quiet. The
        rare loser is a write that lands after the photo — lost — or a pickle
        that meets a store mid-change, which fails loudly on that user alone.
        """
        with self.dispatch_lock:
            cut = list(self._pendings)
            self._pendings.clear()
            for waiting_order in self._freeze_order_waits.values():
                waiting_order.set()
            self._freeze_order_waits.clear()
        if cut:
            self._logger.warning(
                "Worker %s: %s user(s) still had a call in flight %.1fs into the quit — "
                "parking them without it: %s",
                self.name,
                len(cut),
                PENDING_CALL_GRACE_SECONDS,
                ", ".join(sorted(cut)),
            )
        self._transfers_changed.set()

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
        """Attach the photo to an envelope going out, when one is due."""
        if not self._snapshot_due:
            return data
        data[ENVELOPE_SLOT_WORKER_SNAPSHOT] = self.worker_snapshot
        self._snapshot_sent_ts = time.time()
        self._population_changed = False
        return data

    async def _answer_then_quit(self, frame: Frame, payload: dict[str, Any]) -> None:
        """Answer the order to leave with everybody already flagged, then leave.

        Args:
            frame: the CALL being answered.
            payload: its payload; ``freezer_path`` is where the parcels go.

        Acts on the flags before the answer, so the photo riding it shows every
        user ceded and the level above parks them all in one read.
        """
        self._flag_everybody_for_departure()
        await self.send_reply(frame, result={})
        await self.quit(freezer_path=payload.get("freezer_path"))

    def _flag_everybody_for_departure(self) -> None:
        """Cede every user and make the plan terminal: sets ``_quitting`` and the flags."""
        self._quitting = True
        self.plan_transfers(transfer_users=self.user_register.keys())

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
        departure that had to wait for it happens — on the connection the
        SERVICE settled on, which is the one the site named while serving when
        it named one, and the one the request came in on otherwise.
        """
        cid = payload["http"]["cid"]
        user = payload.get("identity")
        served: dict[str, Any] = {}
        if user is not None:
            self.open_request(user)
        try:
            await self._resolve_row(user, cid, payload)
            seam = WsgiSeam(self.wsgi_app)
            service_started = time.monotonic()
            try:
                served = await self._run_in_pool(
                    self.traffic_pool,
                    functools.partial(self._serve_on_thread, seam, payload),
                )
            finally:
                # Counted whatever the stitching did: a call that failed or ran
                # long is exactly the one the measure must not lose.
                if user is not None:
                    self._record_service(user, time.monotonic() - service_started)
            return served
        finally:
            if user is not None:
                await self.close_request(user)
            await self.freeze_connection(served.get("connection_id") or cid)

    def _serve_on_thread(self, seam: WsgiSeam, payload: dict[str, Any]) -> dict[str, Any]:
        """Serve the stitching on the pool thread, under a slot of its own.

        The slot is opened HERE and not on the loop, because the thread is what
        makes it this request's: the site's verbs are called on this very
        thread and find it by asking for it. What the site named while serving
        LEAVES with the answer — the front has no other way of learning the
        connection this request settled on, and its cookie is written off it.
        """
        self.open_request_slot()
        answer = seam.serve(payload["http"], payload.get("identity"))
        answer["connection_id"] = self.request_slot.connection_id
        return answer

    async def _resolve_row(self, user: str | None, cid: str, payload: dict[str, Any]) -> None:
        """Put the row of an incoming request in order.

        Who the user IS was decided by the caller: the identity the front
        routed on, or None for a cookie the indexes do not carry yet — the
        ANONYMOUS first visit, which touches no register: the site baptises
        while serving, and the rows are born from its own verbs. For a known
        user the store comes home only if the envelope authorises it, and the
        connection is looked for in the deposit with no authorisation at all.
        """
        if user is None:
            return
        if payload.get("user_frozen"):
            await self.adopt_user(user)
        await self.adopt_connection(user, cid)
        self._stamp_request(user, cid)

    def _record_service(self, user: str, seconds: float) -> None:
        """Add one served call to the user's cumulative counters.

        Args:
            user: whom the call belonged to.
            seconds: how long the stitching held a traffic thread for it.

        Acts on his register item: ``served_call_count`` and ``service_seconds``
        grow monotonically, raw readings for the envelope layer's deltas. A user
        whose row is gone — dropped mid-call — is counted nowhere, silently.
        """
        with self.dispatch_lock:
            item = self.user_register.get(user)
            if item is None:
                return
            item["served_call_count"] = item.get("served_call_count", 0) + 1
            item["service_seconds"] = item.get("service_seconds", 0.0) + seconds

    def _stamp_request(self, user: str, cid: str) -> None:
        """Stamp the user a request came in for, and his connection under it.

        The http form names no page: what it proves is a real call of that
        user, which is the clock the group's judgment reads off the photo.
        """
        with self.dispatch_lock:
            connection = self.connection_register.get(cid)
            row = self.user_register.get(user)
            items = [item for item in (connection, row) if item is not None]
            self._stamp_items(items, ("last_rpc_ts",))

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

    def _user_row(self, user: str, item: dict[str, Any]) -> dict[str, Any]:
        """One user item projected for the photo: state, clocks, service counters.

        Args:
            user: whose row it is — the pendings are keyed by him, not by the item.
            item: his user register item.

        Returns:
            The scalar projection: his state, his connection count, his three
            clocks, and the three service counters — the two cumulatives the
            calls of his wrote (0 before his first), plus how many are open now.
        """
        row: dict[str, Any] = {
            "state": item["state"],
            "connection_count": len(item["connections"]),
            "served_call_count": item.get("served_call_count", 0),
            "service_seconds": item.get("service_seconds", 0.0),
            "pending_call_count": self._pendings.get(user, 0),
        }
        row.update({clock: item[clock] for clock in CLOCK_NAMES})
        return row

    async def _run_in_pool(self, pool: ThreadPoolExecutor, work: Callable[[], Any]) -> Any:
        """Run one piece of synchronous work on the pool it belongs to."""
        return await asyncio.get_running_loop().run_in_executor(pool, work)

    async def _execute_transfer(self, user: str, flag: str) -> None:
        """Let one flagged user go to the deposit.

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
            if user in self._pendings:
                return
            if not self._claim_departure(user):
                return
            adopting = self._unfreeze_waits.get(user)
        settled = True
        try:
            if adopting is not None:
                await adopting.wait()
            settled = await self.freeze_user(user) is not None
        except Exception:
            settled = True
            self._freeze_failures += 1
            self._logger.exception(
                "Worker %s: the departure of %s fell over; the others go on", self.name, user
            )
        finally:
            with self.dispatch_lock:
                if settled or user not in self.user_register:
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
        """Give the claim back, say so if that was the last departure, wake the cycle.

        The wakeup is owed to whoever found this claim TAKEN and went away with
        nothing done: the ordered freeze and the transfer cycle reach the same
        user by two roads, and the loser leaves the flag where it is. Without
        this the cycle of a quit would sleep on a change that nobody else is
        going to announce.
        """
        with self.dispatch_lock:
            self._departing_users.discard(user)
            self._settle_transfers()
            self._transfers_changed.set()

    def _settle_transfers(self) -> None:
        """Declare the departures over: no flag left, and nobody on his way out.

        Both halves are asked, because a flag popped by the man who is at that
        instant writing his parcels would otherwise let a ``quit`` leave from
        under him.
        """
        with self.dispatch_lock:
            if not self._transfer_flags and not self._departing_users:
                self._transfers_done.set()

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

    def _connection_parcel(self, cid: str) -> dict[str, Any]:
        """One connection with its pages, in the shape the adoption reads back.

        The edges of the tree are left out on purpose: the folder already says
        whose the connection is, and the pages half is what rebuilds the rest.
        A page leaves its two collectors and its deposit container behind as
        well — objects bound to the Bags of THIS process, which the birth on the
        other side makes anew — while the prefixes they were filtered on travel
        as plain sets and are subscribed again there.
        """
        item = self.connection_register.get(cid)
        return {
            # The parcel names its own connection: the deposit filename hashes
            # the id one-way, and the wake reads it back from here.
            "connection_id": cid,
            "connection": {
                key: value
                for key, value in item.items()
                if key not in PARCEL_CONNECTION_REBUILT_FIELDS
            },
            "pages": {
                page_id: {
                    key: value
                    for key, value in self.page_register.get(page_id).items()
                    if key not in PARCEL_PAGE_REBUILT_FIELDS
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
        The pages leaving are announced as ``drop_pages`` in every case — the
        vertex's projection follows the page rows, resident or not.
        """
        page_ids = sorted(self.connection_register.get(cid)["pages"])
        if page_ids:
            self.add_worker_event("drop_pages", user=user, page_ids=page_ids)
        for page_id in page_ids:
            self._remove_page_item(page_id)
        self._remove_connection_item(cid)
        if previous_user.startswith(GUEST_PREFIX) and previous_user in self.user_register:
            self._remove_user_item(previous_user)
        resident = self.user_register.get(user)
        if resident is not None and not resident["connections"]:
            self._remove_user_item(user)
            self.add_worker_event("user_rows_released", user=user)

    def _release_rows(self, user: str) -> None:
        """Take a user's rows out of memory; his departure names him, this names his pages.

        Everything of his goes — pages, connections, the user row itself. No
        emptied row is left resident: he is the vertex's to place now, and
        whatever comes back for him starts from the parcel in the deposit. Two
        departures end here — the freeze that parked him, and the pull that
        failed to bring him home. The pages leaving are announced as
        ``drop_pages``: the vertex's desk queues and index rows are a projection
        of the page rows, and a page taken out of memory is taken out of the
        projection — the wake's own announcements rebuild it.
        """
        item = self.user_register.get(user)
        for cid in sorted(item["connections"]):
            page_ids = sorted(self.connection_register.get(cid)["pages"])
            if page_ids:
                self.add_worker_event("drop_pages", user=user, page_ids=page_ids)
            for page_id in page_ids:
                self._remove_page_item(page_id)
            self._remove_connection_item(cid)
        self._remove_user_item(user)
        self._unfreeze_waits.pop(user, None)

    def _add_user_item(self, user: str, **fields: Any) -> dict[str, Any]:
        """Put a user item in the register, born stamped and with a live store."""
        fields.setdefault("state", "active")
        return self.registry.new_user(user, **self._stamped(**fields))

    def _add_connection_item(self, cid: str, user: str, **fields: Any) -> dict[str, Any]:
        """Put a connection item in the register and join it to its user."""
        return self.registry.new_connection(cid, user, **self._stamped(**fields))

    def _add_page_item(self, page_id: str, cid: str, **fields: Any) -> dict[str, Any]:
        """Put a page item in the register and join it to its connection."""
        return self.registry.new_page(
            page_id,
            user=self.connection_register.get(cid)["user"],
            connection_id=cid,
            **self._stamped(**fields),
        )

    def _remove_page_item(self, page_id: str) -> None:
        """Take a page item out of the register, capture and edge with it."""
        self.registry.drop_page(page_id, cascade=False)

    def _remove_connection_item(self, cid: str) -> None:
        """Take a connection item out of the register and off its user."""
        self.registry.drop_connection(cid, cascade=False)

    def _remove_user_item(self, user: str) -> None:
        """Take a user item out of the register."""
        self.registry.user_items.drop(user)

    def _get_register_rows(self, register: Register) -> list[tuple[str, dict[str, Any]]]:
        """Every key of a register paired with its live item, in one snapshot."""
        return [(key, register.get(key)) for key in register.keys()]

    def _install_page_subscriptions(self, page_id: str, replayed: dict[str, Any]) -> None:
        """Put back on a woken page the subscriptions its parcel carried.

        The row is born with its sets empty and its capture filtered on nothing:
        the prefixes are subscribed again here, so the page wakes capturing what
        it captured before it went to the deposit.
        """
        page = self.page_register.get(page_id)
        for table in replayed.get("table_subscriptions", ()):
            page["table_subscriptions"].add(table)
        for prefix in replayed.get("subscribed_paths", ()):
            page["subscribed_paths"].add(prefix)
            page["collector"].subscribe_path(prefix)
        for prefix in replayed.get("store_subscriptions", ()):
            self.registry.subscribe_store_path(page_id, prefix)

    def _drop_emptied_user(self, user: str) -> None:
        """Take the user away when the connection just removed was his last."""
        if not self.user_register.get(user)["connections"]:
            self._remove_user_item(user)
            self._unfreeze_waits.pop(user, None)
            self.add_worker_event("drop_user", user=user)

    def _stamped(self, **fields: Any) -> dict[str, Any]:
        """An item born with the three clocks on the server's own instant."""
        now = time.time()
        for clock in CLOCK_NAMES:
            fields.setdefault(clock, now)
        return fields

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
            return await self._run_in_pool(self.service_pool, functools.partial(read, user, *args))
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
