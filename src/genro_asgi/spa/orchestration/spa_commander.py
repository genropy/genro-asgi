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

**The cookie routes, the site baptises.** The front mints the cookie and keeps
no state; the vertex mints NOBODY. A cid the indexes do not carry travels
ANONYMOUS to the default group's reception, and the hosted site names its own
connection and its own guest while serving — the worker attaches the request's
cookie to that birth, and the fold of ``new_connection`` is what writes
``connection_user_map`` and the user row, at the fact (``record_connection_user``).
This replaced the founding doctrine ("routing somebody the indexes do not carry
is exactly what cannot be done, so the writing comes first", owner decision
2026-08-21): the identity and the guest name belong to the site, and a parallel
vocabulary at the vertex made every visitor exist twice. A cid whose USER ROW is
gone — a cookie that outlived it — is healed with an empty row: the browser is
still known, its state is not.

**The master of the store lives here, and it is a Bag.** Every worker holds a
replica of it and never writes it: what a worker wants written travels up, is
written here, and comes back down as the whole content again. The Bag is where
the store meets the application; the TYTX encoding is where it meets the channel,
so it happens on the way out and nowhere else. The read-modify-write grant — one
worker at a time holding the master while it computes a new value — is the lock,
and it arrives with the request chain.

**Two writers, both here.** The minting above is one; the other is the fold — the
chain of the envelope, which turns what the processes announce into these
indexes, one worker event at a time, synchronously. The mutators live on this
class because the data does, and the chain calls them by name.

**The groups are its own.** The grammar of the machine arrives as
``groups={name: kwargs}`` and one ``GroupHandler`` per entry is built right here,
each handed ``memory_concession_bytes`` — the total it is a share of — so the one
number of the cascade is never carried by hand from outside. Building a group by
hand stays legitimate and is what the tests do; either way the group hangs itself
in ``group_map``, in the order it was named. ``default_group`` is the group
that receives whoever arrives with no past: the elected one, or the first
declared.

**A request walks the whole chain from here.** ``serve_request`` takes a
cookie and gives back what the site answered: the cid becomes an identity, the
identity names a group (his own, or the elected one when he has none yet), the
group names the worker — placing him NOW if he has no home — and the request
travels as the ``http`` form with the identity and the freezer verdict beside it.
The front hands over a cid and a request and nothing else: it never names a
group, a worker or a wire, and it keeps no state to name them with. What comes
back is the child's whole REPLY, folded by the chain before this returns.

The refusals travel as CLASSES, because the caller's next step is written in
which one arrives: nobody could take him is ``AssignmentRefused`` carrying the
seconds to come back in; a site that failed inside its process is
``SiteFailedRequest``; a wire that is gone is ``ConnectionError``. The
waiting is the one that does not travel: a user between two homes is waited for
here, on the budget the request gave, and the walk starts over at the top — the
map is the authority at every step, so nothing is remembered across the wait.

**The waiting room has a door.** ``on_hold`` on a row is what ``resolve_user``
raises ``UserOnHold`` on; ``user_hold_event_map`` is what a request PARKS on while
that lasts. One Event per user on hold, born with the hold and gone with its
release — the same mutators, in the same breath: ``hold_user`` raises both,
``mark_user_frozen``, ``mark_user_adopted`` and ``drop_user`` let both go. Nobody
else writes either, so the row and the door cannot say different things.

**Up and down.** ``start`` brings the base group's reception into being and
only then starts the clock: a reception that has presented itself is what READY
means, and the front serves from that instant. ``stop`` stops the clock and
takes every group down dry — no mass freeze on the way out, because without the
soft boot those files would be read by nobody.

**The freezer is not on the ladder.** A worker parks a user's state on disk
itself and announces it; the vertex only writes the mark. The one time the vertex
touches the freezer is when nobody below can: pruning the traces of a wild death
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

**The memory cascade starts here.** ``memory_max_percent`` is what this server
may hold of the machine, and ``memory_concession_bytes`` is that share in bytes:
the ONE total of the machine, from which a group takes its quota and a worker its
ceiling, each as a percentage of the rung above. A machine that does not say how
much memory it has leaves the whole cascade unmeasured, which is what an ungated
pool honestly is.

**There is ONE clock in the machine, and it is here.** ``heartbeat_loop`` waits
for its timer OR for any group's wake, whichever comes first: the timer gives a
full round — every group a turn, and the vertex's own tasks each on its own count
of beats — while a wake gives an anticipated round on THAT group alone, which is
how the end of a wire is answered in milliseconds whatever the cadence. There is
no caretaker object anywhere: the probe IS the beat, and the monitor gets a fresh
photo by ringing the wake like everybody else. A group whose previous turn is
still open is skipped rather than given a second one, so a mute process delays
its own group and never the machine; every turn is awaited, an exception is a
value and not a cancellation, and a round that fails is written down and
followed by the next beat.

**Three tasks are the vertex's own, because nobody below can do them.** The
frozen whose age ran out have no process to notice them, so ``drop_expired_users``
prunes the row and the disk itself — the declared exception to the rule that the
levels below prune themselves. ``cleanup_frozen`` discards what the freezer holds
for nobody the indexes know. ``check_resources`` reads the machine's memory
against its alarm line and the freezer's storage against the reserve — the
memory alone writes ``state``, a storage under reserve is said out loud — and
calls ``need_resources``, which does nothing here and is where a commander that
can grow its own machine says so. All three open the disk, so they read it OFF the
loop: the vertex must never be the reason a healthy child reads as mute.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from genro_bag import Bag
from genro_tytx import from_tytx, to_tytx

from ..global_store import GlobalStore, GlobalStoreLock
from ..subscription_index import SubscriptionIndex
from .beats import every
from .envelope_handler import CommanderEnvelopeHandler
from .exceptions import AssignmentRefused, UserOnHold, SiteFailedRequest
from .freeze_handler import FreezeHandler
from .group_handler import CHECK_OCCUPANCY_BEATS, GroupHandler
from .worker_handler import INSPECT_OP_PATH

#: What a user with no name of his own is called: the prefix plus his cid. The
#: name itself carries the rule — whoever reads it knows nobody logged in here.
#: Redefined with its ratified value rather than imported: the machine it is
#: shared with dies at the cutover.
GUEST_PREFIX = "guest_"

#: The logger the orchestration log is written on, whether or not a file is
#: attached to it.
ORDERS_LOGGER_NAME = "genro_asgi.orchestration.orders"

#: Seconds between two beats of the one clock — the twin of
#: ``PROCESS_PING_INTERVAL``, which is the cadence a single process is beaten at.
HEARTBEAT_SECONDS = 5.0

# Beats between two rounds of each task of the vertex — the cadences, each where
# its own knowledge is: an expiry is hours away, so the frozen are read every few
# minutes; the sweep of the freezer opens the disk over everything ever frozen,
# which F18 measured in seconds at scale, so it goes hourly; the machine's gauges
# are trends and not emergencies, and a minute is soon enough for a trend.
DROP_EXPIRED_USERS_BEATS = 60
CLEANUP_FROZEN_BEATS = 720
CHECK_RESOURCES_BEATS = 12

# The reserve line of the storage the freezer lives on: under this much free
# room the sysop is told, and the machine asks the world outside for more. It is
# a technical line and not a policy — a full disk is full for every installation.
STORAGE_RESERVE_PERCENT = 10.0

# The conversion the expiry hours of the grammar meet the clock through.
SECONDS_PER_HOUR = 3600.0

#: What a refused request is told to wait, in seconds. DERIVED and never a number
#: of its own: it is exactly when the pool will have re-read its own shape and
#: decided again, so what is promised to a browser stays true the day the beat
#: changes.
SHAPE_REVIEW_SECONDS = HEARTBEAT_SECONDS * CHECK_OCCUPANCY_BEATS

#: The routing key every request of the hosted site travels under. Nothing routes
#: on it — the child tells the http form by its payload — but it is what a human
#: reads in a log, and it keeps a site page called ``/op/something`` from looking
#: like one of the contract ops.
SITE_PATH_PREFIX = "/site"

#: The namespace of the lane going UP: a worker places its desk CALLs on
#: ``/desk/<op>``, the way the orders going down travel on ``/op/<name>``. The
#: segment after the prefix IS the name of the method that serves it.
DESK_PATH_PREFIX = "/desk/"

#: What ``kind`` names when an addressed write is a STATE one: the target is a
#: store, and the write is a real Bag write wherever it lands. Redefined with
#: its ratified value rather than imported: the module that declares it is the
#: child's, and the vertex does not depend on the child.
STATE_KINDS = frozenset({"page_store", "user_store", "connection_store"})

#: How long a queued event is worth delivering. Past it a delivery is garbage —
#: the browser would paint a value the machine has long moved on from — so the
#: drain discards it instead of shipping it. One rule for all three species.
EVENT_MAX_AGE_SECONDS = 300.0

__all__ = [
    "DESK_PATH_PREFIX",
    "EVENT_MAX_AGE_SECONDS",
    "GUEST_PREFIX",
    "HEARTBEAT_SECONDS",
    "ORDERS_LOGGER_NAME",
    "STATE_KINDS",
    "DeliveryDesk",
    "SpaCommander",
]


class DeliveryDesk:
    """The vertex's desk: who subscribes what, and what waits for whom.

    The commander alone holds the subscription index and the pending queues, and
    every one of them is fed and drained by CALLs a worker places on the lane.
    Three species, never mixed: a page's **datachanges** (explicit writes
    addressed at it), a page's **dbevents** (the deposits of a commit on a table
    it subscribed), and a user's **store changes** (STATE writes addressed at his
    own store, applied to his Bag by whichever of his pages retires them —
    usersticky puts them all in one process, and the siblings capture the write
    locally on their own ``user_view``).

    **The global store is served here too**, for the same reason: it lives on
    the commander and nowhere else, so ``store_set``, ``store_del`` and the two
    halves of the read-modify-write grant are lane CALLs like the rest. There is
    no replica anywhere to keep aligned.

    **Outside the pickled surface, on purpose.** The queues are ephemeral: what
    is waiting for a user who goes into the freezer is lost with the websockets
    that would have carried it, and nothing here is dumped or restored.

    **The subscription answers only once it is filed**, so a site that subscribes
    a table and commits it inside the same request finds it active: the
    subscribe-window is closed by construction, not by luck.

    **The exchange files first and answers after**, so the caller's own events
    come back in the same round; a sibling page's events wait in its own queue
    for its own next exchange, since nothing is ever pushed from here.

    Args:
        spa_commander: the vertex this desk belongs to.
        event_max_age_seconds: how long a queued event stays deliverable.
    """

    def __init__(
        self, spa_commander: Any, *, event_max_age_seconds: float = EVENT_MAX_AGE_SECONDS
    ) -> None:
        self.spa_commander = spa_commander
        self.event_max_age_seconds = event_max_age_seconds
        #: Which pages want which table, both directions, one mutator each.
        self.page_subscriptions = SubscriptionIndex()
        #: The pending changes of each page, in arrival order.
        self.page_datachange_map: dict[str, list[dict[str, Any]]] = {}
        #: The pending table-event deposits of each page, in arrival order.
        self.page_dbevent_map: dict[str, list[dict[str, Any]]] = {}
        #: The pending STATE writes addressed at each user's own store.
        self.user_store_change_map: dict[str, list[dict[str, Any]]] = {}
        self._logger = logging.getLogger(__name__)

    @property
    def subscribed_tables(self) -> list[str]:
        """Every table holding at least one subscription — the workers' source filter."""
        return sorted(self.page_subscriptions.table_pages)

    def serve_child_call(self, path: str, data: dict[str, Any]) -> Any:
        """Serve one CALL a worker placed on the lane, by the name in its path.

        Args:
            path: the routing key, ``/desk/<op>``.
            data: the payload, handed over as the op's own keyword arguments.

        Returns:
            Whatever the op answers, which becomes the ``result`` of the REPLY.

        Raises:
            AttributeError: no op of that name — the wire answers an error REPLY,
                never a silent discard.
        """
        return getattr(self, f"op_{path.removeprefix(DESK_PATH_PREFIX)}")(**data)

    def install_page_subscriptions(self, page_id: str, tables: list[str]) -> None:
        """File a page's announced subscriptions: the index rebuilt from the row.

        Args:
            page_id: the page the announcement is about.
            tables: the ``table_subscriptions`` its register row carries —
                empty at birth, the replayed set at the wake.

        Acts on ``page_subscriptions``.
        """
        for table in tables:
            self.page_subscriptions.subscribe(page_id, table)

    def op_subscribe_table(
        self, page_id: str, table: str, subscribe: bool = True
    ) -> dict[str, Any]:
        """File (or unfile) a page's subscription to a table's events.

        Args:
            page_id: the subscribing page — whoever asks, so there is no target.
            table: the table whose events it wants.
            subscribe: opening the subscription, or closing it.

        Returns:
            The subscription as it was taken, plus the whole subscribed-table
            list the worker caches as its source filter.

        Acts on ``page_subscriptions`` BEFORE it answers.
        """
        if subscribe:
            self.page_subscriptions.subscribe(page_id, table)
        else:
            self.page_subscriptions.unsubscribe(page_id, table)
        return {
            "page_id": page_id,
            "table": table,
            "subscribe": subscribe,
            "tables": self.subscribed_tables,
        }

    def op_exchange(
        self,
        page_id: str,
        user: str,
        datachanges: list[dict[str, Any]] | None = None,
        dbevents: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Take a request's events in, and hand back what waits for its page.

        Args:
            page_id: the exchanging page — whose queues are retired.
            user: its owner, whose store queue is retired with them.
            datachanges: the addressed writes the request produced, each a header
                (``kind``, ``target``, ``filters``, ``replace``) around a
                TYTX-encoded ``change``.
            dbevents: the deposits the request produced, as the worker shaped
                them.

        Returns:
            The two page species, the user's store changes and the current
            subscribed-table list. The changes travel TYTX-encoded: their
            ``change_ts`` is a datetime, which JSON has no word for.

        Acts on all three queue maps: the arrivals are filed first, so what the
        caller itself produced for itself is in the answer.
        """
        for message in datachanges or ():
            self.file_datachange(message)
        for deposit in dbevents or ():
            self.file_dbevent(deposit)
        return {
            "datachanges": to_tytx(self.drain_page_datachanges(page_id), "json"),
            "dbevents": self.drain_page_dbevents(page_id),
            "store_changes": to_tytx(self.drain_user_store_changes(user), "json"),
            "tables": self.subscribed_tables,
        }

    def file_datachange(self, message: dict[str, Any]) -> None:
        """Put one addressed write in the queue of whoever it is addressed at.

        Args:
            message: the header — ``op``, ``kind``, ``target``, ``filters`` —
                plus what the op adds: the TYTX-encoded ``change`` of a
                ``set_datachange``, the ``path`` of a ``drop_datachanges``.

        Raises:
            NotImplementedError: a filtered address — the page surface here
                answers no field yet, exactly as on the worker before it.

        Acts on ``page_datachange_map`` for a SIGNAL address and on
        ``user_store_change_map`` for a STATE one. ``replace`` coalesces with the
        pending change of the same key — path, reason, fired — so a value
        written over and over reaches the browser once. ``reset_datachanges``
        empties that queue and ``drop_datachanges`` takes one prefix out of it,
        the semantics the page collector had before the queue moved here.
        """
        if message.get("filters") is not None:
            raise NotImplementedError(f"desk: the filtered address {message['filters']!r}")
        if message["kind"] in STATE_KINDS:
            queue = self.user_store_change_map.setdefault(message["target"], [])
        else:
            queue = self.page_datachange_map.setdefault(message["target"], [])
        if message.get("op") == "reset_datachanges":
            queue.clear()
            return
        if message.get("op") == "drop_datachanges":
            queue[:] = [
                pending
                for pending in queue
                if not self._under(pending["key"]["path"], message["path"])
            ]
            return
        change = from_tytx(message["change"], "json")
        if message.get("replace"):
            queue[:] = [pending for pending in queue if pending["key"] != change["key"]]
        queue.append(change)

    def file_dbevent(self, deposit: dict[str, Any]) -> None:
        """Put one deposit in the queue of every page subscribing its table.

        Args:
            deposit: the deposit as the worker shaped it — ``table``, ``batch``,
                ``from_page_id``, ``reason``, ``ts``.

        Acts on ``page_dbevent_map``. A table nobody subscribes anywhere costs
        one dict lookup that misses and the deposit dies here: a dbevent is a
        signal, and there is no queue for a listener that does not exist.
        """
        for page_id in self.page_subscriptions.pages_for(deposit["table"]):
            self.page_dbevent_map.setdefault(page_id, []).append(deposit)

    def drain_page_datachanges(self, page_id: str) -> list[dict[str, Any]]:
        """Retire a page's pending changes, the stale ones discarded."""
        return self._fresh_changes(self.page_datachange_map.pop(page_id, []))

    def drain_page_dbevents(self, page_id: str) -> list[dict[str, Any]]:
        """Retire a page's pending deposits, the stale ones discarded."""
        horizon = time.time() - self.event_max_age_seconds
        return [
            deposit
            for deposit in self.page_dbevent_map.pop(page_id, [])
            if deposit["ts"] >= horizon
        ]

    def drain_user_store_changes(self, user: str) -> list[dict[str, Any]]:
        """Retire a user's pending store writes, the stale ones discarded."""
        return self._fresh_changes(self.user_store_change_map.pop(user, []))

    def op_store_set(self, path: str, value: Any = None) -> dict[str, Any]:
        """Write one path of the store, and answer once it holds the value.

        Args:
            path: the path to write.
            value: what to write there.

        Returns:
            The path written, which is what the site's protocol expects.

        Acts on ``global_register``. Last writer wins: there is one copy and no
        version, so two workers writing the same path are ordered by the lane
        and the second one is the truth.
        """
        self.spa_commander.global_register.set_item(path, value)
        return {"path": path}

    def op_store_del(self, path: str) -> dict[str, Any]:
        """Remove one path of the store — the node is gone, not set to None.

        Args:
            path: the path to remove.

        Returns:
            The path removed.

        Acts on ``global_register``.
        """
        self.spa_commander.global_register.pop(path)
        return {"path": path}

    def op_store_get(self, path: str) -> dict[str, Any]:
        """Read one path of the store, and answer what it holds right now.

        Args:
            path: the path to read.

        Returns:
            The path and its value, TYTX-encoded so datetimes and nested Bags
            travel whole; a path the store does not hold answers None — the
            Bag's own read semantics, exactly what the caller would have seen
            reading the master itself.

        Acts on nothing: a read of the only copy there is.
        """
        return {
            "path": path,
            "value": to_tytx(self.spa_commander.global_register.get_item(path), "json"),
        }

    async def op_store_lock(
        self, worker: str, request_id: str
    ) -> dict[str, Any]:
        """Park on the FIFO grant, then hand the store itself to the winner.

        Args:
            worker: the process asking — whose death releases the grant.
            request_id: the hold's own id, which the release quotes back.

        Returns:
            The store as it stands at grant time, TYTX-encoded: the holder never
            has to ask whether what it reads is current, because what it mounts
            IS the only copy.

        Acts on ``global_lock``. The answer is the grant, so a worker whose call
        is still parked here simply has not been answered yet.
        """
        await self.spa_commander.global_lock.acquire(worker, request_id)
        return {
            "request_id": request_id,
            "store": to_tytx(self.spa_commander.global_register, "json"),
        }

    def op_store_unlock(
        self, request_id: str, changes: Any = None
    ) -> dict[str, Any]:
        """Apply a holder's drained changes and let the next waiter in.

        Args:
            request_id: the grant being given back.
            changes: what the body captured on its working copy, TYTX-encoded —
                attributes, reason and fired included, so nothing of the write's
                shape is lost on the way up. Empty when the body raised.

        Returns:
            Whether anything was applied — a release for a grant no longer in
            force applies nothing, which is the all-or-nothing rule.

        Acts on ``global_register`` and on ``global_lock``, the store written
        BEFORE the release so the next waiter's grant carries these changes.
        """
        if not self.spa_commander.global_lock.holds(request_id):
            self._logger.debug(
                "desk: the release of the grant %s is no longer in force", request_id
            )
            return {"applied": False}
        GlobalStore(self.spa_commander.global_register).apply_changes(from_tytx(changes, "json"))
        self.spa_commander.global_lock.release()
        return {"applied": True}

    def release_worker_lock(self, worker: str) -> None:
        """Give the grant back for a worker that died holding it, applying nothing.

        Args:
            worker: the process whose wire has just ended.

        Acts on ``global_lock`` when that worker was the holder, and on nothing
        at all otherwise. The changes it had made live only on its own working
        copy, which died with it — the whole death rule, and the reason the
        protocol needs no rollback.
        """
        if not self.spa_commander.global_lock.held_by(worker):
            return
        self.spa_commander.global_lock.release()
        self._logger.info("Worker %s died holding the store: released, nothing applied", worker)

    def drop_page(self, page_id: str) -> None:
        """Forget a page here: its two queues and its subscriptions, one breath.

        Args:
            page_id: the page that is gone.

        Acts on both page queue maps and on ``page_subscriptions``: nothing is
        delivered to a page that is not there any more, and nothing keeps its
        tables alive in the source filter.
        """
        self.page_datachange_map.pop(page_id, None)
        self.page_dbevent_map.pop(page_id, None)
        self.page_subscriptions.drop_page(page_id)

    def drop_user(self, user: str) -> None:
        """Forget what was waiting for a user's own store; his pages go on their own."""
        self.user_store_change_map.pop(user, None)

    def _under(self, path: str, prefix: str) -> bool:
        """Whether a pending change's path falls under a dropped prefix."""
        return path == prefix or path.startswith(f"{prefix}.")

    def _fresh_changes(self, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """The changes still young enough to deliver, in the order they arrived."""
        horizon = datetime.now(UTC) - timedelta(seconds=self.event_max_age_seconds)
        return [change for change in changes if change["change_ts"] >= horizon]


class SpaCommander:
    """The vertex of the pool: the indexes, the minting, the master store, the log.

    Args:
        frozen_users_path: the freezer root — the same one the workers are given,
            since a parcel written on one side is read on the other.
        groups: the grammar of this machine's groups, ``{name: kwargs}`` — one
            ``GroupHandler`` per entry, each built with the concession this
            vertex owns. Building one by hand stays legitimate: it hangs itself
            here the same way.
        default_group: which group receives whoever arrives with no past;
            None elects the first declared.
        orchestration_log_path: where the log of the orders goes; None keeps them
            on the logger alone, which is what a test wants.
        orchestration_log_max_bytes: the size at which that file rotates.
        orchestration_log_backup_count: how many rotations are kept.
        user_expiry_hours: how long a frozen user is kept before the machine
            forgets him whole.
        guest_expiry_hours: the same for somebody who never logged in, and it is
            shorter — a guest is a browser, not a person the machine knows.
        machine_memory_alarm_percent: the health line of the WHOLE machine, not
            of what this server was conceded: past it nothing grows.
        memory_max_percent: what this server may hold OF THE MACHINE — the
            concession every percentage below it is a share of. All of it by
            default.
        event_max_age_seconds: how long an event waiting at the delivery desk
            stays deliverable; past it the drain discards it.
    """

    def __init__(
        self,
        frozen_users_path: str | Path,
        *,
        groups: dict[str, dict[str, Any]] | None = None,
        default_group: str | None = None,
        orchestration_log_path: str | Path | None = None,
        orchestration_log_max_bytes: int = 10 * 1024 * 1024,
        orchestration_log_backup_count: int = 5,
        user_expiry_hours: float = 720.0,
        guest_expiry_hours: float = 24.0,
        machine_memory_alarm_percent: float = 90.0,
        memory_max_percent: float = 100.0,
        event_max_age_seconds: float = EVENT_MAX_AGE_SECONDS,
    ) -> None:
        self.freeze_handler = FreezeHandler(frozen_users_path)
        self.user_expiry_hours = user_expiry_hours
        self.guest_expiry_hours = guest_expiry_hours
        self.machine_memory_alarm_percent = machine_memory_alarm_percent
        self.memory_max_percent = memory_max_percent
        #: The global store itself: not a master over replicas any more, the
        #: ONLY copy there is. Every read and every write of the hosted sites
        #: reaches it as a CALL on the lane, answered once it has landed.
        self.global_register = Bag()
        #: The grant of that store for a read-modify-write hold: FIFO, one
        #: holder, and a holder whose process dies releases it applying nothing.
        self.global_lock = GlobalStoreLock()
        #: The desk of the deliveries: the subscriptions and the three queue
        #: species, held here alone and outside everything that is pickled.
        self.delivery_desk = DeliveryDesk(self, event_max_age_seconds=event_max_age_seconds)
        self.envelope_handler = CommanderEnvelopeHandler(self)
        #: Where the whole machine stands: ``running`` or ``saturated`` (no room
        #: for a newcomer anywhere). Written by the check of the resources, which
        #: arrives with the heartbeat.
        self.state = "running"
        #: The aggregate counts, one key per thing worth counting.
        self.counters: Counter[str] = Counter()
        #: The anagraph: one row per identity the machine knows. Read it through
        #: the predicates, and leave the writing to the mutators.
        self.user_map: dict[str, dict[str, Any]] = {}
        #: Whose each cid is. A cid stays here once written: the cookie outlives
        #: the process, the placement and the freezer.
        self.connection_user_map: dict[str, str] = {}
        #: Which connection each page belongs to; written once, only ever removed.
        self.page_connection_map: dict[str, str] = {}
        #: The groups of this machine, by name — a group hangs itself here when
        #: it is built, the way a worker hangs itself in its own group's map.
        self.group_map: dict[str, Any] = {}
        self._group_turns: dict[str, asyncio.Task[None]] = {}
        self._beat_timer: asyncio.Task[None] | None = None
        #: One row per periodic method of this vertex — turns seen, runs, errors
        #: and the last one's text: the dashboard of who is due and who is broken.
        self.beat_counts: dict[str, dict[str, Any]] = {}
        #: Whoever is waiting for a user to have a home again, one Event per user
        #: on hold. An entry is born with the hold and dies with its release, so
        #: outside that window this map is empty.
        self.user_hold_event_map: dict[str, asyncio.Event] = {}
        self._default_group = default_group
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._logger = logging.getLogger(__name__)
        self._orders_logger = self._build_orders_logger(
            orchestration_log_path,
            orchestration_log_max_bytes,
            orchestration_log_backup_count,
        )
        for name, group_settings in (groups or {}).items():
            GroupHandler(
                self,
                name,
                memory_concession_bytes=self.memory_concession_bytes,
                **group_settings,
            )

    @property
    def memory_concession_bytes(self) -> int:
        """What this server may hold of the machine's memory, in bytes.

        Returns:
            The concession — the machine's whole memory times
            ``memory_max_percent``. It is the ONE total of the cascade: a
            group's quota and a worker's ceiling are shares of it.
        """
        total = self._machine_memory_gauges()["MemTotal"]
        return int(total * self.memory_max_percent / 100.0)

    @property
    def default_group(self) -> str:
        """The group that receives whoever arrives with no past.

        Returns:
            The elected name, or the first group declared when none was elected —
            ``group_map`` keeps them in the order the recipe named them.

        Raises:
            KeyError: the elected name is nobody's, or there is no group at all;
                either way a newcomer has nowhere to go.
        """
        name = self._default_group or next(iter(self.group_map), None)
        if name not in self.group_map:
            raise KeyError(f"Vertex: no group to receive a newcomer ({name!r})")
        return name

    async def serve_request(
        self, cid: str, http: dict[str, Any], *, hold_timeout: float
    ) -> dict[str, Any]:
        """Serve one request of the hosted site, from the cookie to the answer.

        Args:
            cid: the connection the request carries.
            http: the request in the form the child reads, without the cid.
            hold_timeout: the WHOLE time this request may spend waiting for a user
                who is between two homes, however many times it has to wait.

        Returns:
            The child's REPLY payload, untouched — reading it is the front's job.

        Raises:
            AssignmentRefused: nobody can take him now, and ``retry_after`` says
                when the machine will have decided again.
            SiteFailedRequest: his worker answered with a failure.
            ConnectionError: the wire of his worker is gone.

        Acts on the indexes only through the chain: a cid never seen travels
        ANONYMOUS to the default group's reception — the site baptises while
        serving, and the fold of its own announcements is what writes the
        indexes. A known user with no home is placed, as ever.
        """
        deadline = asyncio.get_running_loop().time() + hold_timeout
        while True:
            try:
                user = self.resolve_user(cid)
                break
            except UserOnHold as waiting:
                await self._wait_out_hold(waiting.user, deadline)
        if user is None or user.startswith(GUEST_PREFIX):
            # RECEPTION-FIRST, the ratified rule: as long as somebody is a
            # guest he never leaves the reception — anonymous first visit and
            # baptised guest alike. Only the login makes him placeable.
            group_handler = self.group_map[
                (self.user_map[user]["group"] if user is not None else None) or self.default_group
            ]
            reception = group_handler.reception
            # The saturation doctrine holds for the STRANGER: no room, polite
            # refusal. A guest already inside is served as ever.
            if reception is None or (user is None and group_handler.state == "saturated"):
                raise self._refused(
                    AssignmentRefused(cid, "no room for a newcomer: the pool is restricted")
                ) from None
            worker_handler = reception
        else:
            group_handler = self.group_map[self.user_map[user]["group"] or self.default_group]
            try:
                worker_name = group_handler.user_worker_map.get(user) or group_handler.assign_user(
                    user
                )
            except AssignmentRefused as refusal:
                raise self._refused(refusal) from None
            worker_handler = group_handler.worker_handler_map[worker_name]
        reply = await worker_handler.connector.call(
            f"{SITE_PATH_PREFIX}{http['path']}",
            {
                "http": {**http, "cid": cid},
                "identity": user,
                "user_frozen": self.user_is_frozen(user) if user is not None else False,
            },
        )
        if "error" in reply:
            raise SiteFailedRequest(user, str(reply["error"]))
        return reply

    async def _wait_out_hold(self, user: str, deadline: float) -> None:
        """Wait for a user to have a home again, inside what is left of the budget.

        A budget already spent is a wait of no seconds, which is the refusal
        itself: the request has waited as long as it said it would.
        """
        try:
            await self.await_user_release(user, deadline - asyncio.get_running_loop().time())
        except TimeoutError:
            raise self._refused(
                AssignmentRefused(user, "he is still between two homes")
            ) from None

    def _refused(self, refusal: AssignmentRefused) -> AssignmentRefused:
        """Count one request the pool could not take, and tell it when to come back."""
        self.counters["requests_refused"] += 1
        refusal.retry_after = SHAPE_REVIEW_SECONDS
        return refusal

    @property
    def inspect_targets(self) -> list[str]:
        """Every process the debug door can look into: this vertex, then the workers."""
        names = ["commander"]
        for group_handler in self.group_map.values():
            names.extend(group_handler.worker_handler_map)
        return names

    async def inspect_target(self, target: str, expr: str) -> str:
        """Evaluate one debug expression in one process of the pool, repr back.

        Args:
            target: ``commander`` for this very process, or a worker's name.
            expr: a Python expression; the namespace holds ``commander`` here,
                ``worker`` inside a child.

        Returns:
            The ``repr`` of the value, whatever the expression reached — the
            point of an eval door is answering questions nobody predicted.

        Raises:
            KeyError: no such target; the ones there are travel in the error.
            RuntimeError: the child refused the expression — its error verbatim.

        Full eval power by construction: the door exists only where the
        inspector surface was mounted on purpose, never in production.
        """
        if target == "commander":
            return repr(eval(expr, {"commander": self}))
        for group_handler in self.group_map.values():
            worker_handler = group_handler.worker_handler_map.get(target)
            if worker_handler is not None:
                reply = await worker_handler.connector.call(INSPECT_OP_PATH, {"expr": expr})
                if "error" in reply:
                    raise RuntimeError(str(reply["error"]))
                return reply["result"]["repr"]
        raise KeyError(
            f"inspect: no target {target!r} here — have: {', '.join(self.inspect_targets)}"
        )

    def resolve_user(self, cid: str) -> str | None:
        """Whose cid this is — None for a cookie the site has not baptised yet.

        Args:
            cid: the identity the cookie carries.

        Returns:
            The user this connection belongs to, or None: the vertex MINTS
            NOBODY — the identity and the guest name are the hosted site's,
            learned from its own ``new_connection`` through the fold. A None
            routes to the reception, anonymous.

        Raises:
            UserOnHold: this user is between two homes.

        Acts on the indexes only to heal a known cid whose user row is gone —
        the cookie outlived the row, the browser is still known, its state is
        not.
        """
        user = self.connection_user_map.get(cid)
        if user is None:
            return None
        if user not in self.user_map:
            self.user_map[user] = self._new_row()
        row = self.user_map[user]
        if row["on_hold"] is not None:
            raise UserOnHold(user, row["on_hold"])
        return user

    def record_connection_user(self, cid: str, user: str) -> None:
        """The junction, written at the fact: the routing cookie learns whose it is.

        Args:
            cid: the ``sticky_cid`` the request travelled under.
            user: the identity the site baptised while serving it.

        Acts on ``connection_user_map`` and, for an identity never seen, on
        ``user_map``. Called by the fold of ``new_connection`` — the one road
        an identity enters the vertex by.
        """
        self.connection_user_map[cid] = user
        if user not in self.user_map:
            self.user_map[user] = self._new_row()

    def user_is_frozen(self, user: str) -> bool:
        """Whether this user's state is in the freezer rather than in a process.

        Args:
            user: the identity to judge.

        Returns:
            True when the mark is on. An identity with no row at all is not
            frozen — there is nothing of his anywhere.
        """
        row = self.user_map.get(user)
        return bool(row and row["frozen"])

    def hold_user(self, user: str, cause: str) -> None:
        """Put a user in the waiting room: his next request waits instead of routing.

        Args:
            user: the identity on his way out of the process he lives on.
            cause: what put him there, kept for the log.

        Acts on his row AND on the barrier whoever asks for him will wait on;
        a hold already there keeps its first cause and its own Event.
        """
        row = self.user_map[user]
        if row["on_hold"] is None:
            row["on_hold"] = cause
            self.user_hold_event_map[user] = asyncio.Event()

    async def await_user_release(self, user: str, timeout: float) -> None:
        """Wait until this user has a home again, or give up at the deadline.

        Args:
            user: the identity somebody's request found on hold.
            timeout: how long that request may wait — the caller's own patience.

        Raises:
            TimeoutError: the hold outlived the deadline.

        Nothing is written. A user whose hold fell between the raise and this
        call has no barrier left and is not waited for at all.
        """
        event = self.user_hold_event_map.get(user)
        if event is not None:
            await asyncio.wait_for(event.wait(), timeout)

    def _release_hold(self, user: str) -> None:
        """Let go of whoever was waiting for this user, and forget his barrier."""
        event = self.user_hold_event_map.pop(user, None)
        if event is not None:
            event.set()

    def drop_page(self, page_id: str) -> None:
        """Forget a page.

        Args:
            page_id: the page that is gone; one already forgotten is that same
                outcome.

        Acts on ``page_connection_map`` and on the desk, whose queues and
        subscriptions of that page go with it.
        """
        self.page_connection_map.pop(page_id, None)
        self.delivery_desk.drop_page(page_id)

    def drop_connection(self, cid: str) -> None:
        """Forget a connection's pages, and keep the connection's identity.

        Args:
            cid: the connection that is gone.

        Acts on ``page_connection_map`` and on the desk each of those pages had
        a queue in: the cid stays in ``connection_user_map``, because the cookie
        is eternal.
        """
        for page_id in [page for page, owner in self.page_connection_map.items() if owner == cid]:
            del self.page_connection_map[page_id]
            self.delivery_desk.drop_page(page_id)

    def drop_user(self, user: str) -> bool:
        """Forget an identity whole: his row, his connections, his pages, his freezer state.

        Args:
            user: the identity that is gone; one already forgotten is that same
                outcome.

        Returns:
            Whether the freezer was holding anything of his.

        Acts on all three indexes, on the desk — his own store queue goes, his
        pages went with their connections — on his barrier — whoever waited for
        him is woken to find him gone and starts over — and on the freezer, counting
        what was waiting for him and will now never be delivered.
        """
        row = self.user_map.pop(user, None) or {}
        self._release_hold(user)
        for cid in [cid for cid, owner in self.connection_user_map.items() if owner == user]:
            self.drop_connection(cid)
            del self.connection_user_map[cid]
        self.counters["pendings_lost"] += len(row.get("pending_dbevents") or ()) + len(
            row.get("pending_datachanges") or ()
        )
        self.delivery_desk.drop_user(user)
        had_state = self.freeze_handler.drop_user_folder(user)
        if had_state:
            self.counters["frozen_users_discarded"] += 1
        return had_state

    def change_connection_user(self, cid: str, user: str, previous_user: str) -> None:
        """The login, as the surface sees it: a connection changes owner.

        Args:
            cid: the connection that logged in.
            user: the identity it belongs to from now on.
            previous_user: who it belonged to a moment ago.

        Acts on two indexes and on nothing else: the cid points at its new owner,
        whose row is brought into being when he is unknown here, and the guest
        left behind goes — he had this one connection and nothing else, by
        construction. A previous identity that is NOT a guest keeps his row: he
        is a person with a life of his own, and losing a connection is not losing
        him. Nothing is placed: where the user lives is his next request's
        business, and the freezer is not touched — a guest never had a folder.
        """
        self.connection_user_map[cid] = user
        if user not in self.user_map:
            self.user_map[user] = self._new_row()
        if previous_user.startswith(GUEST_PREFIX):
            self.user_map.pop(previous_user, None)

    def record_user_group(self, user: str, group: str) -> None:
        """Write down which group a user was placed on.

        Args:
            user: the identity that has just been given a home.
            group: the group that took him.

        Acts on his row. Called by the group in the same breath in which it
        writes its own map, so the two can never say different things.
        """
        self.user_map[user]["group"] = group

    def mark_user_frozen(self, user: str, occupancy_percent: float | None) -> None:
        """Write down that a user's state is on disk, and what it is expected to cost.

        Args:
            user: the identity that left his process.
            occupancy_percent: what he occupied where he was, normalised; None
                leaves the estimate as it was.

        Acts on his row and on his barrier: the mark goes on and the wait he may
        have been in is over.
        """
        row = self.user_map[user]
        row["frozen"] = True
        row["on_hold"] = None
        self._release_hold(user)
        if occupancy_percent is not None:
            row["occupancy_percent"] = occupancy_percent

    def mark_user_adopted(self, user: str) -> None:
        """Write down that a user came home from the freezer.

        Args:
            user: the identity now living in a process again.

        Acts on his row and on his barrier: the mark goes off, the wait is over,
        the slots of what was waiting are emptied.
        """
        row = self.user_map[user]
        row["frozen"] = False
        row["on_hold"] = None
        self._release_hold(user)
        row["pending_dbevents"] = []
        row["pending_datachanges"] = []

    def drop_users(self, users: list[str], *, cause: str) -> None:
        """Take these users out of the machine and discard whatever they left on disk.

        Args:
            users: the identities to forget.
            cause: why, for the log.

        Acts on all three indexes and on the freezer, one user at a time, each
        departure named in the log with whether it had state to lose.
        """
        for user in users:
            had_state = self.drop_user(user)
            self.log_order(
                "vertex",
                "drop_user",
                user,
                numbers={"had_state": had_state},
                outcome=cause,
            )

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
        """
        self._orders_logger.info(
            "decided_by=%s order=%s subject=%s numbers=%s outcome=%s",
            decided_by,
            order,
            subject,
            numbers,
            outcome,
        )

    async def start(self) -> None:
        """Bring the machine up: the reception of the base group, then the beat.

        Acts on the base group — its reception is launched and awaited, so this
        returns when the machine is READY to be served through — and on this
        vertex, whose clock starts last. A reception that would not start leaves
        its group ``broken``: the beat is running by then, and the group tries
        again at its own round.
        """
        await self.group_map[self.default_group].start_worker()
        self._heartbeat_task = asyncio.ensure_future(self.heartbeat_loop())

    async def stop(self) -> None:
        """Take the machine down dry: the clock off, then every group.

        Acts on this vertex and, through each group, on every process it holds.
        Nothing is frozen on the way out: without the soft boot those files
        would be read by nobody, and the next boot wipes the working folder.
        """
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        for group_handler in list(self.group_map.values()):
            await group_handler.stop()

    async def heartbeat_loop(self) -> None:
        """The one clock: a round at every beat, and never a death by a bad round.

        Never returns — whoever starts it cancels it. Acts through everything
        the round acts on.
        """
        while True:
            woken = await self._wait_beat()
            try:
                if woken:
                    await self.ping_groups(woken)
                    continue
                await self.ping_groups()
            except Exception:
                self._logger.exception("Vertex: the round failed")
                continue
            await self.drop_expired_users()
            await self.cleanup_frozen()
            await self.check_resources()

    async def ping_groups(self, group_handlers: list[Any] | None = None) -> None:
        """Give every group its turn, all at once, and wait for all of them.

        Args:
            group_handlers: the groups to give a turn to; all of them when None,
                which is what the timer asks for.

        Acts through the groups: one still in its turn is skipped, and a turn
        that raises is a value here and cancels no sibling.
        """
        turns = []
        for group_handler in group_handlers or list(self.group_map.values()):
            running = self._group_turns.get(group_handler.name)
            if running is not None and not running.done():
                self._logger.warning("Vertex: group %s is still in its turn", group_handler.name)
                continue
            running = asyncio.get_running_loop().create_task(group_handler.ping())
            self._group_turns[group_handler.name] = running
            turns.append(running)
        await asyncio.gather(*turns, return_exceptions=True)

    @every(DROP_EXPIRED_USERS_BEATS)
    async def drop_expired_users(self) -> None:
        """Forget the frozen whose age ran out — the row here, the folder on disk.

        Acts on the indexes and on the freezer; the disk is opened off the loop.
        """
        frozen_users = [user for user in self.user_map if self.user_is_frozen(user)]
        expired = await asyncio.to_thread(self._expired_users, frozen_users)
        if expired:
            self.drop_users(expired, cause="expired")

    @every(CLEANUP_FROZEN_BEATS)
    async def cleanup_frozen(self) -> None:
        """Discard what the freezer holds for nobody the indexes know.

        Acts on the freezer, counting and naming each folder it discards; the
        disk is opened off the loop.
        """
        claimed = {self.freeze_handler.user_to_userkey(user) for user in self.user_map}
        sweep = self.freeze_handler.cleanup_frozen
        for userkey in await asyncio.to_thread(sweep, claimed):
            self.counters["orphan_folders_discarded"] += 1
            self.log_order("vertex", "cleanup_frozen", userkey, outcome="orphan")

    @every(CHECK_RESOURCES_BEATS)
    async def check_resources(self) -> None:
        """Read the machine's memory against its alarm line, the storage against the reserve.

        Acts on ``state`` — the MEMORY alone decides it — and calls
        ``need_resources`` for as long as either alarm stands. A gauge the
        platform does not offer alarms nobody. The gauges are read off the loop.
        """
        memory_percent, storage_free_percent = await asyncio.to_thread(self._read_resources)
        over = memory_percent is not None and memory_percent > self.machine_memory_alarm_percent
        self.state = "saturated" if over else "running"
        on_reserve = storage_free_percent < STORAGE_RESERVE_PERCENT
        if over or on_reserve:
            numbers = {"memory": memory_percent, "storage_free": storage_free_percent}
            outcome = "saturated" if over else "on_reserve"
            self.log_order("vertex", "check_resources", numbers=numbers, outcome=outcome)
            self.need_resources()

    def need_resources(self) -> None:
        """Ask the world outside this process for more room; here that is nothing.

        A commander that can grow its own machine says so by overriding this.
        """

    async def _wait_beat(self) -> list[Any]:
        """Wait for the timer or for any group's wake, whichever comes first.

        Returns:
            The groups that rang, and an empty list when the timer came — which
            is the full round. The timer SURVIVES the wakes it loses to: a group
            ringing at every breath anticipates its own round as often as it
            likes, but cannot postpone the full round — the beat every group and
            every task of the vertex is owed — past its own due.
        """
        if self._beat_timer is not None and self._beat_timer.done():
            # The beat expired while an anticipated round was running: it is
            # owed as a full round, never discarded.
            self._beat_timer = None
            return []
        if self._beat_timer is None:
            self._beat_timer = asyncio.ensure_future(asyncio.sleep(HEARTBEAT_SECONDS))
        wakes = {
            asyncio.ensure_future(group_handler.ping_now_event.wait()): group_handler
            for group_handler in self.group_map.values()
        }
        done, _pending = await asyncio.wait(
            [self._beat_timer, *wakes], return_when=asyncio.FIRST_COMPLETED
        )
        for wake in wakes:
            if wake not in done:
                wake.cancel()
        if self._beat_timer in done:
            self._beat_timer = None
            return []
        return [group_handler for wake, group_handler in wakes.items() if wake in done]

    def _expired_users(self, users: list[str]) -> list[str]:
        """Which of these frozen users are past their own expiry; runs off the loop.

        A frozen row with nothing on disk has no age to judge, and is left to
        ``cleanup_frozen``.
        """
        now = time.time()
        expired = []
        for user in users:
            header = self.freeze_handler.get_item_header(user)
            guest = user.startswith(GUEST_PREFIX)
            hours = self.guest_expiry_hours if guest else self.user_expiry_hours
            if header and now - header["ts"] > hours * SECONDS_PER_HOUR:
                expired.append(user)
        return expired

    def _read_resources(self) -> tuple[float | None, float]:
        """The machine's memory used and the freezer's storage free, in percent; off the loop."""
        return self._machine_memory_used_percent(), self.freeze_handler.storage_free_percent

    def _machine_memory_used_percent(self) -> float | None:
        """How much of the WHOLE machine's memory is in use, in percent, or None."""
        gauges = self._machine_memory_gauges()
        total, available = gauges.get("MemTotal"), gauges.get("MemAvailable")
        return 100.0 * (total - available) / total if total and available is not None else None

    def _machine_memory_gauges(self) -> dict[str, float]:
        """The machine's whole and available memory in BYTES; the whole is always there.

        ``MemTotal`` is answered by every platform (``os.sysconf``), so the
        cascade of percentages is always anchored. ``MemAvailable`` is a
        capability only ``/proc/meminfo`` offers — where it lacks, how much of
        the machine is in use is simply not judged, which is not the same as full.
        """
        gauges: dict[str, float] = {
            "MemTotal": float(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"))
        }
        try:
            with open("/proc/meminfo", encoding="ascii") as meminfo:
                for row in meminfo:
                    name, _, value = row.partition(":")
                    if name == "MemAvailable":
                        gauges[name] = float(value.split()[0]) * 1024
        except OSError:
            pass
        return gauges

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
        """The dedicated logger of the orders, with its own file in place of whatever was there."""
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
