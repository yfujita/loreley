import { describe, expect, it } from 'vitest'

import { resolvePageWindow } from './pageWindow'

const NAMES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']

describe('resolvePageWindow(先頭の列の名前でページを保つ)', () => {
  it('先頭の名前が null なら 1 ページ目', () => {
    expect(resolvePageWindow({ names: NAMES, perPage: 3, firstName: null })).toEqual({
      firstIndex: 0,
      page: 1,
      pageCount: 3,
    })
  })

  it('先頭の名前を含むページになる(先頭がページの途中でも、そのページの先頭から)', () => {
    expect(resolvePageWindow({ names: NAMES, perPage: 3, firstName: 'd' })).toEqual({
      firstIndex: 3,
      page: 2,
      pageCount: 3,
    })
    expect(resolvePageWindow({ names: NAMES, perPage: 3, firstName: 'e' })).toMatchObject({
      firstIndex: 3,
      page: 2,
    })
  })

  it('幅の変化で列数が変わったら、先頭の名前を含むページにする', () => {
    // 3 列のとき 'd' は 2 ページ目の先頭。5 列にすると 'd' は 1 ページ目(0〜4)
    expect(resolvePageWindow({ names: NAMES, perPage: 5, firstName: 'd' })).toEqual({
      firstIndex: 0,
      page: 1,
      pageCount: 2,
    })
  })

  it('先頭のインデックスがなくなっていれば、最終ページに丸める', () => {
    expect(resolvePageWindow({ names: NAMES, perPage: 3, firstName: 'gone' })).toEqual({
      firstIndex: 6,
      page: 3,
      pageCount: 3,
    })
  })

  it('列が 1 ページに収まるなら 1 ページだけ。0 件でも 1 ページ(0 ページにしない)', () => {
    expect(resolvePageWindow({ names: ['a', 'b'], perPage: 7, firstName: 'b' })).toEqual({
      firstIndex: 0,
      page: 1,
      pageCount: 1,
    })
    expect(resolvePageWindow({ names: [], perPage: 3, firstName: null })).toEqual({
      firstIndex: 0,
      page: 1,
      pageCount: 1,
    })
    expect(resolvePageWindow({ names: [], perPage: 3, firstName: 'x' }).page).toBe(1)
  })

  it('ちょうど割り切れる件数(8 件を 4 列)は 2 ページ', () => {
    expect(resolvePageWindow({ names: NAMES, perPage: 4, firstName: 'h' })).toEqual({
      firstIndex: 4,
      page: 2,
      pageCount: 2,
    })
  })
})
