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

"""The orchestration of the SPA pool — the machine that owns workers and state.

This subpackage grows beside the machine currently running (``spa/commander.py``,
``spa/worker.py``): nothing here imports it and nothing there imports this. The
cutover happens later, in one declared step; until then the two coexist.

Its foundations, in the order they are built: ``FreezeHandler``, the deposit on
disk and the only place in the project that talks to the filesystem directly;
``WorkerConnector``, the wire of one worker; ``WorkerHandler``, which owns one
process and its death; ``SpaWorker``, the registers that process serves from;
``WorkerEntry``, the shell that runs one of those workers in a child process;
the three ``EnvelopeHandler`` layers, the chain everything a process announces
climbs; ``SpaCommander``, the vertex that owns the indexes of the whole machine
and the master of the store every worker replicates; ``GroupHandler``, the
workers of one grammar, where a user of theirs lands and what the group does
about its own shape.
"""

from .envelope_handler import (
    CommanderEnvelopeHandler,
    EnvelopeHandler,
    GroupEnvelopeHandler,
    WorkerEnvelopeHandler,
)
from .exceptions import (
    AssignmentRefused,
    NoRoomError,
    SiteFailedRequest,
    UserOnHold,
    WorkerQuittingError,
)
from .beats import every
from .freeze_handler import FreezeHandler
from .global_store_view import GlobalStorePublisher, GlobalStoreView
from .group_handler import GroupHandler
from .spa_commander import SpaCommander
from .spa_worker import SpaWorker
from .worker_connector import WorkerConnector
from .worker_entry import WorkerEntry
from .worker_handler import WorkerHandler

__all__ = [
    "AssignmentRefused",
    "CommanderEnvelopeHandler",
    "EnvelopeHandler",
    "FreezeHandler",
    "GlobalStorePublisher",
    "GlobalStoreView",
    "GroupEnvelopeHandler",
    "GroupHandler",
    "NoRoomError",
    "SiteFailedRequest",
    "SpaCommander",
    "SpaWorker",
    "UserOnHold",
    "WorkerConnector",
    "WorkerEntry",
    "WorkerEnvelopeHandler",
    "WorkerHandler",
    "WorkerQuittingError",
    "every",
]
