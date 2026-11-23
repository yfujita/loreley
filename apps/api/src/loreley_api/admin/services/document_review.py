"""文書の確認(EP-11。C 3.3 R-9〜R-11・5.6・8.6。D 5.7)。

主たる読み取り(設定の存在確認と、そのタブの一覧)が失敗すれば 503。付随する読み取りの失敗は 200
で、該当の項目を `null`(または `unknown`)にして `unavailable` に理由を載せる:
- 他の 3 タブの件数・登録文書数は、サブ要求ごとに成否が分かれる。行に属さないので最上位の
  `unavailable`(`tab_counts.<タブ>`・`document_count`)。要求したタブの件数は、一覧の `total`。
- `existence`(`skipped` タブ)は 1 回の一括検索。失敗したらページの全行を `unknown` にし、
  全行の `unavailable.existence` に理由を付ける。
"""

import dataclasses
from collections.abc import Callable, Sequence

from loreley_api.admin.base.codes import DocumentTab, UnavailableReason
from loreley_api.admin.base.constants import PAGE_WINDOW_LIMIT
from loreley_api.admin.base.errors import source_config_not_found, unavailable
from loreley_api.admin.derivation import document_view
from loreley_api.admin.derivation.job_view import existence_of
from loreley_api.admin.failures import reason_of, row_unavailable, top_level_unavailable
from loreley_api.admin.schemas.documents import (
    DocumentListResponse,
    DocumentRow,
    ExtractFailedDocument,
    OversizeDocument,
    SkippedDocument,
    SummaryPendingDocument,
    TabCounts,
)
from loreley_api.common.concurrency import CATEGORY_OPENSEARCH, BlockingRunner
from loreley_api.common.results import Failed, Ok, Result
from loreley_api.infrastructure.opensearch import (
    CountsReader,
    CountTarget,
    JobsReader,
    Page,
    PageRequest,
    SearchIndexReader,
    SourcesReader,
    StoredRecord,
)

# 登録文書数。`index_status` を問わない(B 3.1)。
DOCUMENT_COUNT_TARGET: CountTarget = "document_count"
# 存在確認だけなので、設定の項目は読まない(`_source` を返さない)。
NO_SOURCE_FIELDS: tuple[str, ...] = ()

_TAB_COUNT_TARGETS: dict[DocumentTab, CountTarget] = {
    DocumentTab.SKIPPED: "skipped",
    DocumentTab.EXTRACT_FAILED: "extract_failed",
    DocumentTab.OVERSIZE: "oversize",
    DocumentTab.SUMMARY_PENDING: "summary_pending",
}


class DocumentReviewService:
    def __init__(
        self,
        *,
        sources: SourcesReader,
        jobs: JobsReader,
        search_index: SearchIndexReader,
        counts: CountsReader,
        runner: BlockingRunner,
    ) -> None:
        self._sources = sources
        self._jobs = jobs
        self._search_index = search_index
        self._counts = counts
        self._runner = runner

    async def list_documents(
        self,
        *,
        source_id: str,
        tab: DocumentTab,
        page: int,
        items_per_page: int,
        descending: bool,
    ) -> DocumentListResponse:
        """EP-11。`page * items_per_page` が窓(10,000)以内であることは、入力の検証が保証する。"""
        found = await self._runner.run(
            CATEGORY_OPENSEARCH, self._sources.get, source_id, NO_SOURCE_FIELDS
        )
        if isinstance(found, Failed):
            raise unavailable()
        if found.value is None:
            raise source_config_not_found()

        listed = await self._runner.run(
            CATEGORY_OPENSEARCH,
            self._lister_of(tab),
            source_id,
            PageRequest(page, items_per_page, descending),
        )
        if isinstance(listed, Failed):
            raise unavailable()

        top_level_reasons: dict[str, UnavailableReason] = {}
        tab_counts, document_count = await self._read_counts(
            source_id, tab, listed.value.total, top_level_reasons
        )
        rows = await self._rows_of(tab, listed.value)

        return DocumentListResponse(
            tab=tab,
            items=rows,
            total=listed.value.total,
            page=page,
            items_per_page=items_per_page,
            window_limit=PAGE_WINDOW_LIMIT,
            tab_counts=tab_counts,
            document_count=document_count,
            unavailable=top_level_unavailable(top_level_reasons),
        )

    def _lister_of(self, tab: DocumentTab) -> Callable[[str, PageRequest], Result[Page]]:
        match tab:
            case DocumentTab.SKIPPED:
                return self._jobs.list_skipped
            case DocumentTab.OVERSIZE:
                return self._jobs.list_oversize
            case DocumentTab.EXTRACT_FAILED:
                return self._search_index.list_extract_failed
            case DocumentTab.SUMMARY_PENDING:
                return self._search_index.list_summary_pending

    async def _read_counts(
        self,
        source_id: str,
        requested_tab: DocumentTab,
        requested_tab_total: int,
        reasons: dict[str, UnavailableReason],
    ) -> tuple[TabCounts, int | None]:
        """他の 3 タブの件数と登録文書数。要求したタブの件数は、件数の食い違いを避けるため一覧の
        `total` を使う(同じ検索の結果)。
        """
        other_tabs = [tab for tab in DocumentTab if tab is not requested_tab]
        targets = [DOCUMENT_COUNT_TARGET, *(_TAB_COUNT_TARGETS[tab] for tab in other_tabs)]
        results = await self._runner.run(
            CATEGORY_OPENSEARCH, self._counts.count_for_source, source_id, targets
        )

        def read(target: CountTarget, path: str) -> int | None:
            result = results[target]
            if isinstance(result, Failed):
                reasons[path] = reason_of(result)
                return None
            return result.value

        counts_by_tab: dict[DocumentTab, int | None] = {requested_tab: requested_tab_total}
        for tab in other_tabs:
            counts_by_tab[tab] = read(_TAB_COUNT_TARGETS[tab], f"tab_counts.{tab.value}")
        tab_counts = TabCounts(
            skipped=counts_by_tab[DocumentTab.SKIPPED],
            extract_failed=counts_by_tab[DocumentTab.EXTRACT_FAILED],
            oversize=counts_by_tab[DocumentTab.OVERSIZE],
            summary_pending=counts_by_tab[DocumentTab.SUMMARY_PENDING],
        )
        return tab_counts, read(DOCUMENT_COUNT_TARGET, "document_count")

    async def _rows_of(self, tab: DocumentTab, page: Page) -> list[DocumentRow]:
        records = page.items
        match tab:
            case DocumentTab.SKIPPED:
                return await self._skipped_rows(records)
            case DocumentTab.OVERSIZE:
                return [
                    OversizeDocument(
                        **dataclasses.asdict(document_view.read_oversize(record.source)),
                        unavailable={},
                    )
                    for record in records
                ]
            case DocumentTab.EXTRACT_FAILED:
                return [
                    ExtractFailedDocument(
                        **dataclasses.asdict(
                            document_view.read_extract_failed(record.record_id, record.source)
                        ),
                        unavailable={},
                    )
                    for record in records
                ]
            case DocumentTab.SUMMARY_PENDING:
                return [
                    SummaryPendingDocument(
                        **dataclasses.asdict(
                            document_view.read_summary_pending(record.record_id, record.source)
                        ),
                        unavailable={},
                    )
                    for record in records
                ]

    async def _skipped_rows(self, records: Sequence[StoredRecord]) -> list[DocumentRow]:
        """`existence` は、ページ内の `document_id` を 1 回の一括検索で問い合わせて決める。

        一括検索が失敗したら、全行を `unknown` にして全行の `unavailable.existence` に理由を付ける
        (1 回の検索なので、行ごとに成否が分かれることはない)。`document_id` が読めない行は、
        検索の成否によらず `unknown` で、`unavailable` のキーは付けない(値が読めないだけ)。
        """
        views = [document_view.read_skipped(record.source) for record in records]
        document_ids = list(
            dict.fromkeys(view.document_id for view in views if view.document_id is not None)
        )
        existing: Result[frozenset[str]] = Ok(frozenset())
        if document_ids:
            existing = await self._runner.run(
                CATEGORY_OPENSEARCH, self._search_index.existing_ids, document_ids
            )

        reasons_by_row: dict[str, dict[str, UnavailableReason]] = {}
        if isinstance(existing, Failed):
            reason = reason_of(existing)
            reasons_by_row = {record.record_id: {"existence": reason} for record in records}
        row_reasons = row_unavailable([record.record_id for record in records], reasons_by_row)
        existing_ids = None if isinstance(existing, Failed) else existing.value
        return [
            SkippedDocument(
                **dataclasses.asdict(view),
                existence=existence_of(view.document_id, existing_ids),
                unavailable=row_reasons[record.record_id],
            )
            for record, view in zip(records, views, strict=True)
        ]
