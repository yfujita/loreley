// 操作の出し分けの型(DS 4.13・F 3.5)。`PageActions` が描き、画面ごとの表(`sourceActions.ts`・`jobActions.ts`)が返す。
//
// ルール(DS 4.13): (1) 画面の主操作は 1 つ。(2) 今は実行できない操作は**出さない**(実行の見込みがない)か、
// **無効にして理由を近くに出す**(状況が変われば実行できる)。(3) 操作の水準は DS 4.8 の段階で決める。

/** 操作の水準(DS 4.8。admin-view 6 章の割当)。 */
export type ActionLevel =
  // 通常: ダイアログを出さない
  | 'normal'
  // 要確認・標準
  | 'confirm'
  // 要確認・警告つき
  | 'confirm-warning'
  // 要入力確認
  | 'confirm-typed'

export type ActionSpec = {
  id: string
  label: string
  /** false は出さない */
  visible: boolean
  /** 無効にして理由を近くに出すときの理由。null なら有効 */
  disabledReason: string | null
  level: ActionLevel
}
