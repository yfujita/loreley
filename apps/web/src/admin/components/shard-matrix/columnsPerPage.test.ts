import { describe, expect, it } from 'vitest'

import { columnsPerPage, columnWidth, MIN_COLUMN_WIDTH_PX, rowHeaderWidth } from './columnsPerPage'

describe('columnsPerPage(opensearch 3.4 の検算表。W はカードの内容領域の幅)', () => {
  // viewport → W(カード幅 − 枠 2px)→ 列数。仕様の表のとおり
  it.each([
    [1280, 982, false, 7],
    [1145, 847, false, 6],
    [1024, 742, false, 5],
    [840, 558, false, 3],
    [768, 734, false, 5],
    [375, 341, true, 2],
    [320, 286, true, 1],
  ])('viewport %ipx(W=%ipx・narrow=%s)は %i 列', (_viewport, width, narrow, expected) => {
    expect(columnsPerPage(width, narrow)).toBe(expected)
  })

  it('上限はない(広い幅では列が増える)', () => {
    expect(columnsPerPage(2000, false)).toBe(16)
  })

  it('境界: (W − H) がちょうど 112 の倍数なら、その列数。1px 足りなければ 1 列減る', () => {
    const H = rowHeaderWidth(false)
    expect(columnsPerPage(H + MIN_COLUMN_WIDTH_PX * 3, false)).toBe(3)
    expect(columnsPerPage(H + MIN_COLUMN_WIDTH_PX * 3 - 1, false)).toBe(2)
  })

  it('幅が足りなくても、最低 1 列(0・未計測・負にならない)', () => {
    expect(columnsPerPage(0, false)).toBe(1)
    expect(columnsPerPage(100, true)).toBe(1)
  })

  it('H の切替(152 → 112)だけが結果を変える W: W=590 は wide なら 3 列、narrow なら 4 列', () => {
    // (590 − 152) ÷ 112 = 3.91、(590 − 112) ÷ 112 = 4.27
    expect(columnsPerPage(590, false)).toBe(3)
    expect(columnsPerPage(590, true)).toBe(4)
  })

  it('行見出しの幅 H: viewport 600px 以上は 152px、600px 未満は 112px', () => {
    expect(rowHeaderWidth(false)).toBe(152)
    expect(rowHeaderWidth(true)).toBe(112)
  })
})

describe('columnWidth', () => {
  it('ページングするとき(列が列数を超える)は、全ページ同じ幅 floor((W − H) ÷ 列数)', () => {
    expect(columnWidth({ width: 982, narrow: false, perPage: 7, columnCount: 25 })).toBe(118)
  })

  it('ページングしないときは、余りを列で分ける。上限は 200px', () => {
    expect(columnWidth({ width: 982, narrow: false, perPage: 7, columnCount: 3 })).toBe(200)
    expect(columnWidth({ width: 982, narrow: false, perPage: 7, columnCount: 7 })).toBe(118)
  })

  it('列がちょうど 1 ページ分なら、ページングしない側(余りを分ける)', () => {
    expect(columnWidth({ width: 560, narrow: false, perPage: 3, columnCount: 3 })).toBe(136)
  })

  it('幅が未計測(0)でも負にならない', () => {
    expect(columnWidth({ width: 0, narrow: false, perPage: 1, columnCount: 5 })).toBe(0)
  })
})
