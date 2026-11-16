"""途中で止まったソース削除ジョブの再実行(CAPI-K-4。architecture 8.3)。

止まる点(順 4 の Indexer の失敗・順 5 の Store の失敗・ロックの喪失)ごとに、`deleting` のソースに
もう一度ソース削除を受け付けて、最後は `succeeded`・設定とロックの削除まで完了する。
"""

import pytest

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.indexer_client import IndexerRejected, IndexerUnavailable
from loreley_crawler.jobs import Accepted, LockAlreadyHeld
from tests.fakes import in_memory_repository as ops
from tests.fakes.fake_indexer_client import DELETE_DELETION_RECORDS, DELETE_DOCUMENTS
from tests.jobs.support import ADMITTED_JOB_ID, LOCK_ID, SOURCE_ID
from tests.source_delete.support import (
    INDEXER_STEPS,
    SKIP_ID,
    TimelineIndexerClient,
    make_admission,
    make_runner,
    new_timeline_env,
)

# 失敗の理由、ロックを Job Runner が解放するか。
BREAK_POINTS = [
    pytest.param("step4_unavailable", "indexer_unavailable", True, id="step4-indexer-unavailable"),
    pytest.param("step5_store_failure", "store_unavailable", True, id="step5-store-failure"),
    pytest.param("lock_lost", "lock_lost", False, id="lock-lost"),
]


@pytest.mark.parametrize(("break_point", "reason", "lock_released"), BREAK_POINTS)
def test_a_job_stopped_at_any_point_is_completed_by_the_last_rerun(
    break_point: str, reason: str, lock_released: bool
) -> None:
    events: list[str] = []
    jobs = new_timeline_env(events)
    jobs.seed_source()
    jobs.jobs_repository.seed(
        SKIP_ID,
        {"record_type": "skip", "source_id": SOURCE_ID, "document_id": "aaa", "external_id": "a"},
    )
    indexer = TimelineIndexerClient(events)
    if break_point == "step4_unavailable":
        indexer.behavior.inject(DELETE_DELETION_RECORDS, IndexerUnavailable("http_503"), times=3)
    elif break_point == "step5_store_failure":
        jobs.sources_repository.behavior.inject(
            ops.DELETE, StoreUnavailableError("opensearch_unavailable"), times=3
        )
    else:
        indexer.behavior.inject(DELETE_DOCUMENTS, IndexerRejected(409, "lock_not_owned"))
    admission = make_admission(jobs)
    runner = make_runner(jobs, indexer)
    assert isinstance(admission.accept_source_delete(SOURCE_ID), Accepted)

    runner.run_next()

    first = jobs.job_body(ADMITTED_JOB_ID)
    assert (first["status"], first["failure_reason"]) == ("failed", reason)
    source = jobs.sources_repository.body_of(SOURCE_ID)
    assert source is not None and source["status"] == "deleting"  # 順 0 は済んでいる
    assert (jobs.lock_body() is None) is lock_released
    if not lock_released:
        # 喪失時は、Job Runner がロックを削除しない。管理者の解放(ここでは削除で代用)の後に
        # 再実行する。
        assert isinstance(
            make_admission(jobs, random_token=lambda: "1111abcd").accept_source_delete(SOURCE_ID),
            LockAlreadyHeld,
        )
        jobs.jobs_repository.delete_ids([LOCK_ID])

    jobs.clock.advance(seconds=1)
    second = admission.accept_source_delete(SOURCE_ID)
    assert isinstance(second, Accepted)
    runner.run_next()

    assert jobs.job_body(second.job.job_id)["status"] == "succeeded"
    assert jobs.sources_repository.body_of(SOURCE_ID) is None
    assert jobs.lock_body() is None
    assert jobs.jobs_repository.body_of(SKIP_ID) is None
    assert indexer.operations()[-3:] == INDEXER_STEPS  # 順 1・2・4 は冪等にやり直す
