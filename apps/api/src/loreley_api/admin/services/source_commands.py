"""データソースの登録・更新・削除(EP-03・04・05。C 4章。D 5.1・5.4)。

Admin API が検証するのは自身の責務の範囲だけ(B 2.4)。`connector_config` の中身・`schedule_cron` の
書式・`connector_type` の値は検証せず、Crawler に任せる(複製しない。AAPI-K-5)。検証に違反があれば、
Crawler に送らずに 400 `invalid_request`(違反はすべて返す。値は載せない)。通れば、TTL(日 → 秒)と
しきい値(% → 0〜1)を十進数で換算して Crawler に中継し、返ってきた保存内容を応答の単位に戻す。
"""

import math
from dataclasses import dataclass
from functools import partial

from loreley_api.admin.base.codes import Reason
from loreley_api.admin.base.errors import FieldViolation, crawler_error, invalid_request
from loreley_api.admin.crawler_mapping import CrawlerOperation, TtlField
from loreley_api.admin.derivation.units import (
    InvalidValue,
    percent_to_ratio,
    ttl_days_to_seconds,
    validate_min_delete_count,
    validate_ttl_seconds,
)
from loreley_api.admin.schemas.common import JobAccepted, SourceSettings
from loreley_api.admin.schemas.sources import RegisterSourceBody, UpdateSourceBody
from loreley_api.admin.services.crawler_relay import CrawlerRelay, WithStatus
from loreley_api.admin.services.crawler_responses import to_job_accepted, to_source_settings
from loreley_api.infrastructure.crawler_client import CrawlerClient, CrawlerSourceSettings


@dataclass(frozen=True)
class _ValidSettings:
    settings: CrawlerSourceSettings
    # リクエストが TTL を指定した項目。Crawler の `ttl` の違反の写し先になる。
    ttl_field: TtlField


class SourceCommandService:
    def __init__(self, *, crawler: CrawlerClient, relay: CrawlerRelay) -> None:
        self._crawler = crawler
        self._relay = relay

    async def register(self, body: RegisterSourceBody) -> WithStatus[SourceSettings]:
        """EP-03。201(新規)または 200(同じ内容がすでに登録されていた)。"""
        valid = _validate_settings(body)
        succeeded = await self._relay.send(
            CrawlerOperation.REGISTER_SOURCE,
            partial(
                self._crawler.register_source, body.source_id, body.connector_type, valid.settings
            ),
            ttl_field=valid.ttl_field,
        )
        return WithStatus(succeeded.status, _source_settings_of(succeeded.body))

    async def update(self, source_id: str, body: UpdateSourceBody) -> WithStatus[SourceSettings]:
        """EP-04。変更できる項目の全置換。"""
        valid = _validate_settings(body)
        succeeded = await self._relay.send(
            CrawlerOperation.UPDATE_SOURCE,
            partial(self._crawler.update_source, source_id, valid.settings),
            ttl_field=valid.ttl_field,
        )
        return WithStatus(succeeded.status, _source_settings_of(succeeded.body))

    async def start_delete(self, source_id: str) -> JobAccepted:
        """EP-05。ソース削除ジョブの起動(取り消せない削除。確認は画面)。"""
        succeeded = await self._relay.send(
            CrawlerOperation.START_DELETE_JOB,
            partial(self._crawler.start_delete_job, source_id),
            lock_source_id=source_id,
        )
        accepted = to_job_accepted(succeeded.body, has_options=False)
        if accepted is None:
            raise crawler_error()  # 受け付けたかもしれない(B 10.2)
        return accepted


def _source_settings_of(crawler_body: dict[str, object]) -> SourceSettings:
    settings = to_source_settings(crawler_body)
    if settings is None:
        raise crawler_error()  # 保存したかもしれない(B 10.2)
    return settings


def _validate_settings(body: UpdateSourceBody) -> _ValidSettings:
    """範囲・桁・排他の検証と、単位の換算(B 2.4・2.8)。違反はすべて返す。"""
    violations: list[FieldViolation] = []
    ttl_seconds = _ttl_seconds_of(body, violations)
    ratio_threshold = _or_violation(
        percent_to_ratio(body.ratio_threshold_percent), "ratio_threshold_percent", violations
    )
    min_delete_count = _or_violation(
        validate_min_delete_count(body.min_delete_count), "min_delete_count", violations
    )
    if _contains_non_finite_number(body.connector_config):
        # JSON にできない値は Crawler に送れない(中身の検証ではなく、送信の前提)。
        violations.append(FieldViolation("connector_config", Reason.TYPE))
    if violations:
        raise invalid_request(violations)

    # 違反がなければ、換算の結果はすべて値がある。
    return _ValidSettings(
        settings=CrawlerSourceSettings(
            connector_config=body.connector_config,
            ttl_seconds=ttl_seconds,
            ratio_threshold=ratio_threshold,
            min_delete_count=min_delete_count,
            schedule_cron=body.schedule_cron,
        ),
        ttl_field="ttl_days" if body.ttl_days is not None else "ttl_seconds",
    )


def _ttl_seconds_of(body: UpdateSourceBody, violations: list[FieldViolation]) -> int | None:
    """TTL(秒)。`ttl_days` と `ttl_seconds` は、どちらか一方が必須(B 2.4)。

    排他・必須の違反は、どちらの場合も `ttl_days` に付ける(B 3.3 の例)。
    """
    if body.ttl_days is not None and body.ttl_seconds is not None:
        violations.append(FieldViolation("ttl_days", Reason.EXCLUSIVE))
        return None
    if body.ttl_days is not None:
        return _or_violation(ttl_days_to_seconds(body.ttl_days), "ttl_days", violations)
    if body.ttl_seconds is not None:
        return _or_violation(validate_ttl_seconds(body.ttl_seconds), "ttl_seconds", violations)
    violations.append(FieldViolation("ttl_days", Reason.REQUIRED))
    return None


def _or_violation[T](
    value: T | InvalidValue, field: str, violations: list[FieldViolation]
) -> T | None:
    """検証に通った値はそのまま返す。違反なら `violations` に足して `None`。"""
    if isinstance(value, InvalidValue):
        violations.append(FieldViolation(field, value.reason))
        return None
    return value


def _contains_non_finite_number(value: object) -> bool:
    """入れ子の値に、`NaN`・無限大(`1e999` は `inf` に読まれる)があるか。再帰しない。"""
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, float) and not math.isfinite(current):
            return True
        if isinstance(current, dict):
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return False
