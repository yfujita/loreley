// Playwright 用の API モック(E 10.2・F 7.3)。
//
// - モックするのは `/api/admin/v1/…` までのパス。`**/api/**` のような広い glob は使わない
//   (Vite の dev サーバーが返すモジュール(`/admin/src/admin/api/…`)にも一致して誤検出するため。unmockedApi.ts)
// - 宣言は「メソッド + `/api/admin/v1` 以降のパス → 応答」の表。応答は固定・関数・呼び出し回数ごとの列のどれか
// - 表にない `/api/` への要求は `route.fallback()` で、先に登録された捕捉(e2eTest.ts の `guardUnmockedApi`)に渡し、
//   テストを失敗させる(開発プロキシの先に流さない)
import type { Page, Route } from '@playwright/test'

import type { MockResponse } from './apiErrors'

export const ADMIN_API_PREFIX = '/api/admin/v1'

/** `"GET /meta"` のような「メソッド + `/api/admin/v1` 以降のパス(クエリなし)」。 */
export type ApiRouteKey = `${'GET' | 'POST' | 'PUT' | 'DELETE'} /${string}`

export type MockedRequest = {
  method: string
  /** `/api/admin/v1` 以降のパス(エンコードされたまま) */
  path: string
  /** `URLSearchParams`(クエリ) */
  searchParams: URLSearchParams
  /** 本文が JSON のとき、パースした値。なければ undefined */
  bodyJson: unknown
}

type Responder = MockResponse | ((request: MockedRequest) => MockResponse | Promise<MockResponse>)

/** 応答: 固定・関数、または呼び出し回数ごとの列(n 回目に n 番目。足りなければ最後を繰り返す。ポーリング・再取得の検証用)。 */
export type MockApiTable = Readonly<Record<ApiRouteKey, Responder | readonly Responder[]>>

export type MockApi = {
  /** これまでに受けたモック済みの要求(順) */
  readonly requests: readonly MockedRequest[]
  /** 表のキーごとの呼び出し回数 */
  callCount(key: ApiRouteKey): number
  /** 応答を差し替える(以降の呼び出しから。呼び出し回数もリセットする) */
  respond(key: ApiRouteKey, responder: Responder | readonly Responder[]): void
}

function parseJson(text: string | null): unknown {
  if (text === null || text === '') return undefined
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

async function fulfill(route: Route, mock: MockResponse): Promise<void> {
  // 履行も中断もしない。要求は取得中のまま残る(ページを閉じるときに破棄される)。
  if (mock.kind === 'hang') return
  if (mock.kind === 'network-error') {
    await route.abort('failed')
    return
  }
  await route.fulfill({
    status: mock.status,
    contentType: mock.contentType,
    body: mock.body,
    ...(mock.headers !== undefined && { headers: mock.headers }),
  })
}

/**
 * `page` に Admin API のモックを登録する。`e2eTest` の `page` フィクスチャが先に登録した捕捉より後に登録されるので、
 * この表が優先され、表にない要求は捕捉に落ちる。
 */
export async function mockApi(page: Page, table: MockApiTable): Promise<MockApi> {
  const responders = new Map<string, Responder | readonly Responder[]>(Object.entries(table))
  const counts = new Map<string, number>()
  const requests: MockedRequest[] = []

  await page.route(
    (url) => url.pathname.startsWith(`${ADMIN_API_PREFIX}/`),
    async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname.slice(ADMIN_API_PREFIX.length)
      const key = `${request.method()} ${path}`

      const responder = responders.get(key)
      if (responder === undefined) {
        await route.fallback()
        return
      }

      const calls = counts.get(key) ?? 0
      counts.set(key, calls + 1)
      const mocked: MockedRequest = {
        method: request.method(),
        path,
        searchParams: url.searchParams,
        bodyJson: parseJson(request.postData()),
      }
      requests.push(mocked)

      const chosen = Array.isArray(responder)
        ? responder[Math.min(calls, responder.length - 1)]
        : responder
      if (chosen === undefined) throw new Error(`応答の列が空です: ${key}`)
      const mock = typeof chosen === 'function' ? await chosen(mocked) : chosen
      await fulfill(route, mock as MockResponse)
    },
  )

  return {
    requests,
    callCount: (key) => counts.get(key) ?? 0,
    respond(key, responder) {
      responders.set(key, responder)
      counts.set(key, 0)
    },
  }
}
