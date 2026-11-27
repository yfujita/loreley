import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  cancelJobMutation,
  configureApiClient,
  getClusterOptions,
  getDashboardOptions,
  getMetaOptions,
  registerSourceMutation,
  releaseLockMutation,
  startCrawlMutation,
} from '@/admin/api'

import {
  emptyBodyResponse,
  hangResponse,
  jsonResponse,
  type MockResponse,
} from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { dashboard } from '../../../tests/support/fixtures/dashboard'
import { jobAccepted } from '../../../tests/support/fixtures/jobs'
import { meta } from '../../../tests/support/fixtures/meta'
import { opensearch } from '../../../tests/support/fixtures/opensearch'
import { savedSettings } from '../../../tests/support/fixtures/sources'
import { createTestQueryClient, runMutation } from '../../../tests/support/queryTesting'
import { fetchWithTimeout, READ_TIMEOUT_MS, WRITE_TIMEOUT_MS } from './client'
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

  it('2 回呼んでも interceptor が二重に登録されない(request・response・error が 1 つずつ)', async () => {
    const { client, configureApiClient } = await loadFreshModules()

    configureApiClient()
    configureApiClient()
    configureApiClient()

    const registered = (fns: Array<unknown>) => fns.filter((fn) => fn !== null)
    expect(registered(client.interceptors.request.fns)).toHaveLength(1)
    expect(registered(client.interceptors.error.fns)).toHaveLength(1)
    expect(registered(client.interceptors.response.fns)).toHaveLength(1)
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
    [
      'EP-14 /meta',
      () => queryClient().fetchQuery(getMetaOptions()),
      '/api/admin/v1/meta',
      meta.normal(),
    ],
    [
      'EP-13 /dashboard',
      () => queryClient().fetchQuery(getDashboardOptions()),
      '/api/admin/v1/dashboard',
      dashboard.allNormal(),
    ],
    [
      'EP-12 /opensearch/cluster',
      () => queryClient().fetchQuery(getClusterOptions()),
      '/api/admin/v1/opensearch/cluster',
      opensearch.green(),
    ],
  ])('%s の URL にクエリが付かない', async (_name, fetchEndpoint, expectedPath, response) => {
    stub.respondWith(jsonResponse(response))

    await fetchEndpoint()

    expect(stub.requests).toHaveLength(1)
    expect(stub.requests[0]?.pathname).toBe(expectedPath)
    expect(stub.requests[0]?.search).toBe('')
    expect(stub.requests[0]?.url).not.toContain('?')
  })
})

describe('書き込みのリクエスト', () => {
  it('本文があるとき Content-Type: application/json を付ける(EP-06)', async () => {
    stub.respondWith(jsonResponse(jobAccepted.crawl(), 202))

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
    stub.respondWith(jsonResponse(savedSettings.registered(), 201))

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

describe('2xx の本文の検査(空・JSON のオブジェクトでないものは invalid_response)', () => {
  async function failureFor(mock: Parameters<typeof stub.respondWith>[0]) {
    stub.respondWith(mock)
    return createTestQueryClient()
      .fetchQuery(getMetaOptions())
      .then(
        (data) => ({ data }),
        (error: unknown) => ({ error }),
      )
  }

  it('空の本文の 200 は、`{}` を成功として返さず invalid_response(status 200)', async () => {
    expect(await failureFor(emptyBodyResponse(200))).toEqual({
      error: { kind: 'invalid_response', status: 200 },
    })
  })

  it('空の本文の 202(取消の受付など)も invalid_response(status 202)', async () => {
    stub.respondWith(emptyBodyResponse(202))

    const error = await runMutation(createTestQueryClient(), cancelJobMutation(), {
      path: { job_id: 'job-1' },
    }).catch((caught: unknown) => caught)

    expect(error).toEqual({ kind: 'invalid_response', status: 202 })
  })

  it('`content-length: 0` を付けた空の 200(読み取り)も、検証を迂回せず invalid_response(status 200)', async () => {
    const withContentLengthZero = (status: number): MockResponse => ({
      kind: 'response',
      status,
      contentType: 'application/json',
      body: '',
      headers: { 'content-length': '0' },
    })

    expect(await failureFor(withContentLengthZero(200))).toEqual({
      error: { kind: 'invalid_response', status: 200 },
    })
  })

  it('`content-length: 0` を付けた空の 202(書き込み)も invalid_response(status 202)', async () => {
    stub.respondWith({
      kind: 'response',
      status: 202,
      contentType: 'application/json',
      body: '',
      headers: { 'content-length': '0' },
    })

    const error = await runMutation(createTestQueryClient(), cancelJobMutation(), {
      path: { job_id: 'job-1' },
    }).catch((caught: unknown) => caught)

    expect(error).toEqual({ kind: 'invalid_response', status: 202 })
  })

  it('本文ありの応答は、元の content-length(圧縮後の長さなど不正確な値)が外されても、正常に読める', async () => {
    const body = JSON.stringify(META)

    // 実際の長さとは違う content-length(圧縮された応答の、圧縮後の長さを想定)
    const data = await failureFor({
      kind: 'response',
      status: 200,
      contentType: 'application/json',
      body,
      headers: { 'content-length': '3' },
    })

    expect(data).toEqual({ data: META })
  })

  it.each([204, 205])(
    '%i(本文なし)は、`{}` を成功として返さず invalid_response(status つき)。Admin API は返さない(OpenAPI に 204 がない)',
    async (status) => {
      expect(await failureFor(() => new Response(null, { status }) as never)).toEqual({
        error: { kind: 'invalid_response', status },
      })
    },
  )

  it('書き込み(起動・取消・解放)の 204 も invalid_response になり、成功として扱われない(結果不明の導線に載る)', async () => {
    stub.respondWith(() => new Response(null, { status: 204 }))

    const error = await runMutation(createTestQueryClient(), cancelJobMutation(), {
      path: { job_id: 'job-1' },
    }).catch((caught: unknown) => caught)

    expect(error).toEqual({ kind: 'invalid_response', status: 204 })
  })

  it.each([
    ['`{}`(項目のないオブジェクト)', '{}'],
    ['`null`', 'null'],
    ['配列', '[1]'],
    ['文字列', '"ok"'],
    ['数値', '1'],
  ])('JSON の本文が %s のときは invalid_response(status 200)', async (_name, body) => {
    expect(
      await failureFor({ kind: 'response', status: 200, contentType: 'application/json', body }),
    ).toEqual({ error: { kind: 'invalid_response', status: 200 } })
  })

  it('項目を持つオブジェクトは成功として返す', async () => {
    expect(await failureFor(jsonResponse(META))).toEqual({ data: META })
  })
})

describe('タイムアウト付き fetch が返す Response', () => {
  it('本文を読み切って作り直した Response も、status・statusText・headers・本文を保つ', async () => {
    stub.respondWith(
      () =>
        new Response('{"a":1}', {
          status: 202,
          statusText: 'Accepted',
          headers: { 'content-type': 'application/json', 'x-trace': 'abc' },
        }),
    )

    const response = await fetchWithTimeout(new Request('http://localhost/api/admin/v1/meta'))

    expect(response.status).toBe(202)
    expect(response.statusText).toBe('Accepted')
    expect(response.headers.get('x-trace')).toBe('abc')
    expect(response.headers.get('content-type')).toBe('application/json')
    expect(await response.json()).toEqual({ a: 1 })
  })

  it('content-length を外して Response を作り直す(読み切った本文と食い違う値を残さない)', async () => {
    stub.respondWith({
      kind: 'response',
      status: 200,
      contentType: 'application/json',
      body: '{"a":1}',
      headers: { 'content-length': '999' },
    })

    const response = await fetchWithTimeout(new Request('http://localhost/api/admin/v1/meta'))

    expect(response.headers.has('content-length')).toBe(false)
    expect(response.headers.get('content-type')).toBe('application/json')
    expect(await response.json()).toEqual({ a: 1 })
  })

  it('本文を持てないステータス(204・304)でも、例外にならず本文は空', async () => {
    for (const status of [204, 304]) {
      stub.respondWith(() => new Response(null, { status }))

      const response = await fetchWithTimeout(new Request('http://localhost/api/admin/v1/meta'))

      expect(response.status).toBe(status)
      expect(await response.text()).toBe('')
    }
  })
})

describe('2xx の最小限の形(EP ごと。responseShapes.ts)を満たさない応答は invalid_response', () => {
  async function readFailure(fetchData: () => Promise<unknown>, mock: MockResponse) {
    stub.respondWith(mock)
    return fetchData().then(
      (data) => ({ data }),
      (error: unknown) => ({ error }),
    )
  }

  it('Dashboard が {"status":"ok"} のとき、成功として view model に渡さず invalid_response(status 200)', async () => {
    expect(
      await readFailure(
        () => createTestQueryClient().fetchQuery(getDashboardOptions()),
        jsonResponse({ status: 'ok' }),
      ),
    ).toEqual({
      error: { kind: 'invalid_response', status: 200 },
    })
  })

  it.each([
    ['indices が配列でない', { ...opensearch.green(), indices: {} }],
    ['nodes がない', { ...opensearch.green(), nodes: undefined }],
    [
      'shards の要素に node のキーがない(未割り当てと取り違えない)',
      {
        ...opensearch.green(),
        shards: [{ index: 'a', shard: 0, role: 'primary', state: 'started' }],
      },
    ],
    [
      'cluster の件数が文字列',
      { ...opensearch.green(), cluster: { ...opensearch.green().cluster, node_count: '1' } },
    ],
  ])('O1: %s', async (_name, body) => {
    expect(
      await readFailure(
        () => createTestQueryClient().fetchQuery(getClusterOptions()),
        jsonResponse(body),
      ),
    ).toEqual({
      error: { kind: 'invalid_response', status: 200 },
    })
  })

  it('形の合った応答は、そのまま成功として返す(フィクスチャの正常な応答)', async () => {
    expect(
      await readFailure(
        () => createTestQueryClient().fetchQuery(getClusterOptions()),
        jsonResponse(opensearch.green()),
      ),
    ).toEqual({
      data: opensearch.green(),
    })
  })

  it('書き込みの受付(202)で job_id がないとき、成功にせず invalid_response(status 202)', async () => {
    stub.respondWith(jsonResponse({ status: 'queued' }, 202))

    const error = await runMutation(createTestQueryClient(), startCrawlMutation(), {
      path: { source_id: 'demo' },
      body: { force_delete: false, rewrite_mode: false },
    }).catch((caught: unknown) => caught)

    expect(error).toEqual({ kind: 'invalid_response', status: 202 })
  })

  it('ロック解放(200)で released がないとき、成功にしない', async () => {
    stub.respondWith(jsonResponse({ source_id: 'demo' }))

    const error = await runMutation(createTestQueryClient(), releaseLockMutation(), {
      path: { source_id: 'demo' },
    }).catch((caught: unknown) => caught)

    expect(error).toEqual({ kind: 'invalid_response', status: 200 })
  })
})

describe('タイムアウトの値(設計 E 5.3: 読み取り 45 秒・書き込み 90 秒。実装の定数ではなくリテラルで固定する)', () => {
  it('定数は 45 秒・90 秒', () => {
    expect(READ_TIMEOUT_MS).toBe(45_000)
    expect(WRITE_TIMEOUT_MS).toBe(90_000)
  })
})

describe('タイムアウト付き fetch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  async function settle<T>(promise: Promise<T>): Promise<{ result: T } | { error: unknown }> {
    return promise.then(
      (result) => ({ result }),
      (error: unknown) => ({ error }),
    )
  }

  it('読み取り(GET)は 45 秒で時間切れになり、timeout として投げられる', async () => {
    stub.respondWith(hangResponse())
    const outcome = settle(createTestQueryClient().fetchQuery(getMetaOptions()))

    await vi.advanceTimersByTimeAsync(44_999)
    let settled = false
    void outcome.then(() => (settled = true))
    await vi.advanceTimersByTimeAsync(0)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(1)
    expect(await outcome).toEqual({ error: { kind: 'timeout' } })
  })

  it('書き込みは 90 秒で時間切れになる(45 秒では切れない)', async () => {
    stub.respondWith(hangResponse())
    const outcome = settle(
      runMutation(createTestQueryClient(), startCrawlMutation(), {
        path: { source_id: 'demo' },
        body: { force_delete: false, rewrite_mode: false },
      }),
    )

    let settled = false
    void outcome.then(() => (settled = true))
    await vi.advanceTimersByTimeAsync(45_000)
    expect(settled).toBe(false)

    await vi.advanceTimersByTimeAsync(44_999)
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

    await vi.advanceTimersByTimeAsync(44_999)
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

    await vi.advanceTimersByTimeAsync(45_000)

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
    stub.respondWith(hangResponse())
    const controller = new AbortController()

    const outcome = queryWithSignal(controller.signal)
    await vi.waitFor(() => expect(stub.requests).toHaveLength(1))
    controller.abort()

    const error = await outcome
    expect(error).toMatchObject({ name: 'AbortError' })
    expect(error).not.toHaveProperty('kind')
  })

  it('本文の受信中に中断しても AbortError(本文の取得完了まで中断が伝わる)', async () => {
    // `pull` は、本文の読み取りが始まったときに呼ばれる。ヘッダーは返るが、本文は終わらない。
    let bodyReadStarted = false
    stub.respondWith(
      () =>
        new Response(
          new ReadableStream({
            pull() {
              bodyReadStarted = true
              return new Promise<void>(() => {})
            },
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        ),
    )
    const controller = new AbortController()

    const outcome = queryWithSignal(controller.signal)
    await vi.waitFor(() => expect(bodyReadStarted).toBe(true))
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
    stub.respondWith(hangResponse())
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
