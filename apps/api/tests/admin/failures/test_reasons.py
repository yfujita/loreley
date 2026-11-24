import pytest

from loreley_api.admin.base.codes import UnavailableReason
from loreley_api.admin.failures import reason_of
from loreley_api.common.results import Failed


@pytest.mark.parametrize(
    ("failed", "expected"),
    [
        (Failed("unavailable", "store", "ConnectionError"), "store_unavailable"),
        (Failed("unavailable", "search_index", "ConnectionError"), "search_index_unavailable"),
        # タイムアウトを優先する(遅いのか止まっているのかを区別する)。対象を問わない。
        (Failed("timeout", "store", "ConnectionTimeout"), "timeout"),
        (Failed("timeout", "search_index", "ConnectionTimeout"), "timeout"),
    ],
)
def test_the_reason_code_follows_the_kind_and_the_target(failed: Failed, expected: str) -> None:
    assert reason_of(failed) == expected
    assert isinstance(reason_of(failed), UnavailableReason)
