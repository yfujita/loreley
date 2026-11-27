import { describe, expect, it } from 'vitest'

import { keepPreviousWithinScope, rowActionsDisabled } from './placeholder'

type Key = readonly [
  'jobs',
  'list',
  { page: number; sort: string | null; status: string | null; size: number },
]
const key = (params: Partial<Key[2]> = {}): Key => [
  'jobs',
  'list',
  { page: 1, sort: null, status: null, size: 25, ...params },
]
// ページ・並べ替え以外が、同じスコープ。
const scopeOf = (k: Key) => ({ status: k[2].status, size: k[2].size })

const PREVIOUS = ['row-1']

function placeholderFor(next: Key, previous: Key | undefined) {
  const fn = keepPreviousWithinScope<string[], Key>(next, scopeOf)
  return fn(PREVIOUS, previous === undefined ? undefined : { queryKey: previous })
}

describe('keepPreviousWithinScope', () => {
  it('ページだけが変わるときは、前回のデータを保つ', () => {
    expect(placeholderFor(key({ page: 2 }), key({ page: 1 }))).toBe(PREVIOUS)
  })

  it('並べ替えだけが変わるときは、前回のデータを保つ', () => {
    expect(placeholderFor(key({ sort: 'queued_at' }), key({ sort: null }))).toBe(PREVIOUS)
  })

  it('ページと並べ替えの両方が変わっても、スコープが同じなら保つ', () => {
    expect(placeholderFor(key({ page: 3, sort: '-queued_at' }), key({ page: 1 }))).toBe(PREVIOUS)
  })

  it('絞り込みが変わったときは、前回の行を見せない(スケルトン)', () => {
    expect(placeholderFor(key({ status: 'failed' }), key({ status: null }))).toBeUndefined()
  })

  it('件数(size)が変わったときも、見せない', () => {
    expect(placeholderFor(key({ size: 50 }), key({ size: 25 }))).toBeUndefined()
  })

  it('前回のクエリがない(初回)ときは、データがない', () => {
    expect(placeholderFor(key(), undefined)).toBeUndefined()
  })
})

describe('rowActionsDisabled(J1 の取消など。前回データを表示している間は行の操作を無効にする)', () => {
  it('isPlaceholderData が true の間は無効、取得が終われば有効', () => {
    expect(rowActionsDisabled(true)).toBe(true)
    expect(rowActionsDisabled(false)).toBe(false)
  })
})
