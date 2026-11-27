// E2E の前に、dev サーバーを温める(最初のページ読み込み・依存の最適化・再読み込みを、テストの時間の外で済ませる)。
// 負荷の高い環境でも、最初のテストが「ページ読み込みの時間切れ」で落ちないようにするため。
import { chromium, type FullConfig } from '@playwright/test'

import { waitForViteReady } from '../support/viteReady'

export default async function globalSetup(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use.baseURL
  if (baseURL === undefined) throw new Error('baseURL が設定されていません(playwright.config.ts)')

  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ baseURL })
    await page.goto('./', { timeout: 120_000 })
    await waitForViteReady(page)
  } finally {
    await browser.close()
  }
}
