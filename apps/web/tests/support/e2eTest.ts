import { expect, test as base } from '@playwright/test'

/**
 * E2E 用の `test`。モックしていない `/api/` への要求は、中断してテストを失敗させる(E 10.2)。
 * 個別のモック(`page.route`)は、後から登録したものが優先されるので、この捕捉より前に呼ばれる。
 * 本実装(`mockApi.ts`・フィクスチャ)はフェーズ 2 で作る。ここは未モックの検出だけ。
 */
export const test = base.extend({
  page: async ({ page }, use) => {
    const unmockedApiRequests: string[] = []
    await page.route('**/api/**', (route) => {
      unmockedApiRequests.push(`${route.request().method()} ${route.request().url()}`)
      return route.abort('failed')
    })

    await use(page)

    expect(unmockedApiRequests, '未モックの /api/ への要求があります').toEqual([])
  },
})

export { expect }
