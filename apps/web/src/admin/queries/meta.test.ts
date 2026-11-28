import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { apiErrorResponse, jsonResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { meta } from '../../../tests/support/fixtures/meta'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { keys } from './keys'
import { useCronTimezone, useDashboardsUrl, useMetaQuery } from './meta'

const stub = useFetchStub()

describe('useMetaQuery(EP-14。シェル)', () => {
  it('クエリを付けずに /meta を取得し、key は ["meta"]', async () => {
    stub.respondWith(jsonResponse(meta.normal()))
    const queryClient = createTestQueryClient()

    const { result } = await runComposable(() => useMetaQuery(), { queryClient })
    await flushPromises()

    expect(result.data.value).toEqual(meta.normal())
    expect(stub.requests).toHaveLength(1)
    expect(stub.requests[0]).toMatchObject({ pathname: '/api/admin/v1/meta', search: '' })
    expect(queryClient.getQueryState(keys.meta())?.status).toBe('success')
  })

  it('staleTime が Infinity: 画面を開き直しても取り直さない(再読み込みまで)', async () => {
    stub.respondWith(jsonResponse(meta.normal()))
    const queryClient = createTestQueryClient()

    const first = await runComposable(() => useMetaQuery(), { queryClient })
    await flushPromises()
    first.wrapper.unmount()
    await runComposable(() => useMetaQuery(), { queryClient })
    await flushPromises()

    expect(stub.requests).toHaveLength(1)
  })
})

describe('useDashboardsUrl・useCronTimezone', () => {
  it('取得できたときは URL・タイムゾーンを返す', async () => {
    stub.respondWith(jsonResponse(meta.normal()))

    const { result } = await runComposable(() => ({
      url: useDashboardsUrl(),
      timezone: useCronTimezone(),
    }))
    await flushPromises()

    expect(result.url.value).toBe('http://localhost:5601')
    expect(result.timezone.value).toBe('Asia/Tokyo')
  })

  it('未設定(null)のとき null', async () => {
    stub.respondWith(jsonResponse({ cron_timezone: null, dashboards_url: null }))

    const { result } = await runComposable(() => ({
      url: useDashboardsUrl(),
      timezone: useCronTimezone(),
    }))
    await flushPromises()

    expect(result.url.value).toBeNull()
    expect(result.timezone.value).toBeNull()
  })

  it('EP-14 が失敗しても(throw せず)null と同じ扱い。シェルを止めない', async () => {
    stub.respondWith(apiErrorResponse(400, 'invalid_request'))

    const { result } = await runComposable(() => ({
      url: useDashboardsUrl(),
      timezone: useCronTimezone(),
    }))
    await flushPromises()

    expect(result.url.value).toBeNull()
    expect(result.timezone.value).toBeNull()
  })
})
