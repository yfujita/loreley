"""ID のバルク削除(module 4.8。CM-P-24。architecture 3.1)。

ID の一覧を、1 回の件数の上限ごとに分けて `_bulk` の delete で送る。
- 存在しない ID(`result: not_found`)は成功とみなす(再実行で冪等にするため)。
- 一部の ID だけ失敗したもの(429 の拒否など)は、失敗した ID の一覧で返す。リトライは呼び出し側が、
  失敗した ID だけに対して行う。
- 索引全体の異常(`cluster_block_exception` など。どの ID でも同じように失敗する)は、部分失敗ではなく
  `StoreUnavailableError` を送出する。
- 項目単位の失敗は、400 系も含めて、失敗した ID として返す(リクエスト全体の 4xx で
  `StoreUnexpectedResponseError` を送出するのとは非対称)。削除の項目が 400 になる原因は、
  ID が不正なときなどに限られ、再実行しても直らないが、尽きたら呼び出し側が Store 層への書き込みの
  失敗(`store_unavailable`)として扱う(削除に関わる判断は安全側に倒す)。
"""

from collections.abc import Iterator, Sequence
from itertools import batched
from typing import Any

from opensearchpy import OpenSearch

from loreley_crawler.common.errors import StoreUnavailableError
from loreley_crawler.infrastructure.opensearch.classification import (
    UNAVAILABLE_ERROR_TYPES,
    extract_error_type,
)
from loreley_crawler.infrastructure.opensearch.client_calls import run_query
from loreley_crawler.infrastructure.opensearch.results import BulkDeleteResult
from loreley_crawler.infrastructure.opensearch.settings import RepositorySettings


def delete_ids_in_bulk(
    client: OpenSearch, index_name: str, record_ids: Sequence[str], settings: RepositorySettings
) -> BulkDeleteResult:
    # 同じ ID が複数あっても 1 回だけ送る(失敗した ID の一覧にも重複を出さない)。
    unique_ids = tuple(dict.fromkeys(record_ids))
    failed_ids: list[str] = []
    for batch in batched(unique_ids, settings.bulk_delete_batch_size):
        body = [{"delete": {"_index": index_name, "_id": record_id}} for record_id in batch]
        response = run_query(lambda body=body: client.bulk(body=body))
        failed_ids.extend(_failed_ids(response, batch))
    return BulkDeleteResult(failed_ids=tuple(failed_ids))


def _failed_ids(response: dict[str, Any], batch: Sequence[str]) -> Iterator[str]:
    if not response.get("errors"):
        return
    # 応答の項目は、要請と同じ順に並ぶ。
    for record_id, item in zip(batch, response["items"], strict=True):
        result = item["delete"]
        status = result["status"]
        if status == 404 and result.get("result") == "not_found":
            continue
        if 200 <= status < 300:
            continue
        error_type = extract_error_type({"error": result.get("error")})
        if error_type in UNAVAILABLE_ERROR_TYPES:
            raise StoreUnavailableError(error_type)
        yield record_id
