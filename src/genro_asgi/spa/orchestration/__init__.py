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
the per-worker wire; the handler that owns one worker process and its death.
"""

from .freeze_handler import FreezeHandler

__all__ = ["FreezeHandler"]
