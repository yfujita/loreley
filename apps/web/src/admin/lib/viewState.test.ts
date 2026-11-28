import { describe, expect, it } from 'vitest'

import {
  READY_VIEW_STATE,
  resolveViewState,
  type DescribedReadError,
  type ViewStateInput,
} from './viewState'

const DIAGNOSTIC = { code: 'internal_error', status: 500 }

const UPDATED_AT = 1_700_000_000_000

function input(overrides: Partial<ViewStateInput> = {}): ViewStateInput {
  return {
    isLoading: false,
    isFetching: false,
    hasData: true,
    isEmpty: false,
    isLoadingError: false,
    isRefetchError: false,
    dataUpdatedAt: UPDATED_AT,
    error: null,
    ...overrides,
  }
}

function error(overrides: Partial<DescribedReadError> = {}): DescribedReadError {
  return {
    notFound: false,
    retryable: true,
    unexpected: false,
    diagnostic: DIAGNOSTIC,
    ...overrides,
  }
}

describe('resolveViewState(E 6.2 の写像)', () => {
  it('初回の読み込み中(データなしで取得中)→ loading', () => {
    expect(
      resolveViewState(
        input({ isLoading: true, isFetching: true, hasData: false, dataUpdatedAt: 0 }),
      ),
    ).toEqual({
      kind: 'loading',
      isRefreshing: false,
      updatedAt: null,
      canRetry: false,
      diagnostic: null,
    })
  })

  it('再取得中(データあり・取得中)→ ready のまま、進行バー(isRefreshing)を出す。データは消さない', () => {
    expect(resolveViewState(input({ isFetching: true }))).toEqual({
      kind: 'ready',
      isRefreshing: true,
      updatedAt: UPDATED_AT,
      canRetry: false,
      diagnostic: null,
    })
  })

  it('取得済み・取得中でない → ready(最終更新(成功)時刻つき)', () => {
    expect(resolveViewState(input())).toMatchObject({
      kind: 'ready',
      isRefreshing: false,
      updatedAt: UPDATED_AT,
    })
  })

  it('成功・0 件 → empty', () => {
    expect(resolveViewState(input({ isEmpty: true }))).toMatchObject({ kind: 'empty' })
  })

  it('エラー(データなし。isLoadingError)→ error。再試行できる', () => {
    expect(
      resolveViewState(
        input({ isLoadingError: true, hasData: false, dataUpdatedAt: 0, error: error() }),
      ),
    ).toMatchObject({ kind: 'error', canRetry: true, updatedAt: null })
  })

  it('古いデータ(再取得に失敗・前回データあり。isRefetchError)→ stale。前回のデータの時刻を残す', () => {
    expect(resolveViewState(input({ isRefetchError: true, error: error() }))).toMatchObject({
      kind: 'stale',
      canRetry: true,
      updatedAt: UPDATED_AT,
    })
  })

  it('見つかりません(データなし)→ notfound。再試行を出さない', () => {
    expect(
      resolveViewState(
        input({
          isLoadingError: true,
          hasData: false,
          dataUpdatedAt: 0,
          error: error({ notFound: true, retryable: false }),
        }),
      ),
    ).toMatchObject({ kind: 'notfound', canRetry: false })
  })

  it('見つかりません(前回データあり)→ stale にせず notfound に切り替える(消えたリソースを「最新ではない」と読ませない)', () => {
    expect(
      resolveViewState(
        input({ isRefetchError: true, error: error({ notFound: true, retryable: false }) }),
      ),
    ).toMatchObject({ kind: 'notfound', canRetry: false, isRefreshing: false })
  })

  it('パスの ID が不正(API を呼ばない)→ notfound', () => {
    expect(
      resolveViewState(input({ hasData: false, dataUpdatedAt: 0, invalidPathId: true })),
    ).toMatchObject({ kind: 'notfound', canRetry: false })
  })

  it('取得していない(enabled: false。データも取得中もエラーもない)→ 空として扱う(loading にしない)', () => {
    expect(
      resolveViewState(input({ hasData: false, dataUpdatedAt: 0, isLoading: false })),
    ).toMatchObject({ kind: 'empty', isRefreshing: false, updatedAt: null })
  })

  it('想定外のエラーだけ、診断(code と HTTP ステータス)を持つ', () => {
    expect(
      resolveViewState(
        input({
          isLoadingError: true,
          hasData: false,
          dataUpdatedAt: 0,
          error: error({ unexpected: true }),
        }),
      ).diagnostic,
    ).toEqual(DIAGNOSTIC)
    expect(
      resolveViewState(
        input({ isLoadingError: true, hasData: false, dataUpdatedAt: 0, error: error() }),
      ).diagnostic,
    ).toBeNull()
  })

  it('再試行できないエラー(retryable=false)は canRetry=false', () => {
    expect(
      resolveViewState(
        input({
          isLoadingError: true,
          hasData: false,
          dataUpdatedAt: 0,
          error: error({ retryable: false }),
        }),
      ).canRetry,
    ).toBe(false)
  })

  it('placeholderData で前回のデータを見せている間は、ready+isRefreshing(スケルトンにしない)', () => {
    expect(resolveViewState(input({ isFetching: true, isLoading: false }))).toMatchObject({
      kind: 'ready',
      isRefreshing: true,
    })
  })

  it('dataUpdatedAt が 0(未取得)のときは updatedAt を null にする', () => {
    expect(resolveViewState(input({ dataUpdatedAt: 0 })).updatedAt).toBeNull()
  })
})

describe('READY_VIEW_STATE', () => {
  it('取得済み・エラーなしの入力を resolveViewState に通した結果と同じ(偽の入力で ready を作らない)', () => {
    const resolved = resolveViewState({
      isLoading: false,
      isFetching: false,
      hasData: true,
      isEmpty: false,
      isLoadingError: false,
      isRefetchError: false,
      dataUpdatedAt: 0,
      error: null,
    })

    expect(READY_VIEW_STATE).toEqual(resolved)
    expect(READY_VIEW_STATE.kind).toBe('ready')
  })
})
