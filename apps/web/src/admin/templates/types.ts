// 4 型のテンプレートが共有する props の型。
import type { ActionSpec } from '@/admin/lib/actions'
import type { ViewState } from '@/admin/lib/viewState'

/** 画面ごとの文言(画面仕様が正)。 */
export type StateTexts = {
  loadingLabel?: string
  emptyTitle?: string
  emptyMessage?: string
  errorTitle?: string
  errorMessage?: string
  notfoundTitle?: string
  notfoundMessage?: string
  /** stale アラートの追記(「実行中のジョブの状態が実際と異なる可能性があります。」など) */
  staleNote?: string
}

/** ページ見出し領域(`PageHeader`)に渡す値。タイトルは route の `meta.title`(`useRouteTitle`)から作る。 */
export type PageHeaderProps = {
  title: string
  monoTitle?: boolean
  description?: string
  actions?: readonly ActionSpec[]
  /** 主操作の `ActionSpec.id`(DS 4.13: 画面の主操作は 1 つ) */
  primaryActionId?: string | null
}

/** 状態ブロックの出し分け(`ViewStateBody`)に渡す値。 */
export type ViewStateProps = {
  viewState: ViewState
  texts?: StateTexts
  /** `data-testid` の接頭辞(DS 9。画面 ID を小文字にしたもの。例 `s1`) */
  testidPrefix?: string
}
