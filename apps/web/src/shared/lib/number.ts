// 数値の表記(DS 4.9): 3 桁区切り。値がないときの「—」は呼び出し側が表示と合わせて決める。

const INTEGER_FORMAT = new Intl.NumberFormat('ja-JP')

/** 件数を 3 桁区切りにする(例 1284 → "1,284")。 */
export function formatCount(value: number): string {
  return INTEGER_FORMAT.format(value)
}

/** 値がない(null)ときの表記。件数の「—」は「未取得」、「0」は 0 件(DS 4.9)。 */
export const EMPTY_VALUE_MARK = '—'

/** 件数を 3 桁区切りにする。null は「—」。 */
export function formatCountOrDash(value: number | null | undefined): string {
  return value === null || value === undefined ? EMPTY_VALUE_MARK : formatCount(value)
}
