"""`api` が使う部品の束。`main.py`(とテスト)が組み立てて `create_app` に渡す。

`api` は `jobs`・`sources` の入口だけを呼ぶ(R4)。グローバルな状態は持たない。
"""

from dataclasses import dataclass

from loreley_crawler.common.retry import Retrier
from loreley_crawler.jobs import JobAdmission, JobCancellation, LockRelease
from loreley_crawler.sources import ConnectorRegistry, SourceStore


@dataclass(frozen=True)
class ApiDependencies:
    """
    - `retrier`: 設定の更新で `connector_type` を読むときのリトライ(確認点なし。HTTP ハンドラ用)
    - `connector_registry`: 設定の登録・更新で `connector_type` と `connector_config` を検証する
    """

    job_admission: JobAdmission
    job_cancellation: JobCancellation
    lock_release: LockRelease
    source_store: SourceStore
    connector_registry: ConnectorRegistry
    retrier: Retrier
