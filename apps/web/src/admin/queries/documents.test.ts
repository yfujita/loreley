import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { documents } from '../../../tests/support/fixtures/documents'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { useDocumentsQuery } from './documents'
import type { DocumentsQuery } from './params'
import { keys } from './keys'

const stub = useFetchStub()

const SKIPPED: DocumentsQuery = { tab: 'skipped', page: 1, itemsPerPage: 25, sort: null }

describe('useDocumentsQuery(EP-11。X1)', () => {
  it('source をパスの {source_id} に、tab・page・items_per_page をクエリに写す。sort は指定なしなら付けない', async () => {
    stub.respondWith(jsonResponse(documents.skipped()))

    await runComposable(() => useDocumentsQuery('demo', SKIPPED))
    await flushPromises()

    expect(stub.requests[0]?.pathname).toBe('/api/admin/v1/sources/demo/documents')
    expect(Object.fromEntries(new URLSearchParams(stub.requests[0]?.search))).toEqual({
      tab: 'skipped',
      page: '1',
      items_per_page: '25',
    })
  })

  it('tab は API の値(snake_case)で、sort があれば付ける', async () => {
    stub.respondWith(jsonResponse(documents.extractFailed()))

    await runComposable(() =>
      useDocumentsQuery('demo', {
        tab: 'extract_failed',
        page: 2,
        itemsPerPage: 50,
        sort: '-last_seen_at',
      }),
    )
    await flushPromises()

    expect(Object.fromEntries(new URLSearchParams(stub.requests[0]?.search))).toEqual({
      tab: 'extract_failed',
      page: '2',
      items_per_page: '50',
      sort: '-last_seen_at',
    })
  })

  it('key は ["documents", sourceId, params]', async () => {
    stub.respondWith(jsonResponse(documents.skipped()))
    const queryClient = createTestQueryClient()

    await runComposable(() => useDocumentsQuery('demo', SKIPPED), { queryClient })
    await flushPromises()

    expect(queryClient.getQueryState(keys.documents.list('demo', SKIPPED))?.status).toBe('success')
  })

  it('FARC-U-26 (4): source が未選択(null)のとき取得せず、isPending は true のまま・isLoading は false(スケルトンは isLoading で出す)', async () => {
    stub.respondWith(jsonResponse(documents.skipped()))

    const { result } = await runComposable(() => useDocumentsQuery(null, SKIPPED))
    await flushPromises()

    expect(stub.requests).toEqual([])
    expect(result.isPending.value).toBe(true)
    expect(result.isLoading.value).toBe(false)
    expect(result.fetchStatus.value).toBe('idle')
    // 取得しなかった(request interceptor に任せて通ったのではない): 待機中のまま、エラーも取得中もない
    expect(result.status.value).toBe('pending')
    expect(result.error.value).toBeNull()
    expect(result.isLoading.value).toBe(false)
  })

  it('FARC-U-26 (4): 取得中は isLoading が true', async () => {
    stub.respondWith(() => new Promise<never>(() => {}))

    const { result } = await runComposable(() => useDocumentsQuery('demo', SKIPPED))
    await flushPromises()

    expect(result.isPending.value).toBe(true)
    expect(result.isLoading.value).toBe(true)
  })

  it.each(['.', '..', ''])('source が %j のとき、API を呼ばない', async (source) => {
    const { result } = await runComposable(() => useDocumentsQuery(source, SKIPPED))
    await flushPromises()

    expect(stub.requests).toEqual([])
    expect(result.fetchStatus.value).toBe('idle')
    // 取得しなかった(request interceptor に任せて通ったのではない): 待機中のまま、エラーも取得中もない
    expect(result.status.value).toBe('pending')
    expect(result.error.value).toBeNull()
    expect(result.isLoading.value).toBe(false)
  })

  it('source が未選択から選択に変わったら取得を始める', async () => {
    stub.respondWith(jsonResponse(documents.skipped()))
    const source = ref<string | null>(null)
    await runComposable(() => useDocumentsQuery(source, SKIPPED))
    await flushPromises()
    expect(stub.requests).toEqual([])

    source.value = 'demo'
    await flushPromises()

    expect(stub.requests).toHaveLength(1)
  })

  describe('取得中の前回データ', () => {
    async function mountWithPendingNextRequest() {
      const params = ref<DocumentsQuery>(SKIPPED)
      const source = ref<string | null>('demo')
      let release: () => void = () => {}
      let calls = 0
      stub.respondWith(async () => {
        calls += 1
        if (calls === 1) return jsonResponse(documents.skipped())
        await new Promise<void>((resolve) => (release = resolve))
        return jsonResponse(documents.empty())
      })
      const { result } = await runComposable(() => useDocumentsQuery(source, params))
      await flushPromises()
      return { params, source, result, release: () => release() }
    }

    it('ページ・並べ替えの変更では、前回のデータを保つ', async () => {
      const { params, result, release } = await mountWithPendingNextRequest()

      params.value = { ...SKIPPED, page: 2 }
      await flushPromises()
      expect(result.isPlaceholderData.value).toBe(true)
      expect(result.data.value).toEqual(documents.skipped())

      release()
      await vi.waitFor(() => expect(result.isPlaceholderData.value).toBe(false))
    })

    it('タブが変わったときは、前回の行を見せない', async () => {
      const { params, result } = await mountWithPendingNextRequest()

      params.value = { ...SKIPPED, tab: 'oversize' }
      await flushPromises()

      expect(result.data.value).toBeUndefined()
      expect(result.isLoading.value).toBe(true)
    })

    it('データソースが変わったときも、見せない', async () => {
      const { source, result } = await mountWithPendingNextRequest()

      source.value = 'other'
      await flushPromises()

      expect(result.data.value).toBeUndefined()
    })
  })
})
