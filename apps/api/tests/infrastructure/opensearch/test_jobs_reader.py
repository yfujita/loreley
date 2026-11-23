"""JobsReader(R-3〜R-7・R-10 の `skipped`・`oversize`)。"""

from collections.abc import Callable

import pytest
from opensearchpy.exceptions import ConnectionTimeout, TransportError

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch import (
    JobListQuery,
    OpenSearchJobsReader,
    Page,
    PageRequest,
    ReadOnlyOpenSearch,
    SourceJobsSummary,
    StoredRecord,
    queries,
)
from loreley_api.infrastructure.opensearch.ports import JOB_BRIEF_FIELDS, JOB_DETAIL_FIELDS
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.infrastructure.opensearch.conftest import INDEX_NAMES
from tests.infrastructure.opensearch.sample_responses import (
    hit,
    mget_doc,
    mget_response,
    search_response,
)

PAGE = PageRequest(page=2, items_per_page=25, descending=True)


@pytest.fixture
def reader(readonly: ReadOnlyOpenSearch) -> OpenSearchJobsReader:
    return OpenSearchJobsReader(readonly, jobs_index=INDEX_NAMES.jobs)


def top_hits(*hits: dict[str, object]) -> dict[str, object]:
    return {"hits": {"hits": list(hits)}}


def source_bucket(
    source_id: str,
    *,
    crawl: dict[str, object] | None = None,
    delete: dict[str, object] | None = None,
    completed_at: float | None = None,
) -> dict[str, object]:
    return {
        "key": source_id,
        "doc_count": 3,
        "crawl": {
            "doc_count": 2,
            "latest": top_hits(*([crawl] if crawl else [])),
            "completed": {"doc_count": 1, "at": {"value": completed_at}},
        },
        "delete": {"doc_count": 1, "latest": top_hits(*([delete] if delete else []))},
    }


def latest_response(*buckets: dict[str, object]) -> dict[str, object]:
    return search_response(aggregations={"by_source": {"buckets": list(buckets)}})


# --- R-3 ---


def test_latest_by_source_returns_the_jobs_and_the_completion_time_per_source(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    crawl_hit = hit("job-1", {"job_id": "job-1", "status": "succeeded"})
    delete_hit = hit("job-2", {"job_id": "job-2", "status": "running"})
    fake_client.script(
        "search",
        latest_response(
            source_bucket("a", crawl=crawl_hit, delete=delete_hit, completed_at=1.7e12),
            source_bucket("b"),
        ),
    )

    result = reader.latest_by_source(["a", "b", "c"])

    assert result == Ok(
        {
            "a": SourceJobsSummary(
                latest_crawl=StoredRecord("job-1", {"job_id": "job-1", "status": "succeeded"}),
                latest_source_delete=StoredRecord(
                    "job-2", {"job_id": "job-2", "status": "running"}
                ),
                last_completed_epoch_millis=1_700_000_000_000,
            ),
            "b": SourceJobsSummary(None, None, None),
        }
    )  # ジョブが 1 件もないソース(c)はキーがない
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.jobs
    assert request.body == queries.latest_by_source_body(["a", "b", "c"])


def test_latest_by_source_without_sources_does_not_query(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    assert reader.latest_by_source([]) == Ok({})
    assert fake_client.requests == []


@pytest.mark.parametrize(
    "response",
    [
        search_response(),  # `aggregations` がない
        latest_response({"key": 1}),
        latest_response({"key": "a"}),  # サブ集計がない
        latest_response(source_bucket("a", completed_at=float("nan"))),
        search_response(aggregations={"by_source": {"buckets": "x"}}),
    ],
)
def test_latest_by_source_fails_on_a_malformed_aggregation(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient, response: object
) -> None:
    fake_client.script("search", response)

    assert reader.latest_by_source(["a"]) == Failed("unavailable", "store", "ResponseShapeError")


def test_latest_by_source_fails_as_a_whole_on_a_partial_response(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    response = latest_response(source_bucket("a"))
    fake_client.script("search", {**response, "timed_out": True})

    assert reader.latest_by_source(["a"]) == Failed("timeout", "store", "PartialResponseError")


# --- R-4 ---


LOCK_DOC = {"record_type": "lock", "source_id": "a", "job_id": "job-1"}


def test_get_locks_returns_a_result_per_source_keyed_by_source_id(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script(
        "mget",
        mget_response(mget_doc("lock-a", LOCK_DOC), mget_doc("lock-b", found=False)),
    )

    results = reader.get_locks(["a", "b"])

    assert results == {"a": Ok(StoredRecord("lock-a", LOCK_DOC)), "b": Ok(None)}
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.jobs
    assert request.body == {"ids": ["lock-a", "lock-b"]}
    assert request.query_params == {
        "_source_includes": [
            "record_type",
            "source_id",
            "job_id",
            "lease_expires_at",
            "acquired_at",
        ]
    }


def test_get_locks_does_not_treat_a_failed_document_as_no_lock(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    """実在するロックを `lock_state=none` と読み違えないため、文書単位で失敗にする(他は使える)。"""
    fake_client.script(
        "mget",
        mget_response(
            mget_doc("lock-a", LOCK_DOC),
            {"_id": "lock-b", "error": {"type": "x"}},
            {"_id": "lock-c", "found": "yes"},
        ),
    )

    results = reader.get_locks(["a", "b", "c"])

    assert results["a"] == Ok(StoredRecord("lock-a", LOCK_DOC))
    assert results["b"] == Failed("unavailable", "store", "DocumentError")
    assert results["c"] == Failed("unavailable", "store", "DocumentError")


def test_get_locks_treats_a_document_of_another_record_type_as_no_lock(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("lock-a", {"record_type": "job"})))

    assert reader.get_locks(["a"]) == {"a": Ok(None)}


def test_get_locks_fails_every_source_when_the_whole_mget_fails(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", ConnectionTimeout("TIMEOUT", "x", None))

    assert reader.get_locks(["a", "b"]) == dict.fromkeys(
        ["a", "b"], Failed("timeout", "store", "ConnectionTimeout")
    )


def test_get_locks_fails_every_source_when_the_document_count_is_wrong(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("lock-a", LOCK_DOC)))

    assert reader.get_locks(["a", "b"]) == dict.fromkeys(
        ["a", "b"], Failed("unavailable", "store", "ResponseShapeError")
    )


def test_get_locks_without_sources_does_not_query(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    assert reader.get_locks([]) == {}
    assert fake_client.requests == []


def test_get_locks_asks_for_each_source_once(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("lock-a", found=False)))

    assert reader.get_locks(["a", "a"]) == {"a": Ok(None)}
    assert fake_client.requests[0].body == {"ids": ["lock-a"]}


# --- R-5 ---


def test_get_jobs_reads_the_fields_and_the_record_type(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    doc = {"record_type": "job", "status": "running"}
    fake_client.script(
        "mget", mget_response(mget_doc("job-1", doc), mget_doc("job-2", found=False))
    )

    results = reader.get_jobs(["job-1", "job-2"], ["status"])

    assert results == {"job-1": Ok(StoredRecord("job-1", doc)), "job-2": Ok(None)}
    assert fake_client.requests[0].query_params == {"_source_includes": ["status", "record_type"]}


def test_get_jobs_does_not_repeat_the_record_type_when_it_is_requested(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("job-1", found=False)))

    reader.get_jobs(["job-1"], ["record_type", "status"])

    assert fake_client.requests[0].query_params == {"_source_includes": ["record_type", "status"]}


def test_get_jobs_returns_none_for_a_lock_or_skip_record_id(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    """ロック・スキップ記録の ID を `job_id` として渡されたときに 404 にするため。"""
    fake_client.script(
        "mget",
        mget_response(
            mget_doc("lock-a", {"record_type": "lock"}),
            mget_doc("skip-a-d", {"record_type": "skip"}),
        ),
    )

    assert reader.get_jobs(["lock-a", "skip-a-d"], ["status"]) == {
        "lock-a": Ok(None),
        "skip-a-d": Ok(None),
    }


def test_get_jobs_does_not_treat_a_failed_document_as_missing(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    """実在するジョブを EP-10 の 404 にしないため(C 11章 6)。"""
    fake_client.script("mget", mget_response({"_id": "job-1", "error": {"type": "x"}}))

    assert reader.get_jobs(["job-1"], ["status"]) == {
        "job-1": Failed("unavailable", "store", "DocumentError")
    }


def test_the_detail_fields_include_only_the_needed_part_of_the_finish_notice() -> None:
    assert "finish_notice" not in JOB_DETAIL_FIELDS
    assert "finish_notice.send_started_at" in JOB_DETAIL_FIELDS
    assert set(JOB_BRIEF_FIELDS) <= set(JOB_DETAIL_FIELDS)


# --- R-6・R-10 ---


def test_list_jobs_returns_a_page_with_the_exact_total(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    query = JobListQuery(page=PAGE, source_id="a", statuses=("queued", "running"))
    fake_client.script(
        "search", search_response([hit("job-1", {"status": "queued"})], total=12_345)
    )

    result = reader.list_jobs(query)

    assert result == Ok(Page(total=12_345, items=(StoredRecord("job-1", {"status": "queued"}),)))
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.jobs
    assert request.body == queries.jobs_list_body(query)


@pytest.mark.parametrize(
    ("method", "build"),
    [
        ("list_skipped", queries.skipped_list_body),
        ("list_oversize", queries.oversize_list_body),
    ],
)
def test_the_jobs_side_tabs_are_listed_from_the_jobs_index(
    reader: OpenSearchJobsReader,
    fake_client: FakeOpenSearchClient,
    method: str,
    build: Callable[[str, PageRequest], dict[str, object]],
) -> None:
    fake_client.script("search", search_response([hit("skip-a-d", {"document_id": "d"})], total=1))

    result = getattr(reader, method)("a", PAGE)

    assert result == Ok(Page(1, (StoredRecord("skip-a-d", {"document_id": "d"}),)))
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.jobs
    assert request.body == build("a", PAGE)


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (TransportError(503, "x", {}), Failed("unavailable", "store", "TransportError")),
        (ConnectionTimeout("TIMEOUT", "x", None), Failed("timeout", "store", "ConnectionTimeout")),
        (
            search_response([hit("a", {})], total=1, failed_shards=1),
            Failed("unavailable", "store", "PartialResponseError"),
        ),
        (
            search_response([hit("a", {})], total=1, timed_out=True),
            Failed("timeout", "store", "PartialResponseError"),
        ),
        (search_response([hit("a", {})]), Failed("unavailable", "store", "ResponseShapeError")),
    ],
)
def test_the_list_methods_never_leak_an_exception_or_a_partial_result(
    reader: OpenSearchJobsReader,
    fake_client: FakeOpenSearchClient,
    outcome: object,
    expected: Failed,
) -> None:
    for call in (
        lambda: reader.list_jobs(JobListQuery(page=PAGE)),
        lambda: reader.list_skipped("a", PAGE),
        lambda: reader.list_oversize("a", PAGE),
    ):
        fake_client.script("search", outcome)
        assert call() == expected


# --- R-7 ---


def test_latest_crawl_id_returns_the_id_of_the_first_hit(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("search", search_response([hit("job-9")]))

    assert reader.latest_crawl_id("a") == Ok("job-9")
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.jobs
    assert request.body == queries.latest_crawl_id_body("a")


def test_latest_crawl_id_is_none_when_there_is_no_crawl_job(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("search", search_response([]))

    assert reader.latest_crawl_id("a") == Ok(None)


def test_latest_crawl_id_fails_on_a_partial_response(
    reader: OpenSearchJobsReader, fake_client: FakeOpenSearchClient
) -> None:
    """部分的な結果から「最新ではない」と判断しない(`latest_for_source=null`)。"""
    fake_client.script("search", search_response([hit("job-9")], failed_shards=1))

    assert reader.latest_crawl_id("a") == Failed("unavailable", "store", "PartialResponseError")
