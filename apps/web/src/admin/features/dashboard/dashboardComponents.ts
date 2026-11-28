// D1 のコンポーネントの定義表(dashboard 3.2。F 3.5)。タイルはこの表から描く。
// コンポーネントを足すとき(将来の AF-22・AF-26 など)は、行を足し、必要なら導線を持たせる。
// 対象は機能設計 AF-18 のとおり(必須 5 つ+任意 3 つ)。要件にないコンポーネントは足さない。
import type { ComponentId } from '@/admin/api'
import { ROUTE_NAMES, type RouteName } from '@/admin/lib/routeNames'

export type DashboardComponentDefinition = {
  /** API の `components[].id`。表示名と同じ(compose のサービス名。`web` だけは `api` が配信する Web UI の表示名) */
  id: ComponentId
  /** 役割(12px の補足) */
  role: string
  /** 必須は常に出す。任意は設定されていなければ「未設定」のタイルで出す(異常と取り違えないため。#24) */
  group: 'required' | 'optional'
  /** 導線(#28)。crawler・indexer はジョブ(J1)、opensearch は O1。他にはない */
  link: { label: string; routeName: RouteName } | null
}

const JOBS_LINK = { label: 'ジョブの状態を確認', routeName: ROUTE_NAMES.jobs } as const

export const dashboardComponents: readonly DashboardComponentDefinition[] = [
  { id: 'crawler', role: '文書の取得とジョブの実行', group: 'required', link: JOBS_LINK },
  { id: 'indexer', role: '抽出・索引への登録・削除の実行', group: 'required', link: JOBS_LINK },
  {
    id: 'opensearch',
    role: '検索インデックスとデータの保存先',
    group: 'required',
    link: { label: 'OpenSearch の詳細', routeName: ROUTE_NAMES.opensearch },
  },
  { id: 'api', role: '検索と管理操作の窓口', group: 'required', link: null },
  { id: 'web', role: 'この管理画面の配信', group: 'required', link: null },
  {
    id: 'opensearch-dashboards',
    role: 'OpenSearch の管理・調査用',
    group: 'optional',
    link: null,
  },
  { id: 'embedding', role: 'ローカルの埋め込みモデル', group: 'optional', link: null },
  { id: 'llm', role: 'ローカルの要約モデル', group: 'optional', link: null },
]
