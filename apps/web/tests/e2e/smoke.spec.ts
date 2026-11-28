// 基盤の起動確認と、未モックの /api/ 検出の確認。シェル・ルーティングの E2E は shell.spec.ts。
import { expect as baseExpect, test as baseTest } from '@playwright/test'

import { jsonResponse } from '../support/apiErrors'
import { E2E_HOST } from '../support/e2eServer'
import { gotoBlankPage } from '../support/blankPage'
import { expect, test } from '../support/e2eTest'
import { dashboard } from '../support/fixtures/dashboard'
import { meta } from '../support/fixtures/meta'
import { mockApi } from '../support/mockApi'
import { guardUnmockedApi } from '../support/unmockedApi'

test('dev サーバーが /admin/ を配信し、SPA(シェルとダッシュボードの見出し)が描画される', async ({
  page,
}) => {
  // シェルは GET /meta(EP-14)を取る。未モックの /api/ は失敗になるので、モックする。
  await mockApi(page, {
    'GET /meta': jsonResponse(meta.noDashboards()),
    'GET /dashboard': jsonResponse(dashboard.allNormal()),
  })

  await page.goto('./')

  await expect(page).toHaveTitle('ダッシュボード - Loreley 管理')
  await expect(page.getByRole('navigation', { name: 'メインメニュー' })).toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')
})

test('ブラウザのタイムゾーンは Asia/Tokyo(UTC の 0 時が JST の 9 時)', async ({ page }) => {
  await gotoBlankPage(page)

  const hours = await page.evaluate(() => new Date('2026-01-01T00:00:00Z').getHours())

  expect(hours).toBe(9)
})

test.describe('未モックの /api/ の検出', () => {
  // 検出そのものの確認(記録の内容・エラー文)は、失敗を期待する形(test.fail)にせず、ガードを直接呼んで結果を確かめる。
  // 例外: 下の test.fail は、`e2eTest` の `page` フィクスチャが `guard.assertNone()` を実際に呼んでいること
  // (テストの終了時に未モックの要求を失敗にする配線)の確認。呼び出しを消すと、このテストは「失敗するはずが通った」で落ちる。
  baseTest('未モックの /api/ への要求を記録し、失敗として報告する', async ({ page }) => {
    const guard = await guardUnmockedApi(page)

    await page.goto('/api/admin/v1/meta').catch(() => {})

    baseExpect(guard.unmockedRequests).toEqual([`GET http://${E2E_HOST}/api/admin/v1/meta`])
    baseExpect(() => guard.assertNone()).toThrow(
      new RegExp(
        `未モックの /api/ への要求があります:\\n {2}GET http://${E2E_HOST.replace('.', '\\.')}/api/admin/v1/meta`,
      ),
    )
  })

  test.fail(
    'e2eTest の test は、未モックの /api/admin/v1/meta を叩いたテストを、終了時に失敗にする(assertNone の配線)',
    async ({ page }) => {
      await page.goto('/api/admin/v1/meta').catch(() => {})
    },
  )

  test('後から登録したモックが優先され、未モック扱いにならない', async ({ page }) => {
    await page.route('**/api/admin/v1/meta', (route) =>
      route.fulfill({ json: { mocked: true }, contentType: 'application/json' }),
    )

    const response = await page.goto('/api/admin/v1/meta')

    expect(response?.status()).toBe(200)
    expect(await response?.json()).toEqual({ mocked: true })
  })

  test('Vite のモジュール URL(/admin/src/admin/api/…)は中断されない', async ({ page }) => {
    const response = await page.goto('src/admin/api/generated/client.gen.ts')

    expect(response?.status()).toBe(200)
    expect(await response?.text()).toContain('baseUrl')
  })
})
