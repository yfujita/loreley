import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { jobDetails, jobList } from '../../../tests/support/fixtures/jobs'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { keys } from './keys'
import { useJobDetailQuery, useJobsListQuery, type JobsQuery } from './jobs'
import { rowActionsDisabled } from './placeholder'

const stub = useFetchStub()

const DEFAULT_PARAMS: JobsQuery = {
  page: 1,
  itemsPerPage: 25,
  sort: null,
  sourceId: null,
  status: null,
}

describe('useJobsListQuery(EP-09。J1)', () => {
  it('条件を API の名前(items_per_page・source_id)に写して取得する。指定なしの条件は付けない', async () => {
    stub.respondWith(jsonResponse(jobList.normal()))

    await runComposable(() => useJobsListQuery(DEFAULT_PARAMS))
    await flushPromises()

    expect(stub.requests[0]?.pathname).toBe('/api/admin/v1/jobs')
    expect(Object.fromEntries(new URLSearchParams(stub.requests[0]?.search))).toEqual({
      page: '1',
      items_per_page: '25',
    })
  })

  it('並べ替え・データソース・状態(複合値 active を含む)があれば付ける', async () => {
    stub.respondWith(jsonResponse(jobList.normal()))

    await runComposable(() =>
      useJobsListQuery({
        page: 3,
        itemsPerPage: 100,
        sort: 'queued_at',
        sourceId: 'demo',
        status: 'active',
      }),
    )
    await flushPromises()

    expect(Object.fromEntries(new URLSearchParams(stub.requests[0]?.search))).toEqual({
      page: '3',
      items_per_page: '100',
      sort: 'queued_at',
      source_id: 'demo',
      status: 'active',
    })
  })

  it('key は ["jobs","list",params](params を含む)', async () => {
    stub.respondWith(jsonResponse(jobList.normal()))
    const queryClient = createTestQueryClient()

    await runComposable(() => useJobsListQuery(DEFAULT_PARAMS), { queryClient })
    await flushPromises()

    expect(queryClient.getQueryState(keys.jobs.list(DEFAULT_PARAMS))?.status).toBe('success')
  })

  describe('取得中の前回データ(同じスコープのページ・並べ替えの変更だけ)', () => {
    async function mountWithPendingSecondRequest() {
      const params = ref<JobsQuery>(DEFAULT_PARAMS)
      let release: () => void = () => {}
      let calls = 0
      stub.respondWith(async () => {
        calls += 1
        if (calls === 1) return jsonResponse(jobList.normal())
        // 2 回目以降は、解放されるまで応答しない(取得中の状態を観測するため)
        await new Promise<void>((resolve) => (release = resolve))
        return jsonResponse(jobList.empty())
      })
      const { result } = await runComposable(() => useJobsListQuery(params))
      await flushPromises()
      return { params, result, release: () => release() }
    }

    it('ページが変わったとき、取得中は前回のデータを保ち(isPlaceholderData)、行の操作を無効にする', async () => {
      const { params, result, release } = await mountWithPendingSecondRequest()

      params.value = { ...DEFAULT_PARAMS, page: 2 }
      await flushPromises()

      expect(result.isPlaceholderData.value).toBe(true)
      expect(result.data.value).toEqual(jobList.normal())
      expect(rowActionsDisabled(result.isPlaceholderData.value)).toBe(true)

      release()
      await vi.waitFor(() => expect(result.isPlaceholderData.value).toBe(false))
      expect(result.data.value).toEqual(jobList.empty())
      expect(rowActionsDisabled(result.isPlaceholderData.value)).toBe(false)
    })

    it('並べ替えが変わったときも保つ', async () => {
      const { params, result } = await mountWithPendingSecondRequest()

      params.value = { ...DEFAULT_PARAMS, sort: 'queued_at' }
      await flushPromises()

      expect(result.isPlaceholderData.value).toBe(true)
      expect(result.data.value).toEqual(jobList.normal())
    })

    it('絞り込みが変わったときは、前回の行を見せない(スケルトン)', async () => {
      const { params, result } = await mountWithPendingSecondRequest()

      params.value = { ...DEFAULT_PARAMS, status: 'failed' }
      await flushPromises()

      expect(result.isPlaceholderData.value).toBe(false)
      expect(result.data.value).toBeUndefined()
      expect(result.isLoading.value).toBe(true)
    })

    it('件数(size)が変わったときも、見せない', async () => {
      const { params, result } = await mountWithPendingSecondRequest()

      params.value = { ...DEFAULT_PARAMS, itemsPerPage: 50 }
      await flushPromises()

      expect(result.data.value).toBeUndefined()
    })
  })
})

describe('useJobDetailQuery(EP-10。J2)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  async function elapse(ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
    await flushPromises()
  }

  it('ジョブ ID を URL にエンコードして取得し、key は ["jobs","detail",id]', async () => {
    stub.respondWith(jsonResponse(jobDetails.succeeded()))
    const queryClient = createTestQueryClient()

    await runComposable(() => useJobDetailQuery('a%b?c#d'), { queryClient })
    await flushPromises()

    expect(stub.requests[0]?.pathname).toBe('/api/admin/v1/jobs/a%25b%3Fc%23d')
    expect(queryClient.getQueryState(keys.jobs.detail('a%b?c#d'))?.status).toBe('success')
  })

  it.each(['.', '..', ''])('ジョブ ID が %j のとき、API を呼ばない', async (id) => {
    stub.respondWith(jsonResponse(jobDetails.succeeded()))

    const { result } = await runComposable(() => useJobDetailQuery(id))
    await flushPromises()

    expect(stub.requests).toEqual([])
    expect(result.fetchStatus.value).toBe('idle')
  })

  it('実行中は 10 秒ごとに取り直し、終端になったら止まる(取消の要求後も終端まで続く)', async () => {
    const responses = [jobDetails.running(), jobDetails.running(), jobDetails.succeeded()]
    let calls = 0
    stub.respondWith(() => jsonResponse(responses[Math.min(calls++, responses.length - 1)]))
    await runComposable(() => useJobDetailQuery('job-1'))
    await flushPromises()
    expect(stub.requests).toHaveLength(1)

    await elapse(9_999)
    expect(stub.requests).toHaveLength(1)
    await elapse(1)
    expect(stub.requests).toHaveLength(2)
    await elapse(10_000)
    expect(stub.requests).toHaveLength(3)

    await elapse(120_000)
    expect(stub.requests).toHaveLength(3)
  })

  it('実行待ち(queued)も取り直す', async () => {
    stub.respondWith(jsonResponse(jobDetails.queued()))
    await runComposable(() => useJobDetailQuery('job-1'))
    await flushPromises()

    await elapse(10_000)

    expect(stub.requests).toHaveLength(2)
  })

  it('リース切れ(stalled。保存上は running)もポーリングが続く', async () => {
    stub.respondWith(jsonResponse(jobDetails.stalledWithLeaseExpiry()))
    await runComposable(() => useJobDetailQuery('job-1'))
    await flushPromises()

    await elapse(30_000)

    expect(stub.requests.length).toBeGreaterThanOrEqual(4)
  })

  it('最初から終端のジョブは取り直さない', async () => {
    stub.respondWith(jsonResponse(jobDetails.failedRerunnable()))
    await runComposable(() => useJobDetailQuery('job-1'))
    await flushPromises()

    await elapse(60_000)

    expect(stub.requests).toHaveLength(1)
  })
})
