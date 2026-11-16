"""起動時の整合性検査(architecture 12章 #39 の単体部分。CM-P-25、CM-U-9 の仮置き(a))。

実 Indexer に対して、上限ちょうどの値でバッチ登録・`last-seen` が 400 にならないことの確認は、
統合テスト(スコープ外)。
"""

from dataclasses import replace

import pytest

from loreley_crawler.config import (
    CrawlerSizeLimits,
    IndexerLimits,
    LimitViolation,
    check_size_limits,
)

MIB = 1024 * 1024

# architecture 11章の仮値。
CRAWLER_DEFAULTS = CrawlerSizeLimits(
    max_raw_bytes=20 * MIB,
    batch_max_documents=20,
    batch_max_raw_bytes=32 * MIB,
    last_seen_max_ids=500,
    finish_id_list_warning_threshold=8_000,
)

# Indexer の既定値(Indexer README 3章。`apps/indexer/src/loreley_indexer/config.py`)。
INDEXER_DEFAULTS = IndexerLimits(
    max_raw_bytes=20 * MIB,
    max_batch_documents=50,
    max_batch_bytes=64 * MIB,
    max_request_body_bytes=100 * MIB,
    max_last_seen_ids=1_000,
    skip_oversize_id_limit=10_000,
)

ALL_UNSET = IndexerLimits()


def violations_of(crawler: CrawlerSizeLimits, indexer: IndexerLimits) -> list[LimitViolation]:
    return list(check_size_limits(crawler, indexer).violations)


def test_the_provisional_values_pass_against_the_indexer_defaults() -> None:
    result = check_size_limits(CRAWLER_DEFAULTS, INDEXER_DEFAULTS)
    assert result.violations == ()
    assert result.unchecked_limits == ()


@pytest.mark.parametrize(
    ("crawler_field", "indexer_field", "limit_name"),
    [
        ("max_raw_bytes", "max_raw_bytes", "MAX_RAW_BYTES"),
        ("batch_max_documents", "max_batch_documents", "MAX_BATCH_DOCUMENTS"),
        ("batch_max_raw_bytes", "max_batch_bytes", "MAX_BATCH_BYTES"),
        ("last_seen_max_ids", "max_last_seen_ids", "MAX_LAST_SEEN_IDS"),
        (
            "finish_id_list_warning_threshold",
            "skip_oversize_id_limit",
            "SKIP_OVERSIZE_ID_LIMIT",
        ),
    ],
)
def test_a_value_above_the_indexer_limit_is_a_violation_and_the_exact_limit_is_not(
    crawler_field: str, indexer_field: str, limit_name: str
) -> None:
    value = getattr(CRAWLER_DEFAULTS, crawler_field)
    at_limit = replace(INDEXER_DEFAULTS, **{indexer_field: value})
    just_below = replace(INDEXER_DEFAULTS, **{indexer_field: value - 1})

    assert violations_of(CRAWLER_DEFAULTS, at_limit) == []
    assert violations_of(CRAWLER_DEFAULTS, just_below) == [
        LimitViolation(crawler_field, value, limit_name, value - 1)
    ]


def test_the_batch_size_in_base64_must_fit_in_the_request_body_limit() -> None:
    # 32 MiB の原本は base64 後に約 42.67 MiB。
    request_body_limit = 42 * MIB
    indexer = replace(INDEXER_DEFAULTS, max_request_body_bytes=request_body_limit)

    [violation] = violations_of(CRAWLER_DEFAULTS, indexer)

    assert violation.item == "batch_max_raw_bytes_in_base64"
    assert violation.value == -(-32 * MIB * 4 // 3)
    assert violation.limit_name == "MAX_REQUEST_BODY_BYTES"
    assert violation.limit_value == request_body_limit


@pytest.mark.parametrize("batch_max_raw_bytes", [3, 4, 5, 3_000, 3_001, 3_002])
def test_the_base64_check_is_exact_at_the_boundary(batch_max_raw_bytes: int) -> None:
    base64_bytes = -(-batch_max_raw_bytes * 4 // 3)
    crawler = replace(CRAWLER_DEFAULTS, max_raw_bytes=1, batch_max_raw_bytes=batch_max_raw_bytes)
    indexer = replace(
        INDEXER_DEFAULTS, max_batch_bytes=batch_max_raw_bytes, max_request_body_bytes=base64_bytes
    )
    tighter = replace(indexer, max_request_body_bytes=base64_bytes - 1)

    assert violations_of(crawler, indexer) == []
    assert [v.item for v in violations_of(crawler, tighter)] == ["batch_max_raw_bytes_in_base64"]


def test_max_raw_bytes_above_the_batch_size_is_a_violation_against_the_own_value() -> None:
    crawler = replace(CRAWLER_DEFAULTS, max_raw_bytes=33 * MIB)
    indexer = replace(INDEXER_DEFAULTS, max_raw_bytes=100 * MIB)

    assert violations_of(crawler, indexer) == [
        LimitViolation("max_raw_bytes", 33 * MIB, "batch_max_raw_bytes", 32 * MIB)
    ]


def test_max_raw_bytes_equal_to_the_batch_size_passes_the_own_value_check() -> None:
    crawler = replace(CRAWLER_DEFAULTS, max_raw_bytes=32 * MIB)
    indexer = replace(INDEXER_DEFAULTS, max_raw_bytes=100 * MIB)

    assert violations_of(crawler, indexer) == []


def test_the_own_value_check_runs_even_when_every_indexer_limit_is_unset() -> None:
    crawler = replace(CRAWLER_DEFAULTS, max_raw_bytes=33 * MIB)

    result = check_size_limits(crawler, ALL_UNSET)

    assert [v.limit_name for v in result.violations] == ["batch_max_raw_bytes"]


def test_every_violation_is_reported_not_only_the_first() -> None:
    crawler = CrawlerSizeLimits(
        max_raw_bytes=10,
        batch_max_documents=10,
        batch_max_raw_bytes=10,
        last_seen_max_ids=10,
        finish_id_list_warning_threshold=10,
    )
    indexer = IndexerLimits(
        max_raw_bytes=1,
        max_batch_documents=1,
        max_batch_bytes=1,
        max_request_body_bytes=1,
        max_last_seen_ids=1,
        skip_oversize_id_limit=1,
    )

    assert [v.limit_name for v in violations_of(crawler, indexer)] == [
        "MAX_RAW_BYTES",
        "MAX_BATCH_DOCUMENTS",
        "MAX_BATCH_BYTES",
        "MAX_REQUEST_BODY_BYTES",
        "MAX_LAST_SEEN_IDS",
        "SKIP_OVERSIZE_ID_LIMIT",
    ]


def test_an_unset_indexer_limit_is_reported_and_only_its_check_is_skipped() -> None:
    """CM-U-9 の仮置き(a): 警告して、その項目の検査を省略する。ほかの項目は検査する。"""
    crawler = replace(CRAWLER_DEFAULTS, batch_max_documents=999, last_seen_max_ids=9_999)
    indexer = replace(INDEXER_DEFAULTS, max_batch_documents=None)

    result = check_size_limits(crawler, indexer)

    assert result.unchecked_limits == ("MAX_BATCH_DOCUMENTS",)
    assert [v.item for v in result.violations] == ["last_seen_max_ids"]


def test_all_unset_limits_skip_every_indexer_check() -> None:
    crawler = replace(CRAWLER_DEFAULTS, batch_max_documents=10**9)

    result = check_size_limits(crawler, ALL_UNSET)

    assert result.violations == ()
    assert result.unchecked_limits == (
        "MAX_RAW_BYTES",
        "MAX_BATCH_DOCUMENTS",
        "MAX_BATCH_BYTES",
        "MAX_REQUEST_BODY_BYTES",
        "MAX_LAST_SEEN_IDS",
        "SKIP_OVERSIZE_ID_LIMIT",
    )


def test_a_violation_message_has_the_item_and_both_values() -> None:
    violation = LimitViolation("batch_max_documents", 60, "MAX_BATCH_DOCUMENTS", 50)
    assert violation.describe() == "batch_max_documents=60 exceeds MAX_BATCH_DOCUMENTS=50"


def test_the_check_does_not_read_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MAX_RAW_BYTES", "LORELEY_CRAWLER_MAX_RAW_BYTES", "LORELEY_INDEXER_MAX_RAW_BYTES"):
        monkeypatch.setenv(name, "1")

    assert check_size_limits(CRAWLER_DEFAULTS, INDEXER_DEFAULTS).violations == ()
