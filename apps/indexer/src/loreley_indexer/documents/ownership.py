"""書き込み前のロック所有確認(arch 8章、M-7)。登録と `last-seen` で共有する。"""

from loreley_indexer.common.clock import Clock
from loreley_indexer.common.locks import is_lock_owned
from loreley_indexer.documents.requests import CrawlContext
from loreley_indexer.infrastructure.opensearch import JobsReader


class LockOwnershipChecker:
    def __init__(self, jobs: JobsReader, clock: Clock) -> None:
        self._jobs = jobs
        self._clock = clock

    def is_owned(self, context: CrawlContext) -> bool:
        """文書ごとに呼ぶ。ロック文書の取得は毎回行い、期限切れを見逃さない。"""
        return is_lock_owned(
            self._jobs.fetch_lock(context.source_id),
            owner=context.lock.owner,
            job_id=context.lock.job_id,
            now=self._clock.now(),
        )
