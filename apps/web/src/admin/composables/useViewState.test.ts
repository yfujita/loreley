import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { ref, type Ref } from 'vue'

import { getSourceOptions, isValidPathId } from '@/admin/api'
import { useQuery } from '@tanstack/vue-query'

import {
  apiErrorResponse,
  jsonResponse,
  networkErrorResponse,
  nginxHtmlResponse,
} from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { sourceList } from '../../../tests/support/fixtures/sources'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { useSourceDetailQuery, useSourcesListQuery } from '../queries/sources'
import { useViewState, type QueryStateSource } from './useViewState'

const stub = useFetchStub()
const UPDATED_AT = 1_700_000_000_000

/** `useQuery` の戻り値のうち、状態の決定に使う部分を手で作る(組み合わせを網羅するため)。 */
function fakeQuery<T>(
  state: Partial<{ [K in keyof QueryStateSource<T>]: QueryStateSource<T>[K]['value'] }> = {},
) {
  const refs = {
    data: ref(undefined) as Ref<T | undefined>,
    error: ref<unknown>(null),
    isLoading: ref(false),
    isFetching: ref(false),
    isLoadingError: ref(false),
    isRefetchError: ref(false),
    dataUpdatedAt: ref(0),
  }
  for (const [key, value] of Object.entries(state)) {
    ;(refs as Record<string, Ref<unknown>>)[key]!.value = value
  }
  return refs satisfies QueryStateSource<T>
}

describe('useViewState(E 6.2・F 3.7)', () => {
  it('取得中・データなし → loading', async () => {
    const query = fakeQuery({ isLoading: true, isFetching: true })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value.kind).toBe('loading')
  })

  it('データあり → ready(最終更新の時刻つき)', async () => {
    const query = fakeQuery({ data: { items: [1] }, dataUpdatedAt: UPDATED_AT })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({
      kind: 'ready',
      updatedAt: UPDATED_AT,
      isRefreshing: false,
    })
  })

  it('isEmpty が true → empty。isEmpty を渡さなければ 0 件の状態を持たない', async () => {
    const query = fakeQuery({ data: { items: [] as number[] }, dataUpdatedAt: UPDATED_AT })
    const withEmpty = await runComposable(() =>
      useViewState(query, { isEmpty: (data) => data.items.length === 0 }),
    )
    const withoutEmpty = await runComposable(() => useViewState(query))

    expect(withEmpty.result.value.kind).toBe('empty')
    expect(withoutEmpty.result.value.kind).toBe('ready')
  })

  it('再取得中(データあり・取得中)→ ready+isRefreshing', async () => {
    const query = fakeQuery({ data: {}, isFetching: true, dataUpdatedAt: UPDATED_AT })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({ kind: 'ready', isRefreshing: true })
  })

  it('503 unavailable(データなし)→ error(再試行できる・想定外ではないので診断なし)', async () => {
    const query = fakeQuery({
      isLoadingError: true,
      error: {
        kind: 'api',
        status: 503,
        code: 'unavailable',
        retryable: true,
        outcomeUnknown: false,
      },
    })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({ kind: 'error', canRetry: true, diagnostic: null })
  })

  it('再取得の失敗(前回データあり)→ stale(前回の更新時刻を残す)', async () => {
    const query = fakeQuery({
      data: {},
      dataUpdatedAt: UPDATED_AT,
      isRefetchError: true,
      error: { kind: 'timeout' },
    })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({ kind: 'stale', canRetry: true, updatedAt: UPDATED_AT })
  })

  it.each(['source_config_not_found', 'job_not_found', 'invalid_request', 'not_found'])(
    '%s → notfound(データなし)',
    async (code) => {
      const query = fakeQuery({
        isLoadingError: true,
        error: { kind: 'api', status: 404, code, retryable: false, outcomeUnknown: false },
      })
      const { result } = await runComposable(() => useViewState(query))

      expect(result.value).toMatchObject({ kind: 'notfound', canRetry: false })
    },
  )

  it('404 は前回データがあっても、stale ではなく notfound(消えたリソースを「最新ではない」と読ませない)', async () => {
    const query = fakeQuery({
      data: {},
      dataUpdatedAt: UPDATED_AT,
      isRefetchError: true,
      error: {
        kind: 'api',
        status: 404,
        code: 'source_config_not_found',
        retryable: false,
        outcomeUnknown: false,
      },
    })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value.kind).toBe('notfound')
  })

  it('invalidPathId(パス値の検証が偽)→ API を呼ばず notfound', async () => {
    const invalid = ref(false)
    const query = fakeQuery()
    const { result } = await runComposable(() => useViewState(query, { invalidPathId: invalid }))
    expect(result.value.kind).toBe('empty')

    invalid.value = true

    expect(result.value.kind).toBe('notfound')
  })

  it('想定外のエラー(internal_error)→ error+診断(code と HTTP ステータス。message は含めない)', async () => {
    const query = fakeQuery({
      isLoadingError: true,
      error: {
        kind: 'api',
        status: 500,
        code: 'internal_error',
        retryable: false,
        outcomeUnknown: false,
      },
    })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({
      kind: 'error',
      diagnostic: { code: 'internal_error', status: 500 },
    })
  })

  it('Nginx の HTML(invalid_response)→ error+診断(HTTP ステータスだけ。code なし)', async () => {
    const query = fakeQuery({
      isLoadingError: true,
      error: { kind: 'invalid_response', status: 502 },
    })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({
      kind: 'error',
      diagnostic: { code: null, status: 502 },
    })
  })

  it('ApiError でない値(生の本文・Error)は invalid_response として扱う(unknown として確認する)', async () => {
    const query = fakeQuery({
      isLoadingError: true,
      error: { error: { code: 'something', message: 'x', retryable: false } },
    })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value).toMatchObject({ kind: 'error', diagnostic: { code: null, status: null } })
  })

  it('error が null なら、エラーの記述を作らない', async () => {
    const query = fakeQuery({ data: {}, dataUpdatedAt: UPDATED_AT })
    const { result } = await runComposable(() => useViewState(query))

    expect(result.value.diagnostic).toBeNull()
  })
})

describe('実際の Query との組み合わせ', () => {
  it('一覧の取得: 取得中は loading → 成功したら ready。0 件なら empty', async () => {
    stub.respondWith(jsonResponse(sourceList.empty()))

    const { result } = await runComposable(() => {
      const query = useSourcesListQuery()
      return {
        query,
        viewState: useViewState(query, { isEmpty: (data) => data.items.length === 0 }),
      }
    })
    expect(result.viewState.value.kind).toBe('loading')
    await flushPromises()

    expect(result.viewState.value.kind).toBe('empty')
  })

  it('404 source_config_not_found → notfound', async () => {
    stub.respondWith(apiErrorResponse(404, 'source_config_not_found'))

    const { result } = await runComposable(() => {
      const query = useSourceDetailQuery('gone')
      return useViewState(query)
    })
    await flushPromises()

    expect(result.value.kind).toBe('notfound')
  })

  it('Nginx の HTML の 502(書き込みでなく読み取り)→ error+診断', async () => {
    stub.respondWith(nginxHtmlResponse(502))

    const { result } = await runComposable(() => useViewState(useSourceDetailQuery('a')))
    await flushPromises()

    expect(result.value).toMatchObject({
      kind: 'error',
      canRetry: true,
      diagnostic: { code: null, status: 502 },
    })
  })

  it('通信断 → error。取得に成功した後の通信断 → stale', async () => {
    const queryClient = createTestQueryClient()
    stub.respondWith(jsonResponse(sourceList.normal()))
    const { result } = await runComposable(
      () => {
        const query = useSourcesListQuery()
        return { query, viewState: useViewState(query) }
      },
      { queryClient },
    )
    await flushPromises()
    expect(result.viewState.value.kind).toBe('ready')

    stub.respondWith(networkErrorResponse())
    await result.query.refetch()
    await flushPromises()

    expect(result.viewState.value).toMatchObject({ kind: 'stale', canRetry: true })
    expect(result.viewState.value.updatedAt).toBeGreaterThan(0)
  })

  it('ID が不正で取得しない(enabled: false)ときは、invalidPathId で notfound にする', async () => {
    const { result } = await runComposable(() => {
      const query = useSourceDetailQuery('..')
      return useViewState(query, { invalidPathId: !isValidPathId('..') })
    })
    await flushPromises()

    expect(stub.requests).toEqual([])
    expect(result.value.kind).toBe('notfound')
  })

  it('生成の Options を直接使う Query でも、error は unknown として扱える(型は unknown)', async () => {
    stub.respondWith(apiErrorResponse(503, 'unavailable', { retryable: true }))

    const { result } = await runComposable(() => {
      const query = useQuery(getSourceOptions({ path: { source_id: 'a' } }))
      return useViewState(query)
    })
    await flushPromises()

    expect(result.value.kind).toBe('error')
  })
})
