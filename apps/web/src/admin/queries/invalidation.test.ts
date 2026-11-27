import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import type { WriteOperation } from '@/admin/api'
import type { ApiError } from '@/shared/api/apiError'

import { apiErrorResponse, jsonResponse, nginxHtmlResponse } from '../../../tests/support/apiErrors'
import { runComposable } from '../../../tests/support/composableTesting'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { jobAccepted, jobDetails, releaseLockResponses } from '../../../tests/support/fixtures/jobs'
import { savedSettings, sourceDetails, sourceList } from '../../../tests/support/fixtures/sources'
import { createTestQueryClient } from '../../../tests/support/queryTesting'
import { INVALIDATION_TABLE, invalidateAfter } from './invalidation'
import { keys } from './keys'
import { useCancelJobMutation } from './mutations/cancelJob'
import { useCreateSourceMutation } from './mutations/createSource'
import { useDeleteSourceMutation } from './mutations/deleteSource'
import { useReleaseLockMutation } from './mutations/releaseLock'
import { useStartCrawlMutation } from './mutations/startCrawl'
import { useUpdateSourceMutation } from './mutations/updateSource'
import { useSourceDetailQuery, useSourcesListQuery } from './sources'
import { useJobDetailQuery } from './jobs'
import { createAppQueryClient } from './queryClient'

const stub = useFetchStub()

describe('invalidate の表(E 5.8)', () => {
  it('操作ごとの prefix(順も含めて表のとおり)', () => {
    expect(INVALIDATION_TABLE).toEqual({
      startCrawl: [['sources'], ['jobs']],
      startSourceDelete: [['sources'], ['jobs']],
      cancelJob: [['jobs'], ['sources']],
      releaseLock: [['sources'], ['jobs']],
      registerSource: [['sources']],
      updateSource: [['sources']],
    } satisfies Record<WriteOperation, unknown>)
  })

  it('invalidateAfter は、表の prefix に一致するクエリだけを invalid にして再取得する', async () => {
    stub.respondWith(jsonResponse({ ok: true }))
    const queryClient = createTestQueryClient()
    await runComposable(
      () => ({
        list: useSourcesListQuery(),
        detail: useSourceDetailQuery('a'),
        job: useJobDetailQuery('j'),
      }),
      { queryClient },
    )
    await flushPromises()
    const before = stub.requests.length

    invalidateAfter(queryClient, 'registerSource')
    await flushPromises()

    const refetched = stub.requests
      .slice(before)
      .map((request) => request.pathname)
      .sort()
    expect(refetched).toEqual(['/api/admin/v1/sources', '/api/admin/v1/sources/a'])
  })
})

describe('mutation(EP-03〜08)', () => {
  const cases = [
    {
      name: 'S3 登録(EP-03)',
      use: useCreateSourceMutation,
      variables: {
        body: {
          source_id: 'demo-handbook',
          connector_type: 'file_system',
          connector_config: {},
          ttl_days: 30,
          ratio_threshold_percent: 20,
          min_delete_count: 10,
        },
      },
      response: jsonResponse(savedSettings.registered(), 201),
      expected: { method: 'POST', pathname: '/api/admin/v1/sources' },
      invalidated: ['sources'],
    },
    {
      name: 'S4 保存(EP-04)',
      use: useUpdateSourceMutation,
      variables: {
        path: { source_id: 'demo-handbook' },
        body: {
          connector_config: {},
          ttl_days: 30,
          ratio_threshold_percent: 25,
          min_delete_count: 10,
        },
      },
      response: jsonResponse(savedSettings.updated()),
      expected: { method: 'PUT', pathname: '/api/admin/v1/sources/demo-handbook' },
      invalidated: ['sources'],
    },
    {
      name: 'DLG-1・DLG-4 クロール起動(EP-06)',
      use: useStartCrawlMutation,
      variables: {
        path: { source_id: 'demo-handbook' },
        body: { force_delete: true, rewrite_mode: false },
      },
      response: jsonResponse(jobAccepted.crawl(), 202),
      expected: { method: 'POST', pathname: '/api/admin/v1/sources/demo-handbook/crawl-jobs' },
      invalidated: ['sources', 'jobs'],
    },
    {
      name: 'DLG-2 削除(EP-05)',
      use: useDeleteSourceMutation,
      variables: { path: { source_id: 'demo-handbook' } },
      response: jsonResponse(jobAccepted.sourceDelete(), 202),
      expected: { method: 'POST', pathname: '/api/admin/v1/sources/demo-handbook/delete-jobs' },
      invalidated: ['sources', 'jobs'],
    },
    {
      name: 'DLG-3 取消(EP-07)',
      use: useCancelJobMutation,
      variables: { path: { job_id: 'job-3' } },
      response: jsonResponse({ job_id: 'job-3', status: 'cancelled' }),
      expected: { method: 'POST', pathname: '/api/admin/v1/jobs/job-3/cancel' },
      invalidated: ['jobs', 'sources'],
    },
    {
      name: 'DLG-5 ロック解放(EP-08)',
      use: useReleaseLockMutation,
      variables: { path: { source_id: 'demo-handbook' } },
      response: jsonResponse(releaseLockResponses.released()),
      expected: { method: 'DELETE', pathname: '/api/admin/v1/sources/demo-handbook/lock' },
      invalidated: ['sources', 'jobs'],
    },
  ] as const

  it.each(cases)(
    '$name: 正しい EP へ送り、成功したら表の prefix を invalidate する',
    async (testCase) => {
      stub.respondWith(testCase.response)
      const queryClient = createTestQueryClient()
      const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
      const { result } = await runComposable(() => testCase.use(), { queryClient })

      await (result.mutateAsync as (variables: unknown) => Promise<unknown>)(testCase.variables)

      expect(stub.requests).toHaveLength(1)
      expect(stub.requests[0]).toMatchObject(testCase.expected)
      expect(
        invalidate.mock.calls.map(
          ([filters]) => (filters as { queryKey: readonly unknown[] }).queryKey[0],
        ),
      ).toEqual(testCase.invalidated)
    },
  )

  it('成功したとき、表示中のクエリが取り直される(S2 のロック状態カードが held_delete になる経路)', async () => {
    stub.routes({
      'GET /sources/demo-handbook': () => jsonResponse(sourceDetails.withLock('held_delete')),
      'POST /sources/demo-handbook/delete-jobs': jsonResponse(jobAccepted.sourceDelete(), 202),
    })
    const queryClient = createTestQueryClient()
    // 最初は削除を受け付ける前の状態(ロックなし)
    queryClient.setQueryData(keys.sources.detail('demo-handbook'), sourceDetails.normal())
    const { result } = await runComposable(
      () => ({ detail: useSourceDetailQuery('demo-handbook'), remove: useDeleteSourceMutation() }),
      { queryClient },
    )
    await flushPromises()
    stub.requests.length = 0

    await result.remove.mutateAsync({ path: { source_id: 'demo-handbook' } })
    await vi.waitFor(() => expect(result.detail.data.value?.lock?.state).toBe('held_delete'))

    expect(stub.requests.map((request) => `${request.method} ${request.pathname}`)).toEqual([
      'POST /api/admin/v1/sources/demo-handbook/delete-jobs',
      'GET /api/admin/v1/sources/demo-handbook',
    ])
  })

  it('失敗したときは invalidate しない', async () => {
    stub.respondWith(apiErrorResponse(409, 'lock_held', { details: { lock_state: 'held_crawl' } }))
    const queryClient = createTestQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = await runComposable(() => useStartCrawlMutation(), { queryClient })

    await result
      .mutateAsync({
        path: { source_id: 'demo-handbook' },
        body: { force_delete: false, rewrite_mode: false },
      })
      .catch(() => {})

    expect(invalidate).not.toHaveBeenCalled()
  })

  it('失敗は ApiError として error に載る(unknown として扱う。mutation の isPending は終わる)', async () => {
    stub.respondWith(
      apiErrorResponse(409, 'lock_held', { details: { lock_state: 'lease_expired' } }),
    )
    const { result } = await runComposable(() => useStartCrawlMutation())

    await result
      .mutateAsync({
        path: { source_id: 'demo-handbook' },
        body: { force_delete: false, rewrite_mode: false },
      })
      .catch(() => {})
    await flushPromises()

    const error: unknown = result.error.value
    expect(error).toMatchObject({
      kind: 'api',
      status: 409,
      code: 'lock_held',
      outcomeUnknown: false,
    })
    expect((error as ApiError & { kind: 'api' }).details).toEqual({ lock_state: 'lease_expired' })
    expect(result.isPending.value).toBe(false)
  })

  it('書き込みは再送しない(retry 0): 503 で失敗しても 1 回だけ送る', async () => {
    stub.respondWith(apiErrorResponse(503, 'crawler_unavailable', { retryable: true }))
    const { result } = await runComposable(() => useStartCrawlMutation(), {
      queryClient: createAppQueryClient(),
    })

    await result
      .mutateAsync({
        path: { source_id: 'demo-handbook' },
        body: { force_delete: false, rewrite_mode: false },
      })
      .catch(() => {})

    expect(stub.requests).toHaveLength(1)
  })

  it('Nginx の HTML の 504 でも再送しない(結果不明。error は invalid_response)', async () => {
    stub.respondWith(nginxHtmlResponse(504))
    const { result } = await runComposable(() => useCancelJobMutation(), {
      queryClient: createAppQueryClient(),
    })

    await result.mutateAsync({ path: { job_id: 'job-3' } }).catch(() => {})
    await flushPromises()

    expect(stub.requests).toHaveLength(1)
    expect(result.error.value).toEqual({ kind: 'invalid_response', status: 504 })
  })

  it('二重送信の防止は呼び出し側(isPending)。実行中は isPending が true', async () => {
    let release: () => void = () => {}
    stub.respondWith(async () => {
      await new Promise<void>((resolve) => (release = resolve))
      return jsonResponse(jobAccepted.crawl(), 202)
    })
    const { result } = await runComposable(() => useStartCrawlMutation())

    const pending = result.mutateAsync({
      path: { source_id: 'demo-handbook' },
      body: { force_delete: false, rewrite_mode: false },
    })
    await vi.waitFor(() => expect(stub.requests).toHaveLength(1))
    await flushPromises()
    expect(result.isPending.value).toBe(true)
    release()
    await pending

    expect(result.isPending.value).toBe(false)
  })
})

describe('取消の 409 job_already_finished(成功扱い)でも invalidate する(E 5.8・6.3)', () => {
  async function cancelWith(mock: Parameters<typeof stub.respondWith>[0]) {
    stub.respondWith(mock)
    const queryClient = createTestQueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    const { result } = await runComposable(() => useCancelJobMutation(), { queryClient })

    const error = await result.mutateAsync({ path: { job_id: 'job-3' } }).then(
      () => null,
      (caught: unknown) => caught,
    )
    await flushPromises()

    const prefixes = invalidate.mock.calls.map(
      ([filters]) => (filters as { queryKey: readonly unknown[] }).queryKey[0],
    )
    return { error, prefixes }
  }

  it('409 job_already_finished は、mutation としては失敗(呼び出し側が成功扱いにする)だが、jobs・sources を invalidate する', async () => {
    const { error, prefixes } = await cancelWith(
      apiErrorResponse(409, 'job_already_finished', { details: { status: 'failed' } }),
    )

    expect(error).toMatchObject({ kind: 'api', status: 409, code: 'job_already_finished' })
    expect(prefixes).toEqual(['jobs', 'sources'])
  })

  it('終端済みのジョブが J2 で running のまま残らない(409 の後、表示中の詳細が取り直される)', async () => {
    let calls = 0
    stub.routes({
      'GET /jobs/job-3': () =>
        jsonResponse(calls++ === 0 ? jobDetails.running() : jobDetails.succeeded()),
      'POST /jobs/job-3/cancel': apiErrorResponse(409, 'job_already_finished', {
        details: { status: 'succeeded' },
      }),
    })
    const { result } = await runComposable(() => ({
      detail: useJobDetailQuery('job-3'),
      cancel: useCancelJobMutation(),
    }))
    await flushPromises()
    expect(result.detail.data.value?.status).toBe('running')

    await result.cancel.mutateAsync({ path: { job_id: 'job-3' } }).catch(() => {})
    await vi.waitFor(() => expect(result.detail.data.value?.status).toBe('succeeded'))
  })

  it.each([
    ['409 job_not_cancellable(想定外)', apiErrorResponse(409, 'job_not_cancellable')],
    ['404 job_not_found', apiErrorResponse(404, 'job_not_found')],
    ['503 crawler_unreachable', apiErrorResponse(503, 'crawler_unreachable', { retryable: true })],
    ['504 crawler_response_lost(結果不明)', apiErrorResponse(504, 'crawler_response_lost')],
    ['Nginx の HTML の 502', nginxHtmlResponse(502)],
  ])('他のエラーでは invalidate しない: %s', async (_name, mock) => {
    const { prefixes } = await cancelWith(mock)

    expect(prefixes).toEqual([])
  })
})

describe('jobs 一覧の取り直し(取消の後)', () => {
  it('取消の後、J2 の詳細が取り直される', async () => {
    stub.routes({
      'GET /jobs/job-3': jsonResponse(jobDetails.running()),
      'POST /jobs/job-3/cancel': jsonResponse({ job_id: 'job-3', status: 'running' }, 202),
    })
    const queryClient = createTestQueryClient()
    const { result } = await runComposable(
      () => ({ detail: useJobDetailQuery('job-3'), cancel: useCancelJobMutation() }),
      { queryClient },
    )
    await flushPromises()
    const before = stub.requests.filter((request) => request.method === 'GET').length

    await result.cancel.mutateAsync({ path: { job_id: 'job-3' } })
    await flushPromises()

    expect(stub.requests.filter((request) => request.method === 'GET').length).toBe(before + 1)
  })
})

describe('sources 一覧の取り直し', () => {
  it('登録の後、一覧が取り直される(EP-01 は反映が遅れうるが、取り直しは行う)', async () => {
    stub.routes({
      'GET /sources': jsonResponse(sourceList.normal()),
      'POST /sources': jsonResponse(savedSettings.registered(), 201),
    })
    const queryClient = createTestQueryClient()
    const { result } = await runComposable(
      () => ({ list: useSourcesListQuery(), create: useCreateSourceMutation() }),
      { queryClient },
    )
    await flushPromises()
    stub.requests.length = 0

    await result.create.mutateAsync({
      body: {
        source_id: 'demo-handbook',
        connector_type: 'file_system',
        connector_config: {},
        ttl_days: 30,
        ratio_threshold_percent: 20,
        min_delete_count: 10,
      },
    })
    await flushPromises()

    expect(stub.requests.map((request) => `${request.method} ${request.pathname}`)).toEqual([
      'POST /api/admin/v1/sources',
      'GET /api/admin/v1/sources',
    ])
  })
})
