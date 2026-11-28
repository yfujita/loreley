// API クライアント(`configureApiClient`)の、実ブラウザ(Chromium)での確認(E の FARC-U-22。FMOD-U-12)。
// jsdom の単体テスト(client.test.ts など)では確かめられない点を、dev サーバーが配信するモジュールを読み込んで確かめる:
// 相対 `baseUrl` の `Request` が解決されること、`TypeError`・HTML・タイムアウト・中断が期待どおり ApiError になること、
// key の差し替え(withKey)が実ブラウザの取得・invalidate で動くこと。画面の E2E はフェーズ 3 以降。
import type { Page } from '@playwright/test'

import {
  apiErrorResponse,
  hangResponse,
  jsonResponse,
  networkErrorResponse,
  nginxHtmlResponse,
} from '../support/apiErrors'
import { gotoBlankPage } from '../support/blankPage'
import { expect, test } from '../support/e2eTest'
import { dashboard } from '../support/fixtures/dashboard'
import { jobDetails } from '../support/fixtures/jobs'
import { meta } from '../support/fixtures/meta'
import { sourceDetails } from '../support/fixtures/sources'
import { mockApi } from '../support/mockApi'
import { evaluateInBrowser } from '../support/browser'

/** `configureApiClient()` を呼んだ公開口(`api`)と、アプリの QueryClient(`queryClient`)を使える状態で `body` を実行する。 */
async function inBrowser<T>(page: Page, body: string): Promise<T> {
  return evaluateInBrowser<T>(
    page,
    `
    // R2(テストが admin/api の中身を直接 import しない)の例外: dev サーバーが配信するモジュールを、ブラウザの中で読む。
    const api = await import('/admin/src/admin/api/index.ts')
    const { createAppQueryClient } = await import('/admin/src/admin/queries/queryClient.ts')
    api.configureApiClient()
    const queryClient = createAppQueryClient()
    ${body}
  `,
  )
}

// アプリを起動しない空のページ(同一オリジン)で、dev サーバーが配信するモジュールを読み込む。
test.beforeEach(async ({ page }) => {
  await gotoBlankPage(page)
})

test('相対 baseUrl(/api/admin/v1)の Request が、実ブラウザでは解決される(jsdom では解決されない)', async ({
  page,
}) => {
  const mock = await mockApi(page, { 'GET /meta': jsonResponse(meta.normal()) })

  const data = await inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getMetaOptions())`,
  )

  expect(data).toEqual(meta.normal())
  expect(mock.requests.map((request) => request.path)).toEqual(['/meta'])
})

test('JSON のエラーは kind=api の ApiError として投げられる', async ({ page }) => {
  await mockApi(page, { 'GET /meta': apiErrorResponse(503, 'unavailable', { retryable: true }) })

  const error = await inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getMetaOptions()).catch((e) => e)`,
  )

  expect(error).toEqual({
    kind: 'api',
    status: 503,
    code: 'unavailable',
    retryable: true,
    outcomeUnknown: false,
  })
})

test('Nginx の HTML の 502 は invalid_response(status つき)になる', async ({ page }) => {
  await mockApi(page, { 'GET /meta': nginxHtmlResponse(502) })

  const error = await inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getMetaOptions()).catch((e) => e)`,
  )

  expect(error).toEqual({ kind: 'invalid_response', status: 502 })
})

test('2xx で本文が JSON でない(HTML)は invalid_response(status 200)になる', async ({ page }) => {
  await mockApi(page, {
    'GET /meta': { kind: 'response', status: 200, contentType: 'text/html', body: '<html></html>' },
  })

  const error = await inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getMetaOptions()).catch((e) => e)`,
  )

  expect(error).toEqual({ kind: 'invalid_response', status: 200 })
})

test('通信断(接続できない・切断。fetch が TypeError)は network になる', async ({ page }) => {
  await mockApi(page, { 'GET /meta': networkErrorResponse() })

  const error = await inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getMetaOptions()).catch((e) => e)`,
  )

  expect(error).toEqual({ kind: 'network' })
})

test('通信断の再試行は 1 回だけで、それでも失敗したら network(読み取り)', async ({ page }) => {
  const mock = await mockApi(page, { 'GET /meta': networkErrorResponse() })

  const error = await inBrowser<unknown>(
    page,
    // retryDelay(1 秒)は QueryClient の既定値。実時間で 1 秒待つ。
    `return await queryClient.fetchQuery(api.getMetaOptions()).catch((e) => e)`,
  )

  expect(error).toEqual({ kind: 'network' })
  expect(mock.callCount('GET /meta')).toBe(2)
})

test('パス値の検証: `..` のジョブ ID は送信せずに、合成の 400 invalid_request になる(ブラウザの URL の正規化に化けない)', async ({
  page,
}) => {
  const mock = await mockApi(page, {
    'GET /jobs': jsonResponse({ items: [] }),
    'GET /jobs/..': jsonResponse({}),
  })

  const error = await inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getJobOptions({ path: { job_id: '..' } })).catch((e) => e)`,
  )

  expect(error).toMatchObject({ kind: 'api', status: 400, code: 'invalid_request' })
  expect(mock.requests).toEqual([])
})

// FMOD-U-9: `.` を含むだけの ID は、値全体が `.`・`..` ではないので、ブラウザの URL の正規化に化けず、そのまま送られる。
for (const jobId of ['a.b', '..a', 'a..', '...']) {
  test(`\`.\` を含むだけの ID(${jobId})は拒否されず、そのままのパスで送られる`, async ({
    page,
  }) => {
    const mock = await mockApi(page, {
      [`GET /jobs/${jobId}`]: jsonResponse({ ...jobDetails.succeeded(), job_id: jobId }),
    })

    await inBrowser(
      page,
      `return await queryClient.fetchQuery(api.getJobOptions({ path: { job_id: '${jobId}' } }))`,
    )

    expect(mock.requests.map((request) => request.path)).toEqual([`/jobs/${jobId}`])
  })
}

test('利用者側の中断(AbortError)は、timeout にならず ApiError にもならない', async ({ page }) => {
  const mock = await mockApi(page, { 'GET /meta': hangResponse() })

  // 取得を始める(完了を待たない)。
  await inBrowser(
    page,
    `
    const controller = new AbortController()
    const options = api.getMetaOptions()
    window.__abortTest = {
      controller,
      pending: options.queryFn({ queryKey: options.queryKey, signal: controller.signal }).catch((e) => e),
    }
    return true
    `,
  )
  // fetch が実際に通信中(要求がサーバー側に届き、応答待ち)になってから中断する。
  await expect.poll(() => mock.requests.length).toBe(1)
  const result = await evaluateInBrowser<{ name: string | null; hasKind: boolean }>(
    page,
    `
    window.__abortTest.controller.abort()
    const error = await window.__abortTest.pending
    return { name: error?.name ?? null, hasKind: 'kind' in (error ?? {}) }
    `,
  )

  expect(result).toEqual({ name: 'AbortError', hasKind: false })
})

test('45 秒で時間切れになり timeout になる(読み取り。Playwright の時計で進める)', async ({
  page,
}) => {
  const mock = await mockApi(page, { 'GET /meta': hangResponse() })
  // 時計を止める(実時間で進まないようにする)。境界(44,999 ミリ秒と 45,000 ミリ秒)を、実時間のずれなしに確かめるため。
  await page.clock.install({ time: new Date('2026-01-01T00:00:00Z') })
  await page.clock.pauseAt(new Date('2026-01-01T00:00:10Z'))

  // 取得を始める(完了を待たない)。結果は Node 側で受ける。
  let outcome: unknown = 'pending'
  const pending = inBrowser<unknown>(
    page,
    `return await queryClient.fetchQuery(api.getMetaOptions()).catch((e) => e)`,
  ).then((value) => (outcome = value))
  // fetch が実際に通信中になってから(タイマーは fetch の前に登録される)、時計を進める。
  await expect.poll(() => mock.requests.length).toBe(1)

  // 境界: 44,999 ミリ秒ではまだ時間切れにならない(ページとの往復を 2 回挟んで、時間切れの結果が届く余地を与える)。
  await page.clock.fastForward(44_999)
  await page.evaluate(() => 0)
  await page.evaluate(() => 0)
  expect(outcome).toBe('pending')

  await page.clock.fastForward(1)
  await pending
  expect(outcome).toEqual({ kind: 'timeout' })
})

test('withKey の key の差し替え: 取得はドメインの key で QueryCache に入り、prefix の invalidate で再取得される(実ブラウザ)', async ({
  page,
}) => {
  const mock = await mockApi(page, {
    'GET /sources/demo': jsonResponse({ ...sourceDetails.normal(), source_id: 'demo' }),
    'GET /dashboard': jsonResponse(dashboard.allNormal()),
  })

  const result = await inBrowser<{ states: unknown[]; keys: unknown[] }>(
    page,
    `
    const { withKey } = await import('/admin/src/admin/queries/withKey.ts')
    const { keys } = await import('/admin/src/admin/queries/keys.ts')
    await queryClient.fetchQuery(withKey(api.getSourceOptions({ path: { source_id: 'demo' } }), keys.sources.detail('demo')))
    await queryClient.fetchQuery(withKey(api.getDashboardOptions(), keys.dashboard()))
    const stored = queryClient.getQueryCache().getAll().map((query) => query.queryKey)
    await queryClient.invalidateQueries({ queryKey: keys.sources.all, refetchType: 'none' })
    return {
      keys: stored,
      states: [
        queryClient.getQueryState(keys.sources.detail('demo')).isInvalidated,
        queryClient.getQueryState(keys.dashboard()).isInvalidated,
      ],
    }
    `,
  )

  expect(result.keys).toEqual([['sources', 'detail', 'demo'], ['dashboard']])
  expect(result.states).toEqual([true, false])
  expect(mock.requests.map((request) => request.path)).toEqual(['/sources/demo', '/dashboard'])
})
