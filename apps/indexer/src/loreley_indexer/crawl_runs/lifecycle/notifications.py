"""開始通知・終了通知の入力(arch 9.5、api 4.1・4.4)。

HTTP の JSON から値に変換する(型の検証、日時のパース、列挙値への変換)のは api 層(P5)の責務。
ここは変換済みの値を受け、多層防御として形式を再検証する。不正は ValueError で、
メッセージは項目名だけを含み、入力値は含めない(400 応答やログに入力値を出さないため)。
`ttl`・`ratio_threshold`・`min_delete_count` は型だけを検証し、範囲は検証しない
(確定事項。arch 9.3、9.13(9))。
"""

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from loreley_indexer.crawl_runs.lifecycle.records import FinishOutcome

_DOCUMENT_ID_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class StartNotification:
    """`POST /crawls/start`。`rewrite_mode` の省略は `false`(K37)。"""

    crawl_id: str
    source_id: str
    crawl_started_at: datetime  # タイムゾーン付き
    ttl: int  # 秒
    ratio_threshold: float  # 小数。有限の値だけ(NaN・Inf は形式不正)
    min_delete_count: int
    force_delete: bool = False
    rewrite_mode: bool = False

    def __post_init__(self) -> None:
        _require_text("crawl_id", self.crawl_id)
        _require_text("source_id", self.source_id)
        _require_aware_datetime("crawl_started_at", self.crawl_started_at)
        _require_int("ttl", self.ttl)
        if isinstance(self.ratio_threshold, bool) or not isinstance(
            self.ratio_threshold, int | float
        ):
            raise ValueError("ratio_threshold must be a number")
        if not math.isfinite(self.ratio_threshold):
            raise ValueError("ratio_threshold must be finite")
        _require_int("min_delete_count", self.min_delete_count)
        _require_bool("force_delete", self.force_delete)
        _require_bool("rewrite_mode", self.rewrite_mode)


@dataclass(frozen=True)
class FinishNotification:
    """`POST /crawls/{crawl_id}/finish`。

    `enumeration_completed` では `enumerated_count` と 2 つの ID 一覧が必須。`failed`・`cancelled`
    では省略できる(api 4.4。省略可否は未決のため、送られたものは受け、ダイジェストに含める)。
    `skipped_count`(`skipped_document_ids` の件数)は、ダイジェストにも保存にも使わないので持たない。
    `finished_at` は形式の検証だけで、保存も比較もしない(再送の比較から除く。K25)。
    """

    crawl_id: str
    source_id: str
    outcome: FinishOutcome
    finished_at: datetime
    enumerated_count: int | None = None
    skipped_document_ids: Sequence[str] | None = None
    oversize_document_ids: Sequence[str] | None = None

    def __post_init__(self) -> None:
        _require_text("crawl_id", self.crawl_id)
        _require_text("source_id", self.source_id)
        if not isinstance(self.outcome, FinishOutcome):
            raise ValueError("outcome must be a FinishOutcome")
        _require_aware_datetime("finished_at", self.finished_at)
        if self.enumerated_count is not None:
            _require_int("enumerated_count", self.enumerated_count)
        for name, ids in self._id_lists().items():
            if ids is not None:
                _require_document_ids(name, ids)
        if self.outcome is FinishOutcome.ENUMERATION_COMPLETED:
            self._require_enumeration_results()

    def normalized_skipped_ids(self) -> tuple[str, ...] | None:
        return _normalize_ids(self.skipped_document_ids)

    def normalized_oversize_ids(self) -> tuple[str, ...] | None:
        return _normalize_ids(self.oversize_document_ids)

    def digest(self) -> str:
        """終了通知のダイジェスト(`finish_request_digest`。arch 9.5、K25)。

        `outcome`、`enumerated_count`、重複を除いてソートした 2 つの ID 一覧の SHA-256。
        `finished_at` と `source_id` は含めない(`source_id` は受理の前に別途照合する。K32)。
        """
        canonical = json.dumps(
            {
                "outcome": self.outcome.value,
                "enumerated_count": self.enumerated_count,
                "skipped_document_ids": self.normalized_skipped_ids(),
                "oversize_document_ids": self.normalized_oversize_ids(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _id_lists(self) -> dict[str, Sequence[str] | None]:
        return {
            "skipped_document_ids": self.skipped_document_ids,
            "oversize_document_ids": self.oversize_document_ids,
        }

    def _require_enumeration_results(self) -> None:
        required = {"enumerated_count": self.enumerated_count, **self._id_lists()}
        for name, value in required.items():
            if value is None:
                raise ValueError(f"{name} is required when the outcome is enumeration_completed")


def _normalize_ids(ids: Sequence[str] | None) -> tuple[str, ...] | None:
    return tuple(sorted(set(ids))) if ids is not None else None


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise ValueError(f"{name} must be a non-empty string")


def _require_aware_datetime(name: str, value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a datetime with a timezone")


def _require_int(name: str, value: object) -> None:
    # bool は int のサブクラスだが、数値としては受け付けない。
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")


def _require_document_ids(name: str, ids: Sequence[str]) -> None:
    if isinstance(ids, str) or not all(
        isinstance(item, str) and _DOCUMENT_ID_PATTERN.fullmatch(item) for item in ids
    ):
        raise ValueError(f"{name} must be a list of 64 lowercase hex document ids")
