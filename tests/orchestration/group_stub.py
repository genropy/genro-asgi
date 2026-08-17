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

"""The group of the tests: the level that does not exist yet, and what it must do.

``GroupHandler`` is built in its own phase. Until then a handler still needs a
group above it — for the wake it rings when its process ends, and for the layer of
the chain everything it hears climbs through — so this is that group, and it is
NOT a fake: the layer it carries is the real ``GroupEnvelopeHandler`` over a real
``SpaCommander``, so a worker event born in a child process lands in the real
indexes.

What it stands in for is only the group's OWN work, and this is therefore the
list of what the real one owes the chain: the wake (``ping_now``), whether a photo
is urgent enough to bring its round forward, the placement of its users
(``user_worker_map``, ``None`` meaning "to be assigned") and taking a dead
handler out of the group (``drop_worker``). Everything the tests assert about the
group is asserted on these.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from genro_asgi.spa.orchestration import GroupEnvelopeHandler, SpaCommander


class GroupStub:
    """The GroupHandler seen from below: its wake, its placements, its layer of the chain.

    Args:
        frozen_users_path: the deposit root the vertex reads — the same one the
            workers are given.
        name: the group's name.
        spa_commander: an existing vertex to hang under; one of its own when None.
    """

    def __init__(
        self,
        frozen_users_path: str | Path,
        *,
        name: str = "standard",
        spa_commander: SpaCommander | None = None,
    ) -> None:
        self.name = name
        self.spa_commander = spa_commander or SpaCommander(frozen_users_path)
        self.envelope_handler = GroupEnvelopeHandler(self, self.spa_commander.envelope_handler)
        self.user_worker_map: dict[str, str | None] = {}
        #: What the handler was in when it rang, in the order the wakes came.
        self.wakes: list[str] = []
        #: Who was on board at each of those wakes.
        self.users_on_board: list[set[str]] = []
        #: The handlers taken out of the group, in order.
        self.dropped_workers: list[Any] = []
        #: Whether the next photo counts as urgent — the tests set it.
        self.urgent_snapshots = False
        #: The handler under this group; the tests assign it after construction.
        self.worker_handler: Any = None

    def ping_now(self) -> None:
        """The wake: at this round the group reads the state and who was on board."""
        self.wakes.append(self.worker_handler.state)
        self.users_on_board.append(set(self.worker_handler.hosted_users))

    def snapshot_is_urgent_TBD(self, photo: dict[str, Any]) -> bool:
        """Whether this photo cannot wait for the round the cadence would give it."""
        return self.urgent_snapshots

    def record_placement_TBD(self, user: str, worker: str | None) -> None:
        """Write where a user of this group lives; None means he is to be assigned."""
        self.user_worker_map[user] = worker

    def forget_placement_TBD(self, user: str) -> None:
        """Take a user out of the placement: he is not this group's business any more."""
        self.user_worker_map.pop(user, None)

    def drop_worker(self, worker_handler: Any) -> None:
        """Take a dead handler out of the group, with the placements that pointed at it."""
        self.dropped_workers.append(worker_handler)
        for user in list(self.user_worker_map):
            if self.user_worker_map[user] == worker_handler.name:
                del self.user_worker_map[user]
