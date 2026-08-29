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
read: over the setpoint is ``NoRoomError``, one on its way out
``WorkerQuittingError``. Candidates
exhausted, the base rises — whoever asked answers 503 — and the wake rings on the
way out, so the group grows before he tries again. Two placements in a row are
judged on the same photo, so a group can overshoot by one newcomer: accepted, and
cheaper than a lock.

**The occupancy is the currency of all of it.** A worker's fullness is read off
its last photo the way the pool has always read it: one clamped component per
measurable gauge, the FULLEST of them wins, and the answer is a percentage — so
the memory of a process, the cost of a user and the setpoint of a worker are all
the same number and can be added. On Linux the memory component is PSS, which
divides prefork-shared pages among the processes mapping them; RSS remains the
conservative fallback wherever PSS is unavailable. A photo carrying neither
reads 0, which is what a worker nobody has measured yet honestly is.

**The memory is a CASCADE of percentages, and only the bottom of it is bytes.**
One total is always handed in — ``memory_concession_bytes``, what the machine
concedes — and everything below it is a share: ``memory_max_percent`` is this group's share
of the concession, and ``worker_memory_max_percent`` is what ONE worker may hold
of the group's own quota. The worker share is usually not written at all:
``worker_max_number`` names how many workers the quota is SIZED FOR — an
intuitive count of slots instead of a percentage — and the share is derived as
``100 / worker_max_number``. It is a divisor of the size and nothing else: the
number of processes stays a reading, never a setting. An explicit
``worker_memory_max_percent`` wins over the derivation. So the first gate on the
growth compares ``memory_occupied_percent``, what the living workers hold read
against the concession, PLUS the share one more worker may hold, with
``memory_max_percent``: percent against percent, never a byte count against a
byte count.

The cascade knows only the workers, and a container holds more than them. So a
second gate answers in bytes, on ``SpaCommander.memory_available_bytes``: the
ceiling of the newborn must be free where the process will actually live —
inside the cgroup when there is one, on the machine when there is not. The
commander, the group templates and every other tenant of the container are
counted there and nowhere else. Both gates hold or nobody is born; a machine
that measures nothing refuses nothing.

**The clock is the vertex's, the counting is the group's.** ``ping`` is this
group's turn of the one round there is: it settles every process whose end has
not been read yet — the state is the only word on a death, and a round is where
it is read, whether the process left as it was told to or died wild — it beats
the workers nobody has heard from — a process fresh from traffic has just
photographed itself — and it reads
its own shape only when its own count of turns says so, or when its wake was
rung, which is what a death or a placement nobody admitted does. The wake is
consumed HERE, at the start of the turn, so the group that rings while its turn
runs is given another one.

**The shape is decided on ONE picture, and one step per round.**
``check_occupancy`` takes the occupancy of every living worker once and then does
the FIRST thing that reading calls for: restart the worker whose MEMORY is past
``restart_occupancy_max_percent`` (it will not get better on its own), bring one
into being when nobody has room left for a newcomer, or close one whose share
keeps every survivor under ``close_occupancy_max_percent`` — a threshold
distinctly below the growth's, because reading both decisions against the same
number made each one create the condition for its own reversal (#36): the band
between the two is the pool's normal state. A worker younger than
``worker_min_life_seconds`` is never the one closed, and a closure is refused
when the survivors lack room BY HEADS for the spare's placed users. The next
round re-reads: a decision is never carried over.

**The early CPU growth (#43, experimental, off by default).** With
``cpu_grow_percent`` set, a worker whose smoothed ``cpu_percent`` crosses above
it does TWO things: it asks the round for one worker AHEAD of the demand — the
fork is cheap, and waiting for the admission ceiling proved 70 seconds late on
the bench — and it is CLOSED to new users (``cpu_admission_open``), so the
capacity just created is what fullest-first finds. It reopens only below
``cpu_grow_rearm_percent``; between the two thresholds it keeps its state —
the band is hysteresis. One latch per worker (re-armed below the same rearm
threshold), one spawn per round, under the placement lock. The Hetzner bench
of 2026-08-28 proved the one-shot preference this policy first shipped with a
fixed point at two workers: the newborn took ONE user, fullest-first then
walked every arrival back to the worker already over the threshold, whose
latch was spent — so nobody could father the third. The admission closure
replaces that preference: the newborn takes the new users because it is the
candidate left open, for as long as the trigger worker stays hot, and when the
newborn crosses the threshold itself it fathers the next one — the policy
scales one crossing at a time. The composite occupancy takes no part in this
trigger, the memory protections keep their own judges, and sticky users are
never moved. When no open worker admits the newcomer and the growth is
refused, a closed worker still under the hard ``occupancy_max_percent`` takes
him as a LOGGED fallback — the soft closure protects the pool's shape, never
at the price of a premature 503. The crossing is judged within a beat, not at
the shape's own cadence: the envelope layer rings ``ping_now`` when a fresh
photo crosses a threshold, and the wake anticipates the group's round. And the
RETIREMENT STANDS ASIDE while the CPU speaks: a living worker still CPU-closed,
or any CPU event younger than ``cpu_retirement_quiet_seconds`` — a blocking, a
growth, a quota refusal, a reopening — suspends the closure judge, because
closing the emptiest worker under standing demand hands its users back to the
hot one, which regrows seconds later (the close→grow cycle the bench measured,
churn 2026-08-28). The quiet is CONTINUOUS: every event restarts it whole, the
reopen included. After it, the retirement is exactly what it always was.

**The closure is the departure of a whole worker, in six steps.** The group
orders the quit; the worker answers AT ONCE with the photo of everybody flagged
for the freezer, so the vertex parks them; it then drains, freezing one user at a
time; emptied, it ends itself; the end of its wire was awaited, so the state says
``quitted``; and at the round that reads it the group does ``drop_worker`` — the
socket taken away, the worker out of the list — which is the same verb the
bonifica of a wild death uses. A departure is settled on the LAST PHOTO, so a
worker nobody ever photographed would take its users down with it: the order
takes a photo first, which is what ``ping_process`` is for.

**The soft quit blocks BEFORE it orders.** ``quit_all`` raises the hold on every
user it places on a worker and only then sends that worker's order. It is the
same barrier the photo's flags raise at the vertex — a flag is read there as a
hold — moved ahead of the order, which closes the window the photo cannot: the
photo rides the answer, and until it arrives a request of his would walk into a
process already emptying. The closure of a single worker (``close_worker``,
``restart_worker``) blocks nobody in advance and meets its users on the photo, as
before.

**Both crises are a polite 503.** ``saturated`` says the memory quota is full and
somebody has to leave before anybody else comes in; ``broken`` says a process
could not be started at all. Residents are served as ever in either; newcomers
and the woken get a 503 with a ``Retry-After``. A saturation ends the moment the
group has room again; a broken group is closed by the first process that starts.
A user never changes group: there is no fallback and no policy key.

**Putting one user to sleep is the group's own move, in one order.**
``freeze_hosted_user`` blocks him at the vertex FIRST — from that instant a
request of his waits instead of walking into a process that is emptying — then
orders his worker to park him and waits for the REPLY, which IS the
confirmation. The worker judges nothing on that road; it only executes. A
departure that did not happen gives the block back and leaves him where he was.

**And WHO sleeps is decided here too, on the same photos.**
``check_user_activity`` is the group's second periodic: it reads the two
real clocks of every active user off his worker's last photo, parks whoever has
been silent past ``user_idle_freeze_minutes`` through the order above, and drops
whoever is silent past his own expiry — the same horizon the vertex applies to a
parcel, asked of the vertex. Nothing below this rung has a gauge of its own: the
worker was where that judgment used to live, and it kept no policy after the
freeze order was built.

**The group never touches an index of the vertex and never opens the freezer.**
It READS from a user's row what he is expected to cost, and it writes its own map
only; the marks, the purges and the disk are the vertex's, and so is the
orchestration log every order of this group leaves its row in.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import Counter
from typing import Any

from .envelope_handler import GroupEnvelopeHandler
from .group_policy import GroupPolicy
from .exceptions import AssignmentRefused
from .beats import every
from .template_connector import TemplateConnector
from .worker_handler import DROP_USER_OP_PATH, FREEZE_USER_OP_PATH, WorkerHandler

#: The states of a worker whose process has ended: it is in the list only until
#: the round that reads it, and it is nobody's candidate.
DEAD_STATES = ("quitted", "aborted")

#: How many workers a group's quota is sized for when the recipe says nothing:
#: the per-worker memory ceiling defaults to quota / this. A divisor of the
#: size only — the number of living processes stays a reading, never a setting.
WORKER_MAX_NUMBER = 6

# How many turns of the group pass between two readings of its own shape. The
# health of a process is every turn's business; the shape of the group is a
# slower thing, and the number lives here because the knowledge does.
CHECK_OCCUPANCY_BEATS = 6

# And how many pass between two readings of who has gone quiet. Slower still,
# because the silence it judges is declared in MINUTES: reading it oftener would
# cost turns to answer a question whose answer cannot have changed.
CHECK_USER_ACTIVITY_BEATS = 12

#: The conversion the silence needs: it is a policy of the installation and comes
#: in minutes, the clocks it is read against are seconds.
SECONDS_PER_MINUTE = 60.0

#: The suppression a crossing meets when the growth is refused by the memory
#: quota or the server state. ONE constant, because two readers depend on the
#: same words: the orchestration log, and the pressure clock — a crossing the
#: group cannot honour is UNMET demand, and the retirement must not eat the
#: capacity that demand is waiting for.
CPU_GROW_QUOTA_REFUSAL = "suppressed: the quota or the server state refuses the growth"

#: The other two CPU-growth refusals, shared by the human order and the stable
#: reason-code translation. The journal never parses prose to understand them.
CPU_GROW_TRIGGER_GONE_REFUSAL = "suppressed: the trigger worker is gone"
CPU_GROW_CAPACITY_ARRIVED_REFUSAL = "suppressed: capacity arrived while waiting for the lock"

#: How long the group waits for the confirmation of ONE ordered departure — a
#: freeze or a drop — before giving up, releasing the hold and leaving the user
#: where he is. A beat: the round that sends the order is the group's own, and a
#: round that waits longer than a beat stops the group from beating at all. ONE
#: number for the two orders, because the reason for the ceiling is the same.
DEPARTURE_ORDER_WAIT_LIMIT = 5.0

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
        restart_occupancy_max_percent: past this MEMORY occupancy a process is
            restarted rather than kept. CPU pressure grows and closes
            admission; it never replaces a healthy process.
        close_occupancy_max_percent: a closure is ordered only when the spare's
            share, redistributed, keeps EVERY survivor under this — distinctly
            below ``occupancy_max_percent``, so the band between the two is the
            pool's normal state and never a condition to correct. One threshold
            for both made every growth the evidence for its own reversal (#36).
        cpu_grow_percent: the early-provision threshold (#43, experimental): a
            worker whose smoothed ``cpu_percent`` crosses above it asks for one
            worker AHEAD of the demand — the fork is cheap, waiting for the
            admission ceiling proved 70 seconds late. None, the default, leaves
            the policy off and the pool exactly as it was.
        cpu_grow_rearm_percent: below this the worker's crossing is loaded
            again. The band between the two is hysteresis: a worker sitting
            above the threshold fires ONCE, not once per photo.
        cpu_retirement_quiet_seconds: how long the CPU must stay SILENT — no
            crossing blocked, no growth landed or quota-refused, no worker
            reopened — before the retirement judges again, with the policy on.
            Not the age of a worker (that is ``worker_min_life_seconds``): this
            is the quiet of the whole group, and every CPU event restarts it
            whole. Closing the emptiest worker while demand still speaks hands
            its users back to the hot one, which regrows seconds later
            (measured, churn 2026-08-28).
        worker_min_life_seconds: a worker is no closure candidate before this
            age — younger, its occupancy measures its own birth, not its work.
        reception_reserved_percent: what the reception keeps free for the trade
            only it has; its own placement setpoint is the difference.
        new_user_occupancy_percent: what a user nobody has ever measured is
            expected to cost.
        newcomer_reserve_count: how many newcomers of that size must ALWAYS find
            room — the group grows at its own round before anybody is refused,
            and no closure may eat into it.
        user_idle_freeze_minutes: the silence, IN MINUTES, past which this group
            parks a user in the freezer; with nothing said, silence never parks
            anybody. Minutes because it is a policy of the installation, and the
            comparison against the photo's clocks converts where it is made.
        memory_concession_bytes: what the machine concedes the whole pool, in
            bytes — the total every percentage below is read against.
        memory_max_percent: this group's share of that concession.
        worker_max_number: how many workers the group's quota is sized for —
            the per-worker ceiling divisor, never a cap on how many processes
            exist. It replaces the bridge-era RAM×0.8/workers derivation with
            one intuitive number of slots.
        worker_memory_max_percent: what ONE worker of this group may hold, as a
            share of the group's own quota; None derives it as
            ``100 / worker_max_number``, and an explicit value wins.
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
        close_occupancy_max_percent: float = 40.0,
        cpu_grow_percent: float | None = None,
        cpu_grow_rearm_percent: float = 40.0,
        cpu_retirement_quiet_seconds: float = 60.0,
        worker_min_life_seconds: float = 60.0,
        reception_reserved_percent: float = 50.0,
        new_user_occupancy_percent: float = 5.0,
        newcomer_reserve_count: int = 1,
        worker_max_users: float = math.inf,
        user_idle_freeze_minutes: float = math.inf,
        memory_concession_bytes: int,
        memory_max_percent: float = 100.0,
        worker_max_number: int = WORKER_MAX_NUMBER,
        worker_memory_max_percent: float | None = None,
        engine_factory: str | None = None,
        engine_kwargs: dict[str, Any] | None = None,
        **worker_settings: Any,
    ) -> None:
        if cpu_grow_percent is not None and not (
            0.0 <= cpu_grow_rearm_percent < cpu_grow_percent <= 100.0
        ):
            raise ValueError(
                f"Group {name}: cpu_grow_rearm_percent ({cpu_grow_rearm_percent}) must sit "
                f"below cpu_grow_percent ({cpu_grow_percent}), both inside 0-100 — the band "
                "between them is the hysteresis; without it a steady worker respawns forever"
            )
        self.spa_commander = spa_commander
        self.name = name
        #: Every setpoint of this group, validated together and read through the
        #: properties below. ``inf`` is how the constructor spells "unlimited"
        #: and ``null`` is how a profile spells it, so the two translate here.
        self.policy = GroupPolicy.from_settings(
            {
                "occupancy_max_percent": occupancy_max_percent,
                "restart_occupancy_max_percent": restart_occupancy_max_percent,
                "close_occupancy_max_percent": close_occupancy_max_percent,
                "cpu_grow_percent": cpu_grow_percent,
                "cpu_grow_rearm_percent": cpu_grow_rearm_percent,
                "cpu_retirement_quiet_seconds": cpu_retirement_quiet_seconds,
                "worker_min_life_seconds": worker_min_life_seconds,
                "reception_reserved_percent": reception_reserved_percent,
                "new_user_occupancy_percent": new_user_occupancy_percent,
                "newcomer_reserve_count": newcomer_reserve_count,
                "worker_max_users": None if worker_max_users == math.inf else worker_max_users,
                "user_idle_freeze_minutes": (
                    None if user_idle_freeze_minutes == math.inf else user_idle_freeze_minutes
                ),
                "memory_max_percent": memory_max_percent,
                "worker_max_number": worker_max_number,
                "worker_memory_max_percent": worker_memory_max_percent,
            }
        )
        self.memory_concession_bytes = memory_concession_bytes
        self.worker_settings = worker_settings
        #: This group's template, when a factory was declared for it: the process
        #: its workers are forked from. None means its workers are spawned instead.
        self.template = (
            None
            if engine_factory is None
            else TemplateConnector(
                self,
                engine_factory=engine_factory,
                engine_kwargs=engine_kwargs,
                executable=worker_settings.get("executable"),
            )
        )
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
        self._placement_lock = asyncio.Lock()
        #: When the CPU last spoke (#43): a crossing blocked, a growth landed
        #: or was refused by the quota, a worker reopened — an apply that
        #: actually moves a worker's admission included. None from birth — no
        #: artificial cooldown at boot: until a real CPU event this gate does
        #: not exist, and the retirement judges as it always did. The retirement
        #: resumes only after ``cpu_retirement_quiet_seconds`` of CONTINUOUS
        #: silence past this instant.
        self._cpu_pressure_monotonic: float | None = None
        self._logger = logging.getLogger(__name__)
        self._worker_counter = 0
        #: One row per periodic method of this group — turns seen, runs, errors
        #: and the last one's text.
        self.beat_counts: dict[str, dict[str, Any]] = {}
        self._closing_wires: set[asyncio.Task[None]] = set()
        spa_commander.group_map[name] = self

    # The setpoints are read through here and stored nowhere else: the names
    # are the ones every decision and every reader has always used, and after
    # a swap they answer the new policy at once.
    @property
    def occupancy_max_percent(self) -> float:
        return self.policy.occupancy_max_percent

    @property
    def restart_occupancy_max_percent(self) -> float:
        return self.policy.restart_occupancy_max_percent

    @property
    def close_occupancy_max_percent(self) -> float:
        return self.policy.close_occupancy_max_percent

    @property
    def cpu_grow_percent(self) -> float | None:
        return self.policy.cpu_grow_percent

    @property
    def cpu_grow_rearm_percent(self) -> float:
        return self.policy.cpu_grow_rearm_percent

    @property
    def cpu_retirement_quiet_seconds(self) -> float:
        return self.policy.cpu_retirement_quiet_seconds

    @property
    def worker_min_life_seconds(self) -> float:
        return self.policy.worker_min_life_seconds

    @property
    def reception_reserved_percent(self) -> float:
        return self.policy.reception_reserved_percent

    @property
    def new_user_occupancy_percent(self) -> float:
        return self.policy.new_user_occupancy_percent

    @property
    def newcomer_reserve_count(self) -> int:
        return self.policy.newcomer_reserve_count

    @property
    def worker_max_users(self) -> float:
        return self.policy.worker_max_users

    @property
    def user_idle_freeze_minutes(self) -> float:
        return self.policy.user_idle_freeze_minutes

    @property
    def memory_max_percent(self) -> float:
        return self.policy.memory_max_percent

    @property
    def worker_max_number(self) -> int:
        return self.policy.worker_max_number

    @property
    def worker_memory_max_percent(self) -> float:
        return self.policy.worker_memory_max_percent
    def apply_policy(
        self, new_policy: GroupPolicy, reconciliation: list[tuple[str, bool]]
    ) -> None:
        """Take the new setpoints and settle the CPU admission of the listed workers.

        Args:
            new_policy: the complete policy that governs this group from now on.
            reconciliation: one ``(worker name, cpu_admission_open)`` pair per
                worker the caller judged against the NEW thresholds.

        Guaranteed assignments only: no await, no order on a wire, no birth and
        no log line — everything fallible was done before this is called, so the
        swap cannot half-happen. Every listed worker is re-armed for the CPU
        growth, the band its latch was spent against being gone.

        An admission this apply actually MOVES is a CPU event like any other and
        restarts the retirement's quiet: new thresholds that close a worker, or
        reopen one, are the same fact the periodic judge would have recorded. An
        apply that moves nobody — a new quiet, another setpoint entirely — leaves
        the clock exactly where it was, so nothing invents a cooldown out of a
        reconfiguration. A policy switched OFF moves nobody either, whatever it
        reopens: those reopenings are the gate being dismantled, not the CPU
        speaking, and stamping them would leave a cooldown behind for whoever
        switches the policy back on.
        """
        cpu_policy_on = new_policy.cpu_grow_percent is not None
        self.policy = new_policy
        for name, admission_open in reconciliation:
            worker_handler = self.worker_handler_map[name]
            if cpu_policy_on and worker_handler.cpu_admission_open != admission_open:
                self.record_cpu_pressure()
            worker_handler.cpu_admission_open = admission_open
            worker_handler.cpu_growth_armed = True

    def _policy_held(
        self, policy: GroupPolicy, order: str, subject: str | None = None
    ) -> bool:
        """Whether the policy a decision stood on is still this group's.

        Args:
            policy: the snapshot the decision bound at its top.
            order: the order about to be given, for the log.
            subject: on whom it was to be given, for the log.

        Returns:
            True when the effect may go ahead. False when the policy was swapped
            while the decision was waiting — the effect is suppressed and the
            suppression logged, and the swap's own round judges the group again.
        """
        if self.policy is policy:
            return True
        self.spa_commander.log_order(
            self.name, order, subject, outcome="suppressed: policy changed while deciding"
        )
        return False

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
    def memory_quota_bytes(self) -> float:
        """What this group may hold: its share of the concession, in bytes."""
        return self.memory_concession_bytes * self.memory_max_percent / 100.0

    @property
    def worker_memory_ceiling_bytes(self) -> float:
        """What ONE worker of this group may hold: its share of the quota, in bytes."""
        return self.memory_quota_bytes * self.worker_memory_max_percent / 100.0

    @property
    def memory_occupied_percent(self) -> float:
        """What this group's living workers hold, as a share of the concession.

        Returns:
            The summed accounted memory of their last photos over the
            concession, in percent. PSS is used where Linux reports it; RSS is
            the conservative fallback elsewhere. Read against
            ``memory_max_percent``, so the growth gate compares percent with
            percent without counting prefork-shared pages once per worker.
        """
        accounted_bytes = sum(
            self.get_memory_accounting(worker_handler.worker_snapshot)[0] or 0
            for worker_handler in self.living_workers
        )
        return 100.0 * accounted_bytes / self.memory_concession_bytes

    @staticmethod
    def get_memory_accounting(
        worker_snapshot: dict[str, Any] | None,
    ) -> tuple[float | None, str]:
        """Choose the memory gauge a worker decision may account.

        Args:
            worker_snapshot: the worker's latest photo, or ``None``.

        Returns:
            ``(bytes, kind)``. A finite non-negative PSS wins; otherwise a
            finite non-negative RSS is the conservative portable fallback.
            With neither, the worker is ``unmeasured`` and contributes no
            invented number, preserving the pre-existing no-photo semantics.
        """
        photo = worker_snapshot or {}
        for field, kind in (("pss_bytes", "pss"), ("rss_bytes", "rss_fallback")):
            value = photo.get(field)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            try:
                numeric = float(value)
            except OverflowError:
                continue
            if math.isfinite(numeric) and numeric >= 0:
                return numeric, kind
        return None, "unmeasured"

    @property
    def memory_accounting_kind(self) -> str:
        """How the living workers' memory is accounted in this group."""
        kinds = {
            self.get_memory_accounting(worker.worker_snapshot)[1]
            for worker in self.living_workers
        }
        if not kinds:
            return "unmeasured"
        if len(kinds) == 1:
            return kinds.pop()
        return "mixed"

    def ping_now(self) -> None:
        """Ring this group's wake: its round comes now instead of at its cadence."""
        self.ping_now_event.set()

    async def ping(self) -> None:
        """This group's turn of the round: bury the dead, beat the silent, read the shape.

        Acts on the group: it consumes the wake it was given — which brings the
        reading of the shape forward — settles every process whose end has not
        been read yet, and lets its two periodics take their step. The shape
        comes first: a worker restarted or closed by that step changes who there
        is to read the silence of.
        """
        woken = self.ping_now_event.is_set()
        self.ping_now_event.clear()
        for worker_handler in list(self.worker_handler_map.values()):
            if worker_handler.state in DEAD_STATES:
                worker_handler.envelope_handler.report_death()
        await self.ping_workers()
        await self.check_occupancy(now=woken)
        await self.check_user_activity()

    async def ping_workers(self) -> None:
        """Beat every silent worker of this group at once, and wait for all of them.

        Acts on the processes: a mute one is killed by its own handler, and a
        beat that raises cancels no sibling.
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
            own full — 0.0 when nothing in it is measurable. Memory is PSS
            against this worker's share of the quota, with RSS as its portable
            conservative fallback. ``cpu_percent`` is the share of one core
            burned between the last two photos (#38), which sees a GIL-saturated
            worker whose memory stands still.
        """
        photo = worker_snapshot or {}
        components = [self.get_memory_occupancy_percent(photo) / 100.0]
        cpu_percent = photo.get("cpu_percent")
        if cpu_percent is not None:
            components.append(cpu_percent / 100.0)
        return 100.0 * min(max(components, default=0.0), 1.0)

    def get_memory_occupancy_percent(
        self, worker_snapshot: dict[str, Any] | None
    ) -> float:
        """How full this worker is by memory alone, in percent.

        PSS is the Linux currency and RSS its conservative fallback, selected
        by ``get_memory_accounting``. This separate reading is what the restart
        judge uses: CPU pressure asks for capacity and soft admission, never the
        destruction of a process that still owns live sessions.
        """
        accounted_bytes, _kind = self.get_memory_accounting(worker_snapshot)
        if accounted_bytes is None:
            return 0.0
        return 100.0 * min(accounted_bytes / self.worker_memory_ceiling_bytes, 1.0)

    def get_worker_cap(self, worker_handler: WorkerHandler) -> float:
        """How full a worker of this group takes users up to, in percent.

        Args:
            worker_handler: the worker being judged.

        Returns:
            The setpoint, less the reserve when that worker is the reception.
        """
        if worker_handler is self.reception:
            return self.occupancy_max_percent - self.reception_reserved_percent
        return self.occupancy_max_percent

    async def assign_user(self, user: str) -> str:
        """Place a user: the fullest worker that admits him, or one born for him.

        Args:
            user: the identity to place; his row at the vertex says what he is
                expected to cost, and one nobody has measured costs
                ``new_user_occupancy_percent``.

        Returns:
            The name of the worker that took him.

        Raises:
            AssignmentRefused: the group gave up — nobody admits him, the group
                may not grow (its quota, or the memory the machine still has),
                or the launch failed. The surrender and nothing before it is what
                the front turns into a 503.

        The birth lives INSIDE the placement (owner, 2026-08-25): when no
        living worker admits him and the group may grow, this very call brings
        the worker into being — ``start_worker`` returns at its presentation,
        a moment under a template — and places him on it. The request is never
        parked and never sent away to come back: it waits right here.

        Three levels, each tried only when the one before surrendered. First
        the CPU-open workers, fullest-first (``_placement_candidate``). Then
        the birth. LAST, when the growth was refused or failed, a CPU-closed
        worker still under its hard cap takes him (``_fallback_candidate``) —
        the soft closure shapes the pool, it must never cost a 503 the hard
        limit would not have cost; the fallback is logged, never silent, and
        never reached while an open worker or a birth can serve.

        One placement at a time per group, under ``_placement_lock``: sixteen
        simultaneous arrivals must not father sixteen workers when one is
        enough. Whoever waited recomputes and finds the newborn.

        Acts on ``user_worker_map`` and, in the same breath, on the row at the
        vertex that says which group he is on.
        """
        policy = self.policy
        async with self._placement_lock:
            worker_handler = self._placement_candidate(user)
            placement_reason = "fullest_cpu_open_candidate"
            if worker_handler is None and self._may_grow and self._policy_held(policy, "grow", user):
                worker_handler = await self.start_worker()
                if worker_handler is not None:
                    try:
                        worker_handler.assign_user(user, self._expected_occupancy(user))
                        placement_reason = "new_worker_created_for_placement"
                    except AssignmentRefused:
                        worker_handler = None
            if worker_handler is None:
                worker_handler = self._fallback_candidate(user)
                placement_reason = "cpu_closed_hard_cap_fallback"
            if worker_handler is None:
                # The surrender still rings the wake: the next round is what
                # writes ``saturated`` where the front can read it.
                self.ping_now()
                self.spa_commander.log_decision(
                    self.name,
                    "placement",
                    "refused",
                    reason="no_worker_could_admit_user",
                    subject=user,
                    numbers={"workers": len(self.living_workers)},
                    candidates=self._placement_decision_rows(),
                )
                raise AssignmentRefused(user, f"{self.name} cannot allocate him")
            self.user_worker_map[user] = worker_handler.name
            self.spa_commander.record_user_group(user, self.name)
            if placement_reason != "fullest_cpu_open_candidate":
                self.spa_commander.log_decision(
                    self.name,
                    "placement",
                    worker_handler.name,
                    reason=placement_reason,
                    subject=user,
                    numbers={"expected_occupancy_percent": self._expected_occupancy(user)},
                    candidates=self._placement_decision_rows(),
                )
            return worker_handler.name

    def _placement_candidate(self, user: str) -> WorkerHandler | None:
        """The fullest CPU-open living worker that admits *user* right now, or None.

        The choice is a CALCULATION of the group (owner, 2026-08-25) — the
        numbers are all here: the photos, the caps, the counts. Each worker's
        own judgment (``WorkerHandler.assign_user``) stays the single gate a
        placement passes, so choosing and admitting cannot drift apart. A
        worker the CPU judge closed (``cpu_admission_open`` False) is not in
        the running: fullest-first is applied AMONG THE OPEN ONLY — walking a
        new user back onto the worker whose crossing just fathered capacity is
        the fixed point the bench measured. With the policy off nobody is ever
        closed, and this is fullest-first over everybody, as it always was.
        """
        occupancy_percent = self._expected_occupancy(user)
        candidates = sorted(
            (
                worker_handler
                for worker_handler in self.living_workers
                if worker_handler.cpu_admission_open
            ),
            key=lambda worker_handler: -self.get_occupancy_percent(worker_handler.worker_snapshot),
        )
        decision_rows = [self._get_worker_decision_row(candidate) for candidate in candidates]
        for worker_handler in candidates:
            try:
                worker_handler.assign_user(user, occupancy_percent)
            except AssignmentRefused as refusal:
                self._logger.debug("Group %s: %s", self.name, refusal)
                next(
                    row for row in decision_rows if row["name"] == worker_handler.name
                )["refusal"] = str(refusal)
                continue
            self.spa_commander.log_decision(
                self.name,
                "placement",
                worker_handler.name,
                reason="fullest_cpu_open_candidate",
                subject=user,
                numbers={"expected_occupancy_percent": occupancy_percent},
                candidates=decision_rows,
            )
            return worker_handler
        self.spa_commander.log_decision(
            self.name,
            "placement_candidates",
            "none",
            reason="no_cpu_open_candidate_admitted_user",
            subject=user,
            numbers={"expected_occupancy_percent": occupancy_percent},
            candidates=decision_rows,
        )
        return None

    def _get_worker_decision_row(self, worker_handler: WorkerHandler) -> dict[str, Any]:
        """The facts a placement or growth judge sees for one worker."""
        photo = worker_handler.worker_snapshot or {}
        return {
            "name": worker_handler.name,
            "state": worker_handler.state,
            "users": sum(
                1 for name in self.user_worker_map.values() if name == worker_handler.name
            ),
            "cpu_admission_open": worker_handler.cpu_admission_open,
            "cpu_growth_armed": worker_handler.cpu_growth_armed,
            "cpu_percent": photo.get("cpu_percent"),
            "occupancy_percent": self.get_occupancy_percent(photo),
            "memory_occupancy_percent": self.get_memory_occupancy_percent(photo),
            "worker_cap": self.get_worker_cap(worker_handler),
        }

    def _placement_decision_rows(self) -> list[dict[str, Any]]:
        """The whole living pool, in the order placement considers it."""
        return [
            self._get_worker_decision_row(worker_handler)
            for worker_handler in sorted(
                self.living_workers,
                key=lambda handler: -self.get_occupancy_percent(handler.worker_snapshot),
            )
        ]

    def _fallback_candidate(self, user: str) -> WorkerHandler | None:
        """The fullest CPU-closed worker that still admits *user* under its hard cap.

        Args:
            user: the newcomer nobody else could take.

        Returns:
            The worker that takes him, or None — the true surrender.

        The last level of the placement, reached only when no open worker
        admits him AND the growth was refused or failed: the soft closure is a
        shaping policy, and shaping must never turn into a 503 the hard
        ``occupancy_max_percent`` — which ``assign_user`` still enforces here —
        would not have given. Every fallback placement is logged as its own
        order: capacity served over the soft limit is a fact the bench must see.
        """
        occupancy_percent = self._expected_occupancy(user)
        candidates = sorted(
            (
                worker_handler
                for worker_handler in self.living_workers
                if not worker_handler.cpu_admission_open
            ),
            key=lambda worker_handler: -self.get_occupancy_percent(worker_handler.worker_snapshot),
        )
        for worker_handler in candidates:
            try:
                worker_handler.assign_user(user, occupancy_percent)
            except AssignmentRefused as refusal:
                self._logger.debug("Group %s: %s", self.name, refusal)
                continue
            self.spa_commander.log_order(
                self.name,
                "placement_fallback",
                worker_handler.name,
                numbers={
                    "cpu_percent": (worker_handler.worker_snapshot or {}).get("cpu_percent"),
                    "workers": len(self.living_workers),
                },
                outcome=f"{user} placed over the soft limit: no open worker, no growth",
                reason="cpu_closed_hard_cap_fallback",
            )
            return worker_handler
        return None

    def _expected_occupancy(self, user: str) -> float:
        """What placing *user* is expected to cost, on the photo's own scale."""
        occupancy_percent = self.spa_commander.user_map[user]["occupancy_percent"]
        return (
            self.new_user_occupancy_percent if occupancy_percent is None else occupancy_percent
        )

    async def freeze_hosted_user(self, user: str) -> bool:
        """Block one of this group's users, have his worker park him, let the block fall.

        Args:
            user: a user this group has placed; one it has not placed is a loud
                ``KeyError``, since nobody but the group orders this.

        Returns:
            True when he is in the deposit; False when the departure did not
            happen, its refusal named in the orchestration log.

        Acts on the vertex's barrier, and through the fold on everything else.
        The hold goes up BEFORE the order and comes down at the other end. On
        the confirmation there is nothing left to write: the ``user_frozen``
        worker event travelled in that same REPLY and the fold reads an envelope
        BEFORE the caller of the order is answered, so the mark, the barrier and
        the placement already say what they must. On anything else the hold is
        what this method gives back — a user must never stay blocked on a
        departure that did not happen — and that includes the CANCELLATION of
        this coroutine, which is why the release is in a ``finally``.

        The order has a deadline, ``DEPARTURE_ORDER_WAIT_LIMIT``: the round that
        sends it is the group's own, and a user with a long call in flight would
        otherwise hold that round — and with it the group's whole beat — for as
        long as the call lasts. The expiry takes the road of a refusal and loses
        nothing: the next round of ``check_user_activity`` judges him again.

        ACCEPTED, and stated as the choice it is: at the expiry only the future
        is dropped, the order stays alive on the worker, and it may park the user
        AFTER the hold has fallen. The window ``hold_user`` closes reopens in
        that one case, and no code here covers it.
        """
        worker_handler = self.worker_handler_map[self.user_worker_map[user]]
        self.spa_commander.hold_user(user, f"freeze on {worker_handler.name}")
        refusal: str | None = "CancelledError"
        try:
            reply = await worker_handler.connector.call(
                FREEZE_USER_OP_PATH, {"user": user}, timeout=DEPARTURE_ORDER_WAIT_LIMIT
            )
            refusal = reply.get("error")
        except Exception as exc:
            refusal = f"{type(exc).__name__}: {exc}"
        finally:
            if refusal is not None:
                self.spa_commander.release_user_hold(user)
                self.spa_commander.log_order(
                    self.name, "freeze_hosted_user", user, outcome=str(refusal)
                )
        return refusal is None

    @property
    def _may_grow(self) -> bool:
        """Whether one more worker is allowed right now — the judge `_grow` obeys too.

        Two memory gates, and the growth passes BOTH. The first is the group's
        quota, read PROSPECTIVELY: what its workers hold today plus the ceiling
        of the one about to be born must still fit the quota — a worker born at
        a quota already full is a worker born to be killed. The second is the
        machine, read on ``memory_available_bytes``: the ceiling must be free
        RIGHT NOW where the process will live. Only the second sees the
        commander, the templates and everything else inside the container, so
        the quota alone would let a fork walk into a cgroup that has no room
        left for it. A machine that measures nothing — no ``/proc/meminfo`` and
        no cgroup — does not refuse: what cannot be read is not judged.
        """
        if self.spa_commander.state != "running":
            return False
        ceiling_percent = self.memory_max_percent * self.worker_memory_max_percent / 100.0
        if self.memory_occupied_percent + ceiling_percent > self.memory_max_percent:
            return False
        available_bytes = self.spa_commander.memory_available_bytes
        return available_bytes is None or available_bytes >= self.worker_memory_ceiling_bytes

    @every(CHECK_OCCUPANCY_BEATS)
    async def check_occupancy(self) -> None:
        """Read the group once and take the ONE step that reading calls for.

        Acts on the group: restart when MEMORY is past the restart setpoint,
        the early CPU growth when a crossing asks for it (#43), growth when
        nobody has room left, closure of a worker the others can absorb — and
        ``state`` when the memory quota refuses the growth. CPU remains part of
        the capacity picture but never condemns a process by itself.
        """
        policy = self.policy
        snapshots = {
            worker_handler.name: worker_handler.worker_snapshot
            for worker_handler in self.living_workers
        }
        memory_picture = {
            name: self.get_memory_occupancy_percent(photo) for name, photo in snapshots.items()
        }
        for name, memory_occupancy_percent in memory_picture.items():
            if memory_occupancy_percent > policy.restart_occupancy_max_percent:
                if self._policy_held(policy, "restart_worker", name):
                    await self.restart_worker(self.worker_handler_map[name])
                return
        picture = {
            name: self.get_occupancy_percent(photo) for name, photo in snapshots.items()
        }
        if await self._grow_on_cpu():
            return
        if not self._has_room(picture):
            await self._grow()
            return
        if self.state == "saturated":
            self.state = "running"
        if policy.cpu_grow_percent is not None:
            # The retirement stands aside while the CPU policy is under
            # pressure (#43): closing the emptiest worker while demand stands
            # hands its users back to the hot one, which regrows seconds later
            # — the close→grow cycle the bench measured. With the policy off
            # this gate does not exist.
            suspension = self.get_retirement_suspension(policy)
            if suspension is not None:
                self._logger.debug(
                    "Group %s: retirement suspended — %s", self.name, suspension
                )
                self.spa_commander.log_decision(
                    self.name,
                    "retirement",
                    "no_action",
                    reason="cpu_pressure_holds_retirement",
                    numbers={"detail": suspension, "workers": len(picture)},
                    candidates=self._placement_decision_rows(),
                )
                return
        spare = self._spare_worker(picture, policy)
        if spare is not None and self._policy_held(policy, "close_worker", spare.name):
            await self._order_quit(spare, "close_worker")
            return
        self.spa_commander.log_decision(
            self.name,
            "retirement",
            "no_action",
            reason="no_absorbable_spare_worker",
            numbers={"workers": len(picture)},
            candidates=self._placement_decision_rows(),
        )

    @every(CHECK_USER_ACTIVITY_BEATS)
    async def check_user_activity(self) -> None:
        """Read the silence off the photos and send whoever is due where he belongs.

        Acts on the users of this group's living workers: whoever has been silent
        past his own expiry is DROPPED — on the worker by the order, and at the
        vertex through the fold that reads the announcement — and whoever is
        silent past ``user_idle_freeze_minutes`` is parked through
        ``freeze_hosted_user``. The silence is read on the REAL clocks, never on
        ``last_refresh_ts``, which a beat alone keeps warm forever.

        BOTH departures block the user at the vertex before the order goes out,
        so one coming back at that instant waits instead of being routed onto a
        worker that is erasing him, and BOTH orders carry
        ``DEPARTURE_ORDER_WAIT_LIMIT``: a child that does not answer would
        otherwise hold this round, and with it the group's whole beat, for as
        long as it stays mute. A drop that CONFIRMS releases nothing here —
        ``SpaCommander.drop_user`` lets go of the hold when the fold reads the
        announcement, and whoever was waiting wakes to find him gone — but a
        drop that did not happen gives the block back on the spot, as the freeze
        does, so no user is ever left blocked on a departure that failed. The
        expiry of the deadline is one such refusal, and it loses nothing: the
        next round judges him again.

        The judgment is this rung's alone: the worker keeps no gauge and takes no
        departure decision of its own. The photo it is read off is as fresh as
        the last envelope out — seconds, against a silence declared in minutes —
        and only a user this group still places on that worker is judged, so a
        photo that has not yet caught up with a departure names nobody.
        """
        policy = self.policy
        now = time.time()
        idle_limit = policy.user_idle_freeze_minutes * SECONDS_PER_MINUTE
        for worker_handler in self.living_workers:
            photo = worker_handler.worker_snapshot or {}
            for user, row in photo.get("users", {}).items():
                item = row["item"]
                if item["state"] != "active":
                    continue
                if self.user_worker_map.get(user) != worker_handler.name:
                    continue
                idle = now - max(item["last_user_ts"], item["last_rpc_ts"])
                if idle > self.spa_commander.get_user_expiry_seconds(user):
                    if not self._policy_held(policy, "drop_user", user):
                        continue
                    self.spa_commander.hold_user(user, f"expiry on {worker_handler.name}")
                    refusal: str | None = "CancelledError"
                    try:
                        await worker_handler.connector.call(
                            DROP_USER_OP_PATH,
                            {"user": user},
                            timeout=DEPARTURE_ORDER_WAIT_LIMIT,
                        )
                        refusal = None
                    except Exception as exc:
                        refusal = f"{type(exc).__name__}: {exc}"
                    finally:
                        if refusal is not None:
                            self.spa_commander.release_user_hold(user)
                        self.spa_commander.log_order(
                            self.name, "drop_user", user, outcome=refusal or "expired"
                        )
                elif idle > idle_limit and self._policy_held(policy, "freeze_hosted_user", user):
                    await self.freeze_hosted_user(user)

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

    async def stop(self) -> None:
        """Take every process of this group down and close their wires.

        Acts on each of its workers: the death is DECLARED before it is dealt —
        the wait an order parks is what tells an ordered death from a wild one,
        and a shutdown is an order — then the process is killed and buried and
        the socket is closed. One that has already died is left alone: there is
        nothing to kill and its wire went with it. The template goes last, when
        there is one: it is nobody's watcher, so nothing depends on the order, but
        the workers it forked are collected by it and it should outlive them.
        """
        for worker_handler in list(self.worker_handler_map.values()):
            if worker_handler.process is not None:
                worker_handler.expect_death()
                await worker_handler.terminate_process()
            await worker_handler.connector.stop()
        if self.template is not None:
            await self.template.stop()

    async def restart_worker(self, worker_handler: WorkerHandler) -> WorkerHandler | None:
        """Ask a worker to leave for good and put a fresh one in its place.

        Args:
            worker_handler: the worker that is not coming back.

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
            KeyError: this group has no worker of that name.

        Acts on ``worker_handler_map`` and ``user_worker_map``; the socket is
        taken away detached, since whoever calls this is the fold and cannot wait.
        The CPU admission and the growth latch live ON the handler, so they die
        with it here — no per-name state survives a dropped worker.
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
        """Whether the standing reserve of newcomers is still whole."""
        return self._placeable_newcomers(picture) >= self.newcomer_reserve_count

    def _placeable_newcomers(self, picture: dict[str, float]) -> int:
        """How many newcomers of the default size this picture still takes.

        Args:
            picture: occupancy percent by worker name.

        Returns:
            The count, summed worker by worker against each one's own cap — a
            newcomer lands on ONE worker, so room split across many is not room.
            A worker in ``quitting`` counts zero: it refuses everybody on its way
            out. One in ``starting`` counts: it is capacity arriving, and
            counting it keeps the group from growing twice.
        """
        placeable = 0
        for name, occupancy_percent in picture.items():
            worker_handler = self.worker_handler_map[name]
            if worker_handler.state == "quitting":
                continue
            room = self.get_worker_cap(worker_handler) - occupancy_percent
            placeable += max(0, int(room / self.new_user_occupancy_percent))
        return placeable

    def _spare_worker(
        self, picture: dict[str, float], policy: GroupPolicy
    ) -> WorkerHandler | None:
        """The emptiest worker whose closure leaves the pool cool; None when there is none.

        The remaining workers are read as if they shared what this one holds,
        then asked THREE questions in order: every survivor under
        ``close_occupancy_max_percent`` — distinctly below the growth setpoint,
        so a closure can never create the condition for the next growth (#36) —
        the newcomer reserve still whole, and, the occupancy settled, room BY
        HEADS for the spare's placed users within each survivor's
        ``worker_max_users``. A worker younger than ``worker_min_life_seconds``
        is no candidate: its occupancy measures its own birth.
        """
        # A quitting worker is nobody's spare — its closure is already
        # somebody's order — and nobody's absorber: its room counts for nobody.
        candidates = [
            worker_handler
            for worker_handler in self.living_workers
            if worker_handler is not self.reception
            and worker_handler.state != "quitting"
            and worker_handler.life_seconds >= policy.worker_min_life_seconds
        ]
        if not candidates:
            return None
        spare = min(candidates, key=lambda worker_handler: picture[worker_handler.name])
        remaining = {
            name: pct
            for name, pct in picture.items()
            if name != spare.name and self.worker_handler_map[name].state != "quitting"
        }
        if not remaining:
            return None
        shared = picture[spare.name] / len(remaining)
        after = {name: pct + shared for name, pct in remaining.items()}
        if max(after.values()) > policy.close_occupancy_max_percent:
            return None
        if self._placeable_newcomers(after) < policy.newcomer_reserve_count:
            return None
        placed = Counter(self.user_worker_map.values())
        head_room = sum(max(0, policy.worker_max_users - placed[name]) for name in remaining)
        if head_room < placed[spare.name]:
            return None
        return spare

    async def _grow_on_cpu(self) -> bool:
        """The early-provision judge (#43, experimental): one CPU crossing, one worker.

        Returns:
            True when a worker was brought into being — the round's ONE step.

        Off unless ``cpu_grow_percent`` is set. Reads the smoothed
        ``cpu_percent`` off each photo — never the composite occupancy: its
        memory component must not father CPU workers, and the memory
        protections keep their own judges. The same reading drives the SOFT
        ADMISSION: a worker above the threshold is closed to new users
        (``cpu_admission_open``), one below the rearm threshold is reopened,
        and between the two it keeps its state — so the pass that decides the
        growth is the one pass that writes who the placement may still choose.
        Each worker carries a latch besides: an armed worker above the
        threshold fires, and is loaded again only below
        ``cpu_grow_rearm_percent`` — a worker sitting above the threshold asks
        ONCE, not once per photo, and stays closed while it sits there. A
        crossing the group cannot honour stays armed and is judged again next
        round, its suppression logged with its reason.

        The spawn runs under the placement lock, so the snapshot road and the
        placement road cannot fork twice for one event; a worker that appeared
        while waiting for the lock IS the answer, and the latch stays armed.
        The newborn needs no preference: born open while its father is closed,
        it is what fullest-first finds — and when it crosses the threshold
        itself, its own latch fathers the next one. The latch is consumed only
        by the growth that actually happened.
        """
        policy = self.policy
        if policy.cpu_grow_percent is None:
            self.spa_commander.log_decision(
                self.name,
                "cpu_growth",
                "no_action",
                reason="cpu_policy_disabled",
                candidates=self._placement_decision_rows(),
            )
            return False
        worker_count = len(self.worker_handler_map)
        trigger: tuple[WorkerHandler, float] | None = None
        for worker_handler in self.living_workers:
            cpu_percent = (worker_handler.worker_snapshot or {}).get("cpu_percent")
            if cpu_percent is None:
                continue
            if cpu_percent > policy.cpu_grow_percent:
                if worker_handler.cpu_admission_open:
                    worker_handler.cpu_admission_open = False
                    self.record_cpu_pressure()
                    self.spa_commander.log_order(
                        self.name,
                        "cpu_admission",
                        worker_handler.name,
                        numbers={"cpu_percent": cpu_percent},
                        outcome="blocked: over the growth threshold",
                        reason="cpu_over_growth_threshold",
                    )
                if worker_handler.cpu_growth_armed and trigger is None:
                    trigger = (worker_handler, cpu_percent)
            elif cpu_percent < policy.cpu_grow_rearm_percent:
                if not worker_handler.cpu_admission_open:
                    worker_handler.cpu_admission_open = True
                    self.record_cpu_pressure()
                    self.spa_commander.log_order(
                        self.name,
                        "cpu_admission",
                        worker_handler.name,
                        numbers={"cpu_percent": cpu_percent},
                        outcome="reopened: below the rearm threshold",
                        reason="cpu_below_rearm_threshold",
                    )
                worker_handler.cpu_growth_armed = True
        decision_rows = self._placement_decision_rows()
        decision_numbers = {
            "workers": len(decision_rows),
            "open_workers": sum(
                1 for row in decision_rows if row["cpu_admission_open"]
            ),
            "empty_workers": sum(1 for row in decision_rows if row["users"] == 0),
        }
        if trigger is None:
            self.spa_commander.log_decision(
                self.name,
                "cpu_growth",
                "no_action",
                reason="no_armed_worker_over_cpu_threshold",
                numbers=decision_numbers,
                candidates=decision_rows,
            )
            return False
        worker_handler, cpu_percent = trigger
        numbers = {
            "cpu_percent": cpu_percent,
            "cpu_grow_percent": policy.cpu_grow_percent,
            "worker_cpu": {
                name: (handler.worker_snapshot or {}).get("cpu_percent")
                for name, handler in self.worker_handler_map.items()
            },
            "workers": len(self.living_workers),
            "open_workers": decision_numbers["open_workers"],
            "empty_workers": decision_numbers["empty_workers"],
        }
        refusal = self._cpu_grow_refusal(worker_handler)
        if refusal is not None:
            if refusal == CPU_GROW_QUOTA_REFUSAL:
                self.record_cpu_pressure()
            self.spa_commander.log_order(
                self.name,
                "cpu_grow",
                worker_handler.name,
                numbers=numbers,
                outcome=refusal,
                reason=self._get_cpu_growth_reason(refusal),
            )
            self.spa_commander.log_decision(
                self.name,
                "cpu_growth",
                "suppressed",
                reason=self._get_cpu_growth_reason(refusal),
                subject=worker_handler.name,
                numbers=numbers,
                candidates=decision_rows,
            )
            return False
        async with self._placement_lock:
            # The wait may have changed everything the decision stood on:
            # the same questions again, on what is there NOW.
            refusal = self._cpu_grow_refusal(worker_handler)
            if refusal is None and len(self.worker_handler_map) != worker_count:
                refusal = CPU_GROW_CAPACITY_ARRIVED_REFUSAL
            if refusal is not None:
                if refusal == CPU_GROW_QUOTA_REFUSAL:
                    self.record_cpu_pressure()
                self.spa_commander.log_order(
                    self.name,
                    "cpu_grow",
                    worker_handler.name,
                    numbers=numbers,
                    outcome=refusal,
                    reason=self._get_cpu_growth_reason(refusal),
                )
                self.spa_commander.log_decision(
                    self.name,
                    "cpu_growth",
                    "suppressed",
                    reason=self._get_cpu_growth_reason(refusal),
                    subject=worker_handler.name,
                    numbers=numbers,
                    candidates=decision_rows,
                )
                return False
            if not self._policy_held(policy, "cpu_grow", worker_handler.name):
                return False
            spawn_started = time.monotonic()
            newborn = await self.start_worker()
            if newborn is None:
                return False
            worker_handler.cpu_growth_armed = False
            self.record_cpu_pressure()
            numbers["spawn_seconds"] = round(time.monotonic() - spawn_started, 3)
            self.spa_commander.log_order(
                self.name,
                "cpu_grow",
                worker_handler.name,
                numbers=numbers,
                outcome=f"grown {newborn.name}",
                reason="armed_worker_over_cpu_threshold",
            )
            self.spa_commander.log_decision(
                self.name,
                "cpu_growth",
                newborn.name,
                reason="armed_worker_over_cpu_threshold",
                subject=worker_handler.name,
                numbers=numbers,
                candidates=decision_rows,
            )
        return True

    def _get_cpu_growth_reason(self, refusal: str) -> str:
        """The stable reason code for a CPU-growth refusal."""
        if refusal == CPU_GROW_QUOTA_REFUSAL:
            return "memory_or_server_refused_growth"
        if refusal == CPU_GROW_TRIGGER_GONE_REFUSAL:
            return "trigger_worker_gone"
        if refusal == CPU_GROW_CAPACITY_ARRIVED_REFUSAL:
            return "capacity_arrived_while_waiting"
        return "cpu_growth_refused"

    def record_cpu_pressure(self) -> None:
        """Stamp NOW as the instant the CPU last spoke — the retirement's quiet restarts.

        Called on every CPU event: a worker blocked over the growth threshold, a
        growth that landed, a growth the quota or the server state refused, a
        worker reopened below the rearm threshold — and an apply that actually
        moves a worker's admission, which is the same fact said by a
        reconfiguration instead of a photo.

        The reopen counts ON PURPOSE: a worker that was closed for minutes and
        reopens must not meet the retirement at the very next beat — the bench
        measured exactly that close, and the regrowth it caused 5 seconds later
        (churn of 2026-08-28, rearm30).
        """
        self._cpu_pressure_monotonic = time.monotonic()

    def get_retirement_suspension(self, policy: GroupPolicy) -> str | None:
        """Why the retirement stands aside right now; None when it may judge.

        Args:
            policy: the setpoints THIS round decided on, so the answer belongs
                to the same picture as everything else the round did.

        Returns:
            The reason, ready for the log, or None when the closure judge may
            run.

        Two reasons, in the order they are asked. The policy off is no reason at
        all: with no ``cpu_grow_percent`` this is never consulted and the
        retirement is exactly what it always was. A living worker still
        CPU-closed is standing demand — its load has nowhere to consolidate
        INTO. And a CPU event younger than ``cpu_retirement_quiet_seconds``
        means the pressure only just ended: the quiet must be CONTINUOUS, so
        every event — the reopen included — restarts the whole period. Born
        None, the clock imposes no cooldown at boot: before any CPU event only
        the first answer exists.
        """
        if any(
            not worker_handler.cpu_admission_open for worker_handler in self.living_workers
        ):
            return "a worker is still CPU-closed"
        last_pressure = self._cpu_pressure_monotonic
        if last_pressure is None:
            return None
        elapsed = time.monotonic() - last_pressure
        if elapsed < policy.cpu_retirement_quiet_seconds:
            return (
                f"the CPU spoke {elapsed:.1f}s ago, the quiet lasts "
                f"{policy.cpu_retirement_quiet_seconds:.1f}s"
            )
        return None

    def _cpu_grow_refusal(self, worker_handler: WorkerHandler) -> str | None:
        """Why a CPU growth may not happen right now; None when it may.

        Args:
            worker_handler: the worker whose crossing asks for the growth.

        Returns:
            The suppression reason, ready for the log, or None. NOTHING here
            consumes the latch: a suppressed crossing is judged again at the
            next round.

        Asked twice per growth — before waiting for the placement lock, and
        again after acquiring it, because the wait may have changed every fact
        the decision stood on.
        """
        if not self._may_grow:
            return CPU_GROW_QUOTA_REFUSAL
        if (
            self.worker_handler_map.get(worker_handler.name) is not worker_handler
            or worker_handler.state != "running"
        ):
            return CPU_GROW_TRIGGER_GONE_REFUSAL
        if not worker_handler.cpu_growth_armed:
            return CPU_GROW_CAPACITY_ARRIVED_REFUSAL
        return None

    async def _grow(self) -> None:
        """Bring a worker into being if both memory gates afford it; the saturation when not.

        Under the placement lock, like every other road to a birth: the caller
        decided on a picture that is stale by the time the lock is held, so the
        room is read AGAIN on what is there now — a worker the placement
        fathered in the meantime IS the capacity that was missing, and growing
        on the old picture would fork twice for one need.
        """
        policy = self.policy
        async with self._placement_lock:
            picture = {
                worker_handler.name: self.get_occupancy_percent(worker_handler.worker_snapshot)
                for worker_handler in self.living_workers
            }
            if self._has_room(picture):
                self.spa_commander.log_order(
                    self.name,
                    "grow",
                    numbers={"workers": len(picture)},
                    outcome="suppressed: another road already created the capacity",
                )
                return
            occupied_percent = self.memory_occupied_percent
            if self._may_grow:
                if self._policy_held(policy, "grow"):
                    await self.start_worker()
                return
            if not self._policy_held(policy, "grow"):
                return
            self.state = "saturated"
            self.spa_commander.log_order(
                self.name,
                "grow",
                numbers={
                    "memory_occupied_percent": occupied_percent,
                    "memory_max_percent": policy.memory_max_percent,
                    "worker_memory_ceiling_bytes": self.worker_memory_ceiling_bytes,
                    "memory_available_bytes": self.spa_commander.memory_available_bytes,
                    "workers": len(picture),
                },
                outcome="saturated",
            )

    async def quit_all(self, freezer_path: str) -> None:
        """Block the users of every process of this group, then tell each one to leave.

        Args:
            freezer_path: the directory this group's parcels are written to —
                the reboot directory, never the working deposit.

        Acts on the vertex's barrier and on each of its workers. Every user this
        group places on a worker is BLOCKED before that worker is ordered away:
        from that instant a request of his waits instead of walking into a
        process that is emptying. The order stays ONE per worker — no per-user
        order travels the wire here, the worker's own cycle parks everybody as it
        has since wf/33 — and the holds fall as the freezes confirm, each through
        the fold that reads ``user_frozen``, the death of the process saying it
        for whoever's own announcement did not survive the closing wire. A worker
        already dead is ordered nothing and blocks nobody: its death is written,
        and the round that read it has already marked or purged whoever it held.
        The template goes last: it is nobody's watcher, but it outlives the
        workers it forked.
        """
        for worker_handler in list(self.worker_handler_map.values()):
            if worker_handler.state in DEAD_STATES:
                continue
            for user, name in list(self.user_worker_map.items()):
                if name == worker_handler.name:
                    self.spa_commander.hold_user(user, f"quit of {worker_handler.name}")
            await self._order_quit(worker_handler, "quit_all", freezer_path=freezer_path)
        if self.template is not None:
            await self.template.stop()

    async def _order_quit(
        self, worker_handler: WorkerHandler, order: str, freezer_path: str | None = None
    ) -> None:
        """Ask a worker's process to leave, having made sure a photo of it exists.

        The departure of everybody on board is settled on the LAST photo — who
        was flagged for the freezer — so a worker that has never answered
        anything is photographed first: without that, an ordered quit would purge
        its users as if nobody had promised them the freezer. A worker whose
        death got there first — before the order, or under that very beat — is
        ordered nothing: the death is already written, and the round buries it.
        """
        if worker_handler.state in DEAD_STATES:
            return
        if worker_handler.worker_snapshot is None:
            await worker_handler.ping_process()
        if worker_handler.state in DEAD_STATES:
            return
        self.spa_commander.log_order(
            self.name,
            order,
            worker_handler.name,
            numbers={
                "occupancy_percent": self.get_occupancy_percent(worker_handler.worker_snapshot),
                "memory_occupancy_percent": self.get_memory_occupancy_percent(
                    worker_handler.worker_snapshot
                ),
                "cpu_percent": (worker_handler.worker_snapshot or {}).get("cpu_percent"),
                "workers": len(self.living_workers),
            },
        )
        await worker_handler.quit_process(freezer_path)
