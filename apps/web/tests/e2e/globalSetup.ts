// E2E の前に、dev サーバーを温める(最初のページ読み込みで、アプリのモジュールの変換を済ませる)。
// 冷えた dev サーバーに、複数のワーカーが同時にページを読み込むと、最初のテストが時間切れになることがあるため
// (負荷の高い環境。テストの時間の外で 1 回だけ済ませる)。
// Vite の依存の最適化は、アプリ(main.ts)が使う依存(Vue Query を含む)を起動時に見つけるので、待つ処理は要らない。
import { chromium, type FullConfig } from '@playwright/test'

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL
  if (baseURL === undefined) throw new Error('baseURL が設定されていません(playwright.config.ts)')

  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ baseURL })
    // アプリはシェルのために GET /meta を取る。ここは API をモックしない(失敗してよい。転送先は届かない)。
    await page.goto('./', { timeout: 120_000, waitUntil: 'load' })
    await page.getByRole('heading', { level: 1 }).waitFor({ timeout: 120_000 })
  } finally {
    await browser.close()
  }
}
