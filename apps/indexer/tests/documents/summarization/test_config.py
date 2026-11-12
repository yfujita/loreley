"""`SummarizationConfig` の値の検証。"""

from dataclasses import replace

import pytest

from loreley_indexer.documents.summarization import SummarizationConfig
from tests.documents.summarization.conftest import MIN_RESCAN_INTERVAL_SECONDS


@pytest.mark.parametrize(
    "name",
    [
        "concurrency",
        "max_attempts",
        "queue_size",
        "rescan_page_size",
        "write_conflict_max_rereads",
        "input_max_chars",
    ],
)
def test_counts_below_one_are_rejected(config: SummarizationConfig, name: str) -> None:
    assert getattr(replace(config, **{name: 1}), name) == 1
    for invalid in (0, -1):
        with pytest.raises(ValueError, match=name):
            replace(config, **{name: invalid})


def test_rescan_max_interval_must_not_be_below_the_min_interval(
    config: SummarizationConfig,
) -> None:
    """上限が下限より短いと、間隔を伸ばすどころか縮めてしまう。"""
    at_min = replace(config, rescan_max_interval_seconds=MIN_RESCAN_INTERVAL_SECONDS)
    assert at_min.rescan_max_interval_seconds == MIN_RESCAN_INTERVAL_SECONDS

    with pytest.raises(ValueError, match="rescan_max_interval_seconds"):
        replace(config, rescan_max_interval_seconds=MIN_RESCAN_INTERVAL_SECONDS - 0.1)
