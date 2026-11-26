import { defineConfig, devices } from '@playwright/test'

// E2E 専用のポート。手動確認・UI レビュー用の dev サーバー(5173)と衝突させず、既存のサーバーも再利用しない。
// (設計 E 10.2 は 5173・reuseExistingServer: !CI。起動中の dev サーバーを使うと、転送先が実環境のまま
//  モックの漏れが実 API に届くため、専用ポート・再利用なしに変えた。)
const E2E_PORT = 15173
const E2E_BASE_URL = `http://localhost:${E2E_PORT}/admin/`

export default defineConfig({
  testDir: 'tests/e2e',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  use: {
    // 末尾のスラッシュが要る。遷移は先頭にスラッシュのない相対パス(`goto('sources')`)で書く。
    baseURL: E2E_BASE_URL,
    timezoneId: 'Asia/Tokyo',
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npm run dev -- --port ${E2E_PORT} --strictPort`,
    url: E2E_BASE_URL,
    reuseExistingServer: false,
    // 実環境に届かない転送先。モックの漏れた /api/ 要求が、実際の API に届かず失敗する(多重防御)。
    env: { LORELEY_DEV_API_TARGET: 'http://127.0.0.1:1' },
  },
})
