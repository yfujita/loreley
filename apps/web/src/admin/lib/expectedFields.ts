// 「値があるはずの項目」の表(E 5.9・F 3.5。FMOD-P-31・FMOD-U-13)。
//
// OpenAPI では、B が「null」と書く項目以外の多くも null 許容になっている(EP-01・02・09・10・11 の行型)。
// どの項目が「値があるはず」(`null` なら保存値が読めない=unreadable)かを、EP・行型(EP-11 は `tab`)ごとに
// この 1 つの表に持つ。画面は項目ごとに判断を散らさず、`cellState(…, { expected })` に渡す。
//
// 決め方(FMOD-U-13): Crawler・Indexer が毎回書く項目は expected。B が「null」と明記する項目
// (`title`・`size`(原本サイズ超過)・日時の `started_at`・`finished_at`・`failure_reason` など、
// 状況によって値がない項目)と、`unavailable` で取得失敗を表す項目(`last_crawl` など)は含めない。
import type {
  DocumentTab,
  ExtractFailedDocument,
  JobBrief,
  OversizeDocument,
  Registration,
  SkippedDocument,
  SourceDetailResponse,
  SourceListItem,
  SummaryPendingDocument,
} from '@/admin/api'

type FieldsOf<T> = readonly (keyof T & string)[]

export const EXPECTED_FIELDS = {
  // JobBrief(EP-01 の `last_crawl`・`delete_job`、EP-02 の同、EP-09 の行)。`status=null` のジョブにタグ・操作は出さない
  jobBrief: ['status', 'job_type', 'trigger', 'queued_at'] as const satisfies FieldsOf<JobBrief>,
  // EP-10 の最上位。JobBrief と同じ 4 項目
  jobDetail: ['status', 'job_type', 'trigger', 'queued_at'] as const satisfies FieldsOf<JobBrief>,
  // EP-10 の `registration`。件数・`partial`・`phase`(`phase` は `partial` が null のとき null)
  registration: [
    'created_count',
    'enumerated_count',
    'error_count',
    'invalid_id_count',
    'oversize_count',
    'skipped_count',
    'unchanged_count',
    'updated_count',
    'partial',
    'phase',
  ] as const satisfies FieldsOf<Registration>,
  // EP-01 の行。S1 で使う項目のうち、値があるはずなのは `status` だけ(`connector_type`・`last_completed_at` は S1 で使わない)
  sourceListRow: ['status'] as const satisfies FieldsOf<SourceListItem>,
  // EP-02 の設定項目(null 許容。読めないときは `unavailable.<項目名>=malformed` も付く)。
  // `ttl_days` の null は「日で割り切れない」、`schedule_cron` の null は「手動のみ」なので含めない
  sourceDetail: [
    'connector_type',
    'connector_config',
    'status',
    'ttl_seconds',
    'min_delete_count',
    'ratio_threshold_percent',
    'updated_at',
  ] as const satisfies FieldsOf<SourceDetailResponse>,
  // EP-11 の行型ごと(B 6.1 の項目表)。`existence`・`document_id`(スキップ以外)は OpenAPI で非 null
  skippedDocument: [
    'document_id',
    'external_id',
    'stage',
    'reason',
    'attempts',
    'consecutive_skips',
    'first_skipped_at',
    'last_skipped_at',
    'last_job_id',
  ] as const satisfies FieldsOf<SkippedDocument>,
  // `title` は「なければ null」(画面は「(タイトルなし)」)
  extractFailedDocument: [
    'document_id',
    'external_id',
    'mime_type',
    'size',
    'source_updated_at',
    'last_seen_at',
  ] as const satisfies FieldsOf<ExtractFailedDocument>,
  // `size` は「分かる場合だけ」(画面は「不明」)
  oversizeDocument: [
    'document_id',
    'external_id',
    'detected_by',
    'first_detected_at',
    'last_detected_at',
    'last_job_id',
  ] as const satisfies FieldsOf<OversizeDocument>,
  summaryPendingDocument: [
    'document_id',
    'external_id',
    'mime_type',
    'source_updated_at',
    'indexed_at',
  ] as const satisfies FieldsOf<SummaryPendingDocument>,
} as const

export type ExpectedFieldsKind = keyof typeof EXPECTED_FIELDS

const DOCUMENT_KIND_BY_TAB = {
  skipped: 'skippedDocument',
  extract_failed: 'extractFailedDocument',
  oversize: 'oversizeDocument',
  summary_pending: 'summaryPendingDocument',
} as const satisfies Record<DocumentTab, ExpectedFieldsKind>

/** EP-11 の行型(`tab`)に対応する表の名前。 */
export function expectedKindForDocumentTab(tab: DocumentTab): ExpectedFieldsKind {
  return DOCUMENT_KIND_BY_TAB[tab]
}

/** その項目が「値があるはず」か。`cellState` の `expected` に渡す。 */
export function isExpectedField(kind: ExpectedFieldsKind, field: string): boolean {
  const fields: readonly string[] = EXPECTED_FIELDS[kind]
  return fields.includes(field)
}

/** `cellState(…, expectedFor(kind, field))` の形で渡せる、オプションのオブジェクト。 */
export function expectedFor(kind: ExpectedFieldsKind, field: string): { expected: boolean } {
  return { expected: isExpectedField(kind, field) }
}
