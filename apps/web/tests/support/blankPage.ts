// アプリを起動しない、同一オリジン(`/admin/blank`)の空のページ。
// アプリ(シェル)は起動時に `GET /meta` を取るので、「ブラウザの fetch・dev サーバーのモジュールを使いたいだけ」の
// テスト(API クライアント・モックの基盤の確認)は、アプリの代わりにこのページを使う(余計な API 要求を出さない)。
import type { Page } from '@playwright/test'

const BLANK_PATH = '/admin/blank'

export async function gotoBlankPage(page: Page): Promise<void> {
  await page.route(
    (url) => url.pathname === BLANK_PATH,
    (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: '<!doctype html><html lang="ja"><head><title>blank</title></head><body></body></html>',
      }),
  )
  await page.goto('blank')
}
