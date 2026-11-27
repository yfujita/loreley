import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  configureApiClient,
  getClusterOptions,
  getDashboardOptions,
  getMetaOptions,
  registerSourceMutation,
  startCrawlMutation,
} from '@/admin/api'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { createTestQueryClient, runMutation } from '../../../tests/support/queryTesting'
import { READ_TIMEOUT_MS, WRITE_TIMEOUT_MS } from './client'
// setup(tests/support/setup.ts)が configureApiClient() を呼んだ client そのもの。
import { client as setupClient } from './generated/client.gen'

const stub = useFetchStub()

const META = { cron_timezone: 'Asia/Tokyo', dashboards_url: null }

describe('configureApiClient: baseUrl と冪等性', () => {
  // setup(tests/support/setup.ts)がテスト用に絶対 baseUrl へ差し替えた client とは別の、生成直後のモジュールを読む。
  async function loadFreshModules() {
    vi.resetModules()
    const [{ client }, { configureApiClient, fetchWithTimeout }] = await Promise.all([
      import('./generated/client.gen'),
      import('./client'),
    ])
    return { client, configureApiClient, fetchWithTimeout }
  }

  it('baseUrl は設定せず、生成物が持つ /api/admin/v1 のまま(相対。同一オリジン)', async () => {
    const { client, configureApiClient } = await loadFreshModules()

    configureApiClient()

    expect(client.getConfig().baseUrl).toBe('/api/admin/v1')
  })

  it('タイムアウト付き fetch を設定し、本文は JSON として読む', async () => {
    const { client, configureApiClient, fetchWithTimeout } = await loadFreshModules()

    configureApiClient()

    expect(client.getConfig().fetch).toBe(fetchWithTimeout)
    expect(client.getConfig().parseAs).toBe('json')
  })

  it('2 回呼んでも interceptor が二重に登録されない(request 1 つ・error 1 つ)', async () => {
    const { client, configureApiClient } = await loadFreshModules()

    configureApiClient()
    configureApiClient()
    configureApiClient()

    const registered = (fns: Array<unknown>) => fns.filter((fn) => fn !== null)
    expect(registered(client.interceptors.request.fns)).toHaveLength(1)
    expect(registered(client.interceptors.error.fns)).toHaveLength(1)
    expect(registered(client.interceptors.response.fns)).toHaveLength(0)
  })

  it('呼ぶ前の生成クライアントは interceptor を持たない(設定が configureApiClient の仕事であること)', async () => {
    const { client } = await loadFreshModules()

    expect(client.interceptors.request.fns).toHaveLength(0)
    expect(client.interceptors.error.fns).toHaveLength(0)
  })

  it('setup が設定済みの client に対して呼んでも、interceptor は増えない(main.ts と setup の両方が呼ぶ場合)', () => {
    configureApiClient()
    configureApiClient()

    const registered = (fns: Array<unknown>) => fns.filter((fn) => fn !== null)
    expect(registered(setupClient.interceptors.request.fns)).toHaveLength(1)
    expect(registered(setupClient.interceptors.error.fns)).toHaveLength(1)
  })
})

describe('EP-12・13・14 は query を付けない(E 5.3)', () => {
  const queryClient = () => createTestQueryClient()

  it.each([
    ['EP-14 /meta', () => queryClient().fetchQuery(getMetaOptions()), '/api/admin/v1/meta'],
    [
      'EP-13 /dashboard',
      () => queryClient().fetchQuery(getDashboardOptions()),
      '/api/admin/v1/dashboard',
    ],
    [
      'EP-12 /opensearch/cluster',
      () => queryClient().fetchQuery(getClusterOptions()),
      '/api/admin/v1/opensearch/cluster',
    ],
  ])('%s の URL にクエリが付かない', async (_name, fetchEndpoint, expectedPath) => {
    stub.respondWith(jsonResponse({}))

    await fetchEndpoint()

    expect(stub.requests).toHaveLength(1)
    expect(stub.requests[0]?.pathname).toBe(expectedPath)
    expect(stub.requests[0]?.search).toBe('')
    expect(stub.requests[0]?.url).not.toContain('?')
  })
})

describe('書き込みのリクエスト', () => {
  it('本文があるとき Content-Type: application/json を付ける(EP-06)', async () => {
    stub.respondWith(jsonResponse({ job_id: 'job-1' }, 202))

    await runMutation(createTestQueryClient(), startCrawlMutation(), {
      path: { source_id: 'demo' },
      body: { force_delete: false, rewrite_mode: true },
    })

    expect(stub.requests[0]).toMatchObject({
      method: 'POST',
      pathname: '/api/admin/v1/sources/demo/crawl-jobs',
      bodyJson: { force_delete: false, rewrite_mode: true },
    })
  })

  it('EP-03 の本文は渡したとおりに送る(ttl_days と ttl_seconds の使わない側を足さない)', async () => {
    stub.respondWith(jsonResponse({}, 201))

    await runMutation(createTestQueryClient(), registerSourceMutation(), {
      body: {
        source_id: 'demo',
        connector_type: 'file_system',
        connector_config: { root: '/data' },
        ttl_days: 30,
        ratio_threshold_percent: 20,
        min_delete_count: 10,
        schedule_cron: null,
      },
    })

    const body = stub.requests[0]?.bodyJson as Record<string, unknown>
    expect(body).not.toHaveProperty('ttl_seconds')
    expect(body.ttl_days).toBe(30)
  })
})

describe('タイムアウト付き fetch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const pendingForever = () => new Promise<never>(() => {})

  async function settle<T>(promise: Promise<T>): Promise<{ result: T } | { error: unknown }> {
    return promise.then(
      (result) => ({ result }),
      (error: unknown) => ({ error }),
    )
  }

  it('読み取り(GET)は 45 秒で時間切れになり、timeout として投げられる', async () => {
    stub.respondWith(pendingForever)
    const outcome = settle(createTestQueryClient().fetchQuery(getMetaOptions()))

    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS - 1)
    let settled = false
    void outcome.then(() => (settled = true))
    await vi.advanceTimersByTimeAsync(0)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(1)
    expect(await outcome).toEqual({ error: { kind: 'timeout' } })
  })

  it('書き込みは 90 秒で時間切れになる(45 秒では切れない)', async () => {
    stub.respondWith(pendingForever)
    const outcome = settle(
      runMutation(createTestQueryClient(), startCrawlMutation(), {
        path: { source_id: 'demo' },
        body: { force_delete: false, rewrite_mode: false },
      }),
    )

    let settled = false
    void outcome.then(() => (settled = true))
    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(WRITE_TIMEOUT_MS - READ_TIMEOUT_MS - 1)
    expect(settled).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(await outcome).toEqual({ error: { kind: 'timeout' } })
  })

  it('ヘッダー受信後に本文の受信が止まったときも、時間切れになる(本文の取得完了までが対象。FARC-U-22 (5))', async () => {
    // ヘッダーは返るが、本文のストリームが終わらない。
    stub.respondWith(
      () =>
        new Response(new ReadableStream({ start() {} }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    )
    const outcome = settle(createTestQueryClient().fetchQuery(getMetaOptions()))

    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS - 1)
    let settled = false
    void outcome.then(() => (settled = true))
    await vi.advanceTimersByTimeAsync(0)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(1)
    expect(await outcome).toEqual({ error: { kind: 'timeout' } })
  })

  it('ヘッダー受信後、本文が一部だけ届いて止まったときも時間切れになる', async () => {
    stub.respondWith(() => {
      const encoder = new TextEncoder()
      return new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode('{"cron_timezone":'))
          },
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )
    })
    const outcome = settle(createTestQueryClient().fetchQuery(getMetaOptions()))

    await vi.advanceTimersByTimeAsync(READ_TIMEOUT_MS)

    expect(await outcome).toEqual({ error: { kind: 'timeout' } })
  })

  it('時間内に本文まで届いたら、成功して data を返す(タイマーは残らない)', async () => {
    stub.respondWith(jsonResponse(META))

    const data = await createTestQueryClient().fetchQuery(getMetaOptions())

    expect(data).toEqual(META)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('失敗(HTTP エラー)でもタイマーは残らない', async () => {
    stub.respondWith(jsonResponse({ error: { code: 'unavailable', retryable: true } }, 503))

    await createTestQueryClient()
      .fetchQuery(getMetaOptions())
      .catch(() => {})

    expect(vi.getTimerCount()).toBe(0)
  })

  it('本文のないステータス(204)でも例外にならず、空の応答として読める', async () => {
    stub.respondWith(() => new Response(null, { status: 204 }))

    const data = await createTestQueryClient().fetchQuery(getMetaOptions())

    expect(data).toEqual({})
  })
})

describe('利用者側の中断(AbortError)とタイムアウトの区別', () => {
  const META_URL = 'http://localhost/api/admin/v1/meta'

  // Query が `queryFn` に渡す文脈(key とシグナル)を再現して、シグナルつきで取得する。
  async function queryWithSignal(signal: AbortSignal): Promise<unknown> {
    const options = getMetaOptions()
    const queryFn = options.queryFn as (context: unknown) => Promise<unknown>
    return queryFn({ queryKey: options.queryKey, signal, meta: undefined }).then(
      () => 'resolved',
      (error: unknown) => error,
    )
  }

  it('fetch の待ち中に中断すると AbortError(timeout にならず、ApiError にもならない)', async () => {
    stub.respondWith(() => new Promise<never>(() => {}))
    const controller = new AbortController()

    const outcome = queryWithSignal(controller.signal)
    await vi.waitFor(() => expect(stub.requests).toHaveLength(1))
    controller.abort()

    const error = await outcome
    expect(error).toMatchObject({ name: 'AbortError' })
    expect(error).not.toHaveProperty('kind')
  })

  it('本文の受信中に中断しても AbortError(本文の取得完了まで中断が伝わる)', async () => {
    stub.respondWith(
      () =>
        new Response(new ReadableStream({ start() {} }), {
          status: 200,
          headers: { 'content-type': 'application/json' },
        }),
    )
    const controller = new AbortController()

    const outcome = queryWithSignal(controller.signal)
    await vi.waitFor(() => expect(stub.requests).toHaveLength(1))
    // 本文の読み取りに入るまで少し待つ。
    await new Promise((resolve) => setTimeout(resolve, 10))
    controller.abort()

    expect(await outcome).toMatchObject({ name: 'AbortError' })
  })

  it('すでに中断されたシグナルでは、fetch を呼ばずに AbortError', async () => {
    stub.respondWith(jsonResponse(META))
    const controller = new AbortController()
    controller.abort()

    expect(await queryWithSignal(controller.signal)).toMatchObject({ name: 'AbortError' })
    expect(stub.requests.filter((request) => request.url === META_URL)).toHaveLength(0)
  })

  it('中断の理由(reason)をそのまま通す', async () => {
    stub.respondWith(() => new Promise<never>(() => {}))
    const controller = new AbortController()

    const outcome = queryWithSignal(controller.signal)
    await vi.waitFor(() => expect(stub.requests).toHaveLength(1))
    const reason = new DOMException('cancelled by caller', 'AbortError')
    controller.abort(reason)

    expect(await outcome).toBe(reason)
  })

  it('fetch に渡るシグナルは、呼び出し側のシグナルとは別(内側の AbortController)', async () => {
    stub.respondWith(jsonResponse(META))
    const controller = new AbortController()

    await queryWithSignal(controller.signal)

    expect(stub.requests[0]?.signal).toBeInstanceOf(AbortSignal)
    expect(stub.requests[0]?.signal).not.toBe(controller.signal)
  })
})
