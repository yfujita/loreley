// QueryClient の既定値(E 5.4・F 3.4)。
import { QueryClient } from '@tanstack/vue-query'

import { isApiError } from '@/shared/api/apiError'

/** `invalid_response` のうち、Nginx 由来の一時的な失敗(502・503・504。FARC-P-43)。 */
const TRANSIENT_GATEWAY_STATUSES: ReadonlySet<number> = new Set([502, 503, 504])

const MAX_READ_RETRIES = 1
const RETRY_DELAY_MS = 1000

/**
 * 読み取りを再試行するか(1 回だけ)。判定は `error` を `unknown` として `isApiError` で確認して行う。
 * 再試行する: network、`retryable=true` の api(503 `unavailable` など)、`invalid_response` の 502・503・504。
 * 再試行しない: timeout(45 秒を 2 回待たせない)、400・404・409、`invalid_response` のその他(形が違うだけで変わらない)。
 */
export function shouldRetryRead(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_READ_RETRIES) return false
  if (!isApiError(error)) return false

  switch (error.kind) {
    case 'network':
      return true
    case 'api':
      return error.retryable
    case 'invalid_response':
      return error.status !== undefined && TRANSIENT_GATEWAY_STATUSES.has(error.status)
    case 'timeout':
      return false
  }
}

/**
 * アプリの QueryClient。
 * - staleTime 0: マウント時(画面を開く・戻る)は再取得する。戻る操作で古い一覧が最新の状態を隠さないため
 * - フォーカス・再接続では再取得しない: 「手動更新のみ」の画面で予期しない再取得をしない(更新は更新ボタン・マウント時・D1 と J2 のポーリングだけ)
 * - 書き込みは再送しない(E 5.3)
 * - グローバルの通知(QueryCache・MutationCache の onError)は置かない。自動更新の失敗はページ内の警告に留め、操作の失敗は各ダイアログが扱う
 */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetryRead,
        retryDelay: RETRY_DELAY_MS,
        staleTime: 0,
        refetchOnWindowFocus: false,
        refetchOnReconnect: false,
        gcTime: 5 * 60 * 1000,
      },
      mutations: { retry: 0 },
    },
  })
}
