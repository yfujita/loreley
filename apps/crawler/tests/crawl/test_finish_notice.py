"""終了通知の内容・警告・設定の単位テスト(architecture 7.5・11章)。"""

import dataclasses
from datetime import UTC, datetime

import pytest

from loreley_crawler.config import CrawlerSizeLimits
from loreley_crawler.crawl import CrawlSettings, FinishNotice
from loreley_crawler.crawl.warning_log import WarningLog
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import FinishOutcome

NOW = datetime(2026, 11, 13, 1, 2, 3, 456789, tzinfo=UTC)


def test_the_completed_content_has_the_counts_and_the_lists_as_json_lists() -> None:
    notice = FinishNotice.enumeration_completed(
        now=NOW, enumerated_count=3, skipped_document_ids=("a",), oversize_document_ids=("b", "c")
    )

    assert notice.content_record("docs") == {
        "source_id": "docs",
        "outcome": "enumeration_completed",
        "finished_at": "2026-11-13T01:02:03.456Z",
        "enumerated_count": 3,
        "skipped_document_ids": ["a"],
        "oversize_document_ids": ["b", "c"],
    }


def test_finished_at_is_the_same_instant_in_the_record_and_in_what_is_sent() -> None:
    notice = FinishNotice.enumeration_completed(
        now=NOW, enumerated_count=0, skipped_document_ids=(), oversize_document_ids=()
    )

    assert notice.finished_at == datetime(2026, 11, 13, 1, 2, 3, 456000, tzinfo=UTC)


@pytest.mark.parametrize("outcome", [FinishOutcome.FAILED, FinishOutcome.CANCELLED])
def test_failed_and_cancelled_carry_only_the_outcome_the_source_and_the_time(
    outcome: FinishOutcome,
) -> None:
    notice = FinishNotice.without_counts(outcome, now=NOW)

    assert notice.content_record("docs") == {
        "source_id": "docs",
        "outcome": outcome.value,
        "finished_at": "2026-11-13T01:02:03.456Z",
    }


def test_without_counts_rejects_the_completed_outcome() -> None:
    with pytest.raises(ValueError, match="counts"):
        FinishNotice.without_counts(FinishOutcome.ENUMERATION_COMPLETED, now=NOW)


def test_the_record_keeps_the_send_start_apart_from_the_content() -> None:
    notice = FinishNotice.without_counts(FinishOutcome.FAILED, now=NOW)

    assert notice.to_record("docs", send_started_at=None)["send_started_at"] is None
    started = notice.to_record("docs", send_started_at=NOW)
    assert started["send_started_at"] == "2026-11-13T01:02:03.456Z"
    assert "send_started_at" not in started["content"]


def test_the_warning_log_keeps_one_entry_per_code_and_drops_the_overflow() -> None:
    log = WarningLog(2)

    log.add("a", count=1)
    log.add("a", count=2)
    log.add("b")
    log.add("c")

    assert log.to_record() == [{"code": "a", "count": 1}, {"code": "b"}]


def test_the_warning_log_returns_copies() -> None:
    log = WarningLog(2)
    log.add("a", count=1)

    log.to_record()[0]["count"] = 99

    assert log.to_record() == [{"code": "a", "count": 1}]


@pytest.mark.parametrize(
    "name",
    [
        "finish_id_list_warning_threshold",
        "polling_max_consecutive_failures",
        "warnings_max_entries",
        "previous_crawl_lookup_jobs",
    ],
)
def test_the_new_integer_settings_must_be_positive(name: str) -> None:
    with pytest.raises(ValueError, match=name):
        CrawlSettings(**{name: 0})


@pytest.mark.parametrize("name", ["polling_interval_seconds", "polling_timeout_seconds"])
@pytest.mark.parametrize("value", [0, -1.0])
def test_the_polling_durations_must_be_positive(name: str, value: float) -> None:
    with pytest.raises(ValueError, match=name):
        CrawlSettings(**{name: value})


def test_the_provisional_polling_values_are_those_of_architecture_11() -> None:
    settings = CrawlSettings()

    assert settings.finish_id_list_warning_threshold == 8_000
    assert settings.polling_interval_seconds == 5.0
    assert settings.polling_timeout_seconds == 30 * 60
    assert settings.polling_max_consecutive_failures == 3
    assert settings.warnings_max_entries == 20
    assert settings.previous_crawl_lookup_jobs == 10


def test_every_field_checked_against_the_indexer_limits_is_a_setting_with_the_same_name() -> None:
    # `config.py` の整合性検査(`CrawlerSizeLimits`)の項目は、`CrawlSettings`・`DocumentsSettings` の
    # 同じ名前の項目から詰める(P8)。名前がずれていないことを固定する。
    available = {f.name for f in dataclasses.fields(CrawlSettings)} | {
        f.name for f in dataclasses.fields(DocumentsSettings)
    }
    for field in dataclasses.fields(CrawlerSizeLimits):
        assert field.name in available
