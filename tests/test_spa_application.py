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

"""The SPA front owns its pool: construction, the kwarg split, the lifecycle.

The joint is composition — the application HAS a commander, it is not one — so
what these tests pin is the seam between the two constructors (which kwarg goes
where, and what stays at its default) and the two lifecycle hooks driving a
real single-role pool up and down.
"""

from __future__ import annotations

from typing import Any

from genro_asgi.applications import SpaApplication
from genro_asgi.spa.commander import UserStickyCommander


class RecordingCommander(UserStickyCommander):
    """A commander that remembers how it was built."""

    def __init__(self, **kwargs: Any) -> None:
        self.built_with = dict(kwargs)
        super().__init__(**kwargs)


def test_the_application_owns_a_commander_of_the_default_class() -> None:
    app = SpaApplication()
    assert isinstance(app.commander, UserStickyCommander)
    assert app.commander_class is UserStickyCommander


def test_application_kwargs_never_reach_the_commander() -> None:
    app = SpaApplication(code="site", mount="", commander_class=RecordingCommander)
    assert app.code == "site"
    assert app.mount == ""
    assert app.commander.built_with == {}


def test_commander_kwargs_are_peeled_and_forwarded() -> None:
    app = SpaApplication(
        commander_class=RecordingCommander,
        workers=0,
        local_worker=True,
        group="site-group",
        reception_threshold=0.7,
    )
    assert app.commander.built_with == {
        "workers": 0,
        "local_worker": True,
        "group": "site-group",
        "reception_threshold": 0.7,
    }
    assert app.commander.target == 0
    assert app.commander.local_worker is True
    assert app.commander.group == "site-group"
    assert app.commander.reception_threshold == 0.7


def test_unpassed_commander_kwargs_keep_the_commander_defaults() -> None:
    reference = UserStickyCommander()
    app = SpaApplication(commander_class=RecordingCommander, workers=0)
    assert "probe_interval" not in app.commander.built_with
    assert app.commander.probe_interval == reference.probe_interval
    assert app.commander.max_workers == reference.max_workers


def test_a_custom_commander_class_is_honored() -> None:
    app = SpaApplication(commander_class=RecordingCommander)
    assert app.commander_class is RecordingCommander


def test_a_commander_subclass_receives_its_own_kwargs() -> None:
    class TunedCommander(RecordingCommander):
        def __init__(self, *, spill_threshold: int = 1, **kwargs: Any) -> None:
            self.spill_threshold = spill_threshold
            super().__init__(**kwargs)

    app = SpaApplication(commander_class=TunedCommander, spill_threshold=3, workers=0)
    assert app.commander.spill_threshold == 3
    assert app.commander.built_with == {"workers": 0}
    assert isinstance(app.commander, RecordingCommander)


def test_an_unknown_kwarg_still_raises_at_the_end_of_the_chain() -> None:
    try:
        SpaApplication(nonsense=1)
    except TypeError as error:
        assert "nonsense" in str(error)
    else:
        raise AssertionError("an unknown kwarg must not be swallowed")


async def test_the_lifecycle_hooks_drive_a_real_single_role_pool() -> None:
    app = SpaApplication(workers=0, local_worker=True)
    await app.on_startup()
    try:
        assert app.commander.worker is not None
        assert app.commander.active_workers == [app.commander.worker.name]
        assert app.commander.reception == app.commander.worker.name
    finally:
        await app.on_shutdown()
    assert app.commander.worker is None
    assert app.commander.living_workers == []
