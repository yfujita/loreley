// マトリクスの「いま表示している列の範囲」(opensearch 3.4)。
//
// ページの位置は、番号ではなく「表示中の先頭のインデックスの名前」で覚える。
// 更新(再取得)や幅の変化(列数の変化)の後も、その先頭のインデックスを含むページを保つため。
// そのインデックスがなくなっていれば、最終ページに丸める。

export type PageWindow = {
  /** 先頭の列の位置(0 起点) */
  firstIndex: number
  /** 1 起点 */
  page: number
  pageCount: number
}

export function resolvePageWindow(options: {
  names: readonly string[]
  perPage: number
  /** 表示中の先頭のインデックス名。null は 1 ページ目 */
  firstName: string | null
}): PageWindow {
  const { names, perPage, firstName } = options
  const pageCount = Math.max(1, Math.ceil(names.length / perPage))
  if (firstName === null) return { firstIndex: 0, page: 1, pageCount }

  const position = names.indexOf(firstName)
  const page = position < 0 ? pageCount : Math.floor(position / perPage) + 1
  return { firstIndex: (page - 1) * perPage, page, pageCount }
}
