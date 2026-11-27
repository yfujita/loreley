// D1 のページの状態(F 4・5.2)。自動更新のスイッチ(`ref`。永続化しない)・取得・画面の状態・表示モデルをまとめる。
// 最終取得成功日時は Query の `dataUpdatedAt`(クライアント保持。取得失敗が続いても更新されない。dashboard 4.2)。
import { computed, ref, watch } from 'vue'

import { useViewState } from '@/admin/composables/useViewState'
import { useDashboardQuery } from '@/admin/queries/dashboard'

import {
  buildDashboardViewModel,
  type DashboardViewModel,
} from '@/admin/features/dashboard/models/dashboardViewModel'

export function useDashboardPage() {
  const autoRefresh = ref(true)
  const query = useDashboardQuery(autoRefresh)
  const viewState = useViewState(query)

  // 自動更新を止めていた間の表示は古い。「入」に戻したときは、次の定期更新(最大 30 秒後)を待たずにすぐ取り直す
  // (結果が古いときも「正常」と断定しない。AF-18)。タブへの復帰では取り直さない(フォーカスでの再取得はしない方針。E 5.4)。
  watch(autoRefresh, (enabled) => {
    if (enabled) void query.refetch({ cancelRefetch: false })
  })

  const viewModel = computed<DashboardViewModel | null>(() => {
    const data = query.data.value
    if (data === undefined) return null
    return buildDashboardViewModel(data, {
      stale: viewState.value.kind === 'stale',
      lastSuccessAt: viewState.value.updatedAt,
    })
  })

  // 手動の「更新」を押した直後だけ、結果を読み上げる(自動更新は読み上げない。dashboard 3.4・DS 8)。
  // 結果は「どの取得に対する通知か」を `dataUpdatedAt` で覚え、次の取得で更新された時点で消す。
  const manualResult = ref<{ updatedAt: number; message: string } | null>(null)
  const manualUpdateMessage = computed(() =>
    manualResult.value?.updatedAt === query.dataUpdatedAt.value ? manualResult.value.message : '',
  )

  /** 手動の更新。取得中でも押せるが、進行中の取得をやり直さない(二重送信しない。DS 4.5)。 */
  async function refresh(): Promise<void> {
    const result = await query.refetch({ cancelRefetch: false })
    if (result.isError || result.data === undefined) return
    const { counts } = buildDashboardViewModel(result.data, { stale: false, lastSuccessAt: null })
    manualResult.value = {
      updatedAt: result.dataUpdatedAt,
      message: `更新しました。異常 ${counts.abnormal} 件、判定不能 ${counts.undetermined} 件`,
    }
  }

  /** 「再試行」「再読み込み」。読み上げは付けない(エラー・警告のほうが変わる)。 */
  async function retry(): Promise<void> {
    await query.refetch({ cancelRefetch: false })
  }

  return { autoRefresh, viewState, viewModel, manualUpdateMessage, refresh, retry }
}
