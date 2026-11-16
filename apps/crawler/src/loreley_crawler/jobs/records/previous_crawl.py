"""0 件列挙の警告のための、直前に完了したクロールの登録結果の取得(architecture 7.7。CA-P-52)。

`loreley-jobs` を読めるのは `jobs/records` だけ(R7)なので、`crawl` はここを呼ぶ。
警告を作るかどうかの判断と `warnings` への記録は `crawl` の担当(CM-P-23)。
`registration` は索引しないので、`_source` を読んで判定する。
"""

from dataclasses import dataclass

from loreley_crawler.infrastructure.opensearch import RecordFilter, Repository, SortKey
from loreley_crawler.jobs.records.job_record import JOB_RECORD_TYPE, JobType


@dataclass(frozen=True)
class PreviousCrawl:
    job_id: str
    enumerated_count: int


def find_previous_completed_crawl(
    repository: Repository, *, source_id: str, excluding_job_id: str, max_jobs: int
) -> PreviousCrawl | None:
    """同じソースで直前に列挙を完了した `crawl` ジョブ(`registration.partial=false` の最新のもの)。

    新しい順(`queued_at`)に、自分のジョブを除いて最大 `max_jobs` 件読み、最初に見つかった
    ものを返す。見つからなければ None(警告しない)。`enumerated_count` が整数でないジョブは、
    判定できないので飛ばす。
    """
    if max_jobs < 1:
        raise ValueError("max_jobs must be at least 1")
    records = repository.list_records(
        RecordFilter(
            equals={
                "record_type": JOB_RECORD_TYPE,
                "job_type": JobType.CRAWL.value,
                "source_id": source_id,
            }
        ),
        [SortKey("queued_at", descending=True), SortKey("job_id", descending=True)],
        limit=max_jobs + 1,  # 自分のジョブが含まれうるぶん
    )
    candidates = [record for record in records if record.id != excluding_job_id][:max_jobs]
    for record in candidates:
        registration = record.source.get("registration")
        if not isinstance(registration, dict) or registration.get("partial") is not False:
            continue
        enumerated_count = registration.get("enumerated_count")
        if type(enumerated_count) is int:
            return PreviousCrawl(record.id, enumerated_count)
    return None
