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

"""The UserSticky commander: the pool of workers and the routing picture above it.

The commander is the other half of the UserSticky pair — a derivable base, not
an application (the mountable front arrives with ``SpaApplication`` in 2b). It
owns the :class:`~genro_asgi.channel.hub.ChannelHub` its workers connect to,
spawns and supervises them, and keeps the surface picture of where everything
sits.

**The surface registries are plain dicts, deliberately not the Register
machine of the worker** (the validated lesson: keys and locations up here,
contents down there). There are exactly two:

- ``worker_roster`` — worker name → the ROW that holds everything that is that
  worker's:
  ``{status, pid, group, spawned_at, process, users, occupancy, caretaker}``.
  ``status`` walks ``nascent`` (spawned, not yet presented) →
  ``active`` (REGISTER seen) → ``draining`` (deliberately retired) → ``dead``;
  ``users`` maps each held user to ``{pending, last_activity_ts, occupancy}``
  (``pending`` is that user's live calls, ``occupancy`` a field the future
  evaluator fills — 2a never computes it); ``occupancy`` is the window of the
  last ``METRICS_WINDOW`` raw reports the probe collected (the commander
  archives, judging belongs to the evaluator); ``caretaker`` is that worker's
  own probe task, ``None`` when it has none. A user's routing group is its
  worker's ``group``, read from the row.
- ``user_worker_map`` — user identity → the name of the worker holding it, or
  ``None`` while a placement for that user is in flight. It is the ONLY
  user-keyed structure, and both it and the rows mutate through the single pair
  ``assign_user`` / ``remove_user``.

**Supervision is the legacy ProcessPool's, over the channel.** A worker is
``sys.executable -m genro_asgi.spa.worker_entry`` with its whole configuration
in the ``GENRO_ASGI_WORKER`` env payload, started in its own session so the
whole process group can be signalled. Readiness is the REGISTER frame, death is
the channel EOF: a worker that is gone is ALWAYS swept — deliberately retired
or crashed, it holds nothing any more — and a crashed one is additionally
relaunched under a **fresh name**, a name never being reused, so no late frame
can be mistaken for the newcomer's. A reconcile task is the safety net for the
one death EOF cannot see, the child that dies before ever connecting; it logs
the exit code and respawns at the next tick, with no backoff of its own.

**Liveness is a pull, and it doubles as the occupancy reading.** Every spawned
worker has its OWN caretaker task, born with its REGISTER and cancelled with
its death: an ``/op/occupancy`` CALL every ``probe_interval``, bounded by
``probe_timeout`` — the only CALL of the system that may expire, because it
carries nothing to lose and the silence IS the information. The worker answers
from its own loop, so one exchange proves the loop is alive and hands over the
counters. An expiry is a SIGKILL to the process group: the EOF that follows
enters the ordinary sweep-and-relaunch path. A probe that raises is logged and
the cadence goes on: the blast radius of a failure is the one worker.

**One fold, one drain.** ``fold_events(worker, events)`` applies the events a
REPLY carried, in the order they were delivered — they are the lifecycle the
answered CALL itself caused, so there is nothing to deduplicate and no
watermark to keep. The drain runs in the commander, never in the transport:
``unwrap_reply`` folds the ``events`` of the payload before reading its
``result``/``error``. The owner check is the only guard, and it is the legacy
rule: a late event never re-points a user already assigned elsewhere; only the
explicit ``assign_user`` decision does that.

**The front face is ``forward_call(identity, path, kwargs)``.** ``identity`` is the
sticky key the caller provides — the root avatar identity once logged, the
session id while anonymous; the commander never reads a cookie (that is
``SpaApplication``'s job in 2b). It resolves ``user_worker_map`` and, on a miss,
sends the caller to the **reception**: the first active worker of the pool, the
guests' worker. ``guest_occupancy_limit`` is how many users the reception may
hold before ``check_capacity`` widens the pool.

**Placement happens at login, and the login waits for it.** The worker pushes:
its ``change_connection_user`` event carries the user's whole slice as a
``package`` and the source has already forgotten it. Folding that event writes
``None`` under the new key — the flag "this user's placement is in flight" —
and the caller's own coroutine then runs ``place_login``: ``decide_worker``
picks the least-loaded active worker, ``install_package`` plants the slice
there, the map is pointed at it, the flag falls and only THEN is the login
result released. The room is ready before the guest is told its number. A
``forward_call`` that finds the flag up parks on ``placement_done`` — the parked
coroutines are the queue, there is no structure — and re-reads the map on every
wakeup, so a flag re-raised by a chained login simply parks it again. No clock
bounds any of it: the install CALL waits, and the only terminator is the
destination's death, which fails that CALL. An install that fails unmaps the
user: the source spent its copy, so the user exists nowhere and the surface
says so. Every login has a caller
coroutine holding it — a login is caused by a CALL and comes back on that
CALL's REPLY — so ``place_login`` is never detached.

**The single role is configuration, not a subclass.** ``local_worker=True``
(with ``workers=0``) makes the commander build ONE worker in this very process
and attach it to its own hub through a :class:`~genro_asgi.channel.local.LocalChannel`:
same REGISTER, same fresh name, same encode/decode on every frame, same fold —
only the wire is a pair of queues instead of a socket. That worker is the
reception (it is the first active one) and it is also every login's
destination: the user is evicted and reinstalled onto the very worker it came
from, because there is ONE road and no shortcut around it. Design §3.5a: if the
protocol works in the single role, going multi changes nothing but the wire.

Every ``forward_call`` writes itself under the user's ``pending`` in the row and
clears it when it returns; nothing reads that data in 2a — the
commander-initiated move does, when it arrives.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import signal
import subprocess
import sys
import time
import uuid
from collections import deque
from typing import Any

from ..channel.frame import Frame
from ..channel.hub import ChannelCallError, ChannelHub, ChannelMember
from ..channel.local import LocalChannel
from .worker import LIFECYCLE_OPS, OP_PATH_PREFIX, UserStickyWorker

__all__ = [
    "DEFAULT_GROUP",
    "GUEST_OCCUPANCY_LIMIT",
    "METRICS_WINDOW",
    "PROBE_INTERVAL",
    "PROBE_TIMEOUT",
    "UserStickyCommander",
]

#: The single routing group of 2a: the group column exists everywhere, the
#: groups feature does not. PROVISIONAL — it becomes per-group configuration.
DEFAULT_GROUP = "default"

#: How many raw occupancy reports are kept per worker (~5 minutes at one probe
#: every 5s). PROVISIONAL, transcribed from the legacy commander.
METRICS_WINDOW = 60

#: Seconds between two probes of the same worker. PROVISIONAL — it becomes
#: per-group configuration.
PROBE_INTERVAL = 5.0

#: How long a worker may take to answer its occupancy probe before it is
#: declared gone. The probe is the one CALL that may expire: it carries nothing
#: to lose, and the silence IS the information. PROVISIONAL, as above.
PROBE_TIMEOUT = 10.0

#: The routing key of the occupancy probe.
OCCUPANCY_OP_PATH = f"{OP_PATH_PREFIX}occupancy"

#: How many users the reception may hold before the pool is widened. The 2a
#: reading of occupancy is the head count: no evaluator exists yet, and every
#: guest sits on the reception. PROVISIONAL — it becomes per-group configuration.
GUEST_OCCUPANCY_LIMIT = 50

#: The lifecycle op that is a login: the sticky key changes and a placement is due.
LOGIN_OP = "change_connection_user"

#: The spawn entry point of a worker child.
WORKER_ENTRY_MODULE = "genro_asgi.spa.worker_entry"


class UserStickyCommander:
    """Pool owner and routing surface: spawn, supervise, fold.

    ``workers`` is the initial target size; ``scale()`` moves it afterwards and
    the reconcile task heals the gap. Give ``path``/``host`` to place the hub's
    socket, or neither to let it own a private one.
    """

    RECONCILE_INTERVAL = 0.5
    READY_TIMEOUT = 30.0
    STOP_TIMEOUT = 5.0

    def __init__(
        self,
        *,
        workers: int = 1,
        path: str | None = None,
        host: str | None = None,
        port: int = 0,
        group: str = DEFAULT_GROUP,
        worker_class: str | None = None,
        worker_kwargs: dict[str, Any] | None = None,
        executable: str | None = None,
        max_workers: int | None = None,
        guest_occupancy_limit: int = GUEST_OCCUPANCY_LIMIT,
        probe_interval: float = PROBE_INTERVAL,
        probe_timeout: float = PROBE_TIMEOUT,
        local_worker: bool = False,
    ) -> None:
        """Args:
        workers: how many children to keep alive.
        path: UDS socket path for the hub (mutually exclusive with ``host``).
        host: TCP host for the hub; ``port=0`` lets the OS choose.
        port: TCP port, with ``host``.
        group: the routing group every worker of this commander belongs to.
        worker_class: dotted ``module:Class`` reference passed to the children.
        worker_kwargs: extra constructor kwargs passed to the worker class.
        executable: the interpreter to spawn with (defaults to this one).
        max_workers: ceiling the capacity check never scales past (None = unbounded).
        guest_occupancy_limit: users on the reception above which the pool widens.
        probe_interval: seconds between two probes of the same worker.
        probe_timeout: how long a worker may take to answer its probe.
        local_worker: hold one worker in this process (the single role, §3.5a);
            pair it with ``workers=0`` to spawn no child at all.
        """
        self.target = workers
        self.group = group
        self.worker_class = worker_class
        self.worker_kwargs = dict(worker_kwargs or {})
        self.executable = executable or sys.executable
        self.max_workers = max_workers
        self.guest_occupancy_limit = guest_occupancy_limit
        self.probe_interval = probe_interval
        self.probe_timeout = probe_timeout
        self.local_worker = local_worker
        # The in-process worker of the single role and the wire it sits on;
        # both stay None in the multi role.
        self.worker: UserStickyWorker | None = None
        self.local_channel: LocalChannel | None = None
        self.logger = logging.getLogger(__name__)
        self.hub = ChannelHub(
            path=path,
            host=host,
            port=port,
            on_member_joined=self.member_joined,
            on_channel_lost=self.channel_lost,
            on_event=self.handle_event,
        )
        # The whole surface: one row per worker, one entry per user. ``None`` in
        # the map is the flag "this user's placement is in flight".
        self.worker_roster: dict[str, dict[str, Any]] = {}
        self.user_worker_map: dict[str, str | None] = {}
        # Fired-and-rearmed at the end of every placement: the coroutines parked
        # on it while a flag is up ARE the queue of waiters.
        self.placement_done = asyncio.Event()
        self._reconcile_task: asyncio.Task[None] | None = None
        self._wakeup = asyncio.Event()

    @property
    def address(self) -> str:
        """The address the children connect to."""
        return self.hub.address

    @property
    def active_workers(self) -> list[str]:
        """The names of the workers currently connected, in spawn order."""
        return [
            name for name, entry in self.worker_roster.items() if entry["status"] == "active"
        ]

    @property
    def living_workers(self) -> list[str]:
        """The names of the workers that count toward the target (nascent + active)."""
        return [
            name
            for name, entry in self.worker_roster.items()
            if entry["status"] in ("nascent", "active")
        ]

    @property
    def reception(self) -> str | None:
        """The guests' worker: the FIRST active one, in spawn order.

        Positional, like the legacy reception: no flag and no election, so a
        reception that dies is silently succeeded by the next worker.
        """
        active = self.active_workers
        return active[0] if active else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Bind the hub, attach the local worker if any, start supervision.

        The in-process worker joins BEFORE the first reconcile, so it is the
        first member of the roster and therefore the reception. The caretakers
        are not started here: each is born with its own worker's REGISTER.
        """
        await self.hub.start()
        if self.local_worker:
            await self.attach_local_worker()
        self._reconcile_task = asyncio.create_task(self.reconcile_loop())
        self._wakeup.set()

    async def stop(self) -> None:
        """Deliberate shutdown: retire every worker, close the hub, clean up.

        The caretaker sweep runs LAST, once the hub is stopped. ``channel_lost``
        still fires during the retire and cancels those caretakers itself; what
        no channel loss ever cancels — a nascent child, the local worker, a
        late REGISTER landing mid-stop — is exactly what the final sweep ends,
        and with the hub closed no ``member_joined`` can birth another.
        """
        if self._reconcile_task is not None:
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass
        self._reconcile_task = None
        self.target = 0
        retired = list(self.living_workers)
        for name in retired:
            self.retire_worker(name)
        if self.worker is not None:
            await self.worker.shutdown()
            self.worker = None
            self.local_channel = None
        await self.wait_workers_end(retired)
        await self.hub.stop()
        for name in list(self.worker_roster):
            self.cancel_caretaker(name)

    async def wait_workers_ready(self, count: int | None = None, timeout: float | None = None) -> None:
        """Block until ``count`` workers have presented themselves (readiness gate)."""
        expected = self.target if count is None else count
        limit = self.READY_TIMEOUT if timeout is None else timeout
        loop = asyncio.get_running_loop()
        deadline = loop.time() + limit
        while len(self.active_workers) < expected:
            if loop.time() >= deadline:
                raise TimeoutError(
                    f"{len(self.active_workers)}/{expected} workers ready within {limit}s"
                )
            await asyncio.sleep(0.02)

    def scale(self, count: int) -> None:
        """Move the target to ``count``; reconcile spawns or retires the difference."""
        self.target = count
        surplus = len(self.living_workers) - count
        if surplus > 0:
            for name in self.living_workers[-surplus:]:
                self.retire_worker(name)
        self._wakeup.set()

    def retire(self, name: str) -> None:
        """Retire one named worker and lower the target so reconcile keeps it out."""
        if name not in self.worker_roster:
            raise KeyError(f"no such worker to retire: {name!r}")
        self.target = max(0, self.target - 1)
        self.retire_worker(name)

    # ------------------------------------------------------------------
    # Supervision — the legacy ProcessPool over the channel
    # ------------------------------------------------------------------

    async def reconcile_loop(self) -> None:
        """Keep the living workers == target; woken early by deaths and scale."""
        while True:
            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=self.RECONCILE_INTERVAL)
            except TimeoutError:
                pass
            self._wakeup.clear()
            self.reconcile()

    def reconcile(self) -> None:
        """Cull the children that will never present themselves, spawn the shortfall."""
        now = time.monotonic()
        for name, entry in list(self.worker_roster.items()):
            if entry["status"] != "nascent":
                continue
            process = entry["process"]
            if process is not None and process.poll() is not None:
                self.logger.warning(
                    "Worker %s died before registering (exit code %s)", name, process.poll()
                )
                entry["status"] = "dead"
            elif now - entry["spawned_at"] > self.READY_TIMEOUT:
                self.logger.warning("Worker %s never registered: retiring", name)
                self.retire_worker(name)
        for _ in range(max(0, self.target - len(self.living_workers))):
            self.spawn_worker()

    async def caretaker(self, name: str) -> None:
        """Probe ONE worker on its own cadence, forever — the legacy per-child beat.

        The probe is the commander's liveness reading: it is the one CALL with a
        deadline, because it carries nothing to lose and the silence itself is
        the answer. A worker that does not report in ``probe_timeout`` is killed
        outright — the EOF that follows is the death the sweep already knows how
        to handle. A probe that raises is logged and the cadence goes on: one
        caretaker never takes down another worker's.
        """
        while True:
            await asyncio.sleep(self.probe_interval)
            try:
                await self.probe_worker(name)
            except Exception:
                self.logger.exception("Caretaker of worker %s: probe failed", name)

    def cancel_caretaker(self, name: str) -> None:
        """End the caretaker of one worker; a row without one is left alone."""
        task = self.worker_roster[name]["caretaker"]
        if task is not None:
            task.cancel()
            self.worker_roster[name]["caretaker"] = None

    async def probe_worker(self, name: str) -> None:
        """Ask one worker for its occupancy and archive what comes back."""
        try:
            payload = await self.hub.call(
                name,
                OCCUPANCY_OP_PATH,
                {"identity": None, "kwargs": {}},
                timeout=self.probe_timeout,
            )
            report = await self.unwrap_reply(name, OCCUPANCY_OP_PATH, payload)
        except TimeoutError:
            self.logger.warning("Worker %s did not answer the probe: killing", name)
            self.signal_worker(name, signal.SIGKILL)
        except (ConnectionError, ChannelCallError, LookupError) as exc:
            self.logger.debug("Probe of %s skipped (%s: %s)", name, type(exc).__name__, exc)
        else:
            self.record_occupancy(name, report)

    def next_worker_name(self) -> str:
        """Mint a fresh typed channel name; collision is impossible by construction."""
        return f"W:{uuid.uuid4().hex}"

    def new_roster_row(self, pid: int, process: subprocess.Popen[bytes] | None) -> dict[str, Any]:
        """One roster row: everything that is this worker's, in a single place.

        The row is born ``nascent`` and empty — the users arrive with the fold,
        the occupancy window with the reports, the caretaker with the REGISTER.
        It is never dropped: the roster is the record of who existed.
        """
        return {
            "status": "nascent",
            "pid": pid,
            "group": self.group,
            "spawned_at": time.monotonic(),
            "process": process,
            "users": {},
            "occupancy": deque(maxlen=METRICS_WINDOW),
            "caretaker": None,
        }

    def new_user_row(self) -> dict[str, Any]:
        """One user's half of a roster row: its live calls and its activity.

        ``occupancy`` is the per-user reading the future evaluator fills; 2a
        writes the field and never computes it.
        """
        return {"pending": {}, "last_activity_ts": time.time(), "occupancy": None}

    def spawn_payload(self, name: str) -> dict[str, Any]:
        """The ``GENRO_ASGI_WORKER`` object of one child."""
        payload: dict[str, Any] = {"name": name, "address": self.address}
        if self.worker_class is not None:
            payload["worker_class"] = self.worker_class
        if self.worker_kwargs:
            payload["kwargs"] = self.worker_kwargs
        return payload

    def spawn_worker(self) -> str:
        """Start one child process; it will present itself on the channel."""
        name = self.next_worker_name()
        env = dict(os.environ)
        env["GENRO_ASGI_WORKER"] = json.dumps(self.spawn_payload(name))
        process = subprocess.Popen(
            [self.executable, "-m", WORKER_ENTRY_MODULE], env=env, start_new_session=True
        )
        self.worker_roster[name] = self.new_roster_row(process.pid, process)
        self.logger.info("Spawned worker %s (pid %s)", name, process.pid)
        return name

    def load_worker_class(self) -> type[UserStickyWorker]:
        """The worker class of this pool — the very one a spawned child loads."""
        if self.worker_class is None:
            return UserStickyWorker
        module_path, _, class_name = self.worker_class.partition(":")
        return getattr(importlib.import_module(module_path), class_name)

    async def attach_local_worker(self) -> str:
        """Build the in-process worker and present it on the hub — the single role.

        A spawned child's wiring with the fork taken out: a roster entry with
        ``process=None`` where the OS handle would be, a REGISTER over the
        ``LocalChannel`` and the same receive loop on the hub side. Every frame
        still crosses encode/decode, so this is the whole protocol, not a
        shortcut around it.
        """
        name = self.next_worker_name()
        self.worker_roster[name] = self.new_roster_row(os.getpid(), None)
        self.worker = self.load_worker_class()(name, **self.worker_kwargs)
        self.local_channel = LocalChannel(name)
        self.worker.attach_channel(self.local_channel)
        await self.local_channel.connect()
        await self.hub.attach_local(self.local_channel)
        await self.worker.start()
        self.logger.info("Local worker %s attached in-process", name)
        return name

    def retire_worker(self, name: str) -> None:
        """Deliberately drain one worker: no death signal, no relaunch."""
        entry = self.worker_roster[name]
        entry["status"] = "draining"
        self.signal_worker(name, signal.SIGTERM)

    def signal_worker(self, name: str, sig: int) -> None:
        """Signal the worker's whole process group (idempotent, reaps descendants)."""
        process = self.worker_roster[name]["process"]
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except ProcessLookupError:
            pass

    async def wait_workers_end(self, names: list[str]) -> None:
        """Async-poll the retired children, escalating to SIGKILL at the timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.STOP_TIMEOUT
        while any(self.worker_alive(name) for name in names):
            if loop.time() >= deadline:
                for name in names:
                    if self.worker_alive(name):
                        self.signal_worker(name, signal.SIGKILL)
                break
            await asyncio.sleep(0.05)

    def worker_alive(self, name: str) -> bool:
        """Whether the worker's process is still running."""
        process = self.worker_roster[name]["process"]
        return process is not None and process.poll() is None

    # ------------------------------------------------------------------
    # Channel callbacks
    # ------------------------------------------------------------------

    def member_joined(self, member: ChannelMember) -> None:
        """REGISTER seen: the worker is ready to be routed to, and to be watched.

        Its caretaker is born here — only for a row with a real process: an
        in-process worker cannot outlive the commander that probes it.
        """
        entry = self.worker_roster.get(member.name)
        if entry is None:
            self.logger.warning("Foreign member on the commander hub: %s", member.name)
            return
        entry["status"] = "active"
        entry["pid"] = member.pid
        if entry["process"] is not None:
            entry["caretaker"] = asyncio.create_task(self.caretaker(member.name))
        self.logger.info("Worker %s active (pid %s)", member.name, member.pid)

    async def channel_lost(self, member: ChannelMember) -> None:
        """The channel EOF ends a worker: its users are swept either way.

        Deliberate or not, a worker that is gone holds nothing any more: the
        users on its row exist nowhere and the surface must say so. What the
        crash alone adds is the escalation (a member that lost the channel but
        still breathes is killed) and the relaunch wakeup — a retired worker is
        not replaced. Either way the caretaker ends with the worker it watched.
        """
        entry = self.worker_roster.get(member.name)
        if entry is None:
            return
        deliberate = entry["status"] == "draining"
        entry["status"] = "dead"
        self.cancel_caretaker(member.name)
        if deliberate:
            swept = self.sweep_worker(member.name)
            self.logger.info("Worker %s retired: swept %s users", member.name, len(swept))
            return
        if self.worker_alive(member.name):
            self.logger.warning("Worker %s lost the channel but is alive: killing", member.name)
            self.signal_worker(member.name, signal.SIGKILL)
        swept = self.sweep_worker(member.name)
        self.logger.info("Worker %s died: swept %s users, relaunching", member.name, len(swept))
        self._wakeup.set()

    async def handle_event(self, member: ChannelMember, frame: Frame) -> None:
        """Inbound EVENTs have no consumer in 2a.

        The lifecycle rides the REPLY of the CALL that caused it and the
        occupancy is answered to a probe: nothing pushes EVENTs upward any more.
        """
        self.logger.debug("No consumer for EVENT %s from %s", frame.path, member.name)

    async def unwrap_reply(self, worker: str, path: str, payload: dict[str, Any]) -> Any:
        """The REPLY drain: fold the events the payload carries, then read it.

        Every ``hub.call`` of this commander goes through here. The fold runs
        first, and a login it folds is placed HERE, in the caller's own
        coroutine — so a login result is released only once its user has a room
        on the destination. An error payload becomes the exception the caller
        expects.
        """
        await self.place_logins(worker, payload.get("events") or [])
        if "error" in payload:
            raise ChannelCallError(worker, path, payload["error"])
        return payload.get("result")

    # ------------------------------------------------------------------
    # The fold — one implementation, both drains
    # ------------------------------------------------------------------

    def fold_events(self, worker: str, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply the worker's events in delivered order and return the logins.

        No dedup and no ordering gate: the envelope is causal and delivered
        once, so every event in it is fresh — the legacy removed its own seq
        counters for the same reason (they rejected legitimate post-move
        events). The owner check inside ``fold_event`` is the only guard.
        """
        logins = []
        for event in events:
            self.fold_event(worker, event)
            if event.get("op") == LOGIN_OP:
                logins.append(event)
        return logins

    def fold_event(self, worker: str, event: dict[str, Any]) -> None:
        """Fold one shaped lifecycle event into the surface registries."""
        op = event.get("op")
        user = event.get("user")
        if op == "new_user":
            self.register_user(user, worker)
        elif op == "drop_user":
            self.drop_user(user, worker)
        elif op == LOGIN_OP:
            self.relabel_user(user, event.get("previous_user"))
        elif op in LIFECYCLE_OPS:
            self.logger.debug("fold: op %r has no surface consumer yet", op)
        else:
            self.logger.warning("fold: unknown op %r from %s", op, worker)

    def register_user(self, user: str | None, worker: str) -> None:
        """Map a user to the worker that announced it — the owner check applies.

        An event arriving late from a worker that no longer holds the user never
        re-points it: only the explicit ``assign_user`` decision does.
        """
        if user is None:
            return
        if user in self.user_worker_map and self.user_worker_map[user] != worker:
            self.logger.debug("fold: %s already assigned, ignoring %s's claim", user, worker)
            return
        self.assign_user(user, worker)

    def relabel_user(self, user: str | None, previous_user: str | None) -> None:
        """The login: the anonymous key goes, and the new one is born flagged.

        The worker announcing this has already pushed the user out of its own
        register, so it is nobody's holder any more: the fold writes ``None``
        (placement in flight) and the destination mapping arrives later, from
        ``place_login`` alone.
        """
        if user is None:
            return
        if previous_user is not None and previous_user != user:
            self.remove_user(previous_user)
        self.assign_user(user, None)

    def drop_user(self, user: str | None, worker: str) -> None:
        """Unmap a user, unless it has meanwhile been assigned somewhere else."""
        if user is None or self.user_worker_map.get(user) != worker:
            return
        self.remove_user(user)

    def assign_user(self, user: str, worker: str | None) -> None:
        """Point a user at a worker — the explicit decision, above the owner check.

        One of the two mutators of the surface: the user's half-row travels with
        it, so a re-pointing keeps the pending calls and the activity it already
        had. A user seen for the first time gets a fresh half-row.

        ``worker=None`` raises the placement flag: the user is in the map and on
        no row at all, which is the truth while its slice is on the wire.
        """
        previous = self.user_worker_map.get(user)
        carried = None
        if previous is not None and previous != worker:
            carried = self.worker_roster[previous]["users"].pop(user, None)
        if worker is not None:
            users = self.worker_roster[worker]["users"]
            if user not in users:
                users[user] = self.new_user_row() if carried is None else carried
        self.user_worker_map[user] = worker

    def remove_user(self, user: str) -> None:
        """Drop a user from the surface: its half-row and its map entry, together.

        The other mutator. A user whose placement is in flight (``None`` in the
        map) has no half-row anywhere, so only the flag goes.
        """
        worker = self.user_worker_map.pop(user, None)
        if worker is not None:
            del self.worker_roster[worker]["users"][user]

    def sweep_worker(self, worker: str) -> list[str]:
        """Forget every user of a dead worker: what they pointed at is gone."""
        doomed = sorted(self.worker_roster[worker]["users"])
        for user in doomed:
            self.remove_user(user)
        return doomed

    def users_on(self, worker: str) -> set[str]:
        """The users this worker holds, read from its row."""
        return set(self.worker_roster[worker]["users"])

    def record_occupancy(self, worker: str, report: dict[str, Any]) -> None:
        """Archive one raw occupancy reading in the worker's window."""
        window = self.worker_roster[worker]["occupancy"]
        window.append({"ts": time.time(), "report": report})

    # ------------------------------------------------------------------
    # The front face: sticky routing, the reception, the capacity check
    # ------------------------------------------------------------------

    async def forward_call(
        self,
        identity: str,
        path: str,
        kwargs: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Forward the call to the worker holding ``identity`` and return its result.

        ``identity`` is the sticky key the caller owns — the root avatar identity
        once logged, the session id while anonymous. A user whose placement is in
        flight is waited for first, so the pick lands on the worker the surface
        finally points at; the whole call is one entry under that user's
        ``pending``.
        """
        worker = await self.resolve_worker(identity)
        request_id = self.open_request(worker, identity, path)
        try:
            payload = await self.hub.call(
                worker, path, {"identity": identity, "kwargs": kwargs or {}}, timeout=timeout
            )
            return await self.unwrap_reply(worker, path, payload)
        finally:
            self.close_request(worker, identity, request_id)

    async def resolve_worker(self, identity: str) -> str:
        """The worker to route ``identity`` to, once no placement of it is in flight."""
        await self.await_placement(identity)
        return self.worker_for(identity)

    def worker_for(self, identity: str) -> str:
        """The worker holding ``identity`` — the reception when nobody does.

        A miss is a guest (or a user whose worker died): it goes to the reception,
        which is also the moment to check whether the pool still has room for one.
        A ``None`` is not a miss but the placement flag: nobody may be routed
        while the destination is being decided.
        """
        if identity in self.user_worker_map:
            worker = self.user_worker_map[identity]
            if worker is None:
                raise RuntimeError(f"placement of {identity} is in flight")
            if self.worker_roster[worker]["status"] == "active":
                return worker
        reception = self.reception
        if reception is None:
            raise RuntimeError("no worker available to serve the request")
        self.check_capacity()
        return reception

    def decide_worker(self) -> str:
        """Where a just-logged user belongs: the least-loaded active worker.

        Head count is the 2a reading of load — the evaluator that measures the
        real thing is out of scope. The capacity check runs AFTER the pick, so a
        login never lands on the worker its own arrival spawned.
        """
        candidates = self.active_workers
        if not candidates:
            raise RuntimeError("no worker available to place a login")
        chosen = min(candidates, key=lambda name: len(self.users_on(name)))
        self.check_capacity()
        return chosen

    def check_capacity(self) -> None:
        """Widen the pool when the reception has no room left for its guests.

        A spawn already in flight is waited for instead of being stacked on, and
        ``max_workers`` is a hard ceiling.
        """
        reception = self.reception
        if reception is None or len(self.users_on(reception)) < self.guest_occupancy_limit:
            return
        if len(self.living_workers) > len(self.active_workers):
            return
        if self.max_workers is not None and self.target >= self.max_workers:
            self.logger.warning("Pool full at max_workers=%s; not scaling", self.max_workers)
            return
        self.scale(self.target + 1)
        self.logger.info("Reception %s is full; scaled to %s", reception, self.target)

    # ------------------------------------------------------------------
    # The live calls, written under the user they belong to
    # ------------------------------------------------------------------

    def open_request(self, worker: str, user: str, path: str) -> str:
        """Write one live call under the user's half-row; returns the id that closes it.

        A guest calling for the first time has no half-row yet — the fold of its
        ``new_user`` has not run — so the call itself opens one on the worker
        that is about to serve it.
        """
        users = self.worker_roster[worker]["users"]
        if user not in users:
            users[user] = self.new_user_row()
        entry = users[user]
        request_id = uuid.uuid4().hex
        entry["pending"][request_id] = {"path": path, "ts": time.time()}
        entry["last_activity_ts"] = time.time()
        return request_id

    def close_request(self, worker: str, user: str, request_id: str) -> None:
        """Clear one live call from the user's half-row (the caller's ``finally``).

        The half-row can be gone by now — the worker died and was swept, or the
        user was placed elsewhere — and then there is nothing left to clear.
        """
        entry = self.worker_roster[worker]["users"].get(user)
        if entry is not None:
            entry["pending"].pop(request_id, None)

    # ------------------------------------------------------------------
    # The placement: the login's room, made ready before the key is handed over
    # ------------------------------------------------------------------

    async def place_logins(self, worker: str, events: list[dict[str, Any]]) -> None:
        """Fold this REPLY's events, then hold the caller until each room is ready.

        The fold hands back the logins it applied and they are placed right
        here, in the caller's own coroutine — the only placement path there is,
        because a login exists only as the effect of a CALL. A login result is
        released once its user has a room.
        """
        for event in self.fold_events(worker, events):
            await self.place_login(event["user"], event["package"])

    async def place_login(self, user: str, package: str) -> None:
        """Give a just-logged user its room: decide, install, map, drop the flag.

        The user is already flagged in the map (the fold did that) and its slice
        exists only inside ``package`` — the source spent its copy pushing it.
        So there is nothing to roll back: an install that fails — the destination
        dying is the only way it can — leaves the user nowhere, and the map is
        made to say exactly that.
        """
        path = f"{OP_PATH_PREFIX}install_package"
        try:
            destination = self.decide_worker()
            payload = await self.hub.call(
                destination,
                path,
                {"identity": user, "kwargs": {"package": package}},
            )
            await self.unwrap_reply(destination, path, payload)
        except Exception as exc:
            self.remove_user(user)
            self.logger.warning("Placement of %s failed (%s: %s)", user, type(exc).__name__, exc)
            raise
        else:
            self.assign_user(user, destination)
            self.logger.info("Placed %s on %s", user, destination)
        finally:
            self.release_placement()

    def release_placement(self) -> None:
        """Wake every coroutine parked on the flag, then re-arm for the next one."""
        self.placement_done.set()
        self.placement_done.clear()

    async def await_placement(self, identity: str) -> None:
        """Hold a call whose user is being placed until the flag drops.

        The parked coroutines are the queue: a wakeup re-reads the map, so one
        that finds the flag up again (a second login chained onto the first)
        simply parks once more. Nothing bounds the wait but the placement
        itself: the destination either answers or dies, and its death fails the
        install CALL.
        """
        while self.user_worker_map.get(identity, "") is None:
            await self.placement_done.wait()
