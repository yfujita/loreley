// テスト用の `ViewState`(状態ごと)。本番の `resolveViewState` を通して作り、型・形を本物と同じにする。
import { resolveViewState, type ViewState } from '@/admin/lib/viewState'

const BASE = {
  isLoading: false,
  isFetching: false,
  hasData: true,
  isEmpty: false,
  isLoadingError: false,
  isRefetchError: false,
  dataUpdatedAt: 1_732_000_000_000,
  error: null,
} as const

const describedError = (
  overrides: Partial<NonNullable<Parameters<typeof resolveViewState>[0]['error']>> = {},
) => ({
  notFound: false,
  retryable: true,
  unexpected: false,
  diagnostic: { code: null, status: null },
  ...overrides,
})

export const viewStates = {
  ready: (): ViewState => resolveViewState(BASE),
  refreshing: (): ViewState => resolveViewState({ ...BASE, isFetching: true }),
  loading: (): ViewState =>
    resolveViewState({
      ...BASE,
      isLoading: true,
      isFetching: true,
      hasData: false,
      dataUpdatedAt: 0,
    }),
  empty: (): ViewState => resolveViewState({ ...BASE, isEmpty: true }),
  error: (error = describedError()): ViewState =>
    resolveViewState({ ...BASE, hasData: false, dataUpdatedAt: 0, isLoadingError: true, error }),
  stale: (error = describedError()): ViewState =>
    resolveViewState({ ...BASE, isRefetchError: true, error }),
  notfound: (): ViewState =>
    resolveViewState({
      ...BASE,
      hasData: false,
      dataUpdatedAt: 0,
      isLoadingError: true,
      error: describedError({ notFound: true, retryable: false }),
    }),
  unexpectedError: (): ViewState =>
    viewStates.error(
      describedError({ unexpected: true, diagnostic: { code: 'internal_error', status: 500 } }),
    ),
}
