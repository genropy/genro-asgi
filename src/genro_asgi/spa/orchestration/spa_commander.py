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
done, so the writing comes first. The worker events the reception then sends
upward (``new_user``, ``new_connection``) find the work already done, and are
idempotent no-ops by design. A cid whose row is gone — a cookie that outlived it
— is minted again, empty: the browser is still known, its state is not.

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
import time
from collections import Counter
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from genro_bag import Bag

from .beats import every
from .envelope_handler import CommanderEnvelopeHandler
from .exceptions import UserOnHold
from .freeze_handler import FreezeHandler

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

__all__ = ["GUEST_PREFIX", "HEARTBEAT_SECONDS", "ORDERS_LOGGER_NAME", "SpaCommander"]


class SpaCommander:
    """The vertex of the pool: the indexes, the minting, the master store, the log.

    Args:
        frozen_users_path: the freezer root — the same one the workers are given,
            since a parcel written on one side is read on the other.
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
    """

    def __init__(
        self,
        frozen_users_path: str | Path,
        *,
        orchestration_log_path: str | Path | None = None,
        orchestration_log_max_bytes: int = 10 * 1024 * 1024,
        orchestration_log_backup_count: int = 5,
        user_expiry_hours: float = 720.0,
        guest_expiry_hours: float = 24.0,
        machine_memory_alarm_percent: float = 90.0,
    ) -> None:
        self.freeze_handler = FreezeHandler(frozen_users_path)
        self.user_expiry_hours = user_expiry_hours
        self.guest_expiry_hours = guest_expiry_hours
        self.machine_memory_alarm_percent = machine_memory_alarm_percent
        #: The master of the store every worker holds a replica of: the only
        #: writer of that content is here, and a replica is replaced entire.
        self.global_register = Bag()
        self.envelope_handler = CommanderEnvelopeHandler(self)
        #: Where the whole machine stands: ``running``, ``saturated`` (no room
        #: for a newcomer anywhere) or ``broken``. Written by the check of the
        #: resources, which arrives with the heartbeat.
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
        #: One row per periodic method of this vertex — turns seen, runs, errors
        #: and the last one's text: the dashboard of who is due and who is broken.
        self.beat_counts: dict[str, dict[str, Any]] = {}
        self._logger = logging.getLogger(__name__)
        self._orders_logger = self._build_orders_logger(
            orchestration_log_path,
            orchestration_log_max_bytes,
            orchestration_log_backup_count,
        )

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

        Acts on the indexes when the cid or the row is missing.
        """
        user = self.connection_user_map.get(cid)
        if user is None:
            user = f"{GUEST_PREFIX}{cid}"
            self.connection_user_map[cid] = user
            self._logger.info("Vertex: cid %s is new — minted as %s", cid, user)
        if user not in self.user_map:
            self.user_map[user] = self._new_row()
        row = self.user_map[user]
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
        row = self.user_map.get(user)
        return bool(row and row["frozen"])

    def hold_user(self, user: str, cause: str) -> None:
        """Put a user in the waiting room: his next request waits instead of routing.

        Args:
            user: the identity on his way out of the process he lives on.
            cause: what put him there, kept for the log.

        Acts on his row; a hold already there keeps its first cause, which is
        the one that explains the wait.
        """
        row = self.user_map[user]
        if row["on_hold"] is None:
            row["on_hold"] = cause

    def drop_page(self, page_id: str) -> None:
        """Forget a page.

        Args:
            page_id: the page that is gone; one already forgotten is that same
                outcome.

        Acts on ``page_connection_map``.
        """
        self.page_connection_map.pop(page_id, None)

    def drop_connection(self, cid: str) -> None:
        """Forget a connection's pages, and keep the connection's identity.

        Args:
            cid: the connection that is gone.

        Acts on ``page_connection_map`` only: the cid stays in
        ``connection_user_map``, because the cookie is eternal.
        """
        for page_id in [page for page, owner in self.page_connection_map.items() if owner == cid]:
            del self.page_connection_map[page_id]

    def drop_user(self, user: str) -> bool:
        """Forget an identity whole: his row, his connections, his pages, his freezer state.

        Args:
            user: the identity that is gone; one already forgotten is that same
                outcome.

        Returns:
            Whether the freezer was holding anything of his.

        Acts on all three indexes and on the freezer — an identity nobody answers
        for keeps nothing on disk — and counts what was waiting for him and will
        now never be delivered.
        """
        row = self.user_map.pop(user, None) or {}
        for cid in [cid for cid, owner in self.connection_user_map.items() if owner == user]:
            self.drop_connection(cid)
            del self.connection_user_map[cid]
        self.counters["pendings_lost"] += len(row.get("pending_dbevents") or ()) + len(
            row.get("pending_datachanges") or ()
        )
        had_state = self.freeze_handler.drop_user_folder(user)
        if had_state:
            self.counters["frozen_users_discarded"] += 1
        return had_state

    def mark_user_frozen(self, user: str, occupancy_percent: float | None) -> None:
        """Write down that a user's state is on disk, and what it is expected to cost.

        Args:
            user: the identity that left his process.
            occupancy_percent: what he occupied where he was, normalised — the
                estimate whoever places him next reads. None leaves the estimate
                as it was, which is the case of a user whose own worker event
                died with the wire.

        Acts on his row: the mark goes on and the wait he may have been in is
        over — his next request is routed by the mark itself.
        """
        row = self.user_map[user]
        row["frozen"] = True
        row["on_hold"] = None
        if occupancy_percent is not None:
            row["occupancy_percent"] = occupancy_percent

    def mark_user_adopted(self, user: str) -> None:
        """Write down that a user came home from the freezer.

        Args:
            user: the identity now living in a process again.

        Acts on his row: the mark goes off, the wait is over, the slots of what
        was waiting are emptied.
        """
        row = self.user_map[user]
        row["frozen"] = False
        row["on_hold"] = None
        row["pending_dbevents"] = []
        row["pending_datachanges"] = []

    def drop_users(self, users: list[str], *, cause: str) -> None:
        """Take these users out of the machine and discard whatever they left on disk.

        Args:
            users: the identities to forget.
            cause: why, for the log — a wild death, or a departure that lost
                somebody on the way.

        Acts on all three indexes and on the freezer, one user at a time: what a
        process nobody can question left behind cannot be trusted, so it goes,
        each departure named in the log with whether it had state to lose.
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

    async def heartbeat_loop(self) -> None:
        """The one clock: a round at every beat, and never a death by a bad round.

        Never returns — whoever starts it cancels it. A beat of the timer is a
        full round and then a turn to each of the vertex's own tasks, which decide
        for themselves whether their cadence has come; a wake is an anticipated
        round on the groups that rang, and it is not a beat. A round that raises
        leaves its line and the next beat comes anyway.

        Acts through everything the round acts on.
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

        Acts through the groups. One whose previous turn is still open is skipped
        rather than given a second one, so a mute process spends its timeouts
        inside its own group and delays nobody else; a turn that raises is a
        value here, and cancels no sibling.
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

        Acts on the indexes and on the freezer. It is the declared exception to
        pruning layer by layer: a frozen user lives in no process, so nobody
        below the vertex can notice that his time is up.
        """
        frozen_users = [user for user in self.user_map if self.user_is_frozen(user)]
        expired = await asyncio.to_thread(self._expired_users, frozen_users)
        if expired:
            self.drop_users(expired, cause="expired")

    @every(CLEANUP_FROZEN_BEATS)
    async def cleanup_frozen(self) -> None:
        """Discard what the freezer holds for nobody the indexes know.

        Acts on the freezer: the folders left over — a user forgotten while his
        process was writing, the leavings of a machine that stopped badly — are
        the set the disk carries less the set the vertex claims, and they go
        counted and named. The disk is opened off the loop.
        """
        claimed = {self.freeze_handler.user_to_userkey(user) for user in self.user_map}
        sweep = self.freeze_handler.cleanup_frozen
        for userkey in await asyncio.to_thread(sweep, claimed):
            self.counters["orphan_folders_discarded"] += 1
            self.log_order("vertex", "cleanup_frozen", userkey, outcome="orphan")

    @every(CHECK_RESOURCES_BEATS)
    async def check_resources(self) -> None:
        """Read the machine's memory against its alarm line, the storage against the reserve.

        Acts on ``state`` — the MEMORY alone decides it, ``saturated`` past the
        line and ``running`` back under: room on disk is not something the pool
        can grow into. Storage under the reserve is said out loud instead, since
        what answers it is a sysop who makes room or a bigger volume. Either way
        ``need_resources`` is called for as long as it stands. A gauge the
        platform does not offer alarms nobody: an unmeasured machine is not a
        full one. The gauges are read off the loop.
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

        A commander that can grow its own machine — a Kubernetes one, an
        autoscaler's — says so by overriding this. Called at every check for as
        long as the alarm stands.
        """

    async def _wait_beat(self) -> list[Any]:
        """Wait for the timer or for any group's wake, whichever comes first.

        Returns:
            The groups that rang, and an empty list when the timer came first —
            which is the full round.
        """
        wakes = {
            asyncio.ensure_future(group_handler.ping_now_event.wait()): group_handler
            for group_handler in self.group_map.values()
        }
        timer = asyncio.ensure_future(asyncio.sleep(HEARTBEAT_SECONDS))
        done, pending = await asyncio.wait([timer, *wakes], return_when=asyncio.FIRST_COMPLETED)
        for waiting in pending:
            waiting.cancel()
        return [group_handler for wake, group_handler in wakes.items() if wake in done]

    def _expired_users(self, users: list[str]) -> list[str]:
        """Which of these frozen users are past their own expiry; runs off the loop.

        It OPENS one item per user to read when it was written, which is the
        expensive half of the sweep. A frozen row with nothing on disk has no age
        to judge and is left to ``cleanup_frozen``.
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
        """The machine's memory used and the freezer's storage free, in percent; off the loop.

        The memory is None where the platform does not say — the same honesty the
        worker's own resident size has, and no dependency taken for a gauge a
        machine may simply not offer.
        """
        return self._machine_memory_used_percent(), self.freeze_handler.storage_free_percent

    def _machine_memory_used_percent(self) -> float | None:
        """How much of the WHOLE machine's memory is in use, in percent, or None."""
        gauges: dict[str, float] = {}
        try:
            with open("/proc/meminfo", encoding="ascii") as meminfo:
                for row in meminfo:
                    name, _, value = row.partition(":")
                    if name in ("MemTotal", "MemAvailable"):
                        gauges[name] = float(value.split()[0])
        except OSError:
            return None
        total, available = gauges.get("MemTotal"), gauges.get("MemAvailable")
        return 100.0 * (total - available) / total if total and available is not None else None

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

        The file is attached in place of whatever was there: a second commander
        in the same process replaces the first rather than writing every row
        twice into somebody else's file.
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
