// 列の省略(DS 4.3・7): 840〜1144px はコンテンツ幅が狭いので、画面ごとに列の優先順位を定め、低い順に隠す。
// 判断基準は「状態の判断に要る列を残し、設定値・補足は詳細へ」。共通の優先順位(高→低):
// 識別子 > 状態 > 日時(開始) > 件数 > 操作 > 種別・起動・周期・終了日時。
// どの幅でどこまで残すか(J1 はカード幅、S1・X1 は viewport)は画面ごとに決め、ここは「優先順位の表」と「絞り込み」だけを持つ。

/** 列の優先順位。小さいほど高く、隠すのは大きい方から。 */
export const COLUMN_PRIORITY = {
  id: 1,
  status: 2,
  date: 3,
  count: 4,
  action: 5,
  other: 6,
} as const

export type ColumnPriority = (typeof COLUMN_PRIORITY)[keyof typeof COLUMN_PRIORITY]

/** `priority` が `maxPriority` 以下の列だけを残す(元の並びを保つ)。優先順位のない列は常に残す。 */
export function filterColumnsByPriority<T extends { priority?: number }>(
  columns: readonly T[],
  maxPriority: number,
): T[] {
  return columns.filter((column) => column.priority === undefined || column.priority <= maxPriority)
}
