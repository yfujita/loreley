import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { apiErrorResponse, jsonResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { sourceDetails, sourceList } from '../../../tests/support/fixtures/sources'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { keys } from './keys'
import { useSourceDetailQuery, useSourceEditQuery, useSourcesListQuery } from './sources'

const stub = useFetchStub()

describe('useSourcesListQuery(EP-01)', () => {
  it('クエリを付けずに取得し、key は ["sources","list"]', async () => {
    stub.respondWith(jsonResponse(sourceList.normal()))
    const queryClient = createTestQueryClient()

    const { result } = await runComposable(() => useSourcesListQuery(), { queryClient })
    await flushPromises()

    expect(result.data.value).toEqual(sourceList.normal())
    expect(stub.requests[0]).toMatchObject({ pathname: '/api/admin/v1/sources', search: '' })
    expect(queryClient.getQueryState(keys.sources.list())?.status).toBe('success')
  })
})

describe('useSourceDetailQuery(EP-02。S2)', () => {
  it('ID を URL にエンコードして取得し、key は ["sources","detail",id]', async () => {
    stub.respondWith(jsonResponse(sourceDetails.normal()))
    const queryClient = createTestQueryClient()

    const { result } = await runComposable(() => useSourceDetailQuery('my.source'), { queryClient })
    await flushPromises()

    expect(result.data.value).toEqual(sourceDetails.normal())
    expect(stub.requests[0]?.pathname).toBe('/api/admin/v1/sources/my.source')
    expect(queryClient.getQueryState(keys.sources.detail('my.source'))?.status).toBe('success')
  })

  it.each(['.', '..', '', 'a\u0000b'])(
    'ID が %j のとき、API を呼ばない(enabled: false。「見つかりません」と同じ扱いは画面側)',
    async (id) => {
      stub.respondWith(jsonResponse(sourceDetails.normal()))

      const { result } = await runComposable(() => useSourceDetailQuery(id))
      await flushPromises()

      expect(stub.requests).toEqual([])
      expect(result.fetchStatus.value).toBe('idle')
      // 取得しなかった(request interceptor に任せて通ったのではない): 待機中のまま、エラーも取得中もない
      expect(result.status.value).toBe('pending')
      expect(result.error.value).toBeNull()
      expect(result.isLoading.value).toBe(false)
      expect(result.data.value).toBeUndefined()
    },
  )

  it('ID が変わったら、新しい ID を取得する(別の key)', async () => {
    stub.respondWith(jsonResponse(sourceDetails.normal()))
    const sourceId = ref('a')
    await runComposable(() => useSourceDetailQuery(sourceId))
    await flushPromises()

    sourceId.value = 'b'
    await flushPromises()

    expect(stub.requests.map((request) => request.pathname)).toEqual([
      '/api/admin/v1/sources/a',
      '/api/admin/v1/sources/b',
    ])
  })

  it('不正な ID から有効な ID に変わったら、取得を始める', async () => {
    stub.respondWith(jsonResponse(sourceDetails.normal()))
    const sourceId = ref('..')
    await runComposable(() => useSourceDetailQuery(sourceId))
    await flushPromises()
    expect(stub.requests).toEqual([])

    sourceId.value = 'a'
    await flushPromises()

    expect(stub.requests).toHaveLength(1)
  })

  it('404 source_config_not_found は、正規化された ApiError として error に載る(unknown として扱う)', async () => {
    stub.respondWith(apiErrorResponse(404, 'source_config_not_found'))

    const { result } = await runComposable(() => useSourceDetailQuery('gone'))
    await flushPromises()

    expect(result.error.value).toEqual({
      kind: 'api',
      status: 404,
      code: 'source_config_not_found',
      retryable: false,
      outcomeUnknown: false,
    })
  })
})

describe('useSourceEditQuery(EP-02。S4。FARC-P-12)', () => {
  it('S2 とは別の key(["sources","edit",id])で、同じ EP を取得する', async () => {
    stub.respondWith(jsonResponse(sourceDetails.normal()))
    const queryClient = createTestQueryClient()

    await runComposable(() => useSourceEditQuery('demo'), { queryClient })
    await flushPromises()

    expect(stub.requests[0]?.pathname).toBe('/api/admin/v1/sources/demo')
    expect(queryClient.getQueryState(keys.sources.edit('demo'))?.status).toBe('success')
    expect(queryClient.getQueryState(keys.sources.detail('demo'))).toBeUndefined()
  })

  it('画面を閉じると残らず(gcTime: 0)、開くたびに必ず取得する', async () => {
    stub.respondWith(jsonResponse(sourceDetails.normal()))
    const queryClient = createTestQueryClient()
    const first = await runComposable(() => useSourceEditQuery('demo'), { queryClient })
    await flushPromises()

    first.wrapper.unmount()
    await vi.waitFor(() =>
      expect(queryClient.getQueryState(keys.sources.edit('demo'))).toBeUndefined(),
    )

    await runComposable(() => useSourceEditQuery('demo'), { queryClient })
    await flushPromises()

    expect(stub.requests).toHaveLength(2)
  })

  it('取得後は取り直さない(staleTime: Infinity。編集中にバックグラウンドで値が差し替わらない)', async () => {
    stub.respondWith(jsonResponse(sourceDetails.normal()))
    const queryClient = createTestQueryClient()
    await runComposable(() => useSourceEditQuery('demo'), { queryClient })
    await flushPromises()

    // 同じ key を使う別のオブザーバーがマウントされても、取得済みの値を使う。
    await queryClient.refetchQueries({ queryKey: keys.sources.all, stale: true })

    expect(stub.requests).toHaveLength(1)
  })

  it('ID が不正なら取得しない', async () => {
    const { result } = await runComposable(() => useSourceEditQuery('..'))
    await flushPromises()

    expect(stub.requests).toEqual([])
    expect(result.fetchStatus.value).toBe('idle')
    // 取得しなかった(request interceptor に任せて通ったのではない): 待機中のまま、エラーも取得中もない
    expect(result.status.value).toBe('pending')
    expect(result.error.value).toBeNull()
    expect(result.isLoading.value).toBe(false)
  })
})
