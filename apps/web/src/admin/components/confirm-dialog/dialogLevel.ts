// 確認ダイアログの危険度と見た目の対応(DS 4.8・admin-view 6 章)。
//
// 水準: 通常(ダイアログなし)/ 要確認・標準 / 要確認・警告つき / 要入力確認(`ActionLevel`。`admin/lib/actions.ts`)。
// 色の規則(承認済み): 確認ダイアログが複数の指定を含む場合(強制削除と再書き込みの両方など)、上端の帯と実行ボタンの色は、
// 含まれる指定のうち最も重いものに合わせる(強制削除=赤 `error` / danger > 再書き込み・ロック解放=琥珀 `warning`)。
// 警告枠と確認チェックは指定ごとに置く(それは画面・ダイアログ側)。
import type { ActionLevel } from '@/admin/lib/actions'

/** ダイアログを出す水準(`normal` は出さない)。 */
export type DialogLevel = Exclude<ActionLevel, 'normal'>

/** 指定の重さ。`danger`(強制削除など)は `warning`(再書き込み・ロック解放)より重い。 */
export type Severity = 'danger' | 'warning'

export type DialogAppearance = {
  /** 上端 4px の帯の色。要確認・標準は帯なし */
  band: 'error' | 'warning' | null
  /** 実行ボタンの色(theme の色名) */
  executeColor: 'primary' | 'error' | 'warning'
  /** 誤って閉じないよう、Esc・背面クリックで閉じない(警告つき・要入力確認) */
  persistent: boolean
}

/** 含まれる指定のうち最も重いもの。指定がなければ null。 */
export function heaviestSeverity(severities: readonly Severity[]): Severity | null {
  if (severities.includes('danger')) return 'danger'
  if (severities.includes('warning')) return 'warning'
  return null
}

/**
 * 水準と指定から、帯・実行ボタンの色・閉じ方を決める。
 * 警告つきで指定がないとき(ロック解放など、指定を持たない警告つき)は、琥珀(warning)にする。
 */
export function resolveDialogAppearance(
  level: DialogLevel,
  severities: readonly Severity[] = [],
): DialogAppearance {
  switch (level) {
    case 'confirm':
      return { band: null, executeColor: 'primary', persistent: false }
    case 'confirm-typed':
      return { band: 'error', executeColor: 'error', persistent: true }
    case 'confirm-warning': {
      const heaviest = heaviestSeverity(severities) ?? 'warning'
      const color = heaviest === 'danger' ? 'error' : 'warning'
      return { band: color, executeColor: color, persistent: true }
    }
  }
}
