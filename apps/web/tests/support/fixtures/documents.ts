// EP-11 `GET /sources/{source_id}/documents` のフィクスチャ(F 7.3)。4 つの行型(判別子のない `anyOf`)。
import type {
  DocumentListResponse,
  DocumentTab,
  ExtractFailedDocument,
  OversizeDocument,
  SkippedDocument,
  SummaryPendingDocument,
  TabCounts,
} from '@/admin/api'

const NEVER_COUNTED: TabCounts = {
  skipped: 2,
  extract_failed: 1,
  oversize: 1,
  summary_pending: 0,
}

export function skippedDocument(overrides: Partial<SkippedDocument> = {}): SkippedDocument {
  return {
    document_id: 'a1'.repeat(32),
    external_id: 'manuals/2026/guide.pdf',
    stage: 'fetch',
    reason: 'fetch_permission_denied: 取得の権限がなかった',
    attempts: 3,
    consecutive_skips: 5,
    first_skipped_at: '2026-11-18T03:00:10.000Z',
    last_skipped_at: '2026-11-22T03:00:12.000Z',
    last_job_id: 'job-20261122T030000Z-77aa01bc',
    existence: 'existing',
    unavailable: {},
    ...overrides,
  } satisfies SkippedDocument
}

export function extractFailedDocument(
  overrides: Partial<ExtractFailedDocument> = {},
): ExtractFailedDocument {
  return {
    document_id: 'b2'.repeat(32),
    title: 'Broken PDF',
    external_id: 'manuals/broken.pdf',
    mime_type: 'application/pdf',
    size: 1_048_576,
    source_updated_at: '2026-11-10T00:00:00.000Z',
    last_seen_at: '2026-11-22T03:00:00.000Z',
    unavailable: {},
    ...overrides,
  } satisfies ExtractFailedDocument
}

export function oversizeDocument(overrides: Partial<OversizeDocument> = {}): OversizeDocument {
  return {
    document_id: 'c3'.repeat(32),
    external_id: 'archive/huge.pdf',
    detected_by: 'crawler',
    size: 432_800_000,
    first_detected_at: '2026-11-18T03:00:10.000Z',
    last_detected_at: '2026-11-22T03:00:12.000Z',
    last_job_id: 'job-20261122T030000Z-77aa01bc',
    unavailable: {},
    ...overrides,
  } satisfies OversizeDocument
}

export function summaryPendingDocument(
  overrides: Partial<SummaryPendingDocument> = {},
): SummaryPendingDocument {
  return {
    document_id: 'd4'.repeat(32),
    title: 'Handbook',
    external_id: 'handbook.md',
    mime_type: 'text/markdown',
    source_updated_at: '2026-11-10T00:00:00.000Z',
    indexed_at: '2026-11-22T03:00:00.000Z',
    unavailable: {},
    ...overrides,
  } satisfies SummaryPendingDocument
}

function response(
  tab: DocumentTab,
  items: DocumentListResponse['items'],
  overrides: Partial<DocumentListResponse> = {},
): DocumentListResponse {
  return {
    tab,
    items,
    total: items.length,
    page: 1,
    items_per_page: 25,
    window_limit: 10_000,
    tab_counts: NEVER_COUNTED,
    document_count: 1284,
    unavailable: {},
    ...overrides,
  } satisfies DocumentListResponse
}

/** EP-11 の応答。 */
export const documents = {
  /** スキップ(既存・新規・確認できないが混在) */
  skipped: () =>
    response('skipped', [
      skippedDocument(),
      skippedDocument({ document_id: 'a2'.repeat(32), external_id: 'new.pdf', existence: 'new' }),
    ]),
  /** スキップで、存在確認の一括検索が失敗した(全行の `unavailable.existence`。`existence=unknown`) */
  skippedExistenceUnavailable: () =>
    response('skipped', [
      skippedDocument({
        existence: 'unknown',
        unavailable: { existence: 'search_index_unavailable' },
      }),
      skippedDocument({
        document_id: 'a2'.repeat(32),
        existence: 'unknown',
        unavailable: { existence: 'search_index_unavailable' },
      }),
    ]),
  /** スキップで `document_id` が読めない行(`existence=unknown`・キーなし) */
  skippedUnreadableDocumentId: () =>
    response('skipped', [skippedDocument({ document_id: null, existence: 'unknown' })]),
  extractFailed: () =>
    response('extract_failed', [
      extractFailedDocument(),
      extractFailedDocument({
        document_id: 'b3'.repeat(32),
        title: null,
        external_id: 'no-title.pdf',
      }),
    ]),
  oversize: () =>
    response('oversize', [
      oversizeDocument(),
      oversizeDocument({ document_id: 'c4'.repeat(32), detected_by: 'indexer', size: null }),
    ]),
  /** 要約未生成(実データでは出ない。要約機能の実装後。AAPI-U-8) */
  summaryPending: () =>
    response('summary_pending', [summaryPendingDocument()], {
      tab_counts: { ...NEVER_COUNTED, summary_pending: 1 },
    }),
  /** 0 件(空の状態) */
  empty: () =>
    response('skipped', [], {
      tab_counts: { skipped: 0, extract_failed: 0, oversize: 0, summary_pending: 0 },
    }),
  /** タブの件数の一部と登録文書数が取得できない(最上位の `unavailable`) */
  countsUnavailable: () =>
    response('skipped', [skippedDocument()], {
      document_count: null,
      tab_counts: { ...NEVER_COUNTED, summary_pending: null },
      unavailable: {
        document_count: 'search_index_unavailable',
        'tab_counts.summary_pending': 'search_index_unavailable',
      },
    }),
  /** 10,000 件を超える(`window_limit` で案内する) */
  overWindow: () =>
    response('skipped', [skippedDocument()], {
      total: 25_000,
      tab_counts: { ...NEVER_COUNTED, skipped: 25_000 },
    }),
}
