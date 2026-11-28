// mockApi の動作確認(Playwright の route 経由で、実際のブラウザの fetch に応答できること)。
// 画面の E2E は各画面のフェーズ。ここは、モックの宣言・応答の列・通信断・未モックの扱いという、テスト基盤の確認。
import {
  apiErrorResponse,
  jsonResponse,
  networkErrorResponse,
  nginxHtmlResponse,
} from '../support/apiErrors'
import { expect, test } from '../support/e2eTest'
import { dashboard } from '../support/fixtures/dashboard'
import { meta } from '../support/fixtures/meta'
import { mockApi } from '../support/mockApi'
import { gotoBlankPage } from '../support/blankPage'
import { guardUnmockedApi } from '../support/unmockedApi'
import { test as baseTest, expect as baseExpect } from '@playwright/test'

type FetchResult = { status: number; contentType: string | null; text: string } | { failed: true }

/** ページの中から fetch する(アプリのコードと同じく、ブラウザの fetch が route に捕捉される)。 */
async function fetchInPage(
  page: import('@playwright/test').Page,
  path: string,
  init?: { method?: string; body?: string },
): Promise<FetchResult> {
  return page.evaluate(
    async ([url, options]) => {
      try {
        // ブラウザの中で、アプリの fetch を再現する(Node 側の fetch の呼び出しではない)。
        // eslint-disable-next-line no-restricted-globals -- 上記の理由
        const response = await fetch(url, {
          method: options?.method ?? 'GET',
          ...(options?.body !== undefined && {
            body: options.body,
            headers: { 'content-type': 'application/json' },
          }),
        })
        return {
          status: response.status,
          contentType: response.headers.get('content-type'),
          text: await response.text(),
        }
      } catch {
        return { failed: true as const }
      }
    },
    [`/api/admin/v1${path}`, init] as const,
  )
}

test.describe('mockApi', () => {
  test.beforeEach(async ({ page }) => {
    await gotoBlankPage(page)
  })

  test('固定の応答を返し、生成型で型付けしたフィクスチャの JSON が届く', async ({ page }) => {
    await mockApi(page, { 'GET /meta': jsonResponse(meta.normal()) })

    const result = await fetchInPage(page, '/meta')

    expect(result).toMatchObject({ status: 200, contentType: 'application/json' })
    expect(JSON.parse((result as { text: string }).text)).toEqual(meta.normal())
  })

  test('クエリは表のキーに含めず、関数の応答が受け取る', async ({ page }) => {
    await mockApi(page, {
      'GET /jobs': (request) =>
        jsonResponse({
          page: request.searchParams.get('page'),
          size: request.searchParams.get('items_per_page'),
        }),
    })

    const result = await fetchInPage(page, '/jobs?page=2&items_per_page=50')

    expect(JSON.parse((result as { text: string }).text)).toEqual({ page: '2', size: '50' })
  })

  test('本文つきの要求を記録する', async ({ page }) => {
    const mock = await mockApi(page, {
      'POST /sources/demo/crawl-jobs': jsonResponse({ job_id: 'job-1' }, 202),
    })

    await fetchInPage(page, '/sources/demo/crawl-jobs', {
      method: 'POST',
      body: JSON.stringify({ force_delete: false, rewrite_mode: true }),
    })

    expect(mock.requests).toEqual([
      expect.objectContaining({
        method: 'POST',
        path: '/sources/demo/crawl-jobs',
        bodyJson: { force_delete: false, rewrite_mode: true },
      }),
    ])
  })

  test('応答の列: n 回目に n 番目、足りなければ最後を繰り返す(ポーリング・再取得の検証)', async ({
    page,
  }) => {
    const mock = await mockApi(page, {
      'GET /dashboard': [jsonResponse(dashboard.allNormal()), jsonResponse(dashboard.abnormal())],
    })

    const statuses = []
    for (let call = 0; call < 3; call += 1) {
      const result = await fetchInPage(page, '/dashboard')
      const body = JSON.parse((result as { text: string }).text) as ReturnType<
        typeof dashboard.allNormal
      >
      statuses.push(body.components[0]?.state)
    }

    expect(statuses).toEqual(['normal', 'abnormal', 'abnormal'])
    expect(mock.callCount('GET /dashboard')).toBe(3)
  })

  test('応答を差し替えると、呼び出し回数もリセットされる', async ({ page }) => {
    const mock = await mockApi(page, { 'GET /meta': jsonResponse(meta.normal()) })
    await fetchInPage(page, '/meta')

    mock.respond('GET /meta', jsonResponse(meta.noDashboards()))
    const result = await fetchInPage(page, '/meta')

    expect(JSON.parse((result as { text: string }).text)).toEqual(meta.noDashboards())
    expect(mock.callCount('GET /meta')).toBe(1)
  })

  test('JSON のエラー・Nginx の HTML・通信断を作れる', async ({ page }) => {
    await mockApi(page, {
      'GET /jobs/missing': apiErrorResponse(404, 'job_not_found'),
      'GET /jobs/gateway': nginxHtmlResponse(502),
      'GET /jobs/offline': networkErrorResponse(),
    })

    const notFound = await fetchInPage(page, '/jobs/missing')
    const gateway = await fetchInPage(page, '/jobs/gateway')
    const offline = await fetchInPage(page, '/jobs/offline')

    expect(notFound).toMatchObject({ status: 404, contentType: 'application/json' })
    expect(JSON.parse((notFound as { text: string }).text).error.code).toBe('job_not_found')
    expect(gateway).toMatchObject({ status: 502, contentType: 'text/html' })
    expect(offline).toEqual({ failed: true })
  })

  test('エンコードされたパス(`%2F`)は、エンコードされたまま表のキーに照合される', async ({
    page,
  }) => {
    await mockApi(page, { 'GET /jobs/a%2Fb': jsonResponse({ ok: true }) })

    const result = await fetchInPage(page, '/jobs/a%2Fb')

    expect(result).toMatchObject({ status: 200 })
  })
})

test.describe('未モックの /api/ の扱い', () => {
  // 検出そのものの確認なので、失敗を期待する形(test.fail)にせず、ガードを直接呼んで結果を確かめる。
  baseTest(
    '表にない /api/admin/v1/ の要求は、捕捉に落ちて失敗として報告される',
    async ({ page }) => {
      await gotoBlankPage(page)
      const guard = await guardUnmockedApi(page)
      await mockApi(page, { 'GET /meta': jsonResponse(meta.normal()) })

      const mocked = await fetchInPage(page, '/meta')
      const unmocked = await fetchInPage(page, '/dashboard')

      baseExpect(mocked).toMatchObject({ status: 200 })
      baseExpect(unmocked).toEqual({ failed: true })
      baseExpect(guard.unmockedRequests).toEqual([
        expect.stringMatching(/^GET http:\/\/localhost:\d+\/api\/admin\/v1\/dashboard$/),
      ])
      baseExpect(() => guard.assertNone()).toThrow(/未モックの \/api\/ への要求があります/)
    },
  )

  test('Vite のモジュール URL(/admin/src/admin/api/…)は、モックの対象にならない', async ({
    page,
  }) => {
    await mockApi(page, { 'GET /meta': jsonResponse(meta.normal()) })

    const response = await page.goto('src/admin/api/index.ts')

    expect(response?.status()).toBe(200)
    expect(await response?.text()).toContain('configureApiClient')
  })
})
