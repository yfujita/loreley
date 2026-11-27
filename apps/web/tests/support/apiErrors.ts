// API の失敗応答を作るビルダー(Vitest と Playwright で共有。型付き。F 7.3・E 10.2)。
// フレームワークに依存しない記述(MockResponse)を返し、Vitest は fetchStub が、Playwright は mockApi が実際の応答にする。
import type { ErrorDetails, ErrorResponse } from '@/admin/api'

export type MockResponse =
  // 通常の応答(JSON・HTML・空の本文)
  | { kind: 'response'; status: number; contentType: string; body: string }
  // 通信断(接続できない・切断)。Vitest は fetch の TypeError、Playwright は route.abort() になる
  | { kind: 'network-error' }

/** 200 などの JSON の応答。 */
export function jsonResponse(body: unknown, status = 200): MockResponse {
  return {
    kind: 'response',
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

type ApiErrorOptions = {
  retryable?: boolean
  details?: ErrorDetails
}

/** A 5.2 の形のエラー応答(`api` が返す JSON)。`message` は固定の英語文(診断用)で、画面は使わない。 */
export function apiErrorResponse(
  status: number,
  code: string,
  options: ApiErrorOptions = {},
): MockResponse {
  const body = {
    error: {
      code,
      message: `fixed message for ${code}`,
      retryable: options.retryable ?? false,
      ...(options.details !== undefined && { details: options.details }),
    },
  } satisfies ErrorResponse
  return jsonResponse(body, status)
}

/** Nginx(プロキシ)が返す HTML のエラー。`api` の JSON とは違い、`error.code` を持たない(FARC-P-43)。 */
export function nginxHtmlResponse(status: 413 | 502 | 503 | 504): MockResponse {
  const title = `${status} Error`
  return {
    kind: 'response',
    status,
    contentType: 'text/html',
    body: `<html><head><title>${title}</title></head><body><center><h1>${title}</h1></center><hr><center>nginx</center></body></html>`,
  }
}

/** 空の本文のエラー(上流が本文を返さなかったとき)。 */
export function emptyBodyResponse(status: number): MockResponse {
  return { kind: 'response', status, contentType: 'text/plain', body: '' }
}

/** 2xx なのに JSON でない本文(誤配信の HTML など)。 */
export function htmlOkResponse(): MockResponse {
  return {
    kind: 'response',
    status: 200,
    contentType: 'text/html',
    body: '<html><body>index</body></html>',
  }
}

/** 通信断(接続できない・切断)。 */
export function networkErrorResponse(): MockResponse {
  return { kind: 'network-error' }
}

/** 400 `invalid_request` の項目別エラー(`details.errors`)。 */
export function fieldErrorsResponse(
  errors: ReadonlyArray<{ field: string; reason: string; detail?: string }>,
  code: 'invalid_request' | 'config_invalid' = 'invalid_request',
): MockResponse {
  return apiErrorResponse(400, code, { details: { errors: [...errors] } as ErrorDetails })
}
