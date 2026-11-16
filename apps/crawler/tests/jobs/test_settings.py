"""`jobs` 直下の設定(`owner` の検査と仮値)。"""

import pytest

from loreley_crawler.jobs import OWNER_MAX_BYTES, JobsSettings
from loreley_crawler.jobs.locks import HeartbeatSettings


def test_the_defaults_are_the_documented_provisional_values() -> None:
    settings = JobsSettings(owner="crawler-1")

    assert settings.heartbeat == HeartbeatSettings()
    assert settings.runner_scan_interval_seconds == 5.0
    assert settings.admitting_lock_grace_seconds == 60.0  # architecture 11章


def test_the_owner_may_be_up_to_256_bytes_of_utf8() -> None:
    JobsSettings(owner="a" * OWNER_MAX_BYTES)
    JobsSettings(owner="あ" * (OWNER_MAX_BYTES // 3))  # 3 バイト文字 85 個 = 255 バイト


@pytest.mark.parametrize(
    "owner",
    [
        "",
        "a" * (OWNER_MAX_BYTES + 1),
        "あ" * (OWNER_MAX_BYTES // 3 + 1),  # 文字数は少ないが 256 バイトを超える
        "crawler\n1",
        "crawler\x00",
        "crawler\x7f",
        "crawler\ud800",  # UTF-8 にできない
    ],
)
def test_an_invalid_owner_is_rejected(owner: str) -> None:
    with pytest.raises(ValueError):
        JobsSettings(owner=owner)


@pytest.mark.parametrize("field", ["runner_scan_interval_seconds", "admitting_lock_grace_seconds"])
@pytest.mark.parametrize("value", [0, -1.0])
def test_the_durations_must_be_positive(field: str, value: float) -> None:
    with pytest.raises(ValueError):
        JobsSettings(owner="crawler-1", **{field: value})
