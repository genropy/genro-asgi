"""Contract skeletons for Phase 5 — apply_group_settings, contract half (matrix T6 T15 T27).

Destination: tests/test_apply_group_settings.py (contract tests).
The test names and the wf:contract: lines are read-only; each red body is
replaced by a real implementation of exactly what those lines state.
"""

import pytest


def test_recompute_independent_of_previous_profile():
    # wf:contract: T6 — apply(P2) after apply(P1) equals apply(P2) alone, key by
    # wf:contract: key: every apply recomposes defaults ⊕ recipe_settings ⊕
    # wf:contract: profile ⊕ env_settings; a key present in P1 and absent in P2
    # wf:contract: falls back to env, recipe or default, in that order (T5 sibling
    # wf:contract: at the HTTP level lives in phase 6).
    pytest.fail("phase 5 pending")


def test_derived_setpoint_worker_memory_max_percent():
    # wf:contract: T15 — applying worker_max_number without an explicit
    # wf:contract: worker_memory_max_percent makes the next judgment read
    # wf:contract: quota/N; an explicit value wins; removing the explicit value
    # wf:contract: restores the derivation.
    pytest.fail("phase 5 pending")


def test_generation_advances_on_idempotent_apply():
    # wf:contract: T27 — applying the same profile twice yields empty
    # wf:contract: changed_settings, outcome "applied", and a generation that
    # wf:contract: advances anyway: the audit counts successful attempts, not
    # wf:contract: differences.
    pytest.fail("phase 5 pending")
