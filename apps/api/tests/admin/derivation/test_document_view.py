"""EP-11 の各タブの行の元(B 6.1。C 3.3 R-10)。読めない値は `None`。"""

import dataclasses
from typing import Any

import pytest

from loreley_api.admin.base.codes import OversizeDetector, SkipStage
from loreley_api.admin.derivation.document_view import (
    ExtractFailedView,
    OversizeView,
    SkippedView,
    SummaryPendingView,
    read_extract_failed,
    read_oversize,
    read_skipped,
    read_summary_pending,
)

SKIPPED: dict[str, Any] = {
    "document_id": "doc-1",
    "external_id": "manuals/guide.pdf",
    "stage": "fetch",
    "reason": "fetch_permission_denied: 取得の権限がなかった",
    "attempts": 3,
    "consecutive_skips": 5,
    "first_skipped_at": "2026-11-18T12:00:10+09:00",
    "last_skipped_at": "2026-11-22T03:00:12.345Z",
    "last_job_id": "job-1",
}


def test_a_skip_record_is_read_as_it_is_with_times_in_utc_milliseconds() -> None:
    assert read_skipped(SKIPPED) == SkippedView(
        document_id="doc-1",
        external_id="manuals/guide.pdf",
        stage=SkipStage.FETCH,
        reason="fetch_permission_denied: 取得の権限がなかった",
        attempts=3,
        consecutive_skips=5,
        first_skipped_at="2026-11-18T03:00:10.000Z",
        last_skipped_at="2026-11-22T03:00:12.345Z",
        last_job_id="job-1",
    )


def test_an_empty_skip_record_reads_every_field_as_none() -> None:
    assert read_skipped({}) == SkippedView(*[None] * 9)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_id", ""),
        ("document_id", 1),
        ("stage", "unknown-stage"),
        ("stage", 1),
        ("reason", ["x"]),
        ("attempts", "3"),
        ("attempts", True),
        ("consecutive_skips", 1.5),
        ("first_skipped_at", "2026-11-18T03:00:10"),
        ("last_skipped_at", "yesterday"),
        ("last_job_id", 1),
    ],
)
def test_an_unreadable_skip_value_is_none_and_the_others_are_kept(
    field: str, value: object
) -> None:
    expected = dataclasses.replace(read_skipped(SKIPPED), **{field: None})

    assert read_skipped({**SKIPPED, field: value}) == expected


def test_an_extract_failed_document_takes_its_id_from_the_document_not_the_source() -> None:
    view = read_extract_failed(
        "doc-9",
        {
            "document_id": "ignored",
            "title": "報告書",
            "external_id": "a.pdf",
            "mime_type": "application/pdf",
            "size": 1024,
            "source_updated_at": "2026-11-01T09:00:00+09:00",
            "last_seen_at": "2026-11-22T00:00:00Z",
        },
    )

    assert view == ExtractFailedView(
        document_id="doc-9",
        title="報告書",
        external_id="a.pdf",
        mime_type="application/pdf",
        size=1024,
        source_updated_at="2026-11-01T00:00:00.000Z",
        last_seen_at="2026-11-22T00:00:00.000Z",
    )


def test_an_extract_failed_document_without_a_title_or_a_size_has_none() -> None:
    view = read_extract_failed("doc-9", {"title": None, "size": "big"})

    assert (view.title, view.size) == (None, None)


def test_an_oversize_record_is_read_as_it_is() -> None:
    view = read_oversize(
        {
            "document_id": "doc-2",
            "external_id": "big.bin",
            "detected_by": "indexer",
            "size": 70_000,
            "first_detected_at": "2026-11-20T00:00:00Z",
            "last_detected_at": "2026-11-22T00:00:00Z",
            "last_job_id": "job-2",
        }
    )

    assert view == OversizeView(
        document_id="doc-2",
        external_id="big.bin",
        detected_by=OversizeDetector.INDEXER,
        size=70_000,
        first_detected_at="2026-11-20T00:00:00.000Z",
        last_detected_at="2026-11-22T00:00:00.000Z",
        last_job_id="job-2",
    )


def test_an_oversize_record_without_a_known_size_has_a_none_size() -> None:
    """Crawler が検出したときは、サイズが分からないことがある(B 6.1)。"""
    view = read_oversize({"document_id": "doc-2", "detected_by": "crawler"})

    assert view.size is None
    assert view.detected_by is OversizeDetector.CRAWLER


@pytest.mark.parametrize("detected_by", ["scanner", 1, None])
def test_an_unknown_detector_is_none(detected_by: object) -> None:
    assert read_oversize({"detected_by": detected_by}).detected_by is None


def test_a_summary_pending_document_is_read_as_it_is() -> None:
    view = read_summary_pending(
        "doc-3",
        {
            "title": "議事録",
            "external_id": "minutes.md",
            "mime_type": "text/markdown",
            "source_updated_at": "2026-11-21T00:00:00Z",
            "indexed_at": "2026-11-22T00:00:00Z",
            "content": "never exposed",
        },
    )

    assert view == SummaryPendingView(
        document_id="doc-3",
        title="議事録",
        external_id="minutes.md",
        mime_type="text/markdown",
        source_updated_at="2026-11-21T00:00:00.000Z",
        indexed_at="2026-11-22T00:00:00.000Z",
    )
