"""ジョブ記録の読み書き(module 4.4 の `records/`。architecture 3.3・5.3 の書き手の表)。

`loreley-jobs` に書く唯一の層(`records/` と `locks/`)の一部。書き込みは `create` か、
読んだ版を条件にした置き換えだけで、1 回の試行(`StoreUnavailableError` はそのまま送出)。
リトライと、競合したときの判断(所有権の喪失か、読んだ版でやり直すか)は、呼び出し側
(`JobContext`・受付・取り消し)が行う。

**応答が失われた後のリトライ**(0007 §4-3): 書き込みの応答が失われてリトライすると、最初の
書き込みが成功していたために `AlreadyExists`・`Conflict` が返る。`create`・`update` は、
そのとき記録を読み直し、自分が書いた内容そのものなら成功として返す(誰かが後から書いていれば
内容が変わるので、成功にしない)。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from loreley_crawler.common.errors import StoreUnexpectedResponseError
from loreley_crawler.infrastructure.opensearch import (
    LIST_MAX_SIZE,
    RecordFilter,
    Repository,
    SortKey,
    StoredRecord,
    Written,
)
from loreley_crawler.jobs.records.job_record import (
    JOB_RECORD_TYPE,
    JobRecord,
    JobStatus,
)

# Job Runner が実行する順(`queued_at` の古い順)。同時刻は `job_id` で決める。
_OLDEST_FIRST = [SortKey("queued_at"), SortKey("job_id")]


@dataclass(frozen=True)
class JobCreated:
    record: JobRecord


@dataclass(frozen=True)
class JobIdCollision:
    """同じ `job_id` の別の記録がある(乱数の衝突。呼び出し側が ID を作り直す)。"""


@dataclass(frozen=True)
class JobUpdated:
    record: JobRecord


@dataclass(frozen=True)
class JobSuperseded:
    """読んだ版の後に、別の書き込みが入った。`current` は読み直した記録(消えていれば None)。

    呼び出し側が判断する: 状態が `failed`(`lock_released`)などに変わっていれば所有権の喪失、
    そうでなければ `current` の版で、変更を `current.fields` に重ねてやり直す。
    """

    current: JobRecord | None


CreateJobResult = JobCreated | JobIdCollision
UpdateJobResult = JobUpdated | JobSuperseded


class JobRecordStore:
    def __init__(self, repository: Repository) -> None:
        self._repository = repository

    def create(self, fields: Mapping[str, Any]) -> CreateJobResult:
        """`queued` のジョブ記録を、存在しない場合だけ保存する(`new_queued_job_fields`)。"""
        job_id: str = fields["job_id"]
        outcome = self._repository.create(job_id, fields)
        if isinstance(outcome, Written):
            return JobCreated(JobRecord(job_id, dict(fields), outcome.seq_no, outcome.primary_term))
        existing = self.fetch(job_id)
        if existing is not None and dict(existing.fields) == dict(fields):
            return JobCreated(existing)  # 応答が失われた最初の `create` が成功していた
        return JobIdCollision()

    def fetch(self, job_id: str) -> JobRecord | None:
        """`record_type=job` の記録だけをジョブとみなす(ロックなどの ID は None。api 3.2)。

        空の `job_id` は None。形式不正のロック文書の `job_id` は空文字になる(`parse_lock`)ので、
        回復・解放・受付がそのロックを扱えるように、Store 層へ渡さず「ジョブなし」とする。
        """
        if not job_id:
            return None
        stored = self._repository.fetch(job_id)
        if stored is None or stored.source.get("record_type") != JOB_RECORD_TYPE:
            return None
        return _to_job_record(stored)

    def find_oldest_queued(self, owner: str) -> JobRecord | None:
        """`owner` の `queued` のジョブで、`queued_at` が最も古いもの(Job Runner が取り出す)。"""
        records = self._list_jobs(JobStatus.QUEUED, owner, limit=1)
        return records[0] if records else None

    def list_running(self, owner: str) -> list[JobRecord]:
        """`owner` の `running` のジョブ(起動時の回復が `failed` にする)。

        件数は、実行中のジョブが 1 ソースに 1 つまでなので少ない。上限に達したら、取りこぼした
        一覧を成功にしない(回復の取りこぼしは、`running` のまま残るジョブになる)。
        """
        records = self._list_jobs(JobStatus.RUNNING, owner, limit=LIST_MAX_SIZE)
        if len(records) >= LIST_MAX_SIZE:
            raise StoreUnexpectedResponseError("job_list_truncated")
        return records

    def update(self, record: JobRecord, changes: Mapping[str, Any]) -> UpdateJobResult:
        """読んだ版を条件に、`changes` を重ねた内容で置き換える。"""
        body = {**record.fields, **changes}
        outcome = self._repository.replace_if_unchanged(
            record.job_id, body, seq_no=record.seq_no, primary_term=record.primary_term
        )
        if isinstance(outcome, Written):
            return JobUpdated(JobRecord(record.job_id, body, outcome.seq_no, outcome.primary_term))
        # 記録がない場合も `Conflict`(実 OpenSearch 3.9.0)。読み直して判定する。
        current = self.fetch(record.job_id)
        if current is not None and dict(current.fields) == body:
            return JobUpdated(current)  # 応答が失われた最初の書き込みが成功していた
        return JobSuperseded(current)

    def _list_jobs(self, status: JobStatus, owner: str, *, limit: int) -> list[JobRecord]:
        stored_records = self._repository.list_records(
            RecordFilter(
                equals={
                    "record_type": JOB_RECORD_TYPE,
                    "status": status.value,
                    "owner": owner,
                }
            ),
            _OLDEST_FIRST,
            limit=limit,
        )
        return [_to_job_record(stored) for stored in stored_records]


def _to_job_record(stored: StoredRecord) -> JobRecord:
    return JobRecord(stored.id, dict(stored.source), stored.seq_no, stored.primary_term)
