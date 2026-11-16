"""`indexer_client` の型付きの結果(module 4.9。indexer-api 3.4・4章)。

どの操作も、成功の型、`IndexerUnavailable`、`IndexerRejected` のどれかを返す(例外にしない)。
呼び出し側(`crawl`・`source_delete`)が、リトライの判断とジョブの扱いを決める(architecture 7.8)。
- `IndexerUnavailable`: 500・503・接続エラー・タイムアウト。リトライの対象。
- `IndexerRejected`: 400・409・404・405・その他の HTTP エラーと、2xx なのに契約と合わないとき
  (成功のステータスの違い、応答の形・要請との対応の不一致)。リトライしない(Crawler の不整合・
  契約外の呼び出しの疑い)。

結果に、本文・リクエストの値・Indexer のエラーメッセージを載せない(R11)。`reason`・`error_code` は
固定の短い文字列だけ。
"""

from dataclasses import dataclass
from enum import StrEnum

# 2xx なのに契約と合わない: 成功のステータスが契約と違う(開始通知などは 200、終了通知は 202)、
# または応答が合わない(JSON でない、必須の項目がない、未知の値、要請と結果の対応が合わない)。
MALFORMED_RESPONSE = "malformed_response"


@dataclass(frozen=True)
class IndexerUnavailable:
    """Indexer が応答できない。

    `reason` は `http_500`・`http_503`・`connection_error`・`timeout`。
    """

    reason: str


@dataclass(frozen=True)
class IndexerRejected:
    """Indexer が要請を受け付けなかった。

    `error_code` は Indexer の共通エラー形式の `error.code`(`crawl_start_conflict`・
    `lock_not_owned` など)。応答にコードがない・形が合わない(英小文字・数字・`_` の
    64 文字以内でない)ときは None。2xx なのに契約と合わないときは `MALFORMED_RESPONSE`。
    """

    status_code: int
    error_code: str | None


@dataclass(frozen=True)
class Succeeded:
    """成功(開始通知の 200、終了通知の 202)。

    終了通知の 202 は、冪等に処理されたことだけを示す。受理の確認ではない(architecture 7.5。
    受理は Status API の最初の応答で確認する)。
    """


class LastSeenResult(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"  # 現在値以上のため書かなかった。バッチ登録の `Change.UNCHANGED` とは別
    NOT_FOUND = "not_found"  # 新規文書では正常
    UPDATE_CONFLICT = "update_conflict"  # 上限付きでリトライ。解消しなければジョブ `failed`
    LOCK_NOT_OWNED = "lock_not_owned"  # ジョブ `failed`(`lock_lost`)


@dataclass(frozen=True)
class LastSeenEntry:
    document_id: str
    result: LastSeenResult


@dataclass(frozen=True)
class LastSeenResults:
    """`last-seen` の文書ごとの結果(要請の `document_ids` と同じ順)。"""

    entries: tuple[LastSeenEntry, ...]


class Change(StrEnum):
    """本文・メタデータに関する変更区分(`status: ok` のとき)。"""

    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class FailureType(StrEnum):
    DOCUMENT_REJECTED = "document_rejected"  # 文書固有の拒否。リトライ後にスキップ
    OVERSIZE = "oversize"  # 原本サイズ超過。リトライしない
    LOCK_NOT_OWNED = "lock_not_owned"  # ジョブ `failed`(`lock_lost`)
    WRITE_CONFLICT = "write_conflict"  # 上限付きでリトライ。解消しなければジョブ `failed`
    UPDATE_CONFLICT = "update_conflict"  # 同上


@dataclass(frozen=True)
class DocumentRegistered:
    """`status: ok`。`extract_failed` は、抽出に失敗してタイトルとメタデータを登録した場合。"""

    external_id: str
    document_id: str
    change: Change
    extract_failed: bool


@dataclass(frozen=True)
class DocumentFailed:
    """`status: failed`。Indexer の `message` は、載せない(失敗の種類だけを使う)。"""

    external_id: str
    document_id: str
    failure_type: FailureType


DocumentResult = DocumentRegistered | DocumentFailed


@dataclass(frozen=True)
class BatchResults:
    """バッチ登録の文書ごとの結果(要請の `documents` と同じ順)。

    `document_id` を Crawler の算出値と照合するのは呼び出し側(architecture 7.11)。
    """

    documents: tuple[DocumentResult, ...]


@dataclass(frozen=True)
class CrawlStatus:
    """Status API の応答のうち、削除結果の要約(architecture 7.6)に使う項目。

    値のない項目(未記録・該当しない)は None。時刻は Indexer が返した文字列のまま。
    `status` が `running` 以外なら終端状態。`waiting_for` は、待機中の先行する `crawl_id`。
    """

    crawl_id: str
    source_id: str
    status: str
    reason: str | None = None
    forced: bool | None = None
    target_count: int | None = None
    denominator: int | None = None
    deleted_count: int | None = None
    enumerated_count: int | None = None
    n_seen: int | None = None
    e_missing: int | None = None
    finish_received_at: str | None = None
    deletion_started_at: str | None = None
    finished_at: str | None = None
    waiting_for: str | None = None


@dataclass(frozen=True)
class DiscardResult:
    """ソース削除 1。`discarded` にした `crawl_id`。"""

    discarded_crawl_ids: tuple[str, ...]


@dataclass(frozen=True)
class DocumentsDeleted:
    """ソース削除 2。再送では 0 件でも成功。"""

    deleted_count: int


@dataclass(frozen=True)
class DeletionRecordsDeleted:
    """ソース削除 3。すでに記録がなければ `deleted` は False(成功)。"""

    deleted: bool


StartReply = Succeeded | IndexerUnavailable | IndexerRejected
FinishReply = Succeeded | IndexerUnavailable | IndexerRejected
LastSeenReply = LastSeenResults | IndexerUnavailable | IndexerRejected
BatchReply = BatchResults | IndexerUnavailable | IndexerRejected
StatusReply = CrawlStatus | IndexerUnavailable | IndexerRejected
DiscardReply = DiscardResult | IndexerUnavailable | IndexerRejected
DeleteDocumentsReply = DocumentsDeleted | IndexerUnavailable | IndexerRejected
DeleteRecordsReply = DeletionRecordsDeleted | IndexerUnavailable | IndexerRejected
