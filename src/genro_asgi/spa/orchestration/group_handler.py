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

"""GroupHandler: the workers of one grammar, where a user lands, and the two crises.

A group is the workers built from ONE grammar — the same child, the same policies
— and it owns three things nobody else does: where each of its users lives
(``user_worker_map``, ``None`` meaning "to be assigned"), the manoeuvres on its
own workers, and the shape of the group itself.

**Nobody says how many workers there are.** There is no target and no maximum. At
boot the group brings ONE worker into being — the RECEPTION, which is a role and
not a count — and after that it grows only on demand (nobody admits a newcomer,
so one more is born if the memory quota affords it) and shrinks when the capacity
of one of them is spare. The reception is simply the oldest living worker, and it
is succeeded silently when it dies.

**The placement is EAFP: the refusal IS the answer.** ``assign_user`` walks the
workers from the FULLEST down — filling what is already warm rather than
spreading everybody thin — and asks each one to take the user;
``WorkerHandler.assign_user`` judges itself on its own last photo and refuses by
RAISING, so the reason is a class and never a flag somebody has to remember to
read: over the setpoint is ``NoRoomError``, a process on its way back is
``WorkerRestartingError``, one on its way out ``WorkerQuittingError``. Candidates
exhausted, the base rises — whoever asked answers 503 — and the wake rings on the
way out, so the group grows before he tries again. Two placements in a row are
judged on the same photo, so a group can overshoot by one newcomer: accepted, and
cheaper than a lock.

**The occupancy is the currency of all of it.** A worker's fullness is read off
its last photo the way the pool has always read it: one clamped component per
measurable gauge, the FULLEST of them wins, and the answer is a percentage — so
the memory of a process, the cost of a user and the setpoint of a worker are all
the same number and can be added. Today the photo carries one such gauge, the
resident memory against what a worker of this group may hold; a photo carrying
none reads 0, which is what a worker nobody has measured yet honestly is.

**The memory is a CASCADE of percentages, and only the bottom of it is bytes.**
One total is handed in — ``memory_concession_bytes``, what the machine concedes —
and everything below it is a share: ``memory_max_percent`` is this group's share
of the concession, and ``worker_memory_max_percent`` is what ONE worker may hold
of the group's own quota. So the gate on the growth compares
``memory_occupied_percent``, what the living workers hold read against the
concession, with ``memory_max_percent``: percent against percent, never a byte
count against a byte count. A concession nobody has measured makes every reading
0, which leaves the growth ungated by construction rather than by a special case.

**The clock is the vertex's, the counting is the group's.** ``ping`` is this
group's turn of the one round there is: it beats the workers nobody has heard
from — a process fresh from traffic has just photographed itself — and it reads
its own shape only when its own count of turns says so, or when its wake was
rung, which is what a death or a placement nobody admitted does. The wake is
consumed HERE, at the start of the turn, so the group that rings while its turn
runs is given another one.

**The shape is decided on ONE picture, and one step per round.**
``check_occupancy`` takes the occupancy of every living worker once and then does
the FIRST thing that reading calls for: restart the worker past
``restart_occupancy_max_percent`` (it will not get better on its own), bring one
into being when nobody has room left for a newcomer, or close one whose share the
others can absorb and still admit. The next round re-reads: a decision is never
carried over.

**The closure is the departure of a whole worker, in six steps.** The group
orders the quit; the worker answers AT ONCE with the photo of everybody flagged
for the freezer, so the vertex parks them; it then drains, freezing one user at a
time; emptied, it ends itself; the end of its wire was awaited, so the state says
``quitted``; and at the round that reads it the group does ``drop_worker`` — the
socket taken away, the worker out of the list — which is the same verb the
bonifica of a wild death uses. A departure is settled on the LAST PHOTO, so a
worker nobody ever photographed would take its users down with it: the order
takes a photo first, which is what ``ping_process`` is for.

**Both crises are a polite 503.** ``saturated`` says the memory quota is full and
somebody has to leave before anybody else comes in; ``broken`` says a process
could not be started at all. Residents are served as ever in either; newcomers
and the woken get a 503 with a ``Retry-After``. A saturation ends the moment the
group has room again; a broken group is closed by the first process that starts.
A user never changes group: there is no fallback and no policy key.

**The group never touches an index of the vertex and never opens the freezer.**
It READS from a user's row what he is expected to cost, and it writes its own map
only; the marks, the purges and the disk are the vertex's, and so is the
orchestration log every order of this group leaves its row in.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .envelope_handler import GroupEnvelopeHandler
from .exceptions import AssignmentRefused
from .beats import every
from .worker_handler import WorkerHandler

#: The states of a worker whose process has ended: it is in the list only until
#: the round that reads it, and it is nobody's candidate.
DEAD_STATES = ("quitted", "aborted")

# How many turns of the group pass between two readings of its own shape. The
# health of a process is every turn's business; the shape of the group is a
# slower thing, and the number lives here because the knowledge does.
CHECK_OCCUPANCY_BEATS = 6

__all__ = ["DEAD_STATES", "GroupHandler"]


class GroupHandler:
    """One group: its workers, the placement of its users, its shape, its crises.

    Args:
        spa_commander: the vertex this group hangs under — the layer above in the
            chain, the rows it reads a user's estimate from, and the log every
            order goes to.
        name: the group's name; its workers are named ``<name>_<counter>``, short
            because the name is the socket's too.
        occupancy_max_percent: how full a worker may be before it stops admitting.
        restart_occupancy_max_percent: past this a process is restarted rather
            than kept.
        reception_reserved_percent: what the reception keeps free for the trade
            only it has; its own placement setpoint is the difference.
        new_user_occupancy_percent: what a user nobody has ever measured is
            expected to cost.
        memory_concession_bytes: what the machine concedes the whole pool, in
            bytes — the total every percentage below is read against. None until
            somebody has measured it, and then nothing here is measurable.
        memory_max_percent: this group's share of that concession.
        worker_memory_max_percent: what ONE worker of this group may hold, as a
            share of the group's own quota. In the grammar this rung carries the
            same key as the one above it (``memory_max_percent``): the cascade is
            the vertex's percentage of the machine, the group's of the
            concession, the worker's of the quota, and the prefix is here only
            because two rungs meet in one constructor.
        worker_settings: what every ``WorkerHandler`` of this group is built
            with — the child's identity and the installation's paths — handed
            over verbatim.
    """

    def __init__(
        self,
        spa_commander: Any,
        name: str,
        *,
        occupancy_max_percent: float = 80.0,
        restart_occupancy_max_percent: float = 95.0,
        reception_reserved_percent: float = 50.0,
        new_user_occupancy_percent: float = 5.0,
        memory_concession_bytes: int | None = None,
        memory_max_percent: float = 100.0,
        worker_memory_max_percent: float = 100.0,
        **worker_settings: Any,
    ) -> None:
        self.spa_commander = spa_commander
        self.name = name
        self.occupancy_max_percent = occupancy_max_percent
        self.restart_occupancy_max_percent = restart_occupancy_max_percent
        self.reception_reserved_percent = reception_reserved_percent
        self.new_user_occupancy_percent = new_user_occupancy_percent
        self.memory_concession_bytes = memory_concession_bytes
        self.memory_max_percent = memory_max_percent
        self.worker_memory_max_percent = worker_memory_max_percent
        self.worker_settings = worker_settings
        self.envelope_handler = GroupEnvelopeHandler(self, spa_commander.envelope_handler)
        #: Where each user of this group lives, by worker name; None says his
        #: state is somewhere else and he is to be assigned on his next request.
        self.user_worker_map: dict[str, str | None] = {}
        #: The workers of this group, oldest first — the order the reception is
        #: read off.
        self.worker_handler_map: dict[str, WorkerHandler] = {}
        #: Where this group stands: ``running``, ``saturated`` or ``broken``.
        self.state = "running"
        #: The wake: idempotent, without content, and the only push in the
        #: system. What it says is which group rang it.
        self.ping_now_event = asyncio.Event()
        self._logger = logging.getLogger(__name__)
        self._worker_counter = 0
        #: One row per periodic method of this group — turns seen, runs, errors
        #: and the last one's text.
        self.beat_counts: dict[str, dict[str, Any]] = {}
        self._closing_wires: set[asyncio.Task[None]] = set()
        spa_commander.group_map[name] = self

    @property
    def living_workers(self) -> list[WorkerHandler]:
        """The workers whose process has not ended, oldest first."""
        return [
            worker_handler
            for worker_handler in self.worker_handler_map.values()
            if worker_handler.state not in DEAD_STATES
        ]

    @property
    def reception(self) -> WorkerHandler | None:
        """The worker that receives whoever arrives unplaced: the oldest living one."""
        living = self.living_workers
        return living[0] if living else None

    @property
    def memory_quota_bytes(self) -> float | None:
        """What this group may hold: its share of the concession, in bytes.

        Returns:
            The quota, or None while nobody has measured the concession — and
            then nothing of this group is measurable either.
        """
        if not self.memory_concession_bytes:
            return None
        return self.memory_concession_bytes * self.memory_max_percent / 100.0

    @property
    def memory_occupied_percent(self) -> float:
        """What this group's living workers hold, as a share of the concession.

        Returns:
            The summed resident memory of their last photos over the concession,
            in percent — 0.0 when the concession is unknown, which is what an
            unmeasured group honestly is. Read against ``memory_max_percent``,
            so the gate on the growth is percent against percent.
        """
        if not self.memory_concession_bytes:
            return 0.0
        rss_bytes = sum(
            (worker_handler.worker_snapshot or {}).get("rss_bytes") or 0
            for worker_handler in self.living_workers
        )
        return 100.0 * rss_bytes / self.memory_concession_bytes

    def ping_now(self) -> None:
        """Ring this group's wake: its round comes now instead of at its cadence."""
        self.ping_now_event.set()

    async def ping(self) -> None:
        """This group's turn of the round: beat the silent, read the shape when due.

        Acts on the group: it consumes the wake it was given — which brings the
        reading of the shape forward, whatever its own count says — and lets
        ``check_occupancy`` take the step that reading calls for.
        """
        woken = self.ping_now_event.is_set()
        self.ping_now_event.clear()
        await self.ping_workers()
        await self.check_occupancy(now=woken)

    async def ping_workers(self) -> None:
        """Beat every silent worker of this group at once, and wait for all of them.

        Acts on the processes: a mute one is killed by its own handler, and a
        beat that raises is that worker's business and nobody else's — they are
        all awaited, and none of them cancels a sibling.
        """
        beats = [
            worker_handler.ping_process()
            for worker_handler in self.living_workers
            if worker_handler.requires_beat_ping
        ]
        await asyncio.gather(*beats, return_exceptions=True)

    def get_occupancy_percent(self, worker_snapshot: dict[str, Any] | None) -> float:
        """How full the worker of this photo is, in percent.

        Args:
            worker_snapshot: the photo, or None when the worker has sent none.

        Returns:
            The fullest of the components the photo carries, each clamped to its
            own full — 0.0 when nothing in it is measurable. The memory component
            is read against what one worker of this group may hold, which is
            ``worker_memory_max_percent`` of the group's own quota.
        """
        quota_bytes = self.memory_quota_bytes
        ceiling = quota_bytes * self.worker_memory_max_percent / 100.0 if quota_bytes else None
        rss_bytes = (worker_snapshot or {}).get("rss_bytes")
        components = [rss_bytes / ceiling] if ceiling and rss_bytes is not None else []
        return 100.0 * min(max(components, default=0.0), 1.0)

    def get_worker_cap(self, worker_handler: WorkerHandler) -> float:
        """How full a worker of this group takes users up to, in percent.

        Args:
            worker_handler: the worker being judged.

        Returns:
            The setpoint, less the reserve when that worker is the reception: it
            keeps room for what only it does, receiving whoever arrives unplaced.
        """
        if worker_handler is self.reception:
            return self.occupancy_max_percent - self.reception_reserved_percent
        return self.occupancy_max_percent

    def assign_user(self, user: str) -> str:
        """Place a user on this group's fullest worker that still takes him.

        Args:
            user: the identity to place; his row at the vertex says what he is
                expected to cost, and one nobody has measured costs
                ``new_user_occupancy_percent``.

        Returns:
            The name of the worker that took him.

        Raises:
            AssignmentRefused: every worker refused. The wake is rung on the way
                out, so the group grows before he comes back.

        Acts on ``user_worker_map``.
        """
        occupancy_percent = self.spa_commander.user_map[user]["occupancy_percent"]
        if occupancy_percent is None:
            occupancy_percent = self.new_user_occupancy_percent
        candidates = sorted(
            self.living_workers,
            key=lambda worker_handler: -self.get_occupancy_percent(worker_handler.worker_snapshot),
        )
        for worker_handler in candidates:
            try:
                worker_handler.assign_user(user, occupancy_percent)
            except AssignmentRefused as refusal:
                self._logger.debug("Group %s: %s", self.name, refusal)
                continue
            self.user_worker_map[user] = worker_handler.name
            return worker_handler.name
        self.ping_now()
        raise AssignmentRefused(user, f"no worker of {self.name} admits him")

    @every(CHECK_OCCUPANCY_BEATS)
    async def check_occupancy(self) -> None:
        """Read the group once and take the ONE step that reading calls for.

        Acts on the group: it restarts a worker past the restart setpoint, brings
        one into being when nobody has room for a newcomer left, or closes one
        whose share the others can absorb — and writes ``state`` when the memory
        quota refuses the growth.
        """
        picture = {
            worker_handler.name: self.get_occupancy_percent(worker_handler.worker_snapshot)
            for worker_handler in self.living_workers
        }
        for name, occupancy_percent in picture.items():
            if occupancy_percent > self.restart_occupancy_max_percent:
                await self.restart_worker(self.worker_handler_map[name])
                return
        if not self._has_room(picture):
            await self._grow(picture)
            return
        if self.state == "saturated":
            self.state = "running"
        spare = self._spare_worker(picture)
        if spare is not None:
            await self._order_quit(spare, "close_worker")

    async def start_worker(self) -> WorkerHandler | None:
        """Bring one more worker into this group and start its process.

        Returns:
            The worker now serving, or None when its process could not be started.

        Acts on ``worker_handler_map`` and on ``state``: a launch that lands ends
        both crises, a launch that fails is the ``broken`` one.
        """
        self._worker_counter += 1
        name = f"{self.name}_{self._worker_counter:04d}"
        worker_handler = WorkerHandler(self, name, **self.worker_settings)
        self.worker_handler_map[name] = worker_handler
        try:
            await worker_handler.launch_process()
        except Exception as failure:
            del self.worker_handler_map[name]
            await worker_handler.connector.stop()
            self.state = "broken"
            self._logger.exception("Group %s: %s could not be started", self.name, name)
            self.spa_commander.log_order(self.name, "start_worker", name, outcome=str(failure))
            return None
        self.state = "running"
        self.spa_commander.log_order(
            self.name, "start_worker", name, numbers={"workers": len(self.living_workers)}
        )
        return worker_handler

    async def restart_worker(self, worker_handler: WorkerHandler) -> WorkerHandler | None:
        """Ask a worker to leave for good and put a fresh one in its place.

        Args:
            worker_handler: the worker that is not coming back — its users go to
                the freezer as it drains, and come home wherever they are next
                placed.

        Returns:
            The worker born in its place, or None when that one could not start.

        Acts on the group: the departure is settled through the death of the old
        process, so the placements it held are released before the new one exists.
        """
        await self._order_quit(worker_handler, "restart_worker")
        worker_handler.envelope_handler.report_death()
        return await self.start_worker()

    def drop_worker(self, name: str) -> None:
        """Take a worker out of the group for good: its wire, its placements, itself.

        Args:
            name: the worker that has ended.

        Raises:
            KeyError: this group has no worker of that name — a death reported
                for somebody else's worker is a bug, not a thing to swallow.

        Acts on ``worker_handler_map`` and ``user_worker_map``; the socket is
        taken away detached, since whoever calls this is the fold and cannot wait.
        """
        worker_handler = self.worker_handler_map.pop(name)
        closing = asyncio.get_running_loop().create_task(worker_handler.connector.stop())
        self._closing_wires.add(closing)
        closing.add_done_callback(self._closing_wires.discard)
        for user in [user for user, worker in self.user_worker_map.items() if worker == name]:
            del self.user_worker_map[user]
        self.spa_commander.log_order(
            self.name, "drop_worker", name, outcome=worker_handler.state
        )

    def _has_room(self, picture: dict[str, float]) -> bool:
        """Whether any living worker would still take a newcomer of the default size."""
        return any(
            occupancy_percent + self.new_user_occupancy_percent
            <= self.get_worker_cap(self.worker_handler_map[name])
            for name, occupancy_percent in picture.items()
        )

    def _spare_worker(self, picture: dict[str, float]) -> WorkerHandler | None:
        """The emptiest worker the others could absorb and still admit; None when there is none.

        The others are read as if they shared what this one holds: the group
        closes a worker only while what is left of it would still take a
        newcomer, which is also what keeps a closure from undoing a growth.
        """
        candidates = [
            worker_handler
            for worker_handler in self.living_workers
            if worker_handler is not self.reception
        ]
        if not candidates:
            return None
        shared = sum(picture.values()) / (len(picture) - 1)
        if shared + self.new_user_occupancy_percent > self.occupancy_max_percent:
            return None
        return min(candidates, key=lambda worker_handler: picture[worker_handler.name])

    async def _grow(self, picture: dict[str, float]) -> None:
        """Bring a worker into being if the memory affords it; the saturation when it does not."""
        occupied_percent = self.memory_occupied_percent
        if self.spa_commander.state == "running" and occupied_percent <= self.memory_max_percent:
            await self.start_worker()
            return
        self.state = "saturated"
        self.spa_commander.log_order(
            self.name,
            "grow",
            numbers={
                "memory_occupied_percent": occupied_percent,
                "memory_max_percent": self.memory_max_percent,
                "workers": len(picture),
            },
            outcome="saturated",
        )

    async def _order_quit(self, worker_handler: WorkerHandler, order: str) -> None:
        """Ask a worker's process to leave, having made sure a photo of it exists.

        The departure of everybody on board is settled on the LAST photo — who
        was flagged for the freezer — so a worker that has never answered
        anything is photographed first: without that, an ordered quit would purge
        its users as if nobody had promised them the freezer.
        """
        if worker_handler.worker_snapshot is None:
            await worker_handler.ping_process()
        self.spa_commander.log_order(
            self.name,
            order,
            worker_handler.name,
            numbers={
                "occupancy_percent": self.get_occupancy_percent(worker_handler.worker_snapshot),
                "workers": len(self.living_workers),
            },
        )
        await worker_handler.quit_process()
