"""パスの ID・クエリ・本文の検証(B 2.12。A 5.3)。FastAPI の依存関係(`Depends`)として使う。

**依存関係はすべて `async def`**(同期の関数は共通のスレッドプールで動き、区分ごとの上限を
迂回して枯渇の原因になるため。D R9。`tests/architecture` が検査する)。

違反は 400 `invalid_request`。`details.errors` には項目名と理由だけを載せ、値は載せない。
検証の順序は パス → クエリ → 本文(A 5.3)。
"""

import json
import re
import unicodedata
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from typing import Annotated, Any, NoReturn

from fastapi import Depends, Path, Query, Request

from loreley_api.admin.base.codes import Reason
from loreley_api.admin.base.constants import (
    DEFAULT_ITEMS_PER_PAGE,
    ITEMS_PER_PAGE_CHOICES,
    PAGE_WINDOW_LIMIT,
)
from loreley_api.admin.base.errors import FieldViolation, invalid_request
from loreley_api.common.http.body import read_limited_body
from loreley_api.common.http.handlers import format_field_name_part

# 半角英数字で始まり、半角英数字・`.`・`_`・`-` だけの 256 文字以内。
SOURCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,255}")
JOB_ID_MAX_BYTES = 256
JSON_MEDIA_TYPE = "application/json"

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _is_valid_job_id(job_id: str) -> bool:
    """空でない・UTF-8 で 256 バイト以内・制御文字なし(Crawler の `job_id` と同じ規則)。"""
    if not job_id or _LONE_SURROGATE.search(job_id):
        return False
    if len(job_id.encode("utf-8")) > JOB_ID_MAX_BYTES:
        return False
    return not any(unicodedata.category(character) == "Cc" for character in job_id)


# --- パス ---


async def read_source_id(source_id: Annotated[str, Path()]) -> str:
    if SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise invalid_request([FieldViolation("source_id", Reason.FORMAT)])
    return source_id


async def read_job_id(job_id: Annotated[str, Path()]) -> str:
    if not _is_valid_job_id(job_id):
        raise invalid_request([FieldViolation("job_id", Reason.FORMAT)])
    return job_id


SourceIdPath = Annotated[str, Depends(read_source_id)]
JobIdPath = Annotated[str, Depends(read_job_id)]


# --- クエリ ---


def reject_unknown_query(allowed_names: Collection[str]) -> Callable[[Request], Awaitable[None]]:
    """EP が定義していないクエリ(未知の項目)を 400 `unknown_field` にする依存関係を作る。"""

    async def check_query_names(request: Request) -> None:
        unknown_names = sorted(set(request.query_params) - set(allowed_names))
        if unknown_names:
            raise invalid_request(
                [
                    FieldViolation(format_field_name_part(name), Reason.UNKNOWN_FIELD)
                    for name in unknown_names
                ]
            )

    return check_query_names


@dataclass(frozen=True)
class PageRequest:
    page: int
    items_per_page: int
    sort_field: str
    descending: bool


def read_paging(
    *, sortable_fields: Collection[str], default_sort: str
) -> Callable[..., Awaitable[PageRequest]]:
    """`page`・`items_per_page`・`sort` の依存関係を作る(B 2.1)。

    `sort` は単一の項目で、先頭の `-` が降順。`default_sort` は `-queued_at` のように書く。
    `page * items_per_page` が窓(10,000)を超えると、`page` の `range`。
    """

    async def read_page_request(
        page: Annotated[int, Query(ge=1)] = 1,
        items_per_page: Annotated[int, Query()] = DEFAULT_ITEMS_PER_PAGE,
        sort: Annotated[str, Query()] = default_sort,
    ) -> PageRequest:
        violations: list[FieldViolation] = []
        if items_per_page not in ITEMS_PER_PAGE_CHOICES:
            violations.append(FieldViolation("items_per_page", Reason.UNSUPPORTED))
        elif page * items_per_page > PAGE_WINDOW_LIMIT:
            violations.append(FieldViolation("page", Reason.RANGE))
        sort_field = sort.removeprefix("-")
        if sort_field not in sortable_fields:
            violations.append(FieldViolation("sort", Reason.UNSUPPORTED))
        if violations:
            raise invalid_request(violations)
        return PageRequest(page, items_per_page, sort_field, descending=sort.startswith("-"))

    return read_page_request


# --- 本文 ---


def _reject_json_constant(constant: str) -> NoReturn:
    """`NaN`・`Infinity` は JSON ではない(Python の `json` は既定で受け付ける)。"""
    raise ValueError("invalid JSON constant")


def _media_type_of(request: Request) -> str:
    content_type = request.headers.get("content-type", "")
    return content_type.partition(";")[0].strip().lower()


async def read_json_object(request: Request) -> dict[str, Any]:
    """本文を JSON のオブジェクトとして読む(EP-03・04・06)。型・必須項目の検証は呼び出し側。

    - 本文が空なら、`Content-Type` を問わず `{}`(EP-06 は本文なしと `{}` が同じ)。
    - 本文があるとき、`Content-Type: application/json` でない・JSON として読めない・1 MiB 超は
      400(`details` なし)。オブジェクトでなければ `body` の `type`。
    """
    body = await read_limited_body(request)
    if not body:
        return {}
    if _media_type_of(request) != JSON_MEDIA_TYPE:
        raise invalid_request()
    try:
        parsed = json.loads(body.decode("utf-8"), parse_constant=_reject_json_constant)
    except (ValueError, RecursionError):
        raise invalid_request() from None
    if not isinstance(parsed, dict):
        raise invalid_request([FieldViolation("body", Reason.TYPE)])
    return parsed


JsonObjectBody = Annotated[dict[str, Any], Depends(read_json_object)]
