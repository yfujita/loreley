// ステータスタグの対応表(DS 4.1。F 3.2)。状態は「色・形(アイコン)・文言」の 3 つで区別する(色だけにしない)。
// 値を足すときは、この表に行を足すだけでよい(`StatusTag.vue` は表を引くだけ)。
import {
  mdiAlertOutline,
  mdiCancel,
  mdiCheckCircleOutline,
  mdiClockOutline,
  mdiCloseOctagonOutline,
  mdiHelpCircleOutline,
  mdiLockOpenOutline,
  mdiLockOutline,
  mdiPlayCircleOutline,
  mdiTimerSand,
} from '@/shared/theme/icons'

/** 色の組。`*-container` は淡い面、`on-*-container` はその上の文字色(DS 2.1)。 */
export type StatusTone = 'secondary' | 'info' | 'success' | 'warning' | 'error'

export type StatusEntry = {
  tone: StatusTone
  /** 塗りなし(枠線のみ)。「未設定」「失敗(ロック解放済み)」など */
  outlined?: boolean
  /** `@mdi/js` のアイコン(SVG パス)。文言のないアイコンだけのタグは作らない */
  icon: string
  label: string
}

const CIRCLE_CHECK = mdiCheckCircleOutline
const OCTAGON = mdiCloseOctagonOutline

/** ジョブの状態(AF-8)。リース切れ・ロック解放済みは、保存上の状態ではなく、画面が導く表示用の値。 */
const job = {
  queued: { tone: 'secondary', icon: mdiClockOutline, label: '実行待ち' },
  running: { tone: 'info', icon: mdiPlayCircleOutline, label: '実行中' },
  succeeded: { tone: 'success', icon: CIRCLE_CHECK, label: '成功' },
  partially_succeeded: { tone: 'warning', icon: mdiAlertOutline, label: '一部成功' },
  failed: { tone: 'error', icon: OCTAGON, label: '失敗' },
  cancelled: { tone: 'secondary', icon: mdiCancel, label: '取消' },
  failed_lease_expired: { tone: 'error', icon: mdiLockOutline, label: '失敗(リース切れ)' },
  failed_lock_released: {
    tone: 'error',
    outlined: true,
    icon: mdiLockOpenOutline,
    label: '失敗(ロック解放済み)',
  },
} as const satisfies Record<string, StatusEntry>

/** データソースの状態。`active` はタグを出さない(「削除中」だけ)。 */
const source = {
  deleting: { tone: 'warning', icon: mdiTimerSand, label: '削除中' },
} as const satisfies Record<string, StatusEntry>

/** コンポーネントの死活(D1。AF-18)。 */
const health = {
  normal: { tone: 'success', icon: CIRCLE_CHECK, label: '正常' },
  abnormal: { tone: 'error', icon: OCTAGON, label: '異常' },
  not_configured: { tone: 'secondary', outlined: true, icon: mdiCancel, label: '未設定' },
  undetermined: { tone: 'warning', icon: mdiHelpCircleOutline, label: '判定不能' },
} as const satisfies Record<string, StatusEntry>

/** 削除結果(J2。AF-10)。 */
const deletion = {
  deleted: { tone: 'success', icon: CIRCLE_CHECK, label: '削除完了' },
  skipped_by_ratio: { tone: 'warning', icon: mdiAlertOutline, label: '削除なし(割合ルール)' },
  failed: { tone: 'error', icon: OCTAGON, label: '削除なし(失敗)' },
  validation_failed: { tone: 'error', icon: OCTAGON, label: '削除なし(検証エラー)' },
  discarded: { tone: 'secondary', icon: mdiCancel, label: '削除なし(破棄)' },
  running: { tone: 'info', icon: mdiPlayCircleOutline, label: '実行中' },
} as const satisfies Record<string, StatusEntry>

/** OpenSearch のクラスタの状態(O1。AF-17)。 */
const cluster = {
  green: { tone: 'success', icon: CIRCLE_CHECK, label: 'green(正常)' },
  yellow: { tone: 'warning', icon: mdiAlertOutline, label: 'yellow(注意)' },
  red: { tone: 'error', icon: OCTAGON, label: 'red(異常)' },
} as const satisfies Record<string, StatusEntry>

/** OpenSearch のインデックスの状態(O1 の列見出し)。色・アイコンはクラスタと同じで、文言だけ短い。 */
const index = {
  green: { tone: 'success', icon: CIRCLE_CHECK, label: 'green' },
  yellow: { tone: 'warning', icon: mdiAlertOutline, label: 'yellow' },
  red: { tone: 'error', icon: OCTAGON, label: 'red' },
} as const satisfies Record<string, StatusEntry>

export const statusMaps = { job, source, health, deletion, cluster, index } as const

export type StatusKind = keyof typeof statusMaps

/** `kind` と `value` の組が表にあれば行を返す。なければ null(未登録。`StatusTag` が中立表示にして警告する)。 */
export function findStatusEntry(kind: StatusKind, value: string): StatusEntry | null {
  const map: Readonly<Record<string, StatusEntry>> = statusMaps[kind]
  return Object.hasOwn(map, value) ? (map[value] ?? null) : null
}

// 同じ組で何度も警告しない(一覧の行ごと・コンポーネントのインスタンスごとに出さない)ので、モジュール内で覚える。
const warnedKeys = new Set<string>()

/** 未登録の値を、開発時にだけ警告する(OpenSearch の状態値のように、API が string で返す値は未知の値がありうる)。 */
export function warnUnregisteredStatus(kind: StatusKind, value: string): void {
  if (!import.meta.env.DEV) return
  const key = `${kind}:${value}`
  if (warnedKeys.has(key)) return
  warnedKeys.add(key)
  console.warn(
    `StatusTag: 未登録の状態です(kind=${kind}, value=${value})。shared/ui/statusMaps.ts に行を足してください。`,
  )
}
