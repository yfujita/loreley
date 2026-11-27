// `unavailable`(部分失敗)の参照と、セルの表示状態(E 5.9・F 3.5。FMOD-P-14・31・33)。
//
// - 「`null` で、その行(または最上位)の `unavailable` にキーがある」=取得できなかった
// - 「`null` でキーがない」=値がない(未実行・該当なし)、または保存値が読めない(値があるはずの項目)
// 画面は `unavailable` を直接読まず、ここの関数だけを使う。一覧の行には `rowCell`、単一の応答・EP-11 の最上位には `topCell`。
// D1(EP-13)・O1(EP-12)・シェル(EP-14)は `unavailable` を持たないので使わない。
import type { Unavailable, UnavailableReason } from '@/admin/api'

type WithUnavailable = { unavailable?: MaybeUnavailable }

/**
 * パスの文字列(B 2.2 の正式なパス・行内の相対パス)。B の変更に追従する場所をここ 1 か所にする。
 */
export const UNAVAILABLE_PATH = {
  /** EP-01 の行(`items[i].unavailable`。行内の相対パス) */
  sourceRow: {
    lastCrawl: 'last_crawl',
    lastCrawlStalled: 'last_crawl.stalled',
    lastCompletedAt: 'last_completed_at',
    deleteJob: 'delete_job',
    deleteJobStalled: 'delete_job.stalled',
    documentCount: 'document_count',
  },
  /** EP-09 の行(行内の相対パス) */
  jobRow: { stalled: 'stalled' },
  /** EP-11 の行(行内の相対パス。`skipped` タブの行だけに出る) */
  documentRow: { existence: 'existence' },
  /** EP-02 の最上位(正式なパス) */
  sourceDetail: {
    lock: 'lock',
    lastCrawl: 'last_crawl',
    lastCompletedAt: 'last_completed_at',
    deleteJob: 'delete_job',
    lastCrawlStalled: 'last_crawl.stalled',
    deleteJobStalled: 'delete_job.stalled',
    indexDocumentCount: 'index.document_count',
  },
  /** EP-10 の最上位(正式なパス) */
  jobDetail: {
    stalled: 'stalled',
    leaseExpiresAt: 'lease_expires_at',
    latestForSource: 'latest_for_source',
    rerunnable: 'rerunnable',
    deletionCurrent: 'deletion.current',
  },
  /** EP-11 の最上位(行に属さない項目だけ) */
  documentList: {
    documentCount: 'document_count',
    tabCount: (tab: string) => `tab_counts.${tab}`,
  },
} as const

// 生成型は `unavailable` を常に存在するオブジェクトとするが、実行時の値は信用しない(欠落しても落とさない。E 5.3)。
type MaybeUnavailable = Unavailable | null | undefined

function reasonAt(unavailable: MaybeUnavailable, path: string): UnavailableReason | undefined {
  if (typeof unavailable !== 'object' || unavailable === null) return undefined
  // `in` ではなく自身のキーだけを見る(`constructor` などのプロトタイプのキーを拾わない)。
  return Object.hasOwn(unavailable, path) ? unavailable[path] : undefined
}

/** 一覧の行の `unavailable`(EP-01・09・11)を、行内の相対パスで引く。他の行の失敗には影響されない。 */
export function rowUnavailableReason(
  row: WithUnavailable,
  path: string,
): UnavailableReason | undefined {
  return reasonAt(row.unavailable, path)
}

/**
 * 単一の応答(EP-02・EP-10)と EP-11 の最上位の `unavailable` を、正式なパスで引く。
 * EP-01・09 の最上位は常に `{}` なので引かない。
 */
export function topUnavailableReason(
  response: WithUnavailable,
  path: string,
): UnavailableReason | undefined {
  return reasonAt(response.unavailable, path)
}

/**
 * セルの表示状態。
 * - value: 値がある
 * - unavailable: 取得できなかった(「—」+「取得できません」。表のセルは視覚的に隠した文言、S2 のカードは見える文言)
 * - unreadable: 保存値が読めない(「—」+視覚的に隠した「読み取れません」。見える文言は足さない)
 * - none: 値がない(「—」+「なし」。未実行の `last_crawl` は「未実行」)
 */
export type CellState<T> =
  | { kind: 'value'; value: T }
  | { kind: 'unavailable'; reason: UnavailableReason }
  | { kind: 'unreadable' }
  | { kind: 'none' }

export type CellOptions = {
  /** 値があるはずの項目か(`expectedFields` の表から決める)。`null` のとき、true なら unreadable、false なら none */
  expected: boolean
}

/** `unavailable`(引く対象の 1 つ)・パス・値から、セルの表示状態を返す。 */
export function cellState<T>(
  unavailable: MaybeUnavailable,
  path: string,
  value: T | null | undefined,
  options: CellOptions,
): CellState<T> {
  if (value !== null && value !== undefined) return { kind: 'value', value }

  const reason = reasonAt(unavailable, path)
  if (reason !== undefined) return { kind: 'unavailable', reason }
  return options.expected ? { kind: 'unreadable' } : { kind: 'none' }
}

/** 一覧の行のセル。`path` は行内の相対パス。 */
export function rowCell<T>(
  row: WithUnavailable,
  path: string,
  value: T | null | undefined,
  options: CellOptions,
): CellState<T> {
  return cellState(row.unavailable, path, value, options)
}

/** 単一の応答・EP-11 の最上位のセル。`path` は正式なパス。 */
export function topCell<T>(
  response: WithUnavailable,
  path: string,
  value: T | null | undefined,
  options: CellOptions,
): CellState<T> {
  return cellState(response.unavailable, path, value, options)
}
