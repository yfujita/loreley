// D1 の表示モデル(純関数。dashboard 3・4.3、E 5.7・F 3.5)。
// API の応答(`components[]` 8 件)から、概況バーとタイルの表示用の値を作る。
//
// **取得失敗時の降格**(dashboard 4.3。#25): 再取得に失敗して前回のデータを見せるとき(`stale`)は、
// 前回「正常」「異常」だったタイルのタグを「判定不能」に切り替え、前回の状態を文で添える。
// 前回の「正常」を表示し続けると現在の状態として読まれ、実際には落ちているコンポーネントを見逃させるため。
// 「未設定」は維持する(設定の有無は「正常」と断定する情報ではない)。前回の構成と同じ全タイルを出す。
import type { ComponentStatus, DashboardResponse } from '@/admin/api'
import type {
  ComponentTileModel,
  SummaryItem,
  SummaryModel,
  TileStatus,
} from '@/admin/components/dashboard-parts/types'
import { formatTimeOfDay, parseIsoDateTime } from '@/shared/lib/datetime'

import {
  dashboardComponents,
  type DashboardComponentDefinition,
} from '@/admin/features/dashboard/dashboardComponents'

export type HealthCounts = Record<TileStatus, number>

export type DashboardViewModel = {
  summary: SummaryModel
  required: readonly ComponentTileModel[]
  optional: readonly ComponentTileModel[]
  /** 表示している状態の件数(降格後)。手動の「更新」の結果の読み上げにも使う */
  counts: HealthCounts
}

export type DashboardViewModelOptions = {
  /** 再取得に失敗して、前回のデータを見せている(viewState の `stale`) */
  stale: boolean
  /** 前回の取得成功の時刻(`dataUpdatedAt`。ミリ秒)。降格したタイルの「前回の状態(時刻 時点)」に使う */
  lastSuccessAt: number | null
}

const STATUS_LABEL: Record<TileStatus, string> = {
  normal: '正常',
  abnormal: '異常',
  undetermined: '判定不能',
  not_configured: '未設定',
}

const TILE_STATUSES: readonly TileStatus[] = [
  'normal',
  'abnormal',
  'undetermined',
  'not_configured',
]

/** 未知の `state`(OpenAPI では列挙だが、実行時の値は信用しない)は、確認できていないものとして判定不能にする。 */
function toTileStatus(state: string): TileStatus {
  return TILE_STATUSES.find((known) => known === state) ?? 'undetermined'
}

/** 判定不能の理由(dashboard 3.3)。未知の理由は文を足さない。 */
function undeterminedReasonText(reason: ComponentStatus['reason']): string | null {
  switch (reason) {
    case 'timeout':
      return '時間内に応答がありませんでした'
    case 'connection_error':
      return '接続できませんでした'
    default:
      return null
  }
}

function checkedTime(checkedAt: string): string | null {
  const date = parseIsoDateTime(checkedAt)
  return date === null ? null : formatTimeOfDay(date)
}

function currentDetail(
  status: TileStatus,
  component: ComponentStatus | undefined,
): { detail: string; emphasized: boolean } {
  const time = component === undefined ? null : checkedTime(component.checked_at)
  switch (status) {
    case 'normal':
      return {
        detail: time === null ? '応答しています' : `応答しています · 確認 ${time}`,
        emphasized: false,
      }
    case 'abnormal': {
      const sentence = '応答がありません。コンテナが停止している可能性があります。'
      return { detail: time === null ? sentence : `${sentence}確認 ${time}`, emphasized: true }
    }
    case 'undetermined': {
      const reason = component === undefined ? null : undeterminedReasonText(component.reason)
      return {
        detail:
          reason === null
            ? '状態を取得できませんでした。'
            : `状態を取得できませんでした(${reason})。`,
        emphasized: true,
      }
    }
    case 'not_configured':
      return { detail: '設定されていません(任意)。', emphasized: false }
  }
}

function staleDetail(
  previous: TileStatus,
  lastSuccessAt: number | null,
): { detail: string; emphasized: boolean } {
  if (previous === 'not_configured') {
    return { detail: '前回取得時は、設定されていませんでした(任意)。', emphasized: false }
  }
  const time = lastSuccessAt === null ? null : formatTimeOfDay(new Date(lastSuccessAt))
  const label = STATUS_LABEL[previous]
  return {
    detail: time === null ? `前回の状態: ${label}` : `前回の状態: ${label}(${time} 時点)`,
    emphasized: false,
  }
}

function buildTile(
  definition: DashboardComponentDefinition,
  component: ComponentStatus | undefined,
  options: DashboardViewModelOptions,
): ComponentTileModel {
  // 応答にない(あり得ない)コンポーネントは、確認できていないものとして判定不能にする(出さないと、落ちているのを見逃す)。
  const received: TileStatus =
    component === undefined ? 'undetermined' : toTileStatus(component.state)
  const base = { id: definition.id, role: definition.role }

  if (!options.stale) {
    return {
      ...base,
      status: received,
      ...currentDetail(received, component),
      link: definition.link,
    }
  }
  // 降格: 未設定は維持。それ以外(正常・異常・判定不能)は判定不能にして、前回の状態を添える。導線は出さない。
  const status: TileStatus = received === 'not_configured' ? 'not_configured' : 'undetermined'
  return { ...base, status, ...staleDetail(received, options.lastSuccessAt), link: null }
}

function countStatuses(tiles: readonly ComponentTileModel[]): HealthCounts {
  const counts: HealthCounts = { normal: 0, abnormal: 0, undetermined: 0, not_configured: 0 }
  for (const tile of tiles) counts[tile.status] += 1
  return counts
}

function namesOf(tiles: readonly ComponentTileModel[], status: TileStatus): string[] {
  return tiles.filter((tile) => tile.status === status).map((tile) => tile.id)
}

/** 件数行。問題のあるものは名前を先頭に並べ(異常 → 判定不能)、続けて正常、0 件の異常・判定不能、未設定の順(dashboard 3.4)。 */
function buildSummaryItems(
  tiles: readonly ComponentTileModel[],
  counts: HealthCounts,
): SummaryItem[] {
  const items: SummaryItem[] = []
  if (counts.abnormal > 0) {
    items.push({ key: 'abnormal-names', label: '異常', names: namesOf(tiles, 'abnormal') })
  }
  if (counts.undetermined > 0) {
    items.push({
      key: 'undetermined-names',
      label: '判定不能',
      names: namesOf(tiles, 'undetermined'),
    })
  }
  items.push({ key: 'normal', label: '正常', value: String(counts.normal) })
  if (counts.abnormal === 0) items.push({ key: 'abnormal', label: '異常', value: '0' })
  if (counts.undetermined === 0) items.push({ key: 'undetermined', label: '判定不能', value: '0' })
  items.push({ key: 'not-configured', label: '未設定', value: String(counts.not_configured) })
  return items
}

function buildSummary(
  tiles: readonly ComponentTileModel[],
  counts: HealthCounts,
  stale: boolean,
): SummaryModel {
  if (stale) {
    // 前回の構成と同じ件数であることを示す(通常時の「正常 6 · 未設定 2」と合計が一致する)。
    return {
      tone: 'warning',
      title: '現在の状態を確認できません',
      items: [
        { key: 'undetermined', label: '判定不能', value: String(counts.undetermined) },
        {
          key: 'not-configured',
          label: '未設定',
          value: `${counts.not_configured}(前回取得時の設定)`,
        },
        { key: 'total', label: '前回の構成と同じ', value: `${tiles.length} 件` },
      ],
    }
  }
  const items = buildSummaryItems(tiles, counts)
  // 異常と判定不能の両方があるときは、異常を優先する。
  if (counts.abnormal > 0) {
    return { tone: 'error', title: `異常のコンポーネントがあります(${counts.abnormal} 件)`, items }
  }
  if (counts.undetermined > 0) {
    return {
      tone: 'warning',
      title: `状態を確認できないコンポーネントがあります(${counts.undetermined} 件)`,
      items,
    }
  }
  return { tone: 'success', title: 'すべてのコンポーネントが正常です', items }
}

export function buildDashboardViewModel(
  data: DashboardResponse,
  options: DashboardViewModelOptions,
): DashboardViewModel {
  const byId = new Map(data.components.map((component) => [component.id, component]))
  // 区分(必須・任意)は定義表の行から取る(tiles との添字の一致に頼らない)。
  const entries = dashboardComponents.map((definition) => ({
    group: definition.group,
    tile: buildTile(definition, byId.get(definition.id), options),
  }))
  const tiles = entries.map((entry) => entry.tile)
  const counts = countStatuses(tiles)
  const groupOf = (group: DashboardComponentDefinition['group']) =>
    entries.filter((entry) => entry.group === group).map((entry) => entry.tile)

  return {
    summary: buildSummary(tiles, counts, options.stale),
    required: groupOf('required'),
    optional: groupOf('optional'),
    counts,
  }
}
