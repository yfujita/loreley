import { describe, expect, it } from 'vitest'

import type { ClusterStatus } from '@/admin/lib/clusterValues'

import {
  canonicalStates,
  conditionKey,
  describeCondition,
  filterIndices,
  isFiltering,
  toCondition,
} from './indexFilter'

const INDICES = [
  { name: 'demo-docs-000003', status: 'yellow' },
  { name: 'demo-logs-2026.11.15', status: 'red' },
  { name: 'Demo-Logs-2026.11.01', status: 'green' },
  { name: 'demo-store-jobs', status: 'green' },
  { name: '.demo-sys-tasks', status: 'purple' },
  { name: 'closed-index', status: null },
]
const names = (list: readonly { name: string }[]) => list.map((entry) => entry.name)
const none = { query: '', states: [] } as const

describe('toCondition(正規化)', () => {
  it('名前は前後の空白を除く。空白だけなら条件なし', () => {
    expect(toCondition({ q: '  logs ', states: [] }).query).toBe('logs')
    expect(toCondition({ q: '   ', states: [] }).query).toBe('')
    expect(isFiltering(toCondition({ q: '   ', states: [] }))).toBe(false)
  })

  it('状態は 3 つとも選択すると「すべて」と同じ=条件なしに正規化する(チェックの表示は呼び出し側が保つ)', () => {
    expect(toCondition({ q: '', states: ['green', 'yellow', 'red'] }).states).toEqual([])
    expect(isFiltering(toCondition({ q: '', states: ['red', 'yellow', 'green'] }))).toBe(false)
  })

  it('状態は red → yellow → green の順・重複なしにそろえる', () => {
    expect(toCondition({ q: '', states: ['green', 'red', 'green'] }).states).toEqual([
      'red',
      'green',
    ])
    expect(canonicalStates(['yellow', 'green', 'red'])).toEqual(['red', 'yellow', 'green'])
  })

  it('2 つ選んだときは条件あり', () => {
    expect(isFiltering(toCondition({ q: '', states: ['yellow', 'green'] }))).toBe(true)
  })
})

describe('filterIndices', () => {
  it('条件なしなら、全件を API の並びのまま返す', () => {
    expect(names(filterIndices(INDICES, none))).toEqual(names(INDICES))
  })

  it('名前: 部分一致で、大文字小文字を区別しない', () => {
    expect(names(filterIndices(INDICES, { query: 'LOGS', states: [] }))).toEqual([
      'demo-logs-2026.11.15',
      'Demo-Logs-2026.11.01',
    ])
    expect(names(filterIndices(INDICES, { query: 'store', states: [] }))).toEqual([
      'demo-store-jobs',
    ])
  })

  it('名前は正規表現ではない(`.` や `*` はそのままの文字)', () => {
    expect(names(filterIndices(INDICES, { query: '.demo', states: [] }))).toEqual([
      '.demo-sys-tasks',
    ])
    expect(names(filterIndices(INDICES, { query: 'demo.*', states: [] }))).toEqual([])
  })

  it('状態: 選んだ状態のいずれか(OR)', () => {
    expect(names(filterIndices(INDICES, { query: '', states: ['yellow', 'red'] }))).toEqual([
      'demo-docs-000003',
      'demo-logs-2026.11.15',
    ])
  })

  it('状態を選ぶと、未知の状態値・状態が null のインデックスは除外する', () => {
    expect(names(filterIndices(INDICES, { query: '', states: ['green'] }))).toEqual([
      'Demo-Logs-2026.11.01',
      'demo-store-jobs',
    ])
  })

  it('何も選ばなければ、未知の状態値・null も表示する', () => {
    expect(names(filterIndices(INDICES, none))).toContain('.demo-sys-tasks')
    expect(names(filterIndices(INDICES, none))).toContain('closed-index')
  })

  it('名前と状態は AND', () => {
    expect(
      names(filterIndices(INDICES, { query: 'logs', states: ['green'] as ClusterStatus[] })),
    ).toEqual(['Demo-Logs-2026.11.01'])
  })

  it('一致なしは空', () => {
    expect(filterIndices(INDICES, { query: 'zzz', states: [] })).toEqual([])
  })
})

describe('describeCondition / conditionKey', () => {
  it('名前・状態の文(「名前に「logs」を含む、状態が yellow または green」)', () => {
    expect(describeCondition({ query: 'logs', states: ['yellow', 'green'] })).toBe(
      '名前に「logs」を含む、状態が yellow または green',
    )
    expect(describeCondition({ query: 'logs', states: [] })).toBe('名前に「logs」を含む')
    expect(describeCondition({ query: '', states: ['red'] })).toBe('状態が red')
  })

  it('同じ条件(正規化後)なら同じ key。違えば違う key(1 ページ目に戻す判定)', () => {
    const base = toCondition({ q: 'logs', states: ['yellow'] })

    expect(conditionKey(toCondition({ q: ' logs ', states: ['yellow'] }))).toBe(conditionKey(base))
    expect(conditionKey(toCondition({ q: '', states: [] }))).toBe(
      conditionKey(toCondition({ q: '', states: ['red', 'yellow', 'green'] })),
    )
    expect(conditionKey(toCondition({ q: 'log', states: ['yellow'] }))).not.toBe(conditionKey(base))
    expect(conditionKey(toCondition({ q: 'logs', states: ['red'] }))).not.toBe(conditionKey(base))
  })
})
