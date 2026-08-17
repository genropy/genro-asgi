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

"""What the orchestration raises instead of answering.

A refusal here is not a failure: it is the ANSWER, and the caller's own next step
is written in which exception arrived. So the reasons are types, not codes to
read out of a return value, and nobody has to remember what a False meant.

``UserOnHold`` is the gate of the waiting room: the user is mid-departure, so the
request that just arrived cannot be routed at his old address and must not open a
new one either — it waits, and how long a request may wait belongs to whoever
answers requests. The row at the vertex carries the cause, and the ONLY way that
field is read is by catching this.
"""

from __future__ import annotations

__all__ = ["UserOnHold"]


class UserOnHold(Exception):
    """This user is between two homes: whatever asked for him has to wait.

    Args:
        user: the identity that is on hold.
        cause: what put him there, for the log and for the sysop — never for a
            caller to branch on.
    """

    def __init__(self, user: str, cause: str) -> None:
        super().__init__(f"{user} is on hold: {cause}")
        self.user = user
        self.cause = cause
