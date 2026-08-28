"""Contract skeletons for Phase 7 — grammar words on the application element (design step 7).

Destination: tests/test_spa_profile_grammar.py (contract tests).
The test names and the wf:contract: lines are read-only; each red body is
replaced by a real implementation of exactly what those lines state.
"""

import pytest


def test_application_element_accepts_profile_words():
    # wf:contract: a recipe writes profiles_path, profile_name and
    # wf:contract: orchestration_control on the APPLICATION element of the spa
    # wf:contract: app and they reach the SpaApplication kwargs; they are NOT
    # wf:contract: words of the commander element.
    pytest.fail("phase 7 pending")


def test_env_settings_is_not_grammar():
    # wf:contract: env_settings is not writable from the grammar: it stays a
    # wf:contract: runtime dict passed by the Python recipe.
    pytest.fail("phase 7 pending")
