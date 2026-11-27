// O1 の絞り込み(純関数。opensearch 3.5)。Admin API は全件を返すので、画面側で絞る。
// 条件は インデックス名(部分一致・大文字小文字を区別しない)と 状態(複数選択。OR)。名前と状態は AND。
import { CLUSTER_STATUSES, toClusterStatus, type ClusterStatus } from '@/admin/lib/clusterValues'

/** URL・フォームに持つ条件(正規化の前)。状態は 3 つとも選んだ表示を保てるよう、そのまま持つ。 */
export type RawIndexFilter = {
  q: string
  states: readonly ClusterStatus[]
}

/** 絞り込みに使う条件(正規化後)。 */
export type IndexFilterCondition = {
  /** 前後の空白を除いたもの。空なら名前の条件なし */
  query: string
  /** 空なら状態の条件なし(「すべて」) */
  states: readonly ClusterStatus[]
}

/** 状態は red → yellow → green の順(マトリクスの並びと同じ)。重複を除く。 */
export function canonicalStates(states: readonly ClusterStatus[]): ClusterStatus[] {
  const ordered = [...CLUSTER_STATUSES].reverse()
  return ordered.filter((status) => states.includes(status))
}

/**
 * 正規化: 名前は前後の空白を除く(空白だけなら条件なし)。状態は 3 つとも選択=「すべて」と同じ=条件なし。
 * 「直前の条件と同じなら何もしない」は、この結果で比べる(`conditionKey`)。
 */
export function toCondition(raw: RawIndexFilter): IndexFilterCondition {
  const states = canonicalStates(raw.states)
  return {
    query: raw.q.trim(),
    states: states.length === CLUSTER_STATUSES.length ? [] : states,
  }
}

export function isFiltering(condition: IndexFilterCondition): boolean {
  return condition.query !== '' || condition.states.length > 0
}

/** 同じ条件なら同じ文字列(マトリクスを 1 ページ目に戻すかの判定に使う)。 */
export function conditionKey(condition: IndexFilterCondition): string {
  return JSON.stringify([condition.query, condition.states])
}

/** 絞り込む。並びは変えない(API の並びのまま)。名前は文字列の一致で、正規表現ではない。 */
export function filterIndices<T extends { name: string; status: string | null }>(
  indices: readonly T[],
  condition: IndexFilterCondition,
): T[] {
  const query = condition.query.toLowerCase()
  return indices.filter((index) => {
    if (query !== '' && !index.name.toLowerCase().includes(query)) return false
    if (condition.states.length === 0) return true
    // 状態を選んだときは、未知の値・取得できない(null)インデックスを除く。
    const status = toClusterStatus(index.status)
    return status !== null && condition.states.includes(status)
  })
}

/** 「適用中の条件」の文(例: 名前に「logs」を含む、状態が yellow または green)。 */
export function describeCondition(condition: IndexFilterCondition): string {
  const parts: string[] = []
  if (condition.query !== '') parts.push(`名前に「${condition.query}」を含む`)
  if (condition.states.length > 0) parts.push(`状態が ${condition.states.join(' または ')}`)
  return parts.join('、')
}
