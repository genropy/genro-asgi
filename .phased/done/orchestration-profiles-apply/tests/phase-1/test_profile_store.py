"""Contract skeletons for Phase 1 — ProfileStore (design section 8).

Destination: tests/test_profile_store.py (contract tests).
The test names and the wf:contract: lines are read-only; each red body is
replaced by a real implementation of exactly what those lines state.
"""

import pytest


def test_profile_name_validation():
    # wf:contract: names matching [A-Za-z0-9][A-Za-z0-9._-]{0,63} are accepted,
    # wf:contract: with or without a trailing .json; anything else raises
    # wf:contract: ProfileNameError (a ValueError), including path separators
    # wf:contract: and a leading dot.
    pytest.fail("phase 1 pending")


def test_symlink_refused_on_read_write_delete():
    # wf:contract: a profile path that is a symlink is refused on read, write
    # wf:contract: and delete — no operation follows the link.
    pytest.fail("phase 1 pending")


def test_size_limit_both_directions():
    # wf:contract: reading a file over 1 MiB raises ProfileContentError;
    # wf:contract: writing a payload whose serialized form exceeds 1 MiB raises
    # wf:contract: before touching the target file.
    pytest.fail("phase 1 pending")


def test_object_only_and_nonfinite_literals_rejected():
    # wf:contract: a stored file whose top level is not a JSON object raises
    # wf:contract: ProfileContentError; the literals Infinity, -Infinity and NaN
    # wf:contract: are rejected at read time via json.loads parse_constant.
    pytest.fail("phase 1 pending")


def test_atomic_write_and_allow_nan_false():
    # wf:contract: a write lands via a temp file renamed onto the target
    # wf:contract: (os.replace): a failed serialization leaves the previous
    # wf:contract: content intact; dumps uses allow_nan=False, so an untranslated
    # wf:contract: inf raises a noisy error and never produces an unreadable file.
    pytest.fail("phase 1 pending")


def test_missing_profile_raises_not_found():
    # wf:contract: reading or deleting a profile that does not exist raises
    # wf:contract: ProfileNotFoundError (a ValueError).
    pytest.fail("phase 1 pending")
