import { onlineManager } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { cancelJobMutation, getMetaOptions } from '@/admin/api'
import type { ApiError } from '@/shared/api/apiError'

import {
  apiErrorResponse,
  jsonResponse,
  networkErrorResponse,
  nginxHtmlResponse,
} from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { runMutation } from '../../../tests/support/queryTesting'
import { createAppQueryClient, shouldRetryRead } from './queryClient'

describe('shouldRetryRead(読み取りの再試行は 1 回だけ。E 5.4・6.5)', () => {
  const retried: [string, ApiError][] = [
    ['network', { kind: 'network' }],
    [
      '503 unavailable(retryable=true の api)',
      { kind: 'api', status: 503, code: 'unavailable', retryable: true, outcomeUnknown: false },
    ],
    ['invalid_response の 502', { kind: 'invalid_response', status: 502 }],
    ['invalid_response の 503', { kind: 'invalid_response', status: 503 }],
    ['invalid_response の 504', { kind: 'invalid_response', status: 504 }],
  ]
  const notRetried: [string, unknown][] = [
    ['timeout(45 秒を 2 回待たせない)', { kind: 'timeout' }],
    [
      '404(retryable=false の api)',
      { kind: 'api', status: 404, code: 'job_not_found', retryable: false, outcomeUnknown: false },
    ],
    [
      '400',
      {
        kind: 'api',
        status: 400,
        code: 'invalid_request',
        retryable: false,
        outcomeUnknown: false,
      },
    ],
    [
      '409',
      { kind: 'api', status: 409, code: 'lock_held', retryable: false, outcomeUnknown: false },
    ],
    ['invalid_response の 413', { kind: 'invalid_response', status: 413 }],
    ['invalid_response の 500', { kind: 'invalid_response', status: 500 }],
    ['invalid_response の 200(形が違うだけ)', { kind: 'invalid_response', status: 200 }],
    ['invalid_response(status なし)', { kind: 'invalid_response' }],
    ['ApiError でない値(unknown として扱う)', new Error('boom')],
    ['生成型の ErrorResponse の形(正規化されていない)', { error: { code: 'x', retryable: true } }],
    ['null', null],
  ]

  it.each(retried)('再試行する: %s', (_name, error) => {
    expect(shouldRetryRead(0, error)).toBe(true)
  })

  it.each(notRetried)('再試行しない: %s', (_name, error) => {
    expect(shouldRetryRead(0, error)).toBe(false)
  })

  it('1 回失敗した後(failureCount=1)は、再試行できるエラーでも再試行しない', () => {
    expect(shouldRetryRead(1, { kind: 'network' })).toBe(false)
  })
})

describe('createAppQueryClient の既定値(E 5.4)', () => {
  const defaults = createAppQueryClient().getDefaultOptions()

  it('staleTime 0(マウント時は再取得)・フォーカス・再接続では再取得しない・gcTime 5 分・retryDelay 1 秒', () => {
    expect(defaults.queries).toMatchObject({
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      gcTime: 300_000,
      retryDelay: 1000,
    })
    expect(defaults.queries?.refetchOnMount).toBeUndefined()
  })

  it('mutation は再送しない(retry 0)', () => {
    expect(defaults.mutations?.retry).toBe(0)
  })

  it('networkMode は query・mutation とも always(オフラインでも paused にしない)', () => {
    expect(defaults.queries?.networkMode).toBe('always')
    expect(defaults.mutations?.networkMode).toBe('always')
  })

  it('グローバルの通知を置かない(QueryCache・MutationCache の onError)', () => {
    const queryClient = createAppQueryClient()

    expect(queryClient.getQueryCache().config.onError).toBeUndefined()
    expect(queryClient.getMutationCache().config.onError).toBeUndefined()
  })
})

describe('実際の取得での再試行(1 回・1 秒後)', () => {
  const stub = useFetchStub()

  async function fetchWithRetry(first: Parameters<typeof stub.respondWith>[0]) {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
    try {
      let calls = 0
      stub.respondWith(() => {
        calls += 1
        const answer =
          calls === 1 ? first : jsonResponse({ cron_timezone: null, dashboards_url: null })
        return typeof answer === 'function' ? answer({} as never) : answer
      })
      const queryClient = createAppQueryClient()
      // retry・retryDelay は QueryClient の既定値(defaultOptions)に任せる。
      const outcome = queryClient.fetchQuery(getMetaOptions()).then(
        (data) => ({ data }),
        (error: unknown) => ({ error }),
      )
      await vi.advanceTimersByTimeAsync(1000)
      return { outcome: await outcome, requests: stub.requests.length }
    } finally {
      vi.useRealTimers()
    }
  }

  it('503 unavailable(retryable)は 1 回再試行して成功する', async () => {
    const { outcome, requests } = await fetchWithRetry(
      apiErrorResponse(503, 'unavailable', { retryable: true }),
    )

    expect(requests).toBe(2)
    expect(outcome).toHaveProperty('data')
  })

  it('通信断は 1 回再試行する', async () => {
    const { requests, outcome } = await fetchWithRetry(networkErrorResponse())

    expect(requests).toBe(2)
    expect(outcome).toHaveProperty('data')
  })

  it('Nginx の HTML の 502 は 1 回再試行する', async () => {
    const { requests } = await fetchWithRetry(nginxHtmlResponse(502))

    expect(requests).toBe(2)
  })

  it('404 は再試行しない', async () => {
    const { outcome, requests } = await fetchWithRetry(apiErrorResponse(404, 'job_not_found'))

    expect(requests).toBe(1)
    expect(outcome).toHaveProperty('error')
  })

  it('Nginx の HTML の 413 は再試行しない', async () => {
    const { requests } = await fetchWithRetry(nginxHtmlResponse(413))

    expect(requests).toBe(1)
  })
})

describe('オフライン(navigator.onLine=false 相当)でも要求を送る(networkMode: always)', () => {
  const stub = useFetchStub()

  afterEach(() => {
    onlineManager.setOnline(true)
  })

  it('query: 送信され、通信断なら network のエラーになる(paused のまま待たない)', async () => {
    onlineManager.setOnline(false)
    stub.respondWith(networkErrorResponse())
    const queryClient = createAppQueryClient()

    const error = await queryClient
      .fetchQuery({ ...getMetaOptions(), retry: false })
      .catch((e: unknown) => e)

    expect(stub.requests).toHaveLength(1)
    expect(error).toEqual({ kind: 'network' })
  })

  it('query: オフラインでも、サーバーが応答すれば取得できる', async () => {
    onlineManager.setOnline(false)
    stub.respondWith(jsonResponse({ cron_timezone: null, dashboards_url: null }))

    const data = await createAppQueryClient().fetchQuery(getMetaOptions())

    expect(data).toEqual({ cron_timezone: null, dashboards_url: null })
  })

  it('mutation: 送信され、通信断なら network のエラーになる。paused にならず、再接続後に遅れて実行されない', async () => {
    onlineManager.setOnline(false)
    stub.respondWith(networkErrorResponse())
    const queryClient = createAppQueryClient()

    const error = await runMutation(queryClient, cancelJobMutation(), {
      path: { job_id: 'job-1' },
    }).catch((e: unknown) => e)

    expect(stub.requests).toHaveLength(1)
    expect(error).toEqual({ kind: 'network' })
    expect(
      queryClient
        .getMutationCache()
        .getAll()
        .map((mutation) => mutation.state.isPaused),
    ).toEqual([false])

    // 再接続しても、再送されない(削除・取消・ロック解放が遅れて実行されない)。
    onlineManager.setOnline(true)
    await new Promise((resolve) => setTimeout(resolve, 20))
    expect(stub.requests).toHaveLength(1)
  })

  it('対照: 既定の networkMode(online)の QueryClient だと、オフライン中の mutation は paused のまま送られない', async () => {
    onlineManager.setOnline(false)
    stub.respondWith(networkErrorResponse())
    const queryClient = createAppQueryClient()
    queryClient.setDefaultOptions({ mutations: { networkMode: 'online' } })

    const pending = runMutation(queryClient, cancelJobMutation(), {
      path: { job_id: 'job-1' },
    }).catch(() => {})
    await new Promise((resolve) => setTimeout(resolve, 20))

    expect(stub.requests).toHaveLength(0)
    expect(queryClient.getMutationCache().getAll()[0]?.state.isPaused).toBe(true)
    // 再接続で遅れて実行されないよう、キャッシュから外す(テストの後始末)。
    queryClient.getMutationCache().clear()
    void pending
  })
})
