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

"""WorkerHandler: the handler, which stays, and the process under it, which does not.

A handler belongs to its group, carries a short name (``standard_0001``, minted by
the group; short because the socket path has a hard system budget) and owns one
socket. The process under it is replaceable: it can be killed, it can die on its
own, it can be reborn on the same name and the same socket — and every placement
pointing at the handler is untouched by all of that.

**Four orders, and each verb carries its object.** ``launch_process`` opens the
wire, spawns the child and waits for it to present itself; ``terminate_process``
kills the process group and waits for the OS to bury it; ``restart_process``
does the two in a row, on the same name and socket; ``ping_process`` is one
health beat. Nothing here freezes a user, closes a tap or reads a policy: those
belong one level up, and a handler that took them would be deciding for the pool.

**Low tolerance, and never two processes.** A mute beat is repeated ONCE past
the timeout — against a lost packet, not against a sick worker — and then the
process group is killed and its OS death awaited. Only after that death may a
successor be launched: the wire is one, so a handler is never two processes. The
declared price is that the slow-but-healthy dies and its users log in again,
which is seconds of error instead of minutes of spinner.

**A death is governed only if this handler ordered it.** ``restart_process`` marks
the death it is about to cause; the wire's end then passes transparently and
announces nothing. Every OTHER end of the wire is WILD: the handler says so in the
orchestration log and calls ``on_worker_abort`` on its group, and its job ends
there. It owns the list of its users (``hosted_users``), not the indexes of
anybody else: the group unhooks the handler from the placement and the Commander —
the single writer of the maps — prunes the traces, discards the parcels and
removes the semaphores the dead one had announced. Which is why nothing in this
module touches the deposit.

**No counters here.** The handler holds ``worker_snapshot``, the last photo its
process sent — written by the wire from whatever envelope carried it, so a live
process has one from its very presentation: the gauges the judge reads are all
in there. Counters are
aggregate and belong to the Commander, which is also the one that decides the
orders worth counting.

**The beat has no clock of its own.** ``ping_process`` is one beat and
``process_ping_interval`` is the cadence it is meant to be called at; the clock
that calls it belongs to whoever governs the group. The handler's burial — the
socket taken away — is ``WorkerConnector.stop()``, called by whoever closes the
handler for good.

Every order and every wild death leaves its line here through the module
logger; the dedicated ``orchestration.log`` file, with its path, size and
rotation, is grammar and is not built yet.

``LocalWorkerHandler`` is the handler of the in-process worker: the same handler, no
process to govern. Its health IS the server's, so it refuses every process
order rather than pretending to obey one.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from ...channel.frame import Frame
from .worker_connector import WorkerConnector

#: The environment variable the spawn payload travels in, as today.
WORKER_ENV_VAR = "GENRO_ASGI_WORKER"

#: The routing key of the health beat: the ratified occupancy op, which is also
#: the photo the silent ones are measured by. Redefined here with its ratified
#: value rather than imported: the legacy machine dies at the cutover.
OCCUPANCY_OP_PATH = "/op/occupancy"

#: Seconds between two beats of the same process — the cadence, not a clock.
PROCESS_PING_INTERVAL = 5.0

#: How long a process may stay mute before the beat counts as missed. Twice
#: this, and the process is killed.
PROCESS_PING_TIMEOUT = 10.0

# How often a wait re-reads the thing it waits for (an OS death, the wire
# reporting an ordered death): nothing signals either, so both poll.
WAIT_POLL_INTERVAL = 0.05

__all__ = [
    "OCCUPANCY_OP_PATH",
    "PROCESS_PING_INTERVAL",
    "PROCESS_PING_TIMEOUT",
    "WORKER_ENV_VAR",
    "LocalWorkerHandler",
    "WorkerHandler",
]


class WorkerHandler:
    """One handler of a group: its wire, its process, its users, its last photo.

    Args:
        group_handler: the group this handler belongs to; a wild death is told to
            it as ``on_worker_abort(self)``.
        name: the handler's name, minted by the group as ``<group>_<counter>``;
            it names the socket too, so it is short.
        instance_dir: the directory holding the sockets of this installation.
        frozen_users_path: the deposit root the child builds its own access to.
        entry_module: the module the child is started as (``python -m ...``).
        main_threadpool_size: the child's traffic pool size, None for its own
            default.
        aux_threadpool_size: the child's service pool size, much smaller.
        worker_class: the ``module:Class`` the child loads, None for its own.
        worker_kwargs: the grammar handed to that class; travels as ``kwargs``.
        executable: the interpreter to spawn with, this one by default.
        process_ping_interval: the cadence the beat is meant to be called at.
        process_ping_timeout: how long the process may stay mute per beat.
    """

    def __init__(
        self,
        group_handler: Any,
        name: str,
        *,
        instance_dir: str | Path,
        frozen_users_path: str | Path,
        entry_module: str,
        main_threadpool_size: int | None = None,
        aux_threadpool_size: int | None = None,
        worker_class: str | None = None,
        worker_kwargs: dict[str, Any] | None = None,
        executable: str | None = None,
        process_ping_interval: float = PROCESS_PING_INTERVAL,
        process_ping_timeout: float = PROCESS_PING_TIMEOUT,
    ) -> None:
        self.group_handler = group_handler
        self.name = name
        self.instance_dir = Path(instance_dir)
        self.frozen_users_path = Path(frozen_users_path)
        self.entry_module = entry_module
        self.main_threadpool_size = main_threadpool_size
        self.aux_threadpool_size = aux_threadpool_size
        self.worker_class = worker_class
        self.worker_kwargs = worker_kwargs or {}
        self.executable = executable or sys.executable
        self.process_ping_interval = process_ping_interval
        self.process_ping_timeout = process_ping_timeout
        self.process: subprocess.Popen[bytes] | None = None
        #: The last photo the process sent, on whatever envelope carried it:
        #: memory, load, counts, per-connection clocks. Written by the wire.
        self.worker_snapshot: dict[str, Any] | None = None
        self.connector = WorkerConnector(self, self.instance_dir / f"{name}.sock")
        self._logger = logging.getLogger(__name__)
        self._hosted_users: set[str] = set()
        self._governed_death = False
        self._listening = False

    @property
    def global_register_item_tytx(self) -> str:
        """The whole global store, TYTX-encoded, for the presentation reply.

        Returns:
            The placeholder: the master lives on the Commander, which is built
            in Macro 3, and the store cannot be answered before its owner
            exists.
        """
        return "not yet ready --- wait next phase"

    @property
    def hosted_users(self) -> set[str]:
        """The users living on this handler's process.

        Returns:
            The live set — the group reads it to know who a death took with it.
            Its single writer is the fold, one level up.
        """
        return self._hosted_users

    @property
    def spawn_payload(self) -> dict[str, Any]:
        """The child's whole configuration, strings and numbers only.

        Returns:
            The object that travels JSON-encoded in ``GENRO_ASGI_WORKER``: the
            handler's name, the address of its socket, the deposit root, the two
            pool sizes, the worker class and its grammar.
        """
        return {
            "name": self.name,
            "uds_url": self.connector.address,
            "frozen_users_path": str(self.frozen_users_path),
            "main_threadpool_size": self.main_threadpool_size,
            "aux_threadpool_size": self.aux_threadpool_size,
            "worker_class": self.worker_class,
            "kwargs": self.worker_kwargs,
        }

    async def launch_process(self) -> None:
        """Open the wire if it is closed, spawn the child, wait for it to present itself.

        Raises:
            RuntimeError: a process is already alive under this handler — two of
                them under one handler is the thing the whole surveillance exists
                to make impossible.
            TimeoutError: the child never presented itself within
                ``process_ping_timeout``; it is killed before the raise, so no
                unpresented process is left behind.

        Sets ``process``, and binds the socket on the first launch — a
        successor finds the wire already listening at the same address.
        """
        if self.process is not None and self.process.poll() is None:
            raise RuntimeError(
                f"WorkerHandler {self.name}: its process (pid {self.process.pid}) is still alive"
            )
        if not self._listening:
            await self.connector.start()
            self._listening = True
        env = dict(os.environ)
        env[WORKER_ENV_VAR] = json.dumps(self.spawn_payload)
        self.process = subprocess.Popen(
            [self.executable, "-m", self.entry_module], env=env, start_new_session=True
        )
        self._logger.info(
            "Worker %s: launched its process (pid %s) on %s",
            self.name,
            self.process.pid,
            self.connector.address,
        )
        try:
            await asyncio.wait_for(self.connector.wait_connected(), self.process_ping_timeout)
        except TimeoutError:
            self._logger.warning(
                "Worker %s: its process never presented itself in %.1fs — killing",
                self.name,
                self.process_ping_timeout,
            )
            await self.terminate_process()
            raise

    async def terminate_process(self) -> None:
        """Kill the process group and wait until the OS has buried it.

        SIGKILL, no escalation and no grace: a grace period is the users
        waiting. Clears ``process``; the wire's end tells the rest of the
        machine, which is why nothing is announced from here.
        """
        process = self.process
        self._logger.info("Worker %s: killing its process (pid %s)", self.name, process.pid)
        self._kill_process_group()
        while process.poll() is None:
            await asyncio.sleep(WAIT_POLL_INTERVAL)
        self.process = None

    async def restart_process(self) -> None:
        """Kill the process and launch a fresh one on the same name and socket.

        Raises:
            RuntimeError: the wire never reported the ordered death, so the
                successor cannot be let in without risking two processes.

        Marks the death as GOVERNED — that mark is the whole difference between
        a transparent relaunch and a wild death — then terminates, waits for the
        wire to report that death, and launches the successor. OS level only:
        whoever orders a relaunch has already closed the tap and had the users
        frozen.

        The mark is set ONLY when a child is really on the wire: a wire with
        nobody on it reports nothing, and a mark left behind for a report that
        never comes would make the handler deaf to its next wild death.
        """
        self._logger.info("Worker %s: restarting its process — the death is ordered", self.name)
        self._governed_death = self.connector.connected
        await self.terminate_process()
        if self._governed_death:
            await self._wait_ordered_death_seen()
        await self.launch_process()

    async def ping_process(self) -> None:
        """One health beat: are you alive? Kill the process if it stays mute.

        The photo is not asked for here — it rides whatever envelope the child
        sends, ``worker_snapshot`` slot, and the wire files it. A missed beat is
        repeated ONCE past the timeout, against a lost packet; a process mute to
        both is killed, and the wire that dies with it denounces the death as
        wild.
        """
        for beat in (1, 2):
            try:
                await self.connector.call(OCCUPANCY_OP_PATH, timeout=self.process_ping_timeout)
            except TimeoutError:
                self._logger.warning(
                    "Worker %s: beat %s of 2 unanswered after %.1fs",
                    self.name,
                    beat,
                    self.process_ping_timeout,
                )
            else:
                return
        self._logger.warning("Worker %s: mute to both beats — killing its process", self.name)
        await self.terminate_process()

    def on_child_message(self, frame: Frame) -> None:
        """An EVENT arrived from the process.

        Args:
            frame: the envelope as it came off the wire.

        Returns nothing and changes nothing: the road that carries an
        announcement up to the Commander is built in Macro 2, and inventing a
        consumer here would be deciding the protocol.
        """
        self._logger.info(
            "Worker %s: EVENT %s from its process, not consumed yet", self.name, frame.path
        )

    def on_child_lost(self) -> None:
        """The wire died: transparent if this handler ordered it, denounced if not.

        Consumes the governed mark. A wild death leaves its line in the
        orchestration log and reaches the group as ``on_worker_abort(self)`` —
        and the handler's part ends there.
        """
        if self._governed_death:
            self._governed_death = False
            self._logger.info("Worker %s: its process died as ordered", self.name)
            return
        self._logger.warning(
            "Worker %s: WILD death of its process, %s users on board",
            self.name,
            len(self._hosted_users),
        )
        self.group_handler.on_worker_abort(self)

    def _kill_process_group(self) -> None:
        """SIGKILL the child's whole process group; one already gone is the same outcome."""
        process = self.process
        if process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass

    async def _wait_ordered_death_seen(self) -> None:
        """Wait for the wire to have reported the ordered death; the successor needs it free.

        A report that never comes gives back the mark before raising: a handler
        left marked would swallow the denunciation of its next wild death.
        """
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.process_ping_timeout
        while self._governed_death:
            if loop.time() >= deadline:
                self._governed_death = False
                raise RuntimeError(
                    f"WorkerHandler {self.name}: the wire never reported the ordered death"
                )
            await asyncio.sleep(WAIT_POLL_INTERVAL)


class LocalWorkerHandler(WorkerHandler):
    """The handler of the in-process worker: everything of a handler, no process to govern.

    The single role (``workers=0, local_worker=True``) runs its worker inside
    the server, so there is nothing to probe, nothing to kill and nothing to
    relaunch: its health IS the server's and its death IS the server's crash.
    Every process order is refused rather than obeyed halfway — the group never
    issues one to this handler, so an order arriving here is a bug and says so.
    Everything else is the handler as inherited: the users, the photo, the store
    for the presentation, the announcements.
    """

    async def launch_process(self) -> None:
        """Refused: a local handler forks nothing — see ``_refuse_process_order``."""
        self._refuse_process_order("launch")

    async def terminate_process(self) -> None:
        """Refused: a local handler kills nothing — see ``_refuse_process_order``."""
        self._refuse_process_order("terminate")

    async def restart_process(self) -> None:
        """Refused: a local handler relaunches nothing — see ``_refuse_process_order``."""
        self._refuse_process_order("restart")

    async def ping_process(self) -> None:
        """Refused: a local handler probes nothing — see ``_refuse_process_order``."""
        self._refuse_process_order("ping")

    def _refuse_process_order(self, order: str) -> None:
        """Say why the order cannot be obeyed, naming it."""
        raise RuntimeError(
            f"LocalWorkerHandler {self.name}: no process to {order} — its health is the server's"
        )
