// 基盤の起動確認。画面の E2E はフェーズ 3 以降で書く。
import { expect, test } from '../support/e2eTest'

test('dev サーバーが /admin/ を配信し、SPA が描画される', async ({ page }) => {
  await page.goto('./')

  await expect(page).toHaveTitle('Loreley Admin')
  await expect(page.getByText('Admin View(準備中)')).toBeVisible()
})

test.describe('未モックの /api/ への要求', () => {
  // テストが失敗すること(未モックの要求を検出すること)を期待する。
  test.fail()

  test('テストを失敗させる', async ({ page }) => {
    await page.goto('./')
    // `/admin/` の外の絶対パス。開発プロキシの先(到達不能)ではなく、捕捉に届く。
    await page.goto('/api/admin/v1/meta').catch(() => {})
  })
})
