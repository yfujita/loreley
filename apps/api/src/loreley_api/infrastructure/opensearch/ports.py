"""Reader の入口(Protocol)と、Reader が返す素の値の型(D 4.8。C 3.3)。

`admin` が `infrastructure.opensearch` から import してよいのは、この Protocol と型だけ(D 6章 R6)。
**どの Protocol にも書き込みを表すメソッドを置かない**(R8 (c)。`tests/architecture` が検査する)。

Reader の各メソッドは `Ok(値)` か `Failed` を返し、OpenSearch 由来の例外を呼び出し側へ漏らさない
(C 8.6)。例外になるのは、呼び出し側の誤り(窓を超えるページ指定など)だけで、`ValueError`。

`mget` を使うメソッド(`get_locks`・`get_jobs`・`get`・`get_result`)は、文書ごとに成否を返す
(他の文書の結果は使える。C 3.2)。`mget` 全体が失敗したときは、すべての ID が同じ `Failed`。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from loreley_api.common.results import Result

# 文書の `_source`。値は Crawler・Indexer が書いたもので、読めるかどうかは導出が確かめる(C 5.0)。
type Source = Mapping[str, object]

# C 9章の固定の上限。`admin` は `common` にしか依存しない葉(`admin.base`)にも同じ値を持つ。
MAX_RESULT_WINDOW = 10_000
MAX_ITEMS_PER_PAGE = 100
# `loreley-sources` の全件取得の上限。超えたら取りこぼしを避けるため `Failed`(B 3.1)。
MAX_SOURCES = 10_000
# `existence`(R-11)の 1 回の問い合わせの上限(`MAX_ITEMS_PER_PAGE` と同じ)。
MAX_EXISTENCE_IDS = 100

# `JobBrief` の項目(C 3.3 R-3)。
JOB_BRIEF_FIELDS: tuple[str, ...] = (
    "job_id",
    "source_id",
    "job_type",
    "trigger",
    "status",
    "force_delete",
    "rewrite_mode",
    "queued_at",
    "started_at",
    "finished_at",
    "failure_reason",
)
# EP-10 のジョブ詳細の項目(C 3.3 R-5)。`finish_notice` は ID の一覧を持つので、必要な項目だけ読む。
JOB_DETAIL_FIELDS: tuple[str, ...] = (
    *JOB_BRIEF_FIELDS,
    "failure_detail",
    "warnings",
    "registration",
    "deletion_summary",
    "confirmation",
    "settings_snapshot",
    "finish_notice.send_started_at",
)
LOCK_FIELDS: tuple[str, ...] = (
    "record_type",
    "source_id",
    "job_id",
    "lease_expires_at",
    "acquired_at",
)

CountTarget = Literal["document_count", "skipped", "oversize", "extract_failed", "summary_pending"]


@dataclass(frozen=True)
class StoredRecord:
    """取得した文書 1 件。`record_id` は文書の `_id`(`job_id` の元になる。C 5.0)。"""

    record_id: str
    # 読み取りで指定した項目(`_source_includes`)だけが入る。`mget` で `record_type` を確かめる
    # メソッドでは、指定になくても `record_type` が入ることがある。
    source: Source


@dataclass(frozen=True)
class PageRequest:
    """ページ指定。`page * items_per_page` は窓(10,000)を超えられない(C 3.2。API 層で検証済み)。"""

    page: int
    items_per_page: int
    # 並べ替えの項目(一覧ごとに 1 つ。B 2.1)を降順にするか。同順位は ID の昇順。
    descending: bool

    def __post_init__(self) -> None:
        if self.page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= self.items_per_page <= MAX_ITEMS_PER_PAGE:
            raise ValueError("items_per_page is out of range")
        if self.page * self.items_per_page > MAX_RESULT_WINDOW:
            raise ValueError("page window exceeds the result window")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.items_per_page


@dataclass(frozen=True)
class Page:
    """一覧の 1 ページ。`total` は絞り込み後の総件数(窓を超えても正確)。"""

    total: int
    items: tuple[StoredRecord, ...]


@dataclass(frozen=True)
class JobListQuery:
    """EP-09 の絞り込み。`statuses` が空なら絞らない。複数なら、そのどれか(`active`)。"""

    page: PageRequest
    source_id: str | None = None
    statuses: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceJobsSummary:
    """ソース 1 件の、最新のジョブと最終完了日時(R-3)。該当がなければ `None`。"""

    latest_crawl: StoredRecord | None
    latest_source_delete: StoredRecord | None
    # `succeeded`・`partially_succeeded` の `crawl` の `finished_at` の最大(エポックミリ秒)。
    last_completed_epoch_millis: int | None


@dataclass(frozen=True)
class ClusterSnapshot:
    """EP-12 の元の値(R-12)。値は応答のまま返し、正規化は `derivation` が行う(C 3.4)。"""

    health: Source
    indices: tuple[Source, ...]
    shards: tuple[Source, ...]
    nodes: tuple[Source, ...]


# ID(`source_id`・`job_id`)をキーにした、文書ごとの取得結果。文書がなければ `Ok(None)`。
type RecordResults = dict[str, Result[StoredRecord | None]]


class SourcesReader(Protocol):
    def list_all(self) -> Result[tuple[StoredRecord, ...]]:
        """R-1: データソースの全件(`connector_config` を除く)。上限を超えたら `Failed`。"""
        ...

    def get(self, source_id: str, fields: Sequence[str] | None) -> Result[StoredRecord | None]:
        """R-2: 1 件の取得。`fields` が `None` なら全項目、空なら存在確認だけ(`_source` なし)。"""
        ...


class JobsReader(Protocol):
    def latest_by_source(self, source_ids: Sequence[str]) -> Result[dict[str, SourceJobsSummary]]:
        """R-3: ソースごとの最新ジョブ。ジョブが 1 件もないソースはキーがない。"""
        ...

    def get_locks(self, source_ids: Sequence[str]) -> RecordResults:
        """R-4: ロック文書。キーは `source_id`。`record_type` が `lock` でなければ `Ok(None)`。"""
        ...

    def get_jobs(self, job_ids: Sequence[str], fields: Sequence[str]) -> RecordResults:
        """R-5: ジョブ記録。`record_type` が `job` でなければ `Ok(None)`。"""
        ...

    def list_jobs(self, query: JobListQuery) -> Result[Page]:
        """R-6: ジョブ一覧(`queued_at`、同順位は `job_id` 昇順)。"""
        ...

    def latest_crawl_id(self, source_id: str) -> Result[str | None]:
        """R-7: そのソースの最新の `crawl` ジョブの ID。"""
        ...

    def list_skipped(self, source_id: str, page: PageRequest) -> Result[Page]:
        """R-10: `skipped` タブ(`last_skipped_at`)。"""
        ...

    def list_oversize(self, source_id: str, page: PageRequest) -> Result[Page]:
        """R-10: `oversize` タブ(`last_detected_at`)。"""
        ...


class DeletionsReader(Protocol):
    def get_result(self, job_id: str) -> Result[StoredRecord | None]:
        """R-8: 削除結果。`record_type` が `deletion_result` でなければ `Ok(None)`。"""
        ...


class SearchIndexReader(Protocol):
    def count_by_source(self, source_ids: Sequence[str]) -> Result[dict[str, int]]:
        """R-9(EP-01): ソースごとの登録文書数。文書のないソースは 0。"""
        ...

    def list_extract_failed(self, source_id: str, page: PageRequest) -> Result[Page]:
        """R-10: `extract_failed` タブ(`last_seen_at`)。"""
        ...

    def list_summary_pending(self, source_id: str, page: PageRequest) -> Result[Page]:
        """R-10: `summary_pending` タブ(`indexed_at`)。"""
        ...

    def existing_ids(self, document_ids: Sequence[str]) -> Result[frozenset[str]]:
        """R-11: 検索インデックスにある `document_id` の集合(100 件まで)。"""
        ...


class CountsReader(Protocol):
    def count_for_source(
        self, source_id: str, targets: Sequence[CountTarget]
    ) -> dict[CountTarget, Result[int]]:
        """R-9(EP-02・11): 件数。サブ要求ごとに成否が分かれる(1 つの失敗が他に影響しない)。"""
        ...


class ClusterReader(Protocol):
    def read(self) -> Result[ClusterSnapshot]:
        """R-12: `cluster.health` と `cat.*` を逐次に読む。最初の失敗で打ち切る。"""
        ...
