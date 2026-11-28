// O1 のページの状態(F 4)。取得(`useOpenSearchClusterQuery`。クエリなし)・画面の状態・URL の条件(`q`・`state`。`replace`)・
// 絞り込み後のマトリクスのモデルをまとめる。1 ページの列数とページ位置は、`ShardMatrix` が自分の幅から決める。
// 絞り込みは画面側(Admin API は全件を返す)。条件を API に送らない。
import { computed } from 'vue'

import type { ClusterStatus } from '@/admin/lib/clusterValues'
import { useListParams } from '@/admin/composables/useListParams'
import { useViewState } from '@/admin/composables/useViewState'
import { useOpenSearchClusterQuery } from '@/admin/queries/opensearch'

import { findUnassignedPrimaries } from '@/admin/features/opensearch/models/clusterNotices'
import {
  conditionKey,
  describeCondition,
  filterIndices,
  isFiltering,
  toCondition,
} from '@/admin/features/opensearch/models/indexFilter'
import { buildMatrixModel } from '@/admin/features/opensearch/models/matrixModel'
import { opensearchParams } from '@/admin/features/opensearch/opensearchParams'

export function useOpenSearchPage() {
  const query = useOpenSearchClusterQuery()
  // 空(インデックス 0 件)は `viewState` の空にしない: 概況は 0 件でも出す(マトリクスの領域だけが空になる)。
  const viewState = useViewState(query)
  const { params, update } = useListParams(opensearchParams)

  const condition = computed(() => toCondition(params.value))
  const filtering = computed(() => isFiltering(condition.value))

  const response = query.data
  const visibleIndices = computed(() =>
    response.value === undefined ? [] : filterIndices(response.value.indices, condition.value),
  )
  const matrix = computed(() =>
    response.value === undefined ? null : buildMatrixModel(response.value, visibleIndices.value),
  )
  // 通知はクラスタ全体の値から作る(絞り込みの対象外)。
  const unassignedPrimaries = computed(() =>
    response.value === undefined ? [] : findUnassignedPrimaries(response.value.shards),
  )

  function setName(value: string): Promise<void> {
    return update({ q: value.trim() })
  }
  function setStates(states: ClusterStatus[]): Promise<void> {
    return update({ states })
  }
  function clearCondition(): Promise<void> {
    return update({ q: '', states: [] })
  }

  /** 手動の更新。取得中でも押せるが、進行中の取得をやり直さない(二重送信しない。DS 4.5)。 */
  async function refresh(): Promise<void> {
    await query.refetch({ cancelRefetch: false })
  }

  return {
    viewState,
    response,
    params,
    filtering,
    conditionText: computed(() => describeCondition(condition.value)),
    conditionKey: computed(() => conditionKey(condition.value)),
    matrix,
    unassignedPrimaries,
    setName,
    setStates,
    clearCondition,
    refresh,
  }
}
