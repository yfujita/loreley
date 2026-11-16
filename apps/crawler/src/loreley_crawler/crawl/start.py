"""実行開始(architecture 4.5 の手順 6〜8。module 4.5。CA-P-51)。

Job Runner がリースを設定した後、次の順に行う。
1. `queued` -> `running`(`started_at` を書く。取り消しに負けたら `JobNotStartable`)
2. `loreley-sources` を **1 度だけ**読む。`ttl`・`ratio_threshold`・`min_delete_count` と
   `connector_config` を、この 1 回の結果で確定する。設定がない・`deleting`・値の欠落・型違いは
   `config_invalid`(開始通知の前。`running` からの `failed`)
3. 設定スナップショット(6 項目)と `settings_source_updated_at` を、ジョブ記録に追記する
4. メンテナンスフラグを再確認する(立っていれば `MaintenanceDetected`)
5. 保持した `connector_config` で `validate_config`・`create`(設定は読み直さない)。失敗は
   `config_invalid` / `enumeration_failed`

`connector_config` は、このモジュールの局所変数にだけ持つ。ジョブ記録・`JobContext`・ログ・例外・
`CrawlRun` の状態には出さない(中身は不透明で、認証情報の参照名を含みうる。R11)。
"""

from dataclasses import dataclass

from loreley_crawler.common.errors import StoreUnexpectedResponseError, is_store_unavailable
from loreley_crawler.common.timestamps import parse_instant
from loreley_crawler.connectors.interface import (
    Connector,
    ConnectorError,
    ConnectorType,
    ErrorCategory,
    RetryHint,
)
from loreley_crawler.connectors.registry import ConnectorRegistry
from loreley_crawler.crawl.constants import LOCAL_CHECKS
from loreley_crawler.crawl.failure import CrawlFailure
from loreley_crawler.crawl.snapshot import SettingsSnapshot
from loreley_crawler.infrastructure.indexer_client import LockInfo
from loreley_crawler.jobs import Check, FailureReason, JobContext, JobRecord
from loreley_crawler.sources import MalformedSourceRecord, SourceReader, SourceRecord, SourceStatus

# `failure_detail` の固定文(architecture 4.8。設定なし・`deleting`・欠落・型違いを区別する)。
SOURCE_NOT_FOUND_DETAIL = "データソースの設定が存在しない"
SOURCE_DELETING_DETAIL = "データソースは削除中である"
CONNECTOR_TYPE_UNREGISTERED_DETAIL = "データソースの connector_type が登録されていない"
_SOURCE_MALFORMED_DETAIL = "データソースの設定の値が欠けている、または型が合わない"


@dataclass(frozen=True)
class PreparedCrawl:
    """実行開始が整えたもの。`connector` を閉じるのは `CrawlRun`。"""

    source_id: str
    snapshot: SettingsSnapshot
    lock: LockInfo
    connector: Connector


def prepare_crawl(
    *,
    record: JobRecord,
    context: JobContext,
    source_reader: SourceReader,
    connector_registry: ConnectorRegistry,
) -> PreparedCrawl:
    source_id = record.source_id
    started_at = context.start_running()

    source = _read_usable_source_once(context, source_reader, source_id)
    snapshot = SettingsSnapshot(
        crawl_started_at=parse_instant(started_at),
        ttl=source.ttl,
        ratio_threshold=source.ratio_threshold,
        min_delete_count=source.min_delete_count,
        force_delete=_job_flag(record, "force_delete"),
        rewrite_mode=_job_flag(record, "rewrite_mode"),
    )
    context.record_settings(snapshot.to_record(), source.updated_at)
    context.check(Check.ALL)  # 手順 7: メンテナンスフラグの再確認(所有・取り消しも)

    connector_type = connector_registry.find(source.connector_type)
    if connector_type is None:
        raise CrawlFailure(FailureReason.CONFIG_INVALID, CONNECTOR_TYPE_UNREGISTERED_DETAIL)
    connector = _create_connector(context, connector_type, source_id, source.connector_config)
    return PreparedCrawl(
        source_id=source_id,
        snapshot=snapshot,
        lock=LockInfo(owner=_job_owner(record), job_id=context.job_id),
        connector=connector,
    )


def _read_usable_source_once(
    context: JobContext, source_reader: SourceReader, source_id: str
) -> SourceRecord:
    stored = context.retrier(LOCAL_CHECKS).run(
        lambda: source_reader.fetch(source_id), is_retryable_error=is_store_unavailable
    )
    if stored is None:
        raise CrawlFailure(FailureReason.CONFIG_INVALID, SOURCE_NOT_FOUND_DETAIL)
    if isinstance(stored, MalformedSourceRecord):
        if stored.status is SourceStatus.DELETING:
            raise CrawlFailure(FailureReason.CONFIG_INVALID, SOURCE_DELETING_DETAIL)
        # 項目名だけを載せる(値は載せない)。
        invalid_fields = "、".join(stored.invalid_fields)
        raise CrawlFailure(
            FailureReason.CONFIG_INVALID, f"{_SOURCE_MALFORMED_DETAIL}: {invalid_fields}"
        )
    if stored.status is SourceStatus.DELETING:
        raise CrawlFailure(FailureReason.CONFIG_INVALID, SOURCE_DELETING_DETAIL)
    return stored


def _create_connector(
    context: JobContext, connector_type: ConnectorType, source_id: str, connector_config: object
) -> Connector:
    try:
        connector_type.validate_config(connector_config)
        # 列挙の前なので、一時的な失敗(`source_unreachable` など)はリトライする(6.2)。
        return context.retrier(Check.ALL).run(
            lambda: connector_type.create(source_id, connector_config),
            is_retryable_error=lambda error: (
                isinstance(error, ConnectorError) and error.retry is RetryHint.TRANSIENT
            ),
        )
    except ConnectorError as error:
        reason = (
            FailureReason.CONFIG_INVALID
            if error.category is ErrorCategory.CONFIG_INVALID
            else FailureReason.ENUMERATION_FAILED
        )
        raise CrawlFailure(reason, f"{error.category.value}: {error.message}") from None


def _job_flag(record: JobRecord, name: str) -> bool:
    value = record.fields.get(name)
    if type(value) is not bool:
        raise StoreUnexpectedResponseError("malformed_job_record")
    return value


def _job_owner(record: JobRecord) -> str:
    owner = record.fields.get("owner")
    if not isinstance(owner, str):
        raise StoreUnexpectedResponseError("malformed_job_record")
    return owner
