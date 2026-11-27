// 一覧の条件の型(URL から正規化した型付きの条件。key になる。E 5.4・5.6)。
// key factory(keys.ts)と、取得の composable(jobs.ts・documents.ts)が共有する。
import type { DocumentTab, JobStatus } from '@/admin/api'
import type { ItemsPerPage } from '@/admin/lib/pagination'

/** EP-09 の `sort`。OpenAPI では素の string のため、画面側で union を持つ(許容は `queued_at`・`-queued_at`)。 */
export type JobsSort = 'queued_at' | '-queued_at'

/** `status` の絞り込み。保存上の状態に、画面の「実行待ち・実行中」の複合値 `active` を加えたもの(E 5.6)。 */
export type JobsStatusFilter = JobStatus | 'active'

/** J1 の条件。 */
export type JobsQuery = {
  page: number
  itemsPerPage: ItemsPerPage
  /** `null` は指定なし(API の既定の並び `-queued_at`) */
  sort: JobsSort | null
  /** データソースの絞り込み。`null` はすべて */
  sourceId: string | null
  /** `null` はすべて */
  status: JobsStatusFilter | null
}

/**
 * X1 の条件。`tab` は API の値(snake_case)。URL の kebab-case との対応は features 側の定義表(documentTabs)が持つ。
 */
export type DocumentsQuery = {
  tab: DocumentTab
  page: number
  itemsPerPage: ItemsPerPage
  /** タブごとの項目の昇順・降順。`null` は指定なし(タブごとの既定の並び) */
  sort: string | null
}

/**
 * 同じスコープかの判定に使う部分(ページ・並べ替え以外)。前回データを見せてよいのは、これが同じときだけ(placeholder.ts)。
 * key は `['jobs', 'list', params]`。
 */
export function jobsScopeOf(key: readonly ['jobs', 'list', JobsQuery]) {
  const { sourceId, status, itemsPerPage } = key[2]
  return { sourceId, status, itemsPerPage }
}

/** key は `['documents', sourceId, params]`。データソースは key の 2 番目。 */
export function documentsScopeOf(key: readonly ['documents', string | null, DocumentsQuery]) {
  const { tab, itemsPerPage } = key[2]
  return { sourceId: key[1], tab, itemsPerPage }
}
