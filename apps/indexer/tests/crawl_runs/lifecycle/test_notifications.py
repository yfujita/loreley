"""開始通知・終了通知の入力の形式検証とダイジェスト(arch 9.5、api 4.1・4.4。案 14、K25)。

`ttl`・`ratio_threshold`・`min_delete_count` は型だけを検証し、範囲は検証しない(確定事項)。
"""

import hashlib
import math
from datetime import UTC, datetime

import pytest

from loreley_indexer.crawl_runs import FinishNotification, StartNotification
from loreley_indexer.crawl_runs.lifecycle import FinishOutcome
from tests.crawl_runs.factories import (
    CRAWL_STARTED_AT,
    hex_id,
    make_failed_finish,
    make_finish,
    make_start,
)

# --- 開始通知 ---


def test_a_valid_start_notification_defaults_the_optional_flags_to_false() -> None:  # K37
    notification = StartNotification(
        crawl_id="c1",
        source_id="s1",
        crawl_started_at=CRAWL_STARTED_AT,
        ttl=60,
        ratio_threshold=0.5,
        min_delete_count=1,
    )
    assert (notification.force_delete, notification.rewrite_mode) == (False, False)


@pytest.mark.parametrize("ratio_threshold", [math.nan, math.inf, -math.inf])
def test_non_finite_ratio_threshold_is_malformed(ratio_threshold: float) -> None:  # 案 14
    with pytest.raises(ValueError, match="ratio_threshold"):
        make_start(ratio_threshold=ratio_threshold)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crawl_id", ""),
        ("crawl_id", None),
        ("source_id", ""),
        ("crawl_started_at", datetime(2026, 11, 9, 1, 0, 0)),  # タイムゾーンなし
        ("crawl_started_at", "2026-11-09T01:00:00Z"),
        ("ttl", 1.5),
        ("ttl", "3600"),
        ("ttl", True),
        ("ratio_threshold", "0.2"),
        ("ratio_threshold", True),
        ("min_delete_count", 1.0),
        ("min_delete_count", False),
        ("force_delete", 1),
        ("force_delete", "true"),
        ("rewrite_mode", "false"),
        ("rewrite_mode", 0),
    ],
)
def test_start_notification_fields_with_the_wrong_type_are_malformed(
    field: str, value: object
) -> None:  # D-94(f)
    with pytest.raises(ValueError, match=field):
        make_start(**{field: value})


@pytest.mark.parametrize(
    "overrides",
    [
        {"ttl": 0},
        {"ttl": -1},
        {"ratio_threshold": 1.5},  # 100% 以上
        {"ratio_threshold": -0.1},  # 負の値
        {"ratio_threshold": 1},  # 整数のしきい値も数値として受ける
        {"min_delete_count": -5},
    ],
)
def test_ranges_are_not_validated(overrides: dict[str, object]) -> None:  # 案 14、D-52〜D-54
    make_start(**overrides)


def test_validation_messages_never_contain_the_input_value() -> None:
    with pytest.raises(ValueError) as error:
        make_start(ttl="SECRET-SENTINEL")
    assert "SECRET-SENTINEL" not in str(error.value)


# --- 終了通知の形式 ---


def test_enumeration_completed_requires_the_counts_and_both_id_lists() -> None:
    for name in ("enumerated_count", "skipped_document_ids", "oversize_document_ids"):
        with pytest.raises(ValueError, match=name):
            make_finish(**{name: None})


@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_failed_and_cancelled_may_omit_the_counts_and_id_lists(outcome: FinishOutcome) -> None:
    notification = make_failed_finish(outcome)
    assert notification.enumerated_count is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("crawl_id", ""),
        ("source_id", ""),
        ("outcome", "enumeration_completed"),
        ("finished_at", datetime(2026, 11, 9, 1, 12, 30)),
        ("enumerated_count", "3"),
        ("enumerated_count", True),
        ("skipped_document_ids", "a" * 64),  # 文字列は一覧ではない
        ("skipped_document_ids", ["not-a-hex-id"]),
        ("skipped_document_ids", [hex_id(10).upper()]),
        ("oversize_document_ids", [1]),
    ],
)
def test_finish_notification_with_a_malformed_field_is_rejected(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        make_finish(**{field: value})


# --- ダイジェスト(K25、D-91(f)) ---


def test_digest_is_a_sha256_hex_string_and_stable() -> None:
    digest = make_finish().digest()
    assert len(digest) == 64
    assert digest == make_finish().digest()


def test_digest_ignores_finished_at() -> None:
    later = make_finish(finished_at=datetime(2030, 1, 1, tzinfo=UTC))
    assert later.digest() == make_finish().digest()


def test_digest_does_not_include_source_id() -> None:  # K32
    assert make_finish(source_id="src-other").digest() == make_finish().digest()


def test_digest_ignores_the_order_and_duplicates_of_the_id_lists() -> None:  # D-91(f)
    base = make_finish(skipped_document_ids=(hex_id(1), hex_id(2)), oversize_document_ids=())
    reordered = make_finish(skipped_document_ids=(hex_id(2), hex_id(1)), oversize_document_ids=())
    duplicated = make_finish(
        skipped_document_ids=[hex_id(1), hex_id(2), hex_id(1)], oversize_document_ids=[]
    )
    assert reordered.digest() == base.digest()
    assert duplicated.digest() == base.digest()


@pytest.mark.parametrize(
    "overrides",
    [
        {"enumerated_count": 1204},
        {"skipped_document_ids": (hex_id(1),)},
        {"skipped_document_ids": (hex_id(1), hex_id(2), hex_id(3))},
        {"oversize_document_ids": (hex_id(9),)},
        # 同じ ID でも、どちらの一覧にあるかで内容が違う
        {"skipped_document_ids": (), "oversize_document_ids": (hex_id(1), hex_id(2))},
    ],
)
def test_digest_differs_when_the_content_differs(overrides: dict[str, object]) -> None:  # D-91(b)
    assert make_finish(**overrides).digest() != make_finish().digest()


def test_digest_differs_by_outcome() -> None:  # D-91(n)
    assert (
        make_failed_finish(FinishOutcome.FAILED).digest()
        != make_failed_finish(FinishOutcome.CANCELLED).digest()
    )


def test_digest_distinguishes_an_omitted_list_from_an_empty_one() -> None:
    omitted = make_failed_finish()
    empty = make_failed_finish(skipped_document_ids=(), oversize_document_ids=())
    assert omitted.digest() != empty.digest()


def test_digest_has_a_fixed_value_for_a_known_input() -> None:
    """正規化の形(キー名・区切り・順序)を固定する。変えると保存済みの再送比較が壊れる。"""
    notification = FinishNotification(
        crawl_id="c",
        source_id="s",
        outcome=FinishOutcome.ENUMERATION_COMPLETED,
        finished_at=CRAWL_STARTED_AT,
        enumerated_count=2,
        skipped_document_ids=[hex_id(2), hex_id(1)],
        oversize_document_ids=[],
    )
    canonical = (
        '{"enumerated_count":2,"outcome":"enumeration_completed",'
        f'"oversize_document_ids":[],"skipped_document_ids":["{hex_id(1)}","{hex_id(2)}"]}}'
    )
    assert notification.digest() == hashlib.sha256(canonical.encode()).hexdigest()
