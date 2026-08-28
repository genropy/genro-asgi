"""Contract skeletons for Phase 6 — audit destinations (matrix T22; design section 9).

Destination: tests/orchestration/test_orchestration_audit_destinations.py
(implementation tests, per project rule 10).
The test names and the wf:contract: lines are read-only; each red body is
replaced by a real implementation of exactly what those lines state.
"""

import pytest


def test_boot_failure_logs_on_spa_app_logger():
    # wf:contract: T22a — a failed boot logs on the SpaApplication module logger
    # wf:contract: (caplog) with the violations, and leaves NO orchestration log
    # wf:contract: line: the commander does not exist yet.
    pytest.fail("phase 6 pending")


def test_reload_handler_errors_audited_as_rejected():
    # wf:contract: T22b — a reload of a missing or corrupt profile that reaches
    # wf:contract: the handler leaves a commander log_order line with outcome
    # wf:contract: "rejected: ...".
    pytest.fail("phase 6 pending")


def test_request_parser_400_is_not_orchestration_audit():
    # wf:contract: T22c — malformed JSON on the body is answered 400 by the
    # wf:contract: request layer and leaves NO orchestration log line: it is the
    # wf:contract: single exclusion from the orchestration audit.
    pytest.fail("phase 6 pending")
