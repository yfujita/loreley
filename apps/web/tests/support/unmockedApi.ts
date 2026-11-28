import type { Page } from '@playwright/test'

/**
 * Admin API(origin 直下の `/api/`)への要求か。
 * glob(`**\/api/**`)では、Vite の dev サーバーが返すモジュール(`/admin/src/admin/api/…`)にも一致して
 * 誤検出するので、URL のパスの先頭で判定する。
 */
export function isApiRequestUrl(url: string): boolean {
  return new URL(url).pathname.startsWith('/api/')
}

/**
 * モックしていない `/api/` への要求を中断し、記録する(E 10.2)。
 * 個別のモック(`page.route`)は、後から登録したものが優先されるので、この捕捉より前に呼ばれる。
 * 本実装(`mockApi.ts`・フィクスチャ)はフェーズ 2 で作る。
 */
export async function guardUnmockedApi(page: Page): Promise<{
  unmockedRequests: readonly string[]
  assertNone: () => void
}> {
  const unmockedRequests: string[] = []
  await page.route(
    (url) => isApiRequestUrl(url.href),
    (route) => {
      unmockedRequests.push(`${route.request().method()} ${route.request().url()}`)
      return route.abort('failed')
    },
  )

  return {
    unmockedRequests,
    assertNone() {
      if (unmockedRequests.length === 0) return
      throw new Error(
        `未モックの /api/ への要求があります:\n${unmockedRequests.map((request) => `  ${request}`).join('\n')}`,
      )
    },
  }
}
