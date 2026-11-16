"""警告(`warnings`。architecture 7.5〜7.7。テスト観点 #36・#38)。

警告は観測のためだけで、ジョブの status・終了通知・削除の挙動は変えない。
"""

from datetime import timedelta
from typing import Any

import pytest

from loreley_crawler.connectors.interface import Completed, DocumentRef
from loreley_crawler.crawl import CrawlSettings
from loreley_crawler.documents import DocumentsSettings
from loreley_crawler.infrastructure.indexer_client import FailureType
from loreley_crawler.jobs import JobStatus
from tests.crawl.support import CrawlEnv, crawl_env, document_id_of, run_full
from tests.fakes.clock import DEFAULT_NOW
from tests.fakes.fake_connector import fetched_document
from tests.fakes.fake_indexer_client import FINISH_CRAWL
from tests.jobs.support import SOURCE_ID

PREVIOUS_JOB_ID = "job-20261112T000000Z-00000001"


def seed_previous(
    env: CrawlEnv,
    enumerated_count: int,
    *,
    partial: bool = False,
    job_id: str = PREVIOUS_JOB_ID,
    source_id: str = SOURCE_ID,
) -> None:
    env.jobs.seed_job(
        job_id,
        status=JobStatus.SUCCEEDED,
        source_id=source_id,
        queued_at=DEFAULT_NOW - timedelta(days=1),
        registration={"enumerated_count": enumerated_count, "partial": partial},
    )


def finish_content(env: CrawlEnv) -> dict[str, Any]:
    (call,) = env.indexer.calls_of(FINISH_CRAWL)
    return {
        key: call.arguments[key]
        for key in ("enumerated_count", "skipped_document_ids", "oversize_document_ids")
    }


# --- 0 件列挙の警告(観点 #36) ---


def test_zero_documents_after_a_nonzero_crawl_leaves_a_warning_without_changing_anything() -> None:
    with crawl_env(files={}) as env:
        seed_previous(env, 5)

        body = run_full(env)

        assert body["warnings"] == [
            {
                "code": "enumerated_zero_after_nonzero",
                "previous_job_id": PREVIOUS_JOB_ID,
                "previous_enumerated_count": 5,
            }
        ]
        # ジョブの status・終了通知は、警告の有無で変わらない。
        assert body["status"] == "succeeded"
        assert finish_content(env) == {
            "enumerated_count": 0,
            "skipped_document_ids": [],
            "oversize_document_ids": [],
        }


@pytest.mark.parametrize("previous", [None, 0, "partial", "other_source"])
def test_no_warning_unless_the_previous_completed_crawl_found_documents(
    previous: object,
) -> None:
    with crawl_env(files={}) as env:
        if previous == 0:
            seed_previous(env, 0)
        elif previous == "partial":
            seed_previous(env, 5, partial=True)  # 列挙を完了していない
        elif previous == "other_source":
            seed_previous(env, 5, source_id="other")

        body = run_full(env)

        assert "warnings" not in body
        assert body["status"] == "succeeded"


def test_no_zero_warning_when_this_crawl_found_documents() -> None:
    with crawl_env(files={"a": b"1"}) as env:
        seed_previous(env, 5)

        assert "warnings" not in run_full(env)


def test_the_previous_crawl_is_looked_up_for_at_most_the_configured_number_of_jobs() -> None:
    with crawl_env(files={}, settings=CrawlSettings(previous_crawl_lookup_jobs=1)) as env:
        # 新しい順に 1 件だけ読む。直近の完了(partial=false)が 1 件目になければ警告しない。
        seed_previous(env, 5, job_id="job-20261110T000000Z-00000001")
        env.jobs.seed_job(
            "job-20261111T000000Z-00000001",
            status=JobStatus.FAILED,
            queued_at=DEFAULT_NOW - timedelta(hours=1),
        )

        assert "warnings" not in run_full(env)


# --- 識別子エラー(観点 #38) ---


def test_invalid_ids_leave_a_warning_with_a_count_and_bounded_examples() -> None:
    refs = [DocumentRef("ok", "ok")] + [DocumentRef(f"/bad{i}", i) for i in range(3)]
    with crawl_env(
        items=[*refs, Completed()],
        documents={"ok": fetched_document(b"1")},
        settings=CrawlSettings(invalid_id_example_limit=2),
    ) as env:
        body = run_full(env)

        (warning,) = body["warnings"]
        assert warning["code"] == "invalid_external_id"
        assert warning["count"] == 3
        assert [example["external_id"] for example in warning["examples"]] == ["/bad0", "/bad1"]
        assert all("先頭が `/`" in example["reason"] for example in warning["examples"])
        # 件数照合は成り立つ: 識別子エラーの文書は `enumerated_count` に入らない。
        assert finish_content(env)["enumerated_count"] == 1
        assert body["registration"]["skipped_count"] == 0
        assert body["status"] == "partially_succeeded"  # 識別子エラーだけで partially


def test_a_long_or_control_character_name_is_shown_escaped_and_cut() -> None:
    name = "/bad\n" + "x" * 500
    with crawl_env(items=[DocumentRef(name, 0), Completed()]) as env:
        body = run_full(env)

        shown = body["warnings"][0]["examples"][0]["external_id"]
        assert "\n" not in shown
        assert shown.startswith("/bad\\n")
        assert len(shown) <= 200


# --- 終了通知の ID 一覧の閾値 ---


def test_an_id_list_over_the_threshold_leaves_a_warning_and_is_still_sent_in_full() -> None:
    names = ["a", "b", "c"]
    settings = CrawlSettings(finish_id_list_warning_threshold=2)
    with crawl_env(files={n: b"1" for n in names}, settings=settings) as env:
        for name in names:
            env.indexer.registration_failures[name] = FailureType.DOCUMENT_REJECTED

        body = run_full(env)

        assert body["warnings"] == [
            {"code": "finish_id_list_over_threshold", "count": 3, "threshold": 2}
        ]
        assert finish_content(env)["skipped_document_ids"] == [document_id_of(n) for n in names]
        assert body["status"] == "partially_succeeded"


def test_an_id_list_at_the_threshold_leaves_no_warning() -> None:
    settings = CrawlSettings(finish_id_list_warning_threshold=2)
    with crawl_env(files={"a": b"1", "b": b"1"}, settings=settings) as env:
        env.indexer.registration_failures["a"] = FailureType.DOCUMENT_REJECTED
        env.indexer.registration_failures["b"] = FailureType.DOCUMENT_REJECTED

        assert "warnings" not in run_full(env)


def test_the_warnings_are_capped() -> None:
    settings = CrawlSettings(warnings_max_entries=1, finish_id_list_warning_threshold=1)
    refs = [DocumentRef("/bad", 0), DocumentRef("a", "a"), DocumentRef("b", "b"), Completed()]
    with crawl_env(items=refs, settings=settings, documents={}) as env:
        body = run_full(env)

        assert [warning["code"] for warning in body["warnings"]] == ["invalid_external_id"]


def test_the_warnings_are_already_in_the_job_record_when_the_notice_is_sent() -> None:
    with crawl_env(files={}) as env:
        seed_previous(env, 5)
        seen: list[Any] = []
        env.indexer.behavior.before(
            FINISH_CRAWL, lambda: seen.append(env.job_body().get("warnings"))
        )

        run_full(env)

        assert [warning["code"] for warning in seen[0]] == ["enumerated_zero_after_nonzero"]


@pytest.mark.parametrize(("threshold", "warns"), [(2, True), (3, False)])
def test_the_threshold_applies_to_the_sum_of_both_id_lists(threshold: int, warns: bool) -> None:
    # スキップ 1 件 + 原本サイズ超過 2 件 = 3 件(合算が Indexer の上限に数えられる)。
    with crawl_env(
        files={"a": b"1", "big1": b"x" * 100, "big2": b"x" * 100},
        settings=CrawlSettings(finish_id_list_warning_threshold=threshold),
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        env.indexer.registration_failures["a"] = FailureType.DOCUMENT_REJECTED

        body = run_full(env)

        if warns:
            assert body["warnings"] == [
                {"code": "finish_id_list_over_threshold", "count": 3, "threshold": threshold}
            ]
        else:
            assert "warnings" not in body


def test_skipped_plus_oversize_exactly_at_the_threshold_leaves_no_warning() -> None:
    with crawl_env(
        files={"a": b"1", "big": b"x" * 100},
        settings=CrawlSettings(finish_id_list_warning_threshold=2),
        documents_settings=DocumentsSettings(max_raw_bytes=10),
    ) as env:
        env.indexer.registration_failures["a"] = FailureType.DOCUMENT_REJECTED

        assert "warnings" not in run_full(env)
