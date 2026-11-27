import { describe, expect, it } from 'vitest'

import { keys } from './keys'
import { documentsScopeOf, jobsScopeOf, type DocumentsQuery, type JobsQuery } from './params'
import { keepPreviousWithinScope, rowActionsDisabled } from './placeholder'

const PREVIOUS = ['row-1']

const jobsQuery = (overrides: Partial<JobsQuery> = {}): JobsQuery => ({
  page: 1,
  itemsPerPage: 25,
  sort: null,
  sourceId: null,
  status: null,
  ...overrides,
})

const documentsQuery = (overrides: Partial<DocumentsQuery> = {}): DocumentsQuery => ({
  tab: 'skipped',
  page: 1,
  itemsPerPage: 25,
  sort: null,
  ...overrides,
})

// 実装が使う key factory と scopeOf(params.ts)を、そのまま通す。
function jobsPlaceholder(next: Partial<JobsQuery>, previous: Partial<JobsQuery> | undefined) {
  const nextKey = keys.jobs.list(jobsQuery(next))
  const fn = keepPreviousWithinScope<string[], typeof nextKey>(nextKey, jobsScopeOf)
  return fn(
    PREVIOUS,
    previous === undefined ? undefined : { queryKey: keys.jobs.list(jobsQuery(previous)) },
  )
}

function documentsPlaceholder(
  next: { source: string | null; query: Partial<DocumentsQuery> },
  previous: { source: string | null; query: Partial<DocumentsQuery> } | undefined,
) {
  const nextKey = keys.documents.list(next.source, documentsQuery(next.query))
  const fn = keepPreviousWithinScope<string[], typeof nextKey>(nextKey, documentsScopeOf)
  return fn(
    PREVIOUS,
    previous === undefined
      ? undefined
      : { queryKey: keys.documents.list(previous.source, documentsQuery(previous.query)) },
  )
}

describe('keepPreviousWithinScope(J1。実際の scopeOf)', () => {
  it('ページだけが変わるときは、前回のデータを保つ', () => {
    expect(jobsPlaceholder({ page: 2 }, { page: 1 })).toBe(PREVIOUS)
  })

  it('並べ替えだけが変わるときは、前回のデータを保つ', () => {
    expect(jobsPlaceholder({ sort: 'queued_at' }, { sort: null })).toBe(PREVIOUS)
  })

  it('ページと並べ替えの両方が変わっても、スコープが同じなら保つ', () => {
    expect(jobsPlaceholder({ page: 3, sort: '-queued_at' }, { page: 1 })).toBe(PREVIOUS)
  })

  it('状態の絞り込みが変わったときは、前回の行を見せない(スケルトン)', () => {
    expect(jobsPlaceholder({ status: 'failed' }, { status: null })).toBeUndefined()
  })

  it('データソースの絞り込みが変わったときは、前回の行を見せない', () => {
    expect(jobsPlaceholder({ sourceId: 'b' }, { sourceId: 'a' })).toBeUndefined()
    expect(jobsPlaceholder({ sourceId: null }, { sourceId: 'a' })).toBeUndefined()
    expect(jobsPlaceholder({ sourceId: 'a' }, { sourceId: null })).toBeUndefined()
  })

  it('件数(size)が変わったときも、見せない', () => {
    expect(jobsPlaceholder({ itemsPerPage: 50 }, { itemsPerPage: 25 })).toBeUndefined()
  })

  it('前回のクエリがない(初回)ときは、データがない', () => {
    expect(jobsPlaceholder({}, undefined)).toBeUndefined()
  })
})

describe('keepPreviousWithinScope(X1。実際の scopeOf)', () => {
  const base = { source: 'demo', query: {} }

  it('ページ・並べ替えが変わるときは保つ', () => {
    expect(documentsPlaceholder({ source: 'demo', query: { page: 2 } }, base)).toBe(PREVIOUS)
    expect(
      documentsPlaceholder({ source: 'demo', query: { sort: '-last_skipped_at' } }, base),
    ).toBe(PREVIOUS)
  })

  it('タブが変わったときは見せない', () => {
    expect(
      documentsPlaceholder({ source: 'demo', query: { tab: 'oversize' } }, base),
    ).toBeUndefined()
  })

  it('データソースが変わったときは見せない', () => {
    expect(documentsPlaceholder({ source: 'other', query: {} }, base)).toBeUndefined()
  })

  it('件数が変わったときは見せない', () => {
    expect(
      documentsPlaceholder({ source: 'demo', query: { itemsPerPage: 100 } }, base),
    ).toBeUndefined()
  })
})

describe('rowActionsDisabled(J1 の取消など。前回データを表示している間は行の操作を無効にする)', () => {
  it('isPlaceholderData が true の間は無効、取得が終われば有効', () => {
    expect(rowActionsDisabled(true)).toBe(true)
    expect(rowActionsDisabled(false)).toBe(false)
  })
})
