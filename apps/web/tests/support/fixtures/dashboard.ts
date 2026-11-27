// EP-13 `GET /dashboard` のフィクスチャ(F 7.3)。`components[]` は常に 8 件(固定の順。B 8.1)。
import type { ComponentId, ComponentState, ComponentStatus, DashboardResponse } from '@/admin/api'

const CHECKED_AT = '2026-11-22T01:00:00.000Z'

const COMPONENT_IDS = [
  'crawler',
  'indexer',
  'opensearch',
  'api',
  'web',
  'opensearch-dashboards',
  'embedding',
  'llm',
] as const satisfies readonly ComponentId[]

export function component(
  id: ComponentId,
  state: ComponentState,
  reason: ComponentStatus['reason'] = null,
): ComponentStatus {
  return { id, state, reason, checked_at: CHECKED_AT }
}

/** 8 コンポーネントの状態を、既定(任意のものは未設定)に対して上書きして作る。 */
function build(overrides: Partial<Record<ComponentId, ComponentStatus>> = {}): DashboardResponse {
  const defaults: Record<ComponentId, ComponentStatus> = {
    crawler: component('crawler', 'normal'),
    indexer: component('indexer', 'normal'),
    opensearch: component('opensearch', 'normal'),
    api: component('api', 'normal'),
    web: component('web', 'normal'),
    'opensearch-dashboards': component('opensearch-dashboards', 'not_configured', 'missing'),
    embedding: component('embedding', 'not_configured', 'missing'),
    llm: component('llm', 'not_configured', 'missing'),
  }
  return {
    checked_at: CHECKED_AT,
    components: COMPONENT_IDS.map((id) => overrides[id] ?? defaults[id]),
  } satisfies DashboardResponse
}

export const dashboard = {
  /** 必須コンポーネントがすべて正常、任意のものは未設定 */
  allNormal: () => build(),
  /** crawler が異常(接続拒否) */
  abnormal: () => build({ crawler: component('crawler', 'abnormal', 'connection_refused') }),
  /** indexer が判定不能(タイムアウト) */
  undetermined: () => build({ indexer: component('indexer', 'undetermined', 'timeout') }),
  /** crawler が異常・indexer が判定不能(異常を優先して表示する) */
  mixed: () =>
    build({
      crawler: component('crawler', 'abnormal', 'connection_refused'),
      indexer: component('indexer', 'undetermined', 'connection_error'),
    }),
  /** 任意のコンポーネントがすべて設定済みで正常 */
  allConfigured: () =>
    build({
      'opensearch-dashboards': component('opensearch-dashboards', 'normal'),
      embedding: component('embedding', 'normal'),
      llm: component('llm', 'normal'),
    }),
  /** 未知の `reason`(一般的な文言で出す。B 8.1) */
  unknownReason: () =>
    build({
      crawler: {
        ...component('crawler', 'abnormal'),
        reason: 'brand_new_reason' as ComponentStatus['reason'],
      },
    }),
}
