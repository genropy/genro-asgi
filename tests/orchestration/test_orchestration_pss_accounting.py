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

"""PSS is the worker memory currency; RSS is its explicit portable fallback."""

from __future__ import annotations

import builtins
import io
from types import SimpleNamespace

import pytest

from genro_asgi.spa.orchestration import GroupHandler, SpaCommander, SpaWorker

CONCESSION = 1_000_000


@pytest.fixture
def worker() -> SpaWorker:
    """An uninitialised worker is enough: the gauge reads only the proc file."""
    return object.__new__(SpaWorker)


def rollup(monkeypatch, content: str) -> None:
    """Make the worker's one proc read return this rollup text."""
    monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: io.StringIO(content))


def group(tmp_path) -> GroupHandler:
    commander = SpaCommander(tmp_path / "frozen")
    return GroupHandler(
        commander,
        "pool",
        memory_concession_bytes=CONCESSION,
        worker_memory_max_percent=100.0,
        instance_dir=tmp_path / "instance",
        frozen_users_path=tmp_path / "frozen",
        entry_module="never.launched",
    )


def test_pss_is_read_from_smaps_rollup_in_bytes(worker, monkeypatch):
    rollup(monkeypatch, "Rss: 900 kB\nPss: 321 kB\nPss_Anon: 300 kB\n")

    assert worker.pss_bytes == 321 * 1024


@pytest.mark.parametrize(
    "content",
    [
        "Rss: 900 kB\n",
        "Pss:\n",
        "Pss: garbage kB\n",
        "Pss: -1 kB\n",
        "Pss: 1 MB\n",
        "Pss: 1.5 kB\n",
    ],
)
def test_an_invalid_rollup_reports_no_pss(worker, monkeypatch, content):
    rollup(monkeypatch, content)

    assert worker.pss_bytes is None


def test_a_missing_rollup_reports_no_pss(worker, monkeypatch):
    def absent(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(builtins, "open", absent)

    assert worker.pss_bytes is None


def test_valid_pss_wins_over_a_much_larger_rss(tmp_path):
    subject = group(tmp_path)
    photo = {"rss_bytes": 900_000, "pss_bytes": 200_000}

    assert subject.get_memory_accounting(photo) == (200_000.0, "pss")
    assert subject.get_memory_occupancy_percent(photo) == 20.0
    assert subject.get_occupancy_percent(photo) == 20.0


def test_cpu_is_capacity_but_never_memory_occupancy(tmp_path):
    subject = group(tmp_path)
    photo = {"rss_bytes": 900_000, "pss_bytes": 200_000, "cpu_percent": 96.0}
    thermometer = SimpleNamespace(get_cpu_temperature_percent=lambda: 96.0)

    assert subject.get_memory_occupancy_percent(photo) == 20.0
    assert subject.get_occupancy_percent(photo, thermometer) == 96.0
    assert subject.get_occupancy_percent(photo) == 20.0


@pytest.mark.parametrize(
    "bad_pss", [None, -1, float("nan"), float("inf"), 10**1000, True, "3"]
)
def test_invalid_or_missing_pss_falls_back_to_rss(tmp_path, bad_pss):
    subject = group(tmp_path)
    photo = {"rss_bytes": 400_000, "pss_bytes": bad_pss}

    assert subject.get_memory_accounting(photo) == (400_000.0, "rss_fallback")
    assert subject.get_occupancy_percent(photo) == 40.0


def test_a_photo_with_no_valid_memory_gauge_is_unmeasured(tmp_path):
    subject = group(tmp_path)

    assert subject.get_memory_accounting({"pss_bytes": -1, "rss_bytes": "unknown"}) == (
        None,
        "unmeasured",
    )
    assert subject.get_occupancy_percent({"pss_bytes": -1, "rss_bytes": "unknown"}) == 0.0
