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

"""How ``execute_plan`` treats a step ``build_plan`` would never have produced.

The executor validates nothing, and that is a ratified decision (2026-08-14): the
only producer of steps in production is ``build_plan``, so a malformed step is not
a case the code has to answer for. What the code does with one anyway is an
IMPLEMENTATION fact, photographed here rather than in the contract suite: an
unknown ``op`` falls through to the compaction branch, and a ``replace`` missing
its ``spawn`` raises ``KeyError`` where it reads it.

Both die with the day the executor starts validating.
"""

from __future__ import annotations

from typing import Any

import pytest

from genro_asgi.spa.commander import UserStickyCommander


def a_pool_of_three(tmp_path: Any) -> UserStickyCommander:
    """Three enrolled workers, no wire, no process: placement is bookkeeping."""
    commander = UserStickyCommander(
        workers=0, path=str(tmp_path / "hub.sock"), compaction_margin=0.3, spawn_margin=0.2
    )
    for name in ("W:w-1", "W:w-2", "W:w-3"):
        commander.worker_roster[name] = commander.new_roster_row(0, None)
        commander.worker_roster[name]["status"] = "active"
    commander.target = 3
    return commander


async def test_an_unknown_op_is_run_as_a_compaction(tmp_path: Any) -> None:
    """The branch chain ends in an ``else``, so anything not named lands there:
    the step's worker is drained and folded like any compaction."""
    commander = a_pool_of_three(tmp_path)
    drained: list[str] = []

    async def record(worker: str) -> bool:
        drained.append(worker)
        return True

    commander.drain_worker = record  # type: ignore[method-assign]
    await commander.execute_plan([{"op": "wobble", "worker": "W:w-3"}])
    assert drained == ["W:w-3"]
    assert commander.target == 2


async def test_a_replace_without_its_spawn_answer_raises(tmp_path: Any) -> None:
    """No default is invented for a missing key: the step is read as written, the
    ``KeyError`` ends the plan like any raise, and the claim is still handed back."""
    commander = a_pool_of_three(tmp_path)
    commander.active_plan = [{"op": "replace", "worker": "W:w-2"}]
    with pytest.raises(KeyError):
        await commander.execute_plan([{"op": "replace", "worker": "W:w-2"}])
    assert commander.active_plan is None
