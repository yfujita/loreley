"""リクエストの形式の定義と検証(api 3.2、4.1〜4.8)。

pydantic の strict で型を検証する。数値を文字列から、整数を小数から、真偽値を文字列や数値から
黙って変換しない(`ttl: 1.5` や `rewrite_mode: "true"` は 400)。
未知の項目(`fetched_at`、`metadata` など)は無視する(plan 案7)。

文字列の扱い:
- ID 類(`source_id`・`crawl_id`・`lock.*`)は、空文字・制御文字(NUL・改行など)・長さ超過を
  拒否する。制御文字は、ログに偽の行を注入できるため。
- `external_id` は空文字・長さ超過・NUL だけを拒否する(NUL 以外の制御文字は許可。ログに出ない
  ため)。NUL は `compute_document_id` も拒否するが、ここで拒否しないと位置のない 400 になり、
  どの文書か分からない。
  pydantic の `str` は、JSON の `\\ud800` のような孤立サロゲートも拒否する。
- `title`・`mime_type`・`path`・`url` は孤立サロゲートを受け入れ、ドメインが文書単位の
  `document_rejected` にする(0008 A3: Crawler が Linux で CP932 のファイル名を読むと生じうる。
  その 1 文書のためにバッチ全体を 400 にすると、再送しても直らずジョブが止まる)。

検証エラーの本文には、位置と型だけを出す(入力値は含めない。R9)。
"""

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)
from pydantic_core import PydanticCustomError

from loreley_indexer.common.locks import LockInfo
from loreley_indexer.common.timestamps import parse_instant

# `_id`(512 バイト)に収まるように。`deletion_result-{crawl_id}`(接頭辞 16 バイト)、
# `deletion-{source_id}`・`lock-{source_id}` の接頭辞を足しても超えない値(仮値。
# 設計書に値の規定はない)。
MAX_ID_BYTES = 256
# `external_id` は `_id` ではなくハッシュの素材なので `_id` の制約はない。パスやページ ID が収まる
# 大きさ(仮値)。超える文書があると、リクエスト全体が 400 になる。
MAX_EXTERNAL_ID_BYTES = 4096
MAX_INT64 = 2**63 - 1
CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
MAX_REPORTED_ERRORS = 10


def _check_id(value: str) -> str:
    _check_not_empty_and_short(value, max_bytes=MAX_ID_BYTES)
    if CONTROL_CHARACTERS.search(value):
        raise PydanticCustomError("id_invalid_character", "must not contain control characters")
    return value


def _check_external_id(value: str) -> str:
    # 制御文字(改行・タブ)は拒否しない。Linux のファイル名としては正当で、拒否すると 1 件で
    # バッチ全体が恒久的に 400 になる。値はハッシュの素材と応答の JSON にしか入らず、ログには
    # 出ない(JSON では改行がエスケープされる)。
    # NUL は、ハッシュの素材の区切りと衝突するため拒否する(`compute_document_id` も拒否する
    # が、そこまで届くと位置のない 400 になる)。
    _check_not_empty_and_short(value, max_bytes=MAX_EXTERNAL_ID_BYTES)
    if "\x00" in value:
        raise PydanticCustomError("id_invalid_character", "must not contain NUL")
    return value


def _check_not_empty_and_short(value: str, *, max_bytes: int) -> None:
    if value == "":
        raise PydanticCustomError("id_empty", "must not be empty")
    if len(value.encode("utf-8")) > max_bytes:
        raise PydanticCustomError("id_too_long", "is too long")


def _require_text(value: object) -> object:
    # 孤立サロゲートを含む文字列を通すため、pydantic の `str` 検査(孤立サロゲートを拒否する)
    # を使わず、型だけを確認する。
    if not isinstance(value, str):
        raise PydanticCustomError("string_type", "must be a string")
    return value


def _parse_timestamp(value: object) -> datetime:
    """ISO 8601(タイムゾーン必須)の文字列から、UTC の datetime にする。"""
    if not isinstance(value, str):
        raise PydanticCustomError("timestamp_invalid", "must be an ISO 8601 string")
    try:
        return parse_instant(value)
    except (ValueError, OverflowError):
        raise PydanticCustomError("timestamp_invalid", "must be an ISO 8601 timestamp") from None


IdStr = Annotated[str, AfterValidator(_check_id)]
ExternalIdStr = Annotated[str, AfterValidator(_check_external_id)]
# 孤立サロゲートを許す文字列。実行時は `str`(`_require_text` が保証する)。
LooseText = Annotated[Any, AfterValidator(_require_text)]
HexId = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Timestamp = Annotated[datetime, BeforeValidator(_parse_timestamp)]
Int64 = Annotated[int, Field(ge=-(2**63), le=MAX_INT64)]
NonNegativeInt64 = Annotated[int, Field(ge=0, le=MAX_INT64)]


class _Body(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False, frozen=True)


class LockBody(_Body):
    owner: IdStr
    job_id: IdStr

    def to_domain(self) -> LockInfo:
        return LockInfo(owner=self.owner, job_id=self.job_id)


class StartBody(_Body):
    crawl_id: IdStr
    source_id: IdStr
    crawl_started_at: Timestamp
    ttl: Int64
    ratio_threshold: float
    min_delete_count: Int64
    force_delete: bool = False
    rewrite_mode: bool = False


class FinishBody(_Body):
    source_id: IdStr
    outcome: Literal["enumeration_completed", "failed", "cancelled"]
    finished_at: Timestamp
    enumerated_count: NonNegativeInt64 | None = None
    skipped_document_ids: list[HexId] | None = None
    oversize_document_ids: list[HexId] | None = None
    # 型だけを検証し、値は使わない。ダイジェストと件数照合は ID 一覧から決まり、
    # `skipped_count` は含まれない(K25)。重複を除く数え方が設計書にないため、一致の検証もしない。
    skipped_count: NonNegativeInt64 | None = None

    @model_validator(mode="after")
    def _require_results_when_enumeration_completed(self) -> Self:
        # `failed`・`cancelled` では件数と ID 一覧を省略できる(api 4.4。API-U-12)。
        results = (self.enumerated_count, self.skipped_document_ids, self.oversize_document_ids)
        if self.outcome == "enumeration_completed" and None in results:
            raise PydanticCustomError(
                "required_when_enumeration_completed",
                "enumerated_count and both id lists are required",
            )
        return self


class DocumentBody(_Body):
    external_id: ExternalIdStr
    title: LooseText
    mime_type: LooseText
    raw_content: str  # base64。デコードの前に、長さからサイズを判定する(`raw_content.py`)
    content_hash: HexId  # 形式だけを検証する。Crawler の値を信用する(plan 案4)
    source_updated_at: Timestamp
    size: NonNegativeInt64
    url: LooseText | None = None
    path: LooseText | None = None


class BatchBody(_Body):
    crawl_id: IdStr
    crawl_started_at: Timestamp
    lock: LockBody
    documents: list[DocumentBody]


class LastSeenBody(_Body):
    crawl_id: IdStr
    crawl_started_at: Timestamp
    lock: LockBody
    document_ids: list[HexId]


class DiscardBody(_Body):
    lock: LockBody
    reason: Literal["source_deleted"] | None = None


class LockedBody(_Body):
    """ソース削除 2・3(`DELETE`)のボディ。ロック所有情報を運ぶ。"""

    lock: LockBody


def describe_validation_errors(errors: Sequence[Any]) -> str:
    """検証エラーを、位置と型だけの文にする。入力値(`input`)・`ctx`・`msg` は使わない。

    位置は、モデルの項目名と配列の添字だけ(未知の項目は無視するので、入力のキーは現れない)。
    """
    shown = [_describe_location_and_type(error) for error in errors[:MAX_REPORTED_ERRORS]]
    hidden = len(errors) - len(shown)
    suffix = f"; and {hidden} more" if hidden > 0 else ""
    return "invalid request: " + "; ".join(shown) + suffix


def describe_validation_error(error: ValidationError) -> str:
    return describe_validation_errors(error.errors(include_input=False, include_url=False))


def _describe_location_and_type(error: Any) -> str:
    location = ".".join(str(part) for part in error["loc"]) or "body"
    return f"{location} ({error['type']})"
