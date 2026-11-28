// ブラウザ(Playwright のページ)の中で、dev サーバーが配信するモジュールを使うための道具。
import type { Page } from '@playwright/test'

/** ページの中で `source`(async 関数の本体)を実行する。dev サーバーのモジュール(`@/` の別名・Vue Query を含む)を読み込める。 */
export async function evaluateInBrowser<T>(page: Page, source: string): Promise<T> {
  return page.evaluate(async (code) => {
    const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor as new (
      body: string,
    ) => () => Promise<unknown>
    return new AsyncFunction(code)()
  }, source) as Promise<T>
}
