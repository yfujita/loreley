from typing import ClassVar


class IndexerError(Exception):
    """Indexer が意図して送出する例外の基底。メッセージに本文・秘密情報を入れない。"""


class UnavailableError(IndexerError):
    """OpenSearch など、下位システム全体の異常。

    呼び出し側は個別に処理せず伝播させ、api 層が 503 `unavailable`(retryable)に変換する。
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class UnexpectedResponseError(IndexerError):
    """下位システムの想定外の応答。クエリやマッピングの誤りなど、再試行で直らない異常。

    `error_type` は種別名だけ(例: `parsing_exception`)。api では 500 にして、種別名をログに残す。
    """

    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


class ContractError(IndexerError):
    """契約(api 3.4)で HTTP エラーとして返す、リクエスト全体の拒否。

    api 層が `status_code`・`code`・`message`・`retryable` から共通エラー形式の応答を作る。
    `message` は固定文で、リクエストの値(本文、ID など)を含めない。
    """

    status_code: ClassVar[int]
    code: ClassVar[str]
    message: ClassVar[str]
    retryable: ClassVar[bool] = False

    def __init__(self) -> None:
        super().__init__(self.message)


class AdmissionRejectedError(ContractError):
    """登録の受理条件(arch 9.5)を満たさない。1 件も書かず、リトライしても直らない(409)。"""

    status_code = 409


class CrawlNotStartedError(AdmissionRejectedError):
    code = "crawl_not_started"
    message = "no deletion result exists for the crawl"


class CrawlSourceMismatchError(AdmissionRejectedError):
    code = "crawl_source_mismatch"
    message = "source_id does not match the crawl"


class CrawlStartedAtMismatchError(AdmissionRejectedError):
    code = "crawl_started_at_mismatch"
    message = "crawl_started_at does not match the crawl"


class CrawlAlreadyClosedError(AdmissionRejectedError):
    code = "crawl_already_closed"
    message = "the crawl is already closed"


class CrawlFinishedError(AdmissionRejectedError):
    code = "crawl_finished"
    message = "the finish notification of the crawl was already accepted"


class NotificationRejectedError(ContractError):
    """開始通知・終了通知の拒否。状態は変えず、リトライしても直らない(409)。"""

    status_code = 409


class CrawlAlreadyFinishedError(NotificationRejectedError):
    """開始通知の `crawl_id` の削除結果が、すでに終端状態(arch 9.5 の判定 1)。"""

    code = "crawl_already_finished"
    message = "the crawl is already finished"


class CrawlStartConflictError(NotificationRejectedError):
    """開始通知の再送が、複写済みの項目と一致しない(arch 9.5 の判定 2。K24)。"""

    code = "crawl_start_conflict"
    message = "the start notification differs from the one already accepted for the crawl"


class StaleCrawlStartedAtError(NotificationRejectedError):
    """`crawl_started_at` が現行世代より古い(arch 9.5 の判定 3)。"""

    code = "stale_crawl_started_at"
    message = "crawl_started_at is older than the current generation"


class FinishSourceMismatchError(NotificationRejectedError):
    """終了通知の `source_id` が `deletion_result` のものと違う(K32、K40)。"""

    code = "finish_source_mismatch"
    message = "source_id does not match the crawl"


class FinishContentMismatchError(NotificationRejectedError):
    """終了通知の再送が、最初に受理した内容と違う(K25、K40)。"""

    code = "finish_content_mismatch"
    message = "the finish notification differs from the one already accepted for the crawl"


class CrawlNotFoundError(ContractError):
    """Status API の対象の削除結果がない(保持件数を超えて消えた、開始通知を受けていない、喪失)。"""

    status_code = 404
    code = "crawl_not_found"
    message = "the crawl was not found"


class LockNotOwnedError(ContractError):
    """ソース削除 2・3 の要請者が、ソースのロックを所有していない(api 3.4、4.7、4.8。plan 案 8)。

    ロック文書なし・期限切れ・所有者不一致のすべて。何も書かずに拒否する。
    リクエスト全体の 409 で、リトライしても直らない(Crawler はジョブを `failed` にする)。
    文書単位の `lock_not_owned`(登録・`last-seen`)とは別のもの。
    """

    status_code = 409
    code = "lock_not_owned"
    message = "the lock for the source is not owned by the requester"
