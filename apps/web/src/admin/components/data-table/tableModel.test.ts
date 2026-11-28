import { describe, expect, it } from 'vitest'

import {
  fromVuetifySortBy,
  toVuetifyHeaders,
  toVuetifySortBy,
  type AdminColumn,
} from './tableModel'

describe('toVuetifyHeaders', () => {
  it('列の定義を Vuetify の headers にする。sortable は明示した列だけ(既定は並べ替えなし)', () => {
    const columns: AdminColumn[] = [
      { key: 'source_id', title: 'データソース', sortable: true },
      { key: 'count', title: '登録文書数', align: 'end', width: 120, priority: 4 },
    ]

    expect(toVuetifyHeaders(columns, { key: 'source_id', order: 'asc' })).toEqual([
      {
        key: 'source_id',
        title: 'データソース',
        align: undefined,
        sortable: true,
        width: undefined,
        headerProps: { scope: 'col' },
      },
      {
        key: 'count',
        title: '登録文書数',
        align: 'end',
        sortable: false,
        width: 120,
        headerProps: { scope: 'col' },
      },
    ])
  })

  it('並べ替えできて今の並びの対象でない列に、aria-sort="none" を付ける(並んでいる列・並べ替えできない列には付けない)', () => {
    const columns: AdminColumn[] = [
      { key: 'a', title: 'A', sortable: true },
      { key: 'b', title: 'B', sortable: true },
      { key: 'c', title: 'C' },
    ]

    const headers = toVuetifyHeaders(columns, { key: 'a', order: 'asc' })

    expect(headers.map((header) => header.headerProps)).toEqual([
      { scope: 'col' },
      { scope: 'col', 'aria-sort': 'none' },
      { scope: 'col' },
    ])
  })
})

describe('単一ソートの変換', () => {
  it('AdminSort → Vuetify の sortBy(null は空)', () => {
    expect(toVuetifySortBy({ key: 'queued_at', order: 'desc' })).toEqual([
      { key: 'queued_at', order: 'desc' },
    ])
    expect(toVuetifySortBy(null)).toEqual([])
    expect(toVuetifySortBy(undefined)).toEqual([])
  })

  it('Vuetify の sortBy → AdminSort(空は null・先頭だけ使う)', () => {
    expect(fromVuetifySortBy([])).toBeNull()
    expect(fromVuetifySortBy([{ key: 'a', order: 'asc' }])).toEqual({ key: 'a', order: 'asc' })
    expect(fromVuetifySortBy([{ key: 'a', order: 'desc' }])).toEqual({ key: 'a', order: 'desc' })
    expect(
      fromVuetifySortBy([
        { key: 'a', order: 'desc' },
        { key: 'b', order: 'asc' },
      ]),
    ).toEqual({ key: 'a', order: 'desc' })
  })

  it('order が真偽値・省略の場合も、昇順・降順に正規化する(false=降順)', () => {
    expect(fromVuetifySortBy([{ key: 'a', order: false }])?.order).toBe('desc')
    expect(fromVuetifySortBy([{ key: 'a', order: true }])?.order).toBe('asc')
    expect(fromVuetifySortBy([{ key: 'a' }])?.order).toBe('asc')
  })
})
