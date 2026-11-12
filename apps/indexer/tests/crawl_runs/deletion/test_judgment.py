"""削除判定の純粋な部分(arch 9.3、9.8)。"""

import math
from datetime import UTC, datetime, timedelta

import pytest

from loreley_indexer.crawl_runs.deletion.config import DeletionConfig
from loreley_indexer.crawl_runs.deletion.judgment import (
    MAX_TTL_SECONDS,
    Measurements,
    is_expired,
    passes_ratio_rule,
    progress_update,
    ttl_cutoff,
)
from tests.crawl_runs.factories import make_result

NOW = datetime(2026, 11, 11, 0, 0, 0, tzinfo=UTC)
DAY = 86_400


def ratio_rule(target_count: int, denominator: int, **overrides: float) -> bool:
    arguments = {"min_delete_count": 10, "ratio_threshold": 0.2, **overrides}
    return passes_ratio_rule(target_count=target_count, denominator=denominator, **arguments)  # type: ignore[arg-type]


# --- TTL(判定時刻 - TTL) ---


def test_cutoff_is_now_minus_ttl() -> None:
    assert ttl_cutoff(NOW, 3 * DAY) == NOW - timedelta(days=3)


def test_a_document_is_expired_only_when_last_seen_plus_ttl_is_before_now() -> None:
    ttl = 3 * DAY
    boundary = NOW - timedelta(seconds=ttl)
    assert not is_expired(boundary, now=NOW, ttl_seconds=ttl)  # last_seen_at + TTL == now は対象外
    assert is_expired(boundary - timedelta(milliseconds=1), now=NOW, ttl_seconds=ttl)
    assert not is_expired(boundary + timedelta(milliseconds=1), now=NOW, ttl_seconds=ttl)


@pytest.mark.parametrize("ttl", [10**18, -(10**18)])
def test_out_of_range_ttl_does_not_overflow_the_date_arithmetic(ttl: int) -> None:
    """範囲は検証しない(9.13(9))ので、巨大な値でも例外にならず、約 100 年に丸めて判定する。"""
    cutoff = ttl_cutoff(NOW, ttl)
    assert abs(cutoff - NOW) == timedelta(seconds=MAX_TTL_SECONDS)


def test_a_huge_ttl_expires_nothing() -> None:
    assert not is_expired(NOW - timedelta(days=365), now=NOW, ttl_seconds=10**18)


# --- 割合ルール(判定 1・2) ---


def test_target_at_or_below_the_minimum_count_is_deleted_whatever_the_ratio() -> None:  # D-2
    assert ratio_rule(10, 10)  # T == 最小件数
    assert ratio_rule(1, 1)
    assert not ratio_rule(11, 11)  # 最小件数を超え、率 100%


def test_ratio_at_the_threshold_is_deleted_and_above_it_is_not() -> None:  # D-3、D-1
    assert ratio_rule(20, 100)  # 20% == しきい値
    assert not ratio_rule(21, 100)


def test_threshold_zero_deletes_only_up_to_the_minimum_count() -> None:
    assert ratio_rule(10, 1_000, ratio_threshold=0.0)
    assert not ratio_rule(11, 1_000, ratio_threshold=0.0)


def test_out_of_range_thresholds_follow_the_known_limitation() -> None:  # D-53、D-54
    assert ratio_rule(500, 500, ratio_threshold=1.5)  # 100% 以上: 割合ルールが働かない
    assert not ratio_rule(11, 1_000, ratio_threshold=-0.1)  # 負: 削除しない側
    assert ratio_rule(10, 1_000, ratio_threshold=-0.1)  # ただし最小件数ルールが先


def test_a_nan_threshold_falls_on_the_side_of_not_deleting() -> None:  # D-55(定義なし。安全側)
    assert not ratio_rule(11, 20, ratio_threshold=math.nan)


def test_a_zero_denominator_with_targets_does_not_divide_and_does_not_delete() -> None:
    assert not ratio_rule(11, 0)


# --- 数値の記録 ---


def test_measurements_overwrite_only_the_values_they_hold() -> None:
    record = make_result(n_seen=1, e_missing=2, target_count=3, denominator=4)

    recorded = Measurements(n_seen=10, denominator=40).recorded_in(record)

    assert (recorded.n_seen, recorded.e_missing) == (10, 2)
    assert (recorded.target_count, recorded.denominator) == (3, 40)


def test_progress_update_records_the_measurements_and_the_deleted_count() -> None:
    update = progress_update(Measurements(n_seen=5), deleted_count=7)

    recorded = update(make_result())

    assert (recorded.n_seen, recorded.deleted_count) == (5, 7)


def test_progress_update_without_a_count_keeps_the_recorded_deleted_count() -> None:
    recorded = progress_update(Measurements(n_seen=5))(make_result(deleted_count=4))

    assert recorded.deleted_count == 4


# --- 設定 ---


def make_config(**overrides: float) -> DeletionConfig:
    values: dict[str, float] = {
        "batch_size": 1,
        "max_deletion_targets": 1,
        "search_after_page_size": 1,
        "poll_interval_seconds": 1.0,
        "poll_backoff_max_seconds": 1.0,
        "delete_error_retry_attempts": 1,
        "retry_backoff_initial_seconds": 1.0,
        "retry_backoff_factor": 1.0,
        "retry_backoff_max_seconds": 1.0,
        "write_conflict_max_rereads": 1,
        "discard_max_attempts": 1,
        "delete_by_query_max_reruns": 1,
    }
    return DeletionConfig(**{**values, **overrides})  # type: ignore[arg-type]


def test_config_accepts_the_minimum_values() -> None:
    assert make_config().batch_size == 1


@pytest.mark.parametrize(
    "name",
    [
        "batch_size",
        "max_deletion_targets",
        "search_after_page_size",
        "delete_error_retry_attempts",
        "write_conflict_max_rereads",
        "discard_max_attempts",
        "delete_by_query_max_reruns",
    ],
)
def test_config_rejects_zero_counts_that_would_disable_a_limit(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        make_config(**{name: 0})


@pytest.mark.parametrize(
    "name",
    [
        "poll_interval_seconds",
        "poll_backoff_max_seconds",
        "retry_backoff_initial_seconds",
        "retry_backoff_max_seconds",
    ],
)
def test_config_rejects_non_positive_durations(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        make_config(**{name: 0})


def test_config_rejects_a_backoff_factor_that_shrinks_the_wait() -> None:
    with pytest.raises(ValueError, match="retry_backoff_factor"):
        make_config(retry_backoff_factor=0.9)


def test_config_rejects_a_poll_backoff_maximum_below_the_poll_interval() -> None:
    with pytest.raises(ValueError, match="poll_backoff_max_seconds"):
        make_config(poll_interval_seconds=2.0, poll_backoff_max_seconds=1.9)


def test_config_accepts_a_poll_backoff_maximum_equal_to_the_poll_interval() -> None:
    config = make_config(poll_interval_seconds=2.0, poll_backoff_max_seconds=2.0)

    assert config.poll_backoff_max_seconds == 2.0
