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

"""The scripted child of the end-to-end test: a real process using the real foundations.

The worker of Macro 2 does not exist yet, so this is what the WorkerHandler
launches: the smallest process that uses every foundation the way a worker will.
It is TEST-ONLY, and it is not a fake — the wire is the package's own
``FrameStream``, the deposit is the package's own ``FreezeHandler``, and the
configuration is the very ``GENRO_ASGI_WORKER`` payload the handler writes.

Its life: connect to the socket it was given, present itself with its pid and
the configuration it received, and keep the whole global store that comes back
in the answer. Then serve the parent — the health beat with its photo, the three
deposit orders, and the one EVENT that makes it go mute.

**It reaches the deposit on its own side.** Nothing hands it a FreezeHandler:
it builds one over ``frozen_users_path``, exactly as a worker in another process
must. What it writes there the parent reads back through a FreezeHandler of its
own, over the same root.

**Going mute is how it dies.** On ``/go_mute`` it stops answering while still
reading the wire — a process that is up and no longer serving, which is what the
surveillance kills. Whatever it was holding in the deposit when the SIGKILL
lands stays there: nothing in this stub tidies up, because nothing in the
foundations does.

The routing keys below are this stub's own: the parent side of the protocol is
Macro 2's and its names are baptised there. The one exception is the beat, which
travels on the ratified occupancy path the handler already uses.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from genro_asgi.channel.frame import REGISTER_METHOD, REGISTER_PATH, Frame, FrameStream
from genro_asgi.spa.orchestration import FreezeHandler
from genro_asgi.spa.orchestration.worker_connector import (
    CALL_METHOD,
    EVENT_METHOD,
    GLOBAL_STORE_KEY,
    REPLY_METHOD,
)
from genro_asgi.spa.orchestration.worker_handler import OCCUPANCY_OP_PATH, WORKER_ENV_VAR

#: The child announces upward that it has taken a user's semaphore.
LOCK_TAKEN_EVENT = "/lock_taken"

#: The parent tells the child to stop answering: the mute worker of the drill.
GO_MUTE_EVENT = "/go_mute"

#: The three deposit orders the parent drives the child through.
TAKE_LOCK_OP = "/take_deposit_lock"
WRITE_CONNECTION_ITEM_OP = "/write_connection_item"
RELEASE_LOCK_OP = "/release_deposit_lock"

__all__ = [
    "GO_MUTE_EVENT",
    "LOCK_TAKEN_EVENT",
    "RELEASE_LOCK_OP",
    "TAKE_LOCK_OP",
    "WRITE_CONNECTION_ITEM_OP",
    "ChildStub",
]


class ChildStub:
    """One scripted worker process: its wire, its deposit, and its mute switch."""

    def __init__(self) -> None:
        self.config = json.loads(os.environ[WORKER_ENV_VAR])
        self.name = self.config["name"]
        self.group = self.config["kwargs"]["group"]
        self.freeze_handler = FreezeHandler(self.config["frozen_users_path"])
        self.global_store: str | None = None
        self.answering = True
        self.stream: FrameStream | None = None
        self.operations = {
            OCCUPANCY_OP_PATH: self.answer_occupancy,
            TAKE_LOCK_OP: self.take_deposit_lock,
            WRITE_CONNECTION_ITEM_OP: self.write_connection_item,
            RELEASE_LOCK_OP: self.release_deposit_lock,
        }

    @property
    def photo(self) -> dict[str, Any]:
        """What this process honestly knows of itself.

        Returns:
            Its pid, its name and the global store it was handed at the
            presentation — a real worker adds the memory and the clocks it can
            actually measure.
        """
        return {"pid": os.getpid(), "name": self.name, "global_store": self.global_store}

    async def live(self) -> None:
        """Connect, present, then serve the parent until the wire ends.

        Sets ``stream``; returns when the parent is gone.
        """
        address = self.config["uds_url"].removeprefix("uds:")
        reader, writer = await asyncio.open_unix_connection(address)
        self.stream = FrameStream(reader, writer)
        await self.present()
        while True:
            frame = await self.stream.read()
            if frame is None:
                return
            await self.serve_frame(frame)

    async def present(self) -> None:
        """Say pid and configuration, and keep the whole global store that answers.

        Sets ``global_store``.
        """
        await self.stream.write(
            Frame(
                method=REGISTER_METHOD,
                path=REGISTER_PATH,
                data={"pid": os.getpid(), "config": self.config},
            )
        )
        reply = await self.stream.read()
        self.global_store = reply.data[GLOBAL_STORE_KEY]

    async def serve_frame(self, frame: Frame) -> None:
        """Obey one envelope from the parent.

        Args:
            frame: the envelope as it came off the wire.

        A CALL is answered with its REPLY, reusing its id; the mute EVENT stops
        every answer from then on, and a mute process answers no CALL at all.
        """
        if frame.method == EVENT_METHOD and frame.path == GO_MUTE_EVENT:
            self.answering = False
        elif frame.method == CALL_METHOD and self.answering:
            result = await self.operations[frame.path](frame.data)
            await self.stream.write(
                Frame(id=frame.id, method=REPLY_METHOD, path=frame.path, data={"result": result})
            )

    async def answer_occupancy(self, data: Any) -> dict[str, Any]:
        """The health beat.

        Args:
            data: whatever the beat carried; the beat carries nothing.

        Returns:
            The photo of this process.
        """
        return self.photo

    async def take_deposit_lock(self, data: Any) -> dict[str, Any]:
        """Take the semaphore of a user and announce it upward.

        Args:
            data: the user whose folder is being entered.

        Returns:
            Whether the semaphore is now this process's.

        Writes the lock in the deposit and sends the announcement EVENT.
        """
        user = data["user"]
        taken = self.freeze_handler.take_lock(user, self.name)
        await self.stream.write(
            Frame(
                method=EVENT_METHOD,
                path=LOCK_TAKEN_EVENT,
                data={"user": user, "holder": self.name},
            )
        )
        return {"taken": taken}

    async def write_connection_item(self, data: Any) -> dict[str, Any]:
        """Write one connection parcel under the semaphore this process holds.

        Args:
            data: the user, the connection identity and the payload to park.

        Returns:
            The connection identity written.

        Writes the parcel in the deposit.
        """
        self.freeze_handler.write_connection_item(
            data["user"],
            data["cid"],
            data["payload"],
            writer=self.name,
            cause="freeze",
            group=self.group,
        )
        return {"written": data["cid"]}

    async def release_deposit_lock(self, data: Any) -> dict[str, Any]:
        """Give the semaphore back; whatever was parked stays behind.

        Args:
            data: the user whose folder is being left.

        Returns:
            The user released.

        Removes the lock from the deposit.
        """
        user = data["user"]
        self.freeze_handler.release_lock(user, self.name)
        return {"released": user}


if __name__ == "__main__":
    asyncio.run(ChildStub().live())
