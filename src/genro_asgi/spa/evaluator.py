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

"""OccupancyEvaluator — turns a worker's metrics window into an occupancy in [0, 1].

The commander archives, per worker, a window of raw occupancy readings (each row
``{ts, report, forward}``, see ``UserStickyCommander.record_occupancy``) in that
worker's roster row. This object is the JUDGE half of the contract: it reads the
window through ``commander.worker_window`` and answers the questions the pool
policies ask — how full is this worker, from what, over what recent history, and
at what forward rate.

The occupancy formula: three components per row —

- ``memory`` = ``(rss - reusable) / (memory_limit_mb * 1MB)`` clamped to
  [0, 1], present ONLY when the reading has an ``rss`` (``/proc`` present) AND
  a ``memory_limit_mb`` is configured — the ``reusable`` gauge is the free
  bytes the C heap still holds, so the numerator APPROXIMATES the live memory
  rather than the RSS ratchet (a main-arena gauge: the estimate's bounds are
  on ``row_components``); it counts as 0 when the reading has no ``reusable``
  (no glibc), degrading to the plain rss ratio. rss beyond the limit is the
  normal pre-restart state, and the judgment saturates at "full" (the raw
  gauges stay in the archived reports);
- ``cpu`` = ``min(cpu, 1.0)`` — the measured wall is one core (the GIL), so a
  single process saturates at 1.0;
- ``executor`` = ``min(busy / total, 1.0)`` of the dispatch thread pool — the
  pool's ``busy`` counts queued calls too (demand, not slots held), so past
  saturation the raw ratio exceeds 1; the judgment saturates at "full". The
  raw ``busy``/``total`` stay unclamped in the archived reports.

Each component is FIRST averaged over the last ``SMOOTHING_ROWS`` rows (absorbing
the transient spikes that dominate a naive read), THEN divided by its own TARGET
— the fraction of that resource a worker may hold before it stops admitting. The
result is the RATIO SPACE the pool policies live in: every component reads as
``component / target``, so 1.0 is "at the target" whatever the resource and the
components become commensurable.

Two readings are taken off those ratios:

- ``worker_saturation`` = their MAX — the GATE. The bottleneck answers "can I take
  another user?"; one component at its target closes the worker even if the
  others are idle;
- ``worker_load`` = their QUADRATIC MEAN — the QUANTITY. Ordering candidates wants
  the whole picture, not just the worst component, and the quadratic mean keeps
  the worst one dominant while the others still count.

A worker with no rows (just born) reads 0.0 on both — it admits.

Owned by the commander (semantic parent: ``self.commander``). The window depth
and the report shape are the commander's; this object never mutates them.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .commander import UserStickyCommander

__all__ = ["COMPONENT_NAMES", "SMOOTHING_ROWS", "OccupancyEvaluator"]

#: Bytes per configured megabyte of the memory limit.
_MB = 1024 * 1024

#: How many of the most recent window rows each component is averaged over
#: before the max is taken (~30s at the default 5s probe interval).
#: PROVISIONAL: it becomes configuration with the per-group config.
SMOOTHING_ROWS = 6

#: Every component a reading can carry — the only keys ``component_targets``
#: may name.
COMPONENT_NAMES = ("memory", "cpu", "executor")


class OccupancyEvaluator:
    """Reads a worker's metrics window and answers the pool policies' load questions.

    The commander builds one (``self.evaluator``) and reads its window archive
    through it. It computes, it never stores: every call reflects the window as
    it stands.
    """

    def __init__(
        self,
        commander: UserStickyCommander,
        *,
        admission_threshold: float = 0.8,
        component_targets: dict[str, float] | None = None,
    ) -> None:
        """Args:
        commander: the UserStickyCommander owning this evaluator (semantic parent).
        admission_threshold: the uniform target every component is judged against.
        component_targets: per-component overrides of that uniform target; keys
            must be in ``COMPONENT_NAMES`` and values in (0, 1].

        Raises:
            ValueError: on an unknown component key or a target outside (0, 1].
        """
        self.commander = commander
        self.targets = self.build_targets(admission_threshold, component_targets)

    def build_targets(
        self, admission_threshold: float, component_targets: dict[str, float] | None
    ) -> dict[str, float]:
        """The per-component targets: the uniform default under the overrides."""
        overrides = dict(component_targets or {})
        unknown = set(overrides) - set(COMPONENT_NAMES)
        if unknown:
            raise ValueError(
                f"unknown component target {sorted(unknown)}: "
                f"known components are {list(COMPONENT_NAMES)}"
            )
        for name, value in [("admission_threshold", admission_threshold), *overrides.items()]:
            if not 0.0 < value <= 1.0:
                raise ValueError(f"{name} target must be in (0, 1], got {value}")
        return {name: overrides.get(name, admission_threshold) for name in COMPONENT_NAMES}

    def worker_ratios(self, worker_id: str) -> dict[str, float]:
        """The averaged components divided by their targets — the ratio space.

        Empty when the worker has no measurable component in the window.
        """
        components = self.worker_components(worker_id)
        return {name: value / self.targets[name] for name, value in components.items()}

    def worker_saturation(self, worker_id: str) -> float:
        """The GATE reading: the max of the worker's component ratios.

        1.0 is "at the target" — the bottleneck decides whether the worker still
        admits. 0.0 when the worker has no rows in the window (just born).
        """
        ratios = self.worker_ratios(worker_id)
        if not ratios:
            return 0.0
        return max(ratios.values())

    def worker_load(self, worker_id: str) -> float:
        """The QUANTITY reading: the quadratic mean of the worker's component ratios.

        The whole picture rather than the worst component alone — what orders
        candidates when several still admit. 0.0 with no rows in the window.
        """
        ratios = self.worker_ratios(worker_id)
        if not ratios:
            return 0.0
        return math.sqrt(sum(value * value for value in ratios.values()) / len(ratios))

    def worker_components(self, worker_id: str) -> dict[str, float]:
        """The averaged components present for this worker (memory/cpu/executor).

        Each component is averaged over the last ``SMOOTHING_ROWS`` rows, counting
        only the rows where that component is present (memory needs both an ``rss``
        reading and a configured limit). A component with no contributing row is
        absent from the dict; an empty dict means no rows at all (or none carried
        any measurable component).
        """
        rows = self.recent_rows(worker_id)
        if not rows:
            return {}
        sums: dict[str, float] = {}
        counts: dict[str, int] = {}
        for row in rows:
            for name, value in self.row_components(row.get("report") or {}).items():
                sums[name] = sums.get(name, 0.0) + value
                counts[name] = counts.get(name, 0) + 1
        return {name: sums[name] / counts[name] for name in sums}

    def worker_history(self, worker_id: str) -> list[float]:
        """Per-row saturation across the WHOLE window (the max RATIO of each row).

        One value per archived row, in order — the histogram the monitor draws,
        on the same axis as ``worker_saturation``: 1.0 is "at the target", and a row
        past it reads over 1.0. A row with no measurable component contributes
        0.0.
        """
        window = self.commander.worker_window(worker_id)
        if not window:
            return []
        history: list[float] = []
        for row in window:
            components = self.row_components(row.get("report") or {})
            ratios = [value / self.targets[name] for name, value in components.items()]
            history.append(max(ratios) if ratios else 0.0)
        return history

    def worker_rates(self, worker_id: str) -> dict[str, float | None]:
        """Forward ``rps`` and ``latency_ms`` from the counter DELTAS across the window.

        Computed from the forward-counter snapshots frozen in the first and last
        rows of the window: ``rps`` is the request delta over the wall time
        between those rows (0.0 when nothing completed), ``latency_ms`` the mean
        forward time over that same delta, None when no request completed. Both
        are None with fewer than two rows (no interval to diff). The mean is the
        legacy formula kept verbatim: the SECONDS delta accumulates every
        forward, errors included, while the REQUEST delta counts completions
        only — behind many transport failures the figure inflates accordingly.
        """
        window = self.commander.worker_window(worker_id)
        if not window or len(window) < 2:
            return {"rps": None, "latency_ms": None}
        rows = list(window)
        first, last = rows[0], rows[-1]
        elapsed = last["ts"] - first["ts"]
        req_delta = last["forward"]["requests"] - first["forward"]["requests"]
        sec_delta = last["forward"]["seconds"] - first["forward"]["seconds"]
        rps = req_delta / elapsed if elapsed > 0 else None
        latency_ms = (sec_delta / req_delta) * 1000.0 if req_delta > 0 else None
        return {"rps": rps, "latency_ms": latency_ms}

    def recent_rows(self, worker_id: str) -> list[dict[str, Any]]:
        """The last ``SMOOTHING_ROWS`` rows of the worker's window (fewer if younger)."""
        window = self.commander.worker_window(worker_id)
        if not window:
            return []
        return list(window)[-SMOOTHING_ROWS:]

    def row_components(self, report: dict[str, Any]) -> dict[str, float]:
        """The occupancy components measurable in ONE raw reading.

        ``memory`` judges the ESTIMATED live memory ``rss - reusable`` against
        the limit, clamped to [0, 1] — beyond the limit is still "full", and
        the 0 floor holds where the free heap the worker just trimmed still
        counts in ``reusable`` (an under-read). The estimate is bounded on the
        other side too: the gauge reads the allocator's MAIN arena only, so
        free bytes in a threaded worker's secondary arenas stay invisible and
        the subtraction can OVER-read live memory on busy workers (accuracy
        limit recorded for the #5 admission policy). A missing or None
        ``reusable`` counts as 0, so the reading degrades to the plain rss
        ratio. Present only when the reading has an ``rss`` and the commander
        has a configured ``memory_limit_mb``;
        ``cpu`` (clamped to one core) only when the
        reading carries a cpu fraction (None on the worker's first tick);
        ``executor`` (clamped to 1.0 — the pool's ``busy`` counts queued work)
        only when the pool has a non-zero ``total``.
        """
        components: dict[str, float] = {}
        limit = self.commander.memory_limit_mb
        rss = report.get("rss")
        if rss is not None and limit:
            live = rss - (report.get("reusable") or 0)
            components["memory"] = max(0.0, min(live / (limit * _MB), 1.0))
        cpu = report.get("cpu")
        if cpu is not None:
            components["cpu"] = min(cpu, 1.0)
        executor = report.get("executor") or {}
        total = executor.get("total") or 0
        if total:
            components["executor"] = min(executor.get("busy", 0) / total, 1.0)
        return components
