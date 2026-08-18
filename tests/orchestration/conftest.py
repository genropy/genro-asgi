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

"""The common ground of the orchestration tests: the root, the path, the wait.

``short_root`` is a temporary directory whose name fits inside the system's cap
on a UDS path — about a hundred characters, which pytest's own ``tmp_path`` is
already past, and the very reason worker names are short. ``repo_on_pythonpath``
puts this repository where a spawned child can import the stub modules of the
test package from. ``wait_for`` polls a condition instead of sleeping a guessed
amount: a process dying, a wire ending, a round landing — none has a duration.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def short_root():
    """A temporary root short enough for a socket path; it dies with the test."""
    root = Path(tempfile.mkdtemp(prefix="gnrorch_"))
    yield root
    shutil.rmtree(root, ignore_errors=True)


async def wait_for(condition, timeout: float = 10.0) -> None:
    """Poll until the condition holds, or give up loudly at the deadline."""
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError("the machine never reached the awaited state")
        await asyncio.sleep(0.01)


@pytest.fixture
def repo_on_pythonpath(monkeypatch):
    """Let a spawned child import the test package: this repository on its path."""
    repo_root = Path(__file__).resolve().parents[2]
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv(
        "PYTHONPATH", os.pathsep.join([str(repo_root), inherited]).rstrip(os.pathsep)
    )
