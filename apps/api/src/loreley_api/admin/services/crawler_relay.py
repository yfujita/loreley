"""Crawler への中継の共通手順(EP-03〜08。C 4.2・4.6。D 4.5・5.1)。

Crawler の呼び出しは `crawler` の枠でスレッドに渡し、1 回だけ送る(再送しない)。返り値は
`crawler_mapping` で、成功または `AdminApiError` に写す。

409 `lock_held`・`lock_in_use` のときだけ、付随情報の `lock_state` を、Crawler の応答の**後**に
ロック文書 → ジョブ記録の順で読んで導出する(C 4.6。ロックから始める)。読み取りが失敗しても
`lock_state=unknown` にするだけで、409 のステータスと `existing_job` は変えない(付随情報のために
失敗にしない)。
"""

from collections.abc import Callable
from dataclasses import dataclass

from loreley_api.admin.base.codes import LockState
from loreley_api.admin.base.errors import AdminApiError
from loreley_api.admin.crawler_mapping import (
    CrawlerOperation,
    RequestedOptions,
    TtlField,
    needs_lock_state,
    translate,
)
from loreley_api.admin.services.lock_view import LockViewService
from loreley_api.common.clock import Clock
from loreley_api.common.concurrency import CATEGORY_CRAWLER, BlockingRunner
from loreley_api.infrastructure.crawler_client import CrawlerResult, CrawlerSucceeded


@dataclass(frozen=True)
class WithStatus[BodyT]:
    """Crawler の成功のステータス(200・201・202)を、応答に引き継ぐ EP の結果。"""

    status_code: int
    body: BodyT


class CrawlerRelay:
    def __init__(self, *, runner: BlockingRunner, lock_view: LockViewService, clock: Clock) -> None:
        self._runner = runner
        self._lock_view = lock_view
        self._clock = clock

    async def send(
        self,
        operation: CrawlerOperation,
        call: Callable[[], CrawlerResult],
        *,
        lock_source_id: str | None = None,
        requested: RequestedOptions | None = None,
        ttl_field: TtlField = "ttl_seconds",
    ) -> CrawlerSucceeded:
        """`call`(Crawler クライアントの 1 操作)を送り、成功の返り値を返す。失敗は `AdminApiError`。

        `lock_source_id`: 409 `lock_held`・`lock_in_use` の `lock_state` を読むソース
        (EP-05・06・08 が渡す)。`requested`・`ttl_field` は `translate` にそのまま渡す。
        """
        result = await self._runner.run(CATEGORY_CRAWLER, call)
        lock_state = LockState.UNKNOWN
        if needs_lock_state(operation, result):
            if lock_source_id is None:
                raise ValueError("lock_source_id is required for a lock conflict")
            lock_state = await self._read_lock_state(lock_source_id)
        translated = translate(
            operation, result, lock_state=lock_state, requested=requested, ttl_field=ttl_field
        )
        if isinstance(translated, AdminApiError):
            raise translated
        return translated

    async def _read_lock_state(self, source_id: str) -> LockState:
        # 時刻は、Crawler が応答した後(ロックが取られた後)のもの。`just_acquired` の猶予の判定が、
        # 呼び出しの前の時刻でずれないようにする。
        reading = await self._lock_view.read(source_id, now=self._clock.now())
        if reading.lock is None:
            return LockState.UNKNOWN
        return reading.lock.state
