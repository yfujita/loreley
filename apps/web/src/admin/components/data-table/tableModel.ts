// `VDataTable`・`VDataTableServer` の入出力と、画面に見せる形(`AdminColumn`・`AdminSort`)の変換(FMOD-U-4)。
// 両方の表が同じ形で使えるように、差(単一ソート・ソートの向きの名前・オプションの初期発火)をここと各表で吸収する。

export type AdminColumn = {
  /** 項目名(行の値のキー)。`item.<key>` のスロットで、セルの見た目を差し替えられる */
  key: string
  title: string
  /** 数値・操作列は `end`(右揃え。DS 4.3) */
  align?: 'start' | 'end'
  sortable?: boolean
  /** 列の優先順位(`COLUMN_PRIORITY`)。省略すると常に残す */
  priority?: number
  width?: number | string
}

/** 単一ソート(複数列の並べ替えは持たない)。null は並べ替えなし。 */
export type AdminSort = { key: string; order: 'asc' | 'desc' } | null

/** `VDataTable` の `sort-by` の 1 要素。 */
export type VuetifySortItem = { key: string; order?: boolean | 'asc' | 'desc' }

/**
 * 列の定義を Vuetify の `headers` にする。見出しの `<th>` には `scope="col"` を付ける(Vuetify は付けない。DS 8)。
 * 並べ替えできる列が今の並びの対象でないときは、`aria-sort="none"` も付ける
 * (Vuetify は並んでいる列にしか `aria-sort` を付けない。画面仕様は「並べ替えできる列は常に aria-sort」。admin-view 7.10)。
 */
export function toVuetifyHeaders(
  columns: readonly AdminColumn[],
  sort: AdminSort | undefined = null,
) {
  return columns.map((column) => {
    const sortable = column.sortable === true
    const isSorted = sort !== null && sort !== undefined && sort.key === column.key
    return {
      key: column.key,
      title: column.title,
      align: column.align,
      sortable,
      width: column.width,
      headerProps: { scope: 'col', ...(sortable && !isSorted && { 'aria-sort': 'none' }) },
    }
  })
}

export function toVuetifySortBy(sort: AdminSort | undefined): VuetifySortItem[] {
  return sort === null || sort === undefined ? [] : [{ key: sort.key, order: sort.order }]
}

/** Vuetify の `sortBy` から、単一ソートへ。複数が来ても先頭だけ使う(`multi-sort` を使わないので通常は 1 件以下)。 */
export function fromVuetifySortBy(sortBy: readonly VuetifySortItem[]): AdminSort {
  const first = sortBy[0]
  if (first === undefined) return null
  return { key: first.key, order: first.order === 'desc' || first.order === false ? 'desc' : 'asc' }
}
