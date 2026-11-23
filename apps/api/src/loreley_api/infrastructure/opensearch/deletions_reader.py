"""`loreley-deletions` の読み取り(R-8。C 3.3)。"""

from loreley_api.common.results import Result
from loreley_api.infrastructure.opensearch.ports import StoredRecord
from loreley_api.infrastructure.opensearch.reading import fetch_documents
from loreley_api.infrastructure.opensearch.readonly_client import ReadOnlyOpenSearch

DELETION_RESULT_RECORD_TYPE = "deletion_result"
DELETION_RESULT_FIELDS = (
    "record_type",
    "status",
    "reason",
    "reason_detail",
    "forced",
    "target_count",
    "denominator",
    "deleted_count",
    "ended_at",
)


class OpenSearchDeletionsReader:
    def __init__(self, readonly: ReadOnlyOpenSearch, *, deletions_index: str) -> None:
        self._readonly = readonly
        self._deletions_index = deletions_index

    def get_result(self, job_id: str) -> Result[StoredRecord | None]:
        # `skipped_document_ids`・`oversize_document_ids`(ID の一覧)は読まない(C 3.2)。
        document_id = f"{DELETION_RESULT_RECORD_TYPE}-{job_id}"
        results = fetch_documents(
            self._readonly,
            index=self._deletions_index,
            ids=[document_id],
            target="store",
            operation="deletions.get_result",
            source_includes=DELETION_RESULT_FIELDS,
            expected_record_type=DELETION_RESULT_RECORD_TYPE,
        )
        return results[document_id]
