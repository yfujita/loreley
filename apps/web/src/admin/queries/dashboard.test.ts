import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { dashboard } from '../../../tests/support/fixtures/dashboard'
import { useDashboardQuery } from './dashboard'

const stub = useFetchStub()

describe('useDashboardQuery(EP-13。D1)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  })
  afterEach(() => {
    vi.useRealTimers()
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
  })

  async function elapse(ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }

  it('クエリを付けずに取得する', async () => {
    stub.respondWith(jsonResponse(dashboard.allNormal()))

    const { result } = await runComposable(() => useDashboardQuery(false))
    await flushPromises()

    expect(result.data.value).toEqual(dashboard.allNormal())
    expect(stub.requests[0]).toMatchObject({ pathname: '/api/admin/v1/dashboard', search: '' })
  })

  it('自動更新が入の間は 30 秒ごとに取り直し、切にすると止まり、入に戻すと再開する', async () => {
    stub.respondWith(jsonResponse(dashboard.allNormal()))
    const autoRefresh = ref(true)
    await runComposable(() => useDashboardQuery(autoRefresh))
    await flushPromises()
    expect(stub.requests).toHaveLength(1)

    await elapse(29_999)
    expect(stub.requests).toHaveLength(1)
    await elapse(1)
    expect(stub.requests).toHaveLength(2)
    await elapse(30_000)
    expect(stub.requests).toHaveLength(3)

    autoRefresh.value = false
    await elapse(120_000)
    expect(stub.requests).toHaveLength(3)

    autoRefresh.value = true
    await elapse(30_000)
    expect(stub.requests).toHaveLength(4)
  })

  it('自動更新が切のとき、最初から取り直さない', async () => {
    stub.respondWith(jsonResponse(dashboard.allNormal()))
    await runComposable(() => useDashboardQuery(false))
    await flushPromises()

    await elapse(300_000)

    expect(stub.requests).toHaveLength(1)
  })

  it('タブが見えない間は止める(refetchIntervalInBackground: false)', async () => {
    stub.respondWith(jsonResponse(dashboard.allNormal()))
    await runComposable(() => useDashboardQuery(true))
    await flushPromises()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    await elapse(90_000)
    expect(stub.requests).toHaveLength(1)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await elapse(30_000)
    expect(stub.requests.length).toBeGreaterThan(1)
  })
})
