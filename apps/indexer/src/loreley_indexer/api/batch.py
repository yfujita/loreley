"""バッチ登録の入力サイズの防御と、ドメインの入力への変換(api 4.3、plan 案22)。

件数・サイズの超過は、リクエスト全体を 400 `invalid_request` で拒否する。
サイズは、`raw_content`(base64)をデコードする前に、文字列の長さから算出して判定する。
デコードする文書のサイズ(デコード後の合計)が上限以内と分かってから、デコードを始める。

原本 1 件の上限(`max_raw_bytes`)を超える文書は、デコードせず、文書単位の `oversize` になる
(案1)。デコードされないので、合計(`max_batch_bytes`)には含めない。巨大な原本 1 件のために
バッチ全体が 400 になると、再送しても直らないため。そのような文書の base64 の文字列は、
リクエストボディの上限(`max_request_body_bytes`)が最終的な防御になる(超えるとリクエスト全体が
400 になる)。
"""

from collections.abc import Sequence

from loreley_indexer.api.config import ApiConfig
from loreley_indexer.api.errors import InvalidRequestError
from loreley_indexer.api.raw_content import (
    InvalidBase64Error,
    estimate_decoded_size,
    prepare_raw_content,
)
from loreley_indexer.api.schemas import DocumentBody
from loreley_indexer.documents import DocumentInput


def prepare_documents(documents: Sequence[DocumentBody], config: ApiConfig) -> list[DocumentInput]:
    _check_count(documents, config)
    _check_total_size(documents, config)
    return [_to_domain(index, document, config) for index, document in enumerate(documents)]


def _check_count(documents: Sequence[DocumentBody], config: ApiConfig) -> None:
    if not documents:
        raise InvalidRequestError("documents must not be empty")
    if len(documents) > config.max_batch_documents:
        raise InvalidRequestError("documents has too many items")


def _check_total_size(documents: Sequence[DocumentBody], config: ApiConfig) -> None:
    total_bytes = 0
    for index, document in enumerate(documents):
        try:
            estimated_bytes = estimate_decoded_size(document.raw_content)
        except InvalidBase64Error:
            raise _invalid_base64(index) from None
        if estimated_bytes > config.max_raw_bytes:
            continue  # デコードしない文書(文書単位の `oversize`)は、合計に含めない
        total_bytes += estimated_bytes
        if total_bytes > config.max_batch_bytes:
            raise InvalidRequestError("the documents are too large in total")


def _to_domain(index: int, document: DocumentBody, config: ApiConfig) -> DocumentInput:
    try:
        content = prepare_raw_content(
            document.raw_content,
            declared_size=document.size,
            max_raw_bytes=config.max_raw_bytes,
        )
    except InvalidBase64Error:
        raise _invalid_base64(index) from None
    return DocumentInput(
        external_id=document.external_id,
        title=document.title,
        mime_type=document.mime_type,
        raw_content=content.raw_content,
        content_hash=document.content_hash,
        source_updated_at=document.source_updated_at,
        size=content.size,
        url=document.url,
        path=document.path,
    )


def _invalid_base64(index: int) -> InvalidRequestError:
    return InvalidRequestError(f"invalid request: documents.{index}.raw_content (base64_invalid)")
