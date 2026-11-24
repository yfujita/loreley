"""EP-11 `GET /sources/{source_id}/documents`(B 6.1)。

業務判断をしない。入力を検証し、サービスを呼んで DTO を返すだけ。
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from loreley_api.admin.base.codes import ApiTag, DocumentTab, ErrorCode, Reason
from loreley_api.admin.base.constants import DEFAULT_ITEMS_PER_PAGE
from loreley_api.admin.base.errors import FieldViolation, invalid_request
from loreley_api.admin.routers.request_input import (
    PageParams,
    SourceIdPath,
    reject_unknown_query,
    resolve_paging,
)
from loreley_api.admin.schemas.documents import DocumentListResponse
from loreley_api.admin.schemas.errors import error_responses
from loreley_api.admin.services.document_review import DocumentReviewService

QUERY_NAMES = frozenset({"tab", "page", "items_per_page", "sort"})

# タブごとの並べ替えの項目(1 項目だけ。昇順・降順を選べる。B 2.1)。既定は降順。
TAB_SORT_FIELDS: dict[DocumentTab, str] = {
    DocumentTab.SKIPPED: "last_skipped_at",
    DocumentTab.EXTRACT_FAILED: "last_seen_at",
    DocumentTab.OVERSIZE: "last_detected_at",
    DocumentTab.SUMMARY_PENDING: "indexed_at",
}


@dataclass(frozen=True)
class DocumentQuery:
    tab: DocumentTab
    paging: PageParams


async def read_document_query(
    tab: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    items_per_page: Annotated[int, Query()] = DEFAULT_ITEMS_PER_PAGE,
    sort: Annotated[str | None, Query()] = None,
) -> DocumentQuery:
    """`tab`(必須)と、タブごとの並べ替えの項目でのページング。違反はすべて返す。"""
    violations: list[FieldViolation] = []
    selected_tab: DocumentTab | None = None
    if tab is None:
        violations.append(FieldViolation("tab", Reason.REQUIRED))
    else:
        try:
            selected_tab = DocumentTab(tab)
        except ValueError:
            violations.append(FieldViolation("tab", Reason.UNSUPPORTED))

    # `tab` が決まらないときは、どのタブの項目も受ける(`sort` の違反だけを `tab` と一緒に返す。
    # 既定の並べ替えは使われない。`tab` の違反で 400 になる)。
    if selected_tab is not None:
        sortable_fields = {TAB_SORT_FIELDS[selected_tab]}
        default_field = TAB_SORT_FIELDS[selected_tab]
    else:
        sortable_fields = set(TAB_SORT_FIELDS.values())
        default_field = TAB_SORT_FIELDS[DocumentTab.SKIPPED]
    resolved = resolve_paging(
        page,
        items_per_page,
        sort if sort is not None else f"-{default_field}",
        sortable_fields=sortable_fields,
    )
    if isinstance(resolved, list):
        violations.extend(resolved)
    if selected_tab is None or isinstance(resolved, list):
        raise invalid_request(violations)
    return DocumentQuery(selected_tab, resolved)


def create_documents_router(document_review: DocumentReviewService) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/sources/{source_id}/documents",
        tags=[ApiTag.DOCUMENTS],
        responses=error_responses(ErrorCode.SOURCE_CONFIG_NOT_FOUND, ErrorCode.UNAVAILABLE),
    )
    async def list_documents(
        source_id: SourceIdPath,
        # 検証の順序は パス → クエリ(A 5.3)。引数の順で実行される。
        _query_names: Annotated[None, Depends(reject_unknown_query(QUERY_NAMES))],
        query: Annotated[DocumentQuery, Depends(read_document_query)],
    ) -> DocumentListResponse:
        return await document_review.list_documents(
            source_id=source_id,
            tab=query.tab,
            page=query.paging.page,
            items_per_page=query.paging.items_per_page,
            descending=query.paging.descending,
        )

    return router
