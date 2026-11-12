"""`loreley-deletions` の読み書きの窓口(module 4.2、R5・R6)。

`deletion/` も削除結果の読み書きをこの窓口経由で行う(状態更新の責務を 1 か所にする。M-13)。

- 書き込みは条件付き(`if_seq_no`)。409 は戻り値で返し、読み直しと再判定は呼び出し側が行う(R8)。
- 終端状態へ遷移する書き込みは、保存した ID 一覧を同じ書き込みで削除し、ダイジェストは残す(K35)。
- 終端状態の結果は、ソースごとに直近 N 件だけ残す(U-2)。整理の対象は終端状態だけで、
  `running`(待機中を含む)は数えず、消さない。
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.errors import UnavailableError
from loreley_indexer.common.timestamps import format_instant
from loreley_indexer.crawl_runs.lifecycle.records import (
    DELETION_RESULT_RECORD_TYPE,
    DeletionReason,
    DeletionRecord,
    DeletionResultRecord,
    DeletionStatus,
    MalformedRecordError,
    deletion_record_id,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import (
    Conflict,
    Deleted,
    DeleteOutcome,
    NotFound,
    OpenSearchUnexpectedResponseError,
    RecordFilter,
    Rejected,
    SortKey,
    StoredDocument,
    StoreRepository,
    WriteOutcome,
    Written,
)
from loreley_indexer.infrastructure.opensearch.store import LIST_MAX_SIZE

logger = logging.getLogger(__name__)

ConditionalWrite = Written | Conflict | NotFound

_TERMINAL_STATUS_VALUES = [status.value for status in DeletionStatus if status.is_terminal]


@dataclass(frozen=True)
class StoredResult:
    """読んだ削除結果と、条件付き書き込みに使う版。"""

    record: DeletionResultRecord
    seq_no: int
    primary_term: int


@dataclass(frozen=True)
class StoredGeneration:
    record: DeletionRecord
    seq_no: int
    primary_term: int


def retry_after_conflict[T](attempt: Callable[[], T | Conflict], *, max_rereads: int) -> T:
    """`attempt`(読み直し → 再判定 → 条件付き書き込み)を、409 でなくなるまで繰り返す。

    最初の試行のあと、409 なら `max_rereads` 回まで読み直す。超えたら何も書かずに
    `UnavailableError`(api 層が 503 の再試行可能なエラーにする)。設計書に超過時の規定はなく、
    Crawler の再送で収束する(受理は冪等)ため、再試行可能な失敗に倒した。
    """
    for _ in range(1 + max_rereads):
        result = attempt()
        if not isinstance(result, Conflict):
            return result
    raise UnavailableError("write_conflict")


def queue_order_key(record: DeletionResultRecord) -> tuple[str, str]:
    """待ち行列の順序(arch 9.9 項6): `finish_received_at`、同値なら `crawl_id` の辞書順。"""
    if record.finish_received_at is None:
        raise ValueError("a result without finish_received_at is not in the queue")
    return (format_instant(record.finish_received_at), record.crawl_id)


class DeletionResults:
    def __init__(self, store: StoreRepository, *, retention_count: int, clock: Clock) -> None:
        self._store = store
        self._retention_count = retention_count
        self._clock = clock
        # 不正な記録は走査のたびに現れる。WARNING はプロセスごとに記録 1 件につき 1 回にする。
        self._warned_malformed_record_ids: set[str] = set()

    # --- 読み取り ---

    def fetch_result(self, crawl_id: str) -> StoredResult | None:
        stored = self._store.fetch(deletion_result_record_id(crawl_id))
        return _to_stored_result(stored) if stored is not None else None

    def fetch_generation(self, source_id: str) -> StoredGeneration | None:
        stored = self._store.fetch(deletion_record_id(source_id))
        if stored is None:
            return None
        return StoredGeneration(
            record=DeletionRecord.from_body(stored.source),
            seq_no=stored.seq_no,
            primary_term=stored.primary_term,
        )

    def list_running_without_finish(self, source_id: str) -> list[DeletionResultRecord]:
        """終了通知が届いていない `running` の結果(新しい開始通知で `superseded` にする対象)。"""
        record_filter = RecordFilter(
            equals={
                "record_type": DELETION_RESULT_RECORD_TYPE,
                "source_id": source_id,
                "status": DeletionStatus.RUNNING.value,
            },
            missing=("finish_received_at",),
        )
        return self._list(record_filter, [SortKey("started_at"), SortKey("crawl_id")])

    def list_non_terminal(self, source_id: str) -> list[DeletionResultRecord]:
        """そのソースの終端状態でない結果すべて(終了通知の待ち・待機中・判定中・実行中)。

        ソース削除1(破棄)の対象。順序は決めない。
        """
        record_filter = RecordFilter(
            equals={
                "record_type": DELETION_RESULT_RECORD_TYPE,
                "source_id": source_id,
                "status": DeletionStatus.RUNNING.value,
            }
        )
        return self._list(record_filter, [SortKey("started_at"), SortKey("crawl_id")])

    def list_unfinished_received(self, source_id: str | None = None) -> list[DeletionResultRecord]:
        """終了通知を受理済みで終端状態でない結果(待機中・判定中・実行中)。受理順。

        `source_id` を省略すると全ソース。件数は `LIST_MAX_SIZE` までで、通常は数件。
        """
        equals = {
            "record_type": DELETION_RESULT_RECORD_TYPE,
            "status": DeletionStatus.RUNNING.value,
        }
        if source_id is not None:
            equals["source_id"] = source_id
        record_filter = RecordFilter(equals=equals, exists=("finish_received_at",))
        records = self._list(record_filter, [])
        # 並べ替えは取得側に任せず、順序の規則(`queue_order_key`)を 1 か所で適用する。
        return sorted(records, key=queue_order_key)

    def preceding_results(self, record: DeletionResultRecord) -> list[DeletionResultRecord]:
        """先行する削除結果(arch 9.9 項6)。受理順(古い順)。

        同じソースで、`finish_received_at` が自分より前(同値なら `crawl_id` の辞書順)で
        終端状態でない結果。`finish_received_at` の無い `running` は先行にならない。
        """
        if record.finish_received_at is None:
            return []
        own_key = queue_order_key(record)
        return [
            other
            for other in self.list_unfinished_received(record.source_id)
            if queue_order_key(other) < own_key
        ]

    # --- 書き込み(すべて条件付き。409 は戻り値) ---

    def create_result(self, record: DeletionResultRecord) -> None:
        """新しい結果を書く。呼び出し側は、結果が無いことを確認済みで、ソース単位の直列処理の中にいる。"""
        _require_written(
            self._store.save(deletion_result_record_id(record.crawl_id), record.to_body())
        )

    def replace_generation(
        self, current: StoredGeneration | None, record: DeletionRecord
    ) -> ConditionalWrite:
        record_id = deletion_record_id(record.source_id)
        if current is None:
            return _to_conditional(self._store.save(record_id, record.to_body()))
        return _to_conditional(
            self._store.replace_if_unchanged(
                record_id,
                record.to_body(),
                seq_no=current.seq_no,
                primary_term=current.primary_term,
            )
        )

    def replace_result(
        self, current: StoredResult, record: DeletionResultRecord
    ) -> ConditionalWrite:
        """終端でない更新(受理、`deletion_started_at`、`deleted_count` の進捗など)。"""
        return _to_conditional(
            self._store.replace_if_unchanged(
                deletion_result_record_id(record.crawl_id),
                record.to_body(),
                seq_no=current.seq_no,
                primary_term=current.primary_term,
            )
        )

    def transition_to_terminal(
        self,
        current: StoredResult,
        status: DeletionStatus,
        *,
        reason: DeletionReason | None = None,
        reason_detail: str | None = None,
        progress: DeletionResultRecord | None = None,
    ) -> ConditionalWrite:
        """終端状態へ遷移する。保存した ID 一覧を同じ書き込みで削除し、ダイジェストは残す(K35)。

        `progress` は、判定・実行の記録(`n_seen`、`deleted_count`、`outcome` など)を反映した記録。
        省略すると `current.record` の状態だけを変える。書き込めたら、保持件数 N を超えた古い
        終端状態の結果を消す(整理の失敗は握る)。409・文書なしは戻り値で、読み直しは呼び出し側が行う(R8)。
        """
        if not status.is_terminal:
            raise ValueError("status must be a terminal status")
        base = progress if progress is not None else current.record
        terminal = replace(
            base,
            status=status,
            reason=reason,
            reason_detail=reason_detail,
            ended_at=self._clock.now(),
            skipped_document_ids=None,
            oversize_document_ids=None,
        )
        outcome = self.replace_result(current, terminal)
        if isinstance(outcome, Written):
            self._prune_best_effort(terminal.source_id)
        return outcome

    def delete_source_records(self, source_id: str) -> bool:
        """そのソースの削除の記録(`deletion-{source_id}` と `deletion_result-*`)をすべて消す。

        ソース削除3(arch 9.14 手順4)。何度呼んでも同じ結果になり(冪等)、すでにない記録は
        成功として扱う。1件でも消したら True、何もなければ False。
        """
        record_filter = RecordFilter(
            equals={"record_type": DELETION_RESULT_RECORD_TYPE, "source_id": source_id}
        )
        deleted_any = False
        while True:
            results = self._store.list_records(record_filter, [], limit=LIST_MAX_SIZE)
            for result in results:
                deleted_any |= _was_deleted(self._store.delete(result.id))
            # 一覧の上限に達していたら、まだ残りがありうるので繰り返す。
            if len(results) < LIST_MAX_SIZE:
                break
        deleted_any |= _was_deleted(self._store.delete(deletion_record_id(source_id)))
        return deleted_any

    def prune_terminal_results(self, source_id: str) -> None:
        """終端状態の結果を新しい順に `retention_count` 件残し、古いものを消す。"""
        record_filter = RecordFilter(
            equals={"record_type": DELETION_RESULT_RECORD_TYPE, "source_id": source_id},
            one_of={"status": _TERMINAL_STATUS_VALUES},
        )
        newest_first = [
            SortKey("ended_at", descending=True),
            SortKey("started_at", descending=True),
            SortKey("crawl_id", descending=True),
        ]
        terminal = self._store.list_records(record_filter, newest_first, limit=LIST_MAX_SIZE)
        for stale in terminal[self._retention_count :]:
            self._store.delete(stale.id)

    # --- 内部 ---

    def _prune_best_effort(self, source_id: str) -> None:
        """整理に失敗しても、終端状態の書き込みは成功のまま(次の終端遷移で整理される)。

        失敗を伝播すると、書き込み済みの遷移が失敗に見えて再試行され、すでに終端になった
        結果を読み直して二重に処理しかねない。
        """
        try:
            self.prune_terminal_results(source_id)
        except UnavailableError as error:
            logger.warning(
                "pruning terminal deletion results failed: error=%s", type(error).__name__
            )

    def _list(self, record_filter: RecordFilter, sort: list[SortKey]) -> list[DeletionResultRecord]:
        """形式が不正な記録は、ID だけをログに出して一覧から除く。

        1 件の不正で一覧全体が失敗すると、起動時の整理や削除ワーカーの走査が、ほかの結果の
        処理にも進めない(再起動のたびに落ちる)ため。不正な記録は読まず、書き換えもしない。
        ログは、同じ記録について最初の 1 回だけ WARNING で、以降の走査は DEBUG にする。
        """
        records: list[DeletionResultRecord] = []
        for item in self._store.list_records(record_filter, sort, limit=LIST_MAX_SIZE):
            try:
                records.append(DeletionResultRecord.from_body(item.source))
            except MalformedRecordError:
                is_first_time = item.id not in self._warned_malformed_record_ids
                self._warned_malformed_record_ids.add(item.id)
                logger.log(
                    logging.WARNING if is_first_time else logging.DEBUG,
                    "a malformed deletion record was skipped: record_id=%s",
                    item.id,
                )
        return records


def _to_stored_result(stored: StoredDocument) -> StoredResult:
    return StoredResult(
        record=DeletionResultRecord.from_body(stored.source),
        seq_no=stored.seq_no,
        primary_term=stored.primary_term,
    )


def _to_conditional(outcome: WriteOutcome) -> ConditionalWrite:
    if isinstance(outcome, Rejected):
        # 固定の形の記録が拒否されるのは、文書ではなく Indexer 側の異常。
        raise OpenSearchUnexpectedResponseError(outcome.error_type)
    return outcome


def _was_deleted(outcome: DeleteOutcome) -> bool:
    """削除できたら True、すでにない記録なら False(成功として扱う)。"""
    if isinstance(outcome, Rejected):
        raise OpenSearchUnexpectedResponseError(outcome.error_type)
    if isinstance(outcome, Conflict):
        # 条件なしの削除は 409 にならない。想定外の応答。
        raise OpenSearchUnexpectedResponseError("conflict")
    return isinstance(outcome, Deleted)


def _require_written(outcome: WriteOutcome) -> None:
    if not isinstance(_to_conditional(outcome), Written):
        raise OpenSearchUnexpectedResponseError(type(outcome).__name__.lower())
