"""`RegistrationConfig` の値の検証。"""

from dataclasses import replace

import pytest

from loreley_indexer.documents import RegistrationConfig

VALID = RegistrationConfig(
    max_raw_bytes=1024,
    write_conflict_max_rereads=3,
    max_last_seen_ids=5,
    summary_enabled=False,
)


@pytest.mark.parametrize(
    "name", ["max_raw_bytes", "write_conflict_max_rereads", "max_last_seen_ids"]
)
def test_counts_below_one_are_rejected(name: str) -> None:
    assert getattr(replace(VALID, **{name: 1}), name) == 1
    for invalid in (0, -1):
        with pytest.raises(ValueError, match=name):
            replace(VALID, **{name: invalid})
