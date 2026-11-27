// 1 ページの列数と列幅(DS 4.15・opensearch 3.4)。
//
// 列数 = `max(1, floor((W − H) ÷ 112))`(上限なし)。
// - W: マトリクスの領域(カードの枠を除く内容領域。表はカードの左右の端まで全幅)の幅
// - H: 行見出し列(ノード)の幅。viewport 幅 600px 以上は 152px、600px 未満は 112px
// - 112px: 列の最小幅(等幅 12px・600 の名前が 2〜3 行に折り返しても読め、2 つのチップと左右の余白 16px が 1 行に入る)
// 閾値ではなく式にするのは、カード幅が viewport・サイドバーの有無・画面の最大幅で変わるため(DS 4.3 の方針)。

export const MIN_COLUMN_WIDTH_PX = 112
const ROW_HEADER_WIDTH_WIDE_PX = 152
const ROW_HEADER_WIDTH_NARROW_PX = 112
/** ページングしない(1 ページに収まる)ときの列幅の上限 */
const MAX_COLUMN_WIDTH_PX = 200

/** 行見出し列の幅。`narrow` は viewport 幅 600px 未満(Vuetify の sm 未満)。 */
export function rowHeaderWidth(narrow: boolean): number {
  return narrow ? ROW_HEADER_WIDTH_NARROW_PX : ROW_HEADER_WIDTH_WIDE_PX
}

export function columnsPerPage(width: number, narrow: boolean): number {
  return Math.max(1, Math.floor((width - rowHeaderWidth(narrow)) / MIN_COLUMN_WIDTH_PX))
}

/**
 * 列幅(px)。ページングするときは全ページ同じ(最終ページの列が少なくても幅を変えず、右に余白を残す)。
 * しないときは、余った幅を列で分けて 200px を上限にする。
 */
export function columnWidth(options: {
  width: number
  narrow: boolean
  perPage: number
  columnCount: number
}): number {
  // 幅が未計測(0)のときも、負の幅にしない。
  const available = Math.max(0, options.width - rowHeaderWidth(options.narrow))
  if (options.columnCount > options.perPage) return Math.floor(available / options.perPage)
  return Math.min(MAX_COLUMN_WIDTH_PX, Math.floor(available / Math.max(1, options.columnCount)))
}
