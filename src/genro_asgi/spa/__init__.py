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

"""The SPA world — the machinery behind UserSticky commanders and workers.

Everything here serves single-page applications: the register machinery
(`Register`, `RegisterRegistry` — in-process datasets with secondary
indexes and the users/pages lifecycle vocabulary) and the UserSticky pair
above it (`UserStickyWorker`, the execution unit; `UserStickyCommander`,
the pool owner and routing surface, which also holds the worker itself in
the single role). Nothing in the base server instantiates any of it: this
package is inert until a runtime (or genropy-asgi) mounts it. It is
reached by subpackage import — this ``__init__`` is the public face
(``from genro_asgi.spa import RegisterRegistry``); nothing is re-exported
from ``genro_asgi`` top-level.
"""

from .commander import UserStickyCommander
from .register import Register
from .register_registry import RegisterRegistry
from .worker import UserStickyWorker

__all__ = [
    "Register",
    "RegisterRegistry",
    "UserStickyCommander",
    "UserStickyWorker",
]
