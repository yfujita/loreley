// Vitest 用: `fetch` を差し替え、生成クライアントを**実際に通して**リクエストを記録する(E 10.1・F 7.1。MSW は使わない)。
//
// 差し替えるのは `globalThis.fetch`。`configureApiClient()` が `client.setConfig` に渡すタイムアウト付き fetch は
// 差し替えず、その内側(呼び出しのたびに `globalThis.fetch` を引く)でこの stub が呼ばれる。
// このため、後始末は `vi.unstubAllGlobals()` だけで、client の設定には触れない(元に戻す設定がない)。
import { afterEach, beforeEach, expect, vi } from 'vitest'

import type { MockResponse } from './apiErrors'

export type RecordedRequest = {
  method: string
  url: string
  /** `/api/admin/v1/…` を含むパス(エンコードされたまま) */
  pathname: string
  /** `?` を含むクエリ文字列。クエリがなければ空文字 */
  search: string
  bodyText: string | null
  /** 本文が JSON のとき、パースした値。本文がなければ undefined */
  bodyJson: unknown
  /** fetch に渡された中断シグナル(client.ts のタイムアウト・中断の確認用) */
  signal: AbortSignal | undefined
}

export type Responder =
  | MockResponse
  | Response
  | ((request: RecordedRequest) => MockResponse | Response | Promise<MockResponse | Response>)

const API_PREFIX = '/api/admin/v1'

function toResponse(mock: Extract<MockResponse, { kind: 'response' }>): Response {
  return new Response(mock.body === '' ? null : mock.body, {
    status: mock.status,
    headers: { 'content-type': mock.contentType, ...mock.headers },
  })
}

export type FetchStub = {
  readonly requests: RecordedRequest[]
  /** すべての要求に同じ応答を返す(`routes` を使っていないとき)。 */
  respondWith(responder: Responder): void
  /**
   * `"GET /meta"` のような「メソッド + `/api/admin/v1` 以降のパス(クエリなし)」で応答を決める。
   * 一致しない要求は 404 を返し、`unmatched` に記録する。
   */
  routes(table: Readonly<Record<string, Responder>>): void
  readonly unmatched: string[]
}

async function record(request: Request, signal: AbortSignal | undefined): Promise<RecordedRequest> {
  const url = new URL(request.url)
  const bodyText = request.body === null ? null : await request.clone().text()
  let bodyJson: unknown
  if (bodyText !== null && bodyText !== '') {
    try {
      bodyJson = JSON.parse(bodyText)
    } catch {
      bodyJson = undefined
    }
  }
  return {
    method: request.method,
    url: request.url,
    pathname: url.pathname,
    search: url.search,
    bodyText,
    bodyJson,
    signal,
  }
}

/**
 * `describe` の直下で呼ぶ。各テストの前に `fetch` を差し替え、後に元へ戻す。
 * 返す stub は、テストごとに記録を空にする。
 */
export function useFetchStub(): FetchStub {
  let responder: Responder = { kind: 'network-error' }
  const requests: RecordedRequest[] = []
  const unmatched: string[] = []

  const stubFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const request = input instanceof Request ? input : new Request(input, init)
    const recorded = await record(request, init?.signal ?? undefined)
    requests.push(recorded)

    const result = typeof responder === 'function' ? await responder(recorded) : responder
    if (result instanceof Response) return result
    if (result.kind === 'network-error') throw new TypeError('Failed to fetch')
    if (result.kind === 'hang') return new Promise<Response>(() => {})
    return toResponse(result)
  }

  beforeEach(() => {
    requests.length = 0
    unmatched.length = 0
    responder = { kind: 'network-error' }
    vi.stubGlobal('fetch', stubFetch)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    // `routes()` の表にない要求は、404 を返して黙って進んでしまう。テストが気づけるよう、残っていれば失敗させる。
    expect(unmatched, '`routes()` の表にない要求がありました').toEqual([])
  })

  return {
    requests,
    unmatched,
    respondWith(next) {
      responder = next
    },
    routes(table) {
      responder = (request) => {
        const path = request.pathname.startsWith(API_PREFIX)
          ? request.pathname.slice(API_PREFIX.length)
          : request.pathname
        const key = `${request.method} ${path}`
        const matched = table[key]
        if (matched === undefined) {
          unmatched.push(key)
          return { kind: 'response', status: 404, contentType: 'text/plain', body: 'unmatched' }
        }
        return typeof matched === 'function' ? matched(request) : matched
      }
    },
  }
}
