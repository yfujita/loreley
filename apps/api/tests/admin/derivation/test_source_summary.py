"""`last_completed_at`・`delete_job` の元(C 5.5)。"""

import pytest

from loreley_api.admin.base.codes import SourceStatus
from loreley_api.admin.derivation.source_summary import delete_job_of, last_completed_at_of


@pytest.mark.parametrize(
    ("epoch_millis", "expected"),
    [
        (None, None),
        (0, "1970-01-01T00:00:00.000Z"),
        # ミリ秒の端数がずれない(浮動小数の秒に直すと `.122` になる値)。
        (1_700_000_000_123, "2023-11-14T22:13:20.123Z"),
        (1_700_000_000_999, "2023-11-14T22:13:20.999Z"),
        (1_795_478_400_000, "2026-11-24T00:00:00.000Z"),
        # 範囲を超える値は読めない(`null`)。
        (10**18, None),
        (-(10**18), None),
    ],
)
def test_the_epoch_milliseconds_become_a_utc_millisecond_string(
    epoch_millis: int | None, expected: str | None
) -> None:
    assert last_completed_at_of(epoch_millis) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [(SourceStatus.DELETING, "latest-delete"), (SourceStatus.ACTIVE, None), (None, None)],
)
def test_the_delete_job_is_used_only_while_the_source_is_deleting(
    status: SourceStatus | None, expected: str | None
) -> None:
    assert delete_job_of(status, "latest-delete") == expected


def test_a_deleting_source_without_a_delete_job_has_none() -> None:
    assert delete_job_of(SourceStatus.DELETING, None) is None
