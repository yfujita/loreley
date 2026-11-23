"""DeletionsReader(R-8)。"""

import pytest
from opensearchpy.exceptions import ConnectionTimeout

from loreley_api.common.results import Failed, Ok
from loreley_api.infrastructure.opensearch import (
    OpenSearchDeletionsReader,
    ReadOnlyOpenSearch,
    StoredRecord,
)
from tests.fakes.fake_opensearch_client import FakeOpenSearchClient
from tests.infrastructure.opensearch.conftest import INDEX_NAMES
from tests.infrastructure.opensearch.sample_responses import mget_doc, mget_response

RESULT = {"record_type": "deletion_result", "status": "completed", "deleted_count": 3}


@pytest.fixture
def reader(readonly: ReadOnlyOpenSearch) -> OpenSearchDeletionsReader:
    return OpenSearchDeletionsReader(readonly, deletions_index=INDEX_NAMES.deletions)


def test_get_result_reads_the_deletion_result_document_by_id(
    reader: OpenSearchDeletionsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("deletion_result-job-1", RESULT)))

    result = reader.get_result("job-1")

    assert result == Ok(StoredRecord("deletion_result-job-1", RESULT))
    [request] = fake_client.requests
    assert request.index == INDEX_NAMES.deletions
    assert request.body == {"ids": ["deletion_result-job-1"]}
    # ID の一覧(`skipped_document_ids`・`oversize_document_ids`)は読まない。
    assert request.query_params == {
        "_source_includes": [
            "record_type",
            "status",
            "reason",
            "reason_detail",
            "forced",
            "target_count",
            "denominator",
            "deleted_count",
            "ended_at",
        ]
    }


def test_get_result_is_none_when_there_is_no_record(
    reader: OpenSearchDeletionsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response(mget_doc("deletion_result-job-1", found=False)))

    assert reader.get_result("job-1") == Ok(None)


def test_get_result_is_none_for_a_record_of_another_type(
    reader: OpenSearchDeletionsReader, fake_client: FakeOpenSearchClient
) -> None:
    other = {"record_type": "something_else"}
    fake_client.script("mget", mget_response(mget_doc("deletion_result-job-1", other)))

    assert reader.get_result("job-1") == Ok(None)


def test_get_result_does_not_read_a_failure_as_no_record(
    reader: OpenSearchDeletionsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", mget_response({"_id": "deletion_result-job-1", "error": {}}))

    assert reader.get_result("job-1") == Failed("unavailable", "store", "DocumentError")


def test_get_result_never_leaks_an_exception(
    reader: OpenSearchDeletionsReader, fake_client: FakeOpenSearchClient
) -> None:
    fake_client.script("mget", ConnectionTimeout("TIMEOUT", "x", None))

    assert reader.get_result("job-1") == Failed("timeout", "store", "ConnectionTimeout")


def test_a_job_id_with_special_characters_goes_in_the_body_not_the_path(
    reader: OpenSearchDeletionsReader, fake_client: FakeOpenSearchClient
) -> None:
    job_id = "a%2Fb?c#d"
    fake_client.script("mget", mget_response(mget_doc(f"deletion_result-{job_id}", found=False)))

    reader.get_result(job_id)

    assert fake_client.requests[0].body == {"ids": [f"deletion_result-{job_id}"]}
