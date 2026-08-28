"""Contract skeletons for Phase 3 — GroupPolicy (design sections 4, 6, 8; matrix T7 T16 T17 T25).

Destination: tests/test_group_policy.py (contract tests).
The test names and the wf:contract: lines are read-only; each red body is
replaced by a real implementation of exactly what those lines state.
"""

import pytest


def test_defaults_materialized_from_empty_settings():
    # wf:contract: T7 — GroupPolicy.from_settings({}) yields a COMPLETE policy
    # wf:contract: whose values equal today's GroupHandler constructor defaults;
    # wf:contract: a sparse settings dict fills the absent keys with those same
    # wf:contract: defaults, never a KeyError.
    pytest.fail("phase 3 pending")


def test_validation_rejects_and_lists_all_violations():
    # wf:contract: T16 — from_settings collects EVERY violation into one error:
    # wf:contract: unknown keys; structural keys with the dedicated message
    # wf:contract: "structural, not a profile key"; bool passed as a number
    # wf:contract: (rejected before the numeric check); NaN/Infinity values;
    # wf:contract: percentages outside [0, 100]; memory_max_percent 0 and above
    # wf:contract: 100 both rejected (0 < v <= 100); negative times; non-integer
    # wf:contract: counts; worker_max_number <= 0; a broken CPU band
    # wf:contract: (rearm >= grow); cross rules on the COMPLETE resulting policy:
    # wf:contract: close_occupancy >= occupancy, occupancy > restart_occupancy,
    # wf:contract: reception_reserved >= occupancy, new_user_occupancy <= 0.
    # wf:contract: A single violation means NO policy object is produced.
    pytest.fail("phase 3 pending")


def test_null_means_unlimited_or_off():
    # wf:contract: T17 — worker_max_users null becomes math.inf internally and
    # wf:contract: null again in to_settings(); user_idle_freeze_minutes null the
    # wf:contract: same; cpu_grow_percent null becomes None (policy off);
    # wf:contract: to_settings() output is JSON-safe: json.dumps(...,
    # wf:contract: allow_nan=False) never raises on it.
    pytest.fail("phase 3 pending")


def test_worker_memory_max_percent_explicit_or_derived():
    # wf:contract: the property renders the explicit value when set (it may
    # wf:contract: exceed 100), else 100.0 / worker_max_number; removing the
    # wf:contract: explicit key restores the derivation.
    pytest.fail("phase 3 pending")


def test_profile_version_reserved_key():
    # wf:contract: T25 — profile_version absent is accepted as 1; the value 1 is
    # wf:contract: accepted; any other value is rejected explicitly; the key
    # wf:contract: never enters the setpoints nor to_settings() output.
    pytest.fail("phase 3 pending")
