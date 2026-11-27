// dev サーバーが、E2E のページ内で dev サーバーのモジュール(Vue Query など)を読み込める状態になるまで待つ。
//
// Vite の dev サーバーは、起動後に初めて読み込む依存(Vue Query)を見つけると、最適化してページを再読み込みする
// (今の main.ts は Vue Query を import しないため)。再読み込みが落ち着くまで、読み込みを繰り返して待つ。
// フェーズ 3 で main.ts が Vue Query を import するようになれば、起動時に最適化されるので不要になる。
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

const VITE_READY_TIMEOUT_MS = 120_000

/** 待ち時間が上限を超えたとき、原因(最後の失敗)が分かるメッセージで失敗する。 */
export async function waitForViteReady(page: Page): Promise<void> {
  const deadline = Date.now() + VITE_READY_TIMEOUT_MS
  let lastError: unknown
  while (Date.now() < deadline) {
    try {
      await evaluateInBrowser<boolean>(
        page,
        `await import('/admin/src/admin/queries/queryClient.ts'); return true`,
      )
      return
    } catch (error) {
      lastError = error // 再読み込みで実行コンテキストが破棄された(最適化の最中)など
      await page.waitForLoadState('load').catch(() => {})
    }
  }
  throw new Error(
    `dev サーバーのモジュール(Vue Query)が ${VITE_READY_TIMEOUT_MS / 1000} 秒以内に読み込めませんでした。` +
      `Vite の依存の最適化後の再読み込みが落ち着かないか、dev サーバーが応答していません。最後のエラー: ${String(lastError)}`,
  )
}
