"""`LifecycleConfig` の値の検証。"""

from dataclasses import replace

import pytest

from loreley_indexer.crawl_runs import LifecycleConfig

VALID = LifecycleConfig(
    skip_oversize_id_limit=5, write_conflict_max_rereads=3, deletion_retention_count=2
)


@pytest.mark.parametrize(
    "name", ["skip_oversize_id_limit", "write_conflict_max_rereads", "deletion_retention_count"]
)
def test_counts_below_one_are_rejected(name: str) -> None:
    assert getattr(replace(VALID, **{name: 1}), name) == 1
    for invalid in (0, -1):
        with pytest.raises(ValueError, match=name):
            replace(VALID, **{name: invalid})
