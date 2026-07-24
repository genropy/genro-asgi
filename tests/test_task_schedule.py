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

"""Tests for tasks.schedule (core 1e Phase 4): pure cron/every/at parsing.

No I/O, no server: pure functions and ``CronSpec``. Cron matches are checked by
decoding the returned epoch back to a local ``datetime`` and asserting the
field values, so the tests are timezone-agnostic (the parser evaluates in local
time, like system cron).
"""

from __future__ import annotations

from datetime import datetime

import pytest

from genro_asgi.tasks.schedule import CronSpec, next_run, parse_at, parse_every


class TestParseEvery:
    """``"<n><unit>"`` -> seconds, with strict validation."""

    def test_units(self) -> None:
        assert parse_every("30s") == 30
        assert parse_every("15m") == 15 * 60
        assert parse_every("2h") == 2 * 3600
        assert parse_every("1d") == 86400

    def test_whitespace_tolerated(self) -> None:
        assert parse_every("  45s ") == 45

    @pytest.mark.parametrize("bad", ["", "s", "10", "10x", "1.5h", "-5m"])
    def test_malformed_raises(self, bad: str) -> None:
        with pytest.raises(ValueError):
            parse_every(bad)

    def test_zero_interval_raises(self) -> None:
        with pytest.raises(ValueError, match="zero interval"):
            parse_every("0s")


class TestParseAt:
    """A list of ISO timestamps -> sorted epoch seconds."""

    def test_sorted_epochs(self) -> None:
        got = parse_at(["2030-01-02T00:00:00", "2030-01-01T00:00:00"])
        assert got == sorted(got)
        assert len(got) == 2

    def test_empty_list(self) -> None:
        assert parse_at([]) == []

    def test_not_a_list_raises(self) -> None:
        with pytest.raises(ValueError, match="want a list"):
            parse_at("2030-01-01T00:00:00")

    def test_bad_timestamp_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid at timestamp"):
            parse_at(["not-a-date"])


class TestCronSpec:
    """5-field cron parsing with ``* , - /`` and the dom/dow OR rule."""

    def test_field_count_enforced(self) -> None:
        with pytest.raises(ValueError, match="5 fields"):
            CronSpec("* * * *")

    def test_wildcards(self) -> None:
        spec = CronSpec("* * * * *")
        assert spec.minutes == set(range(60))
        assert spec.hours == set(range(24))
        assert not spec.dom_restricted and not spec.dow_restricted

    def test_list_range_step(self) -> None:
        spec = CronSpec("0,30 9-17 * * *")
        assert spec.minutes == {0, 30}
        assert spec.hours == set(range(9, 18))

    def test_step_opens_range_to_top(self) -> None:
        # "*/15" and "0/15" both -> {0,15,30,45}
        assert CronSpec("*/15 * * * *").minutes == {0, 15, 30, 45}
        assert CronSpec("0/15 * * * *").minutes == {0, 15, 30, 45}

    def test_dow_7_folds_onto_sunday(self) -> None:
        assert CronSpec("0 0 * * 7").weekdays == {0}

    @pytest.mark.parametrize("bad", ["61 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *"])
    def test_out_of_range_raises(self, bad: str) -> None:
        with pytest.raises(ValueError, match="out of range"):
            CronSpec(bad)

    def test_bad_step_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid cron step"):
            CronSpec("*/0 * * * *")

    def test_next_after_daily(self) -> None:
        # every day at 07:30 — the next match is a 07:30 local instant
        after = datetime(2030, 6, 15, 8, 0, 0).timestamp()  # past 07:30 today
        got = datetime.fromtimestamp(CronSpec("30 7 * * *").next_after(after))
        assert (got.hour, got.minute) == (7, 30)
        assert got.date() == datetime(2030, 6, 16).date()   # -> tomorrow

    def test_next_after_strictly_after(self) -> None:
        base = datetime(2030, 6, 15, 7, 30, 0)
        got = CronSpec("30 7 * * *").next_after(base.timestamp())
        assert got > base.timestamp()                       # never returns "now"

    def test_dom_or_dow_when_both_restricted(self) -> None:
        # "0 0 13 * 5" matches day-13 OR any Friday (system-cron OR rule)
        spec = CronSpec("0 0 13 * 5")
        assert spec.dom_restricted and spec.dow_restricted
        got = datetime.fromtimestamp(spec.next_after(datetime(2030, 6, 1).timestamp()))
        assert got.day == 13 or (got.weekday() + 1) % 7 == 5

    def test_impossible_date_raises(self) -> None:
        with pytest.raises(ValueError, match="no occurrence"):
            CronSpec("0 0 31 2 *").next_after(datetime(2030, 1, 1).timestamp())


class TestNextRun:
    """Dispatch across the three kinds + the exhausted ``at`` -> None."""

    def test_every_adds_interval(self) -> None:
        now = 1_000_000.0
        assert next_run("every", "15m", now) == now + 15 * 60

    def test_cron_delegates(self) -> None:
        now = datetime(2030, 6, 15, 8, 0, 0).timestamp()
        got = next_run("cron", "30 7 * * *", now)
        assert got is not None and got > now

    def test_at_returns_first_future(self) -> None:
        now = datetime(2030, 6, 15).timestamp()
        got = next_run("at", ["2030-06-14T00:00:00", "2030-06-16T00:00:00"], now)
        assert got == datetime(2030, 6, 16).timestamp()

    def test_at_exhausted_returns_none(self) -> None:
        now = datetime(2030, 6, 15).timestamp()
        assert next_run("at", ["2030-06-14T00:00:00"], now) is None

    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown schedule kind"):
            next_run("weekly", "x", 0.0)
