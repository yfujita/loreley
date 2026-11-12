"""`loreley-deletions` の記録のモデルと直列化(arch 9.4、`loreley-deletions-v0.9.md`)。

記録は 2 種類。どちらも同じ索引に置き、`record_type` で区別する(仮定義。plan 0002 §3.1)。
- `deletion-{source_id}`: ソースごとの現行世代
- `deletion_result-{crawl_id}`: クロール 1 回分の削除結果

項目名は設計書で未決(U-1)の部分があり、設計書の通知の名称に揃えた仮の名前。変更点はこのファイルに閉じる。
日時は UTC・ISO 8601・ミリ秒の文字列で保存し、読み出すとタイムゾーン付きの datetime になる。
値のない項目は保存しない(置き換え書き込みで消える。arch 9.4: 保存した ID 一覧は終端状態で削除する)。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from loreley_indexer.common.errors import IndexerError
from loreley_indexer.common.timestamps import format_instant, parse_instant

DELETION_RECORD_TYPE = "deletion"
DELETION_RESULT_RECORD_TYPE = "deletion_result"


def deletion_record_id(source_id: str) -> str:
    return f"deletion-{source_id}"


def deletion_result_record_id(crawl_id: str) -> str:
    return f"deletion_result-{crawl_id}"


class DeletionStatus(StrEnum):
    """削除結果の状態(arch 9.10。名前の一覧は案)。`running` 以外が終端状態。"""

    RUNNING = "running"
    DELETED = "deleted"
    SKIPPED_BY_RATIO = "skipped_by_ratio"
    VALIDATION_FAILED = "validation_failed"
    DISCARDED = "discarded"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        return self is not DeletionStatus.RUNNING


class DeletionReason(StrEnum):
    """`reason` の値(コードの名称は案。plan 0002 §3.1)。"""

    # failed
    OUTCOME_FAILED = "outcome_failed"
    OUTCOME_CANCELLED = "outcome_cancelled"
    MAINTENANCE = "maintenance"
    INDEXER_RESTART = "indexer_restart"
    DELETE_ERROR = "delete_error"  # エラーの種類は `reason_detail` に持つ
    # discarded
    SUPERSEDED = "superseded"
    SOURCE_DELETED = "source_deleted"
    # validation_failed
    COUNT_MISMATCH = "count_mismatch"
    ID_LIMIT_EXCEEDED = "id_limit_exceeded"
    TARGET_EXCEEDS_DENOMINATOR = "target_exceeds_denominator"


class FinishOutcome(StrEnum):
    """終了通知の `outcome`。"""

    ENUMERATION_COMPLETED = "enumeration_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MalformedRecordError(IndexerError):
    """保存された記録の形式が不正。Indexer 自身が書いた記録なので、想定外の異常(api では 500)。

    記録の値を含めず、項目名だけを持つ。
    """

    def __init__(self, field_name: str) -> None:
        super().__init__(f"malformed deletion record: field {field_name}")
        self.field_name = field_name


@dataclass(frozen=True)
class DeletionRecord:
    """`deletion-{source_id}`: ソースごとの現行世代。

    直近の開始通知の内容で、開始通知の世代判定(古い `crawl_started_at` の拒否)にだけ使う。
    削除の判断・実行には使わない(`DeletionResultRecord` に複写した値を使う)。
    """

    source_id: str
    crawl_id: str
    crawl_started_at: datetime
    ttl: int  # 秒
    ratio_threshold: float
    min_delete_count: int
    force_delete: bool
    updated_at: datetime

    def to_body(self) -> dict[str, Any]:
        return {
            "record_type": DELETION_RECORD_TYPE,
            "source_id": self.source_id,
            "crawl_id": self.crawl_id,
            "crawl_started_at": format_instant(self.crawl_started_at),
            "ttl": self.ttl,
            "ratio_threshold": self.ratio_threshold,
            "min_delete_count": self.min_delete_count,
            "force_delete": self.force_delete,
            "updated_at": format_instant(self.updated_at),
        }

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "DeletionRecord":
        _require_record_type(body, DELETION_RECORD_TYPE)
        return cls(
            source_id=_str(body, "source_id"),
            crawl_id=_str(body, "crawl_id"),
            crawl_started_at=_instant(body, "crawl_started_at"),
            ttl=_int(body, "ttl"),
            ratio_threshold=_float(body, "ratio_threshold"),
            min_delete_count=_int(body, "min_delete_count"),
            force_delete=_bool(body, "force_delete"),
            updated_at=_instant(body, "updated_at"),
        )


@dataclass(frozen=True)
class DeletionResultRecord:
    """`deletion_result-{crawl_id}`: クロール 1 回分の削除の判断・実行の結果。"""

    crawl_id: str
    source_id: str
    status: DeletionStatus
    started_at: datetime

    # 設定スナップショットと `crawl_started_at` の複写(開始通知の値。arch 9.4)。
    # 判定・実行・登録の受理条件は、常にこの複写を使う。
    crawl_started_at: datetime
    ttl: int  # 秒
    ratio_threshold: float
    min_delete_count: int
    forced: bool  # 複写した `force_delete` そのもの
    rewrite_mode: bool  # 省略は `false` に正規化して保存する(K37)

    reason: DeletionReason | None = None
    reason_detail: str | None = None  # `delete_error` の場合のエラーの種類
    outcome: FinishOutcome | None = None
    ended_at: datetime | None = None

    # 終了通知の受理(`finish_request_digest` の有無が「最初の終了通知を受理済みか」の基準)
    finish_received_at: datetime | None = None
    finish_request_digest: str | None = None
    enumerated_count: int | None = None

    # 保存した ID 一覧。受理時に保存し、終端状態への遷移と同じ書き込みで消す(K31、K35)。
    # 合算件数が上限を超えた通知では保存せず、件数と超過フラグだけを記録する(K34)。
    skipped_document_ids: tuple[str, ...] | None = None
    oversize_document_ids: tuple[str, ...] | None = None
    skip_and_oversize_id_count: int | None = None
    skip_and_oversize_id_limit_exceeded: bool | None = None

    # 判定・実行の記録
    deletion_started_at: datetime | None = None
    n_seen: int | None = None
    e_missing: int | None = None
    target_count: int | None = None  # T
    denominator: int | None = None  # D
    deleted_count: int | None = None

    def to_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "record_type": DELETION_RESULT_RECORD_TYPE,
            "crawl_id": self.crawl_id,
            "source_id": self.source_id,
            "status": self.status.value,
            "started_at": format_instant(self.started_at),
            "crawl_started_at": format_instant(self.crawl_started_at),
            "ttl": self.ttl,
            "ratio_threshold": self.ratio_threshold,
            "min_delete_count": self.min_delete_count,
            "forced": self.forced,
            "rewrite_mode": self.rewrite_mode,
            "reason": _enum_value(self.reason),
            "reason_detail": self.reason_detail,
            "outcome": _enum_value(self.outcome),
            "ended_at": _instant_text(self.ended_at),
            "finish_received_at": _instant_text(self.finish_received_at),
            "finish_request_digest": self.finish_request_digest,
            "enumerated_count": self.enumerated_count,
            "skipped_document_ids": _id_list(self.skipped_document_ids),
            "oversize_document_ids": _id_list(self.oversize_document_ids),
            "skip_and_oversize_id_count": self.skip_and_oversize_id_count,
            "skip_and_oversize_id_limit_exceeded": self.skip_and_oversize_id_limit_exceeded,
            "deletion_started_at": _instant_text(self.deletion_started_at),
            "n_seen": self.n_seen,
            "e_missing": self.e_missing,
            "target_count": self.target_count,
            "denominator": self.denominator,
            "deleted_count": self.deleted_count,
        }
        return {name: value for name, value in body.items() if value is not None}

    @classmethod
    def from_body(cls, body: Mapping[str, Any]) -> "DeletionResultRecord":
        _require_record_type(body, DELETION_RESULT_RECORD_TYPE)
        return cls(
            crawl_id=_str(body, "crawl_id"),
            source_id=_str(body, "source_id"),
            status=_enum(DeletionStatus, body, "status"),
            started_at=_instant(body, "started_at"),
            crawl_started_at=_instant(body, "crawl_started_at"),
            ttl=_int(body, "ttl"),
            ratio_threshold=_float(body, "ratio_threshold"),
            min_delete_count=_int(body, "min_delete_count"),
            forced=_bool(body, "forced"),
            rewrite_mode=_bool(body, "rewrite_mode"),
            reason=_optional_enum(DeletionReason, body, "reason"),
            reason_detail=_optional_str(body, "reason_detail"),
            outcome=_optional_enum(FinishOutcome, body, "outcome"),
            ended_at=_optional_instant(body, "ended_at"),
            finish_received_at=_optional_instant(body, "finish_received_at"),
            finish_request_digest=_optional_str(body, "finish_request_digest"),
            enumerated_count=_optional_int(body, "enumerated_count"),
            skipped_document_ids=_optional_id_list(body, "skipped_document_ids"),
            oversize_document_ids=_optional_id_list(body, "oversize_document_ids"),
            skip_and_oversize_id_count=_optional_int(body, "skip_and_oversize_id_count"),
            skip_and_oversize_id_limit_exceeded=_optional_bool(
                body, "skip_and_oversize_id_limit_exceeded"
            ),
            deletion_started_at=_optional_instant(body, "deletion_started_at"),
            n_seen=_optional_int(body, "n_seen"),
            e_missing=_optional_int(body, "e_missing"),
            target_count=_optional_int(body, "target_count"),
            denominator=_optional_int(body, "denominator"),
            deleted_count=_optional_int(body, "deleted_count"),
        )


# --- 直列化の補助 ---


def _enum_value(value: StrEnum | None) -> str | None:
    return value.value if value is not None else None


def _instant_text(value: datetime | None) -> str | None:
    return format_instant(value) if value is not None else None


def _id_list(value: tuple[str, ...] | None) -> list[str] | None:
    return list(value) if value is not None else None


# --- 復元の補助。不正な値は、値を含めず項目名だけで MalformedRecordError にする ---


def _require_record_type(body: Mapping[str, Any], expected: str) -> None:
    if body.get("record_type") != expected:
        raise MalformedRecordError("record_type")


def _str(body: Mapping[str, Any], name: str) -> str:
    value = body.get(name)
    if not isinstance(value, str):
        raise MalformedRecordError(name)
    return value


def _int(body: Mapping[str, Any], name: str) -> int:
    value = body.get(name)
    # bool は int のサブクラスだが、数値としては受け付けない。
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedRecordError(name)
    return value


def _float(body: Mapping[str, Any], name: str) -> float:
    value = body.get(name)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise MalformedRecordError(name)
    return float(value)


def _bool(body: Mapping[str, Any], name: str) -> bool:
    value = body.get(name)
    if not isinstance(value, bool):
        raise MalformedRecordError(name)
    return value


def _instant(body: Mapping[str, Any], name: str) -> datetime:
    try:
        return parse_instant(_str(body, name))
    except ValueError:
        raise MalformedRecordError(name) from None


def _enum[E: StrEnum](enum_type: type[E], body: Mapping[str, Any], name: str) -> E:
    try:
        return enum_type(_str(body, name))
    except ValueError:
        raise MalformedRecordError(name) from None


def _optional_str(body: Mapping[str, Any], name: str) -> str | None:
    return _str(body, name) if name in body else None


def _optional_int(body: Mapping[str, Any], name: str) -> int | None:
    return _int(body, name) if name in body else None


def _optional_bool(body: Mapping[str, Any], name: str) -> bool | None:
    return _bool(body, name) if name in body else None


def _optional_instant(body: Mapping[str, Any], name: str) -> datetime | None:
    return _instant(body, name) if name in body else None


def _optional_enum[E: StrEnum](enum_type: type[E], body: Mapping[str, Any], name: str) -> E | None:
    return _enum(enum_type, body, name) if name in body else None


def _optional_id_list(body: Mapping[str, Any], name: str) -> tuple[str, ...] | None:
    if name not in body:
        return None
    value = body[name]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise MalformedRecordError(name)
    return tuple(value)
