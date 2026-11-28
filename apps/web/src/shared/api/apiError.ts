// API 共通のエラーの形(A 5.2)と、それを読む純粋な関数。生成型・fetch に依存しない(Search View も使える)。
// 投げられた値を ApiError にする正規化は admin/api/errors/toApiError.ts(F 3.3)。

/** `details`。キーは Admin API ごとに違うので、中身は呼び出し側が型ガードで読む(`unknown`)。 */
export type ApiErrorDetails = Readonly<Record<string, unknown>>

export type ApiError =
  // A 5.2 の形で `api` が返した JSON のエラー
  | {
      kind: 'api'
      status: number
      code: string
      retryable: boolean
      details?: ApiErrorDetails
      /** `details.outcome_unknown`(B 2.3 の `crawler_response_lost`)から作る */
      outcomeUnknown: boolean
    }
  // 接続できない・切断された
  | { kind: 'network' }
  // クライアント側のタイムアウト
  | { kind: 'timeout' }
  // JSON でない・形が違う(Nginx の HTML・空の本文など)。応答がなければ status なし。
  // Nginx 由来の 502・503・504・413 を区別し、書き込みの結果不明を判定するために status を持つ(FARC-P-43)
  | { kind: 'invalid_response'; status?: number }

/** A 5.2 のエラー本文(`{ error: { code, message, retryable, details? } }`)から読み取った値。`message` は画面に出さない。 */
export type ErrorBody = {
  code: string
  retryable: boolean
  details?: ApiErrorDetails
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 本文が A 5.2 の形(`error.code` が string)かを判定し、読み取る。
 * JSON のエラー(Admin API)と、Nginx・プロキシの HTML を区別する分かれ目(FARC-P-44)。
 */
export function readErrorBody(value: unknown): ErrorBody | null {
  if (!isRecord(value)) return null
  const error = value.error
  if (!isRecord(error)) return null
  if (typeof error.code !== 'string') return null

  const details = isRecord(error.details) ? error.details : undefined
  return {
    code: error.code,
    retryable: error.retryable === true,
    ...(details !== undefined && { details }),
  }
}

const API_ERROR_KINDS: ReadonlySet<unknown> = new Set([
  'api',
  'network',
  'timeout',
  'invalid_response',
])

/**
 * 値が ApiError かを確認する。Query の `error` は生成型で `ErrorResponse | null` に見えるが、
 * 実行時の値は型と食い違うため、`unknown` として扱ってこの関数で確認する(E 5.3)。
 */
export function isApiError(value: unknown): value is ApiError {
  if (!isRecord(value)) return false
  if (!API_ERROR_KINDS.has(value.kind)) return false

  switch (value.kind) {
    case 'api':
      return (
        typeof value.status === 'number' &&
        typeof value.code === 'string' &&
        typeof value.retryable === 'boolean' &&
        typeof value.outcomeUnknown === 'boolean'
      )
    case 'invalid_response':
      return value.status === undefined || typeof value.status === 'number'
    default:
      return true
  }
}
