"""登録の受理条件の照会(arch 9.5、`loreley-deletions-v0.9.md` 4.1。K23)。

バッチ登録と `last_seen_at` の部分更新が、書き込みの前にリクエストの先頭で 1 回呼ぶ。
`deletion_result` の読み方を 1 か所にするため、判定は lifecycle が持つ(M-6)。
読み取りだけを行う(R6)。ロック所有の確認(条件 6)は文書ごとの処理で、ここでは扱わない。
"""

from dataclasses import dataclass
from datetime import datetime

from loreley_indexer.common.errors import (
    CrawlAlreadyClosedError,
    CrawlFinishedError,
    CrawlNotStartedError,
    CrawlSourceMismatchError,
    CrawlStartedAtMismatchError,
)
from loreley_indexer.common.timestamps import format_instant
from loreley_indexer.crawl_runs.lifecycle.records import (
    DeletionResultRecord,
    DeletionStatus,
    deletion_result_record_id,
)
from loreley_indexer.infrastructure.opensearch import StoreReader


@dataclass(frozen=True)
class Admission:
    """受理した結果。バッチ登録は `rewrite_mode` を、この値から使う(K33)。"""

    rewrite_mode: bool


class AdmissionChecker:
    def __init__(self, deletions_store: StoreReader) -> None:
        self._deletions_store = deletions_store

    def check(self, *, source_id: str, crawl_id: str, crawl_started_at: datetime) -> Admission:
        """受理条件 1〜5 を順に確認し、満たさなければリクエスト全体の拒否として例外を送出する。

        `crawl_started_at` は、ミリ秒精度の UTC に正規化して、複写した値と比べる
        (表記の違いでは拒否しない)。
        例外は `AdmissionRejectedError` のサブクラスで、拒否の種類ごとに分かれる。
        OpenSearch の全体異常は `UnavailableError` のまま伝播する。
        """
        stored = self._deletions_store.fetch(deletion_result_record_id(crawl_id))
        if stored is None:
            raise CrawlNotStartedError
        result = DeletionResultRecord.from_body(stored.source)

        if result.source_id != source_id:
            raise CrawlSourceMismatchError
        if format_instant(result.crawl_started_at) != format_instant(crawl_started_at):
            raise CrawlStartedAtMismatchError
        # 状態と終了通知の受理は両方必要(arch 9.5): `failed`・`cancelled` の終了通知では
        # `finish_received_at` が記録されず、`enumeration_completed` の受理後は `running` のまま。
        if result.status is not DeletionStatus.RUNNING:
            raise CrawlAlreadyClosedError
        if result.finish_received_at is not None:
            raise CrawlFinishedError
        return Admission(rewrite_mode=result.rewrite_mode)
