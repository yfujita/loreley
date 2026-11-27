// error interceptor に登録する正規化関数(E 5.3・F 3.3。FARC-P-44)。
//
// 生成された `{Op}Errors` の型はすべて `ErrorResponse` だが、実行時に投げられる値は型と食い違う
// (JSON のエラーはパース済みオブジェクト、Nginx の HTML は string、通信断は TypeError ほか)。
// ここで ApiError に揃える。interceptor が返した値が、そのまま投げられる(生成クライアントの実装)。
import { readErrorBody, type ApiError } from '@/shared/api/apiError'

import { InvalidPathParamError } from '@/admin/api/pathParams'

function hasName(value: unknown, name: string): boolean {
  return typeof value === 'object' && value !== null && 'name' in value && value.name === name
}

/** 利用者側の中断(Query の破棄・キャンセル)。結果は使われないので ApiError にしない。 */
export function isAbortError(value: unknown): boolean {
  return hasName(value, 'AbortError')
}

/** クライアントのタイムアウト(client.ts の fetch が投げる)。 */
export function isTimeoutError(value: unknown): boolean {
  return hasName(value, 'TimeoutError')
}

// パス値の検証の拒否は、画面からは「ID の形式違反の 400 `invalid_request`」と同じに見せる。
// 読み取りでは「見つかりません」(E 6.2)、書き込みでは `details` がない `invalid_request` として想定外(E 6.3)。
const REJECTED_PATH_PARAM: ApiError = {
  kind: 'api',
  status: 400,
  code: 'invalid_request',
  retryable: false,
  outcomeUnknown: false,
}

/**
 * interceptor が受け取った値を ApiError にする。
 * 応答があるときだけ HTTP ステータスが取れる(`response`)。AbortError だけは変換せず、そのまま通す。
 */
export function toApiError(error: unknown, response?: Response): unknown {
  if (isAbortError(error)) return error
  if (isTimeoutError(error)) return { kind: 'timeout' } satisfies ApiError
  if (error instanceof InvalidPathParamError) return REJECTED_PATH_PARAM
  // TypeError は fetch の失敗(接続できない・切断)。realm をまたいでも判定できるよう名前で見る。
  if (hasName(error, 'TypeError')) return { kind: 'network' } satisfies ApiError

  const status = response?.status
  const body = readErrorBody(error)
  if (body !== null && status !== undefined) {
    return {
      kind: 'api',
      status,
      code: body.code,
      retryable: body.retryable,
      ...(body.details !== undefined && { details: body.details }),
      outcomeUnknown: body.details?.outcome_unknown === true,
    } satisfies ApiError
  }

  // error.code を持たない JSON、Nginx の HTML・空の本文(string)、2xx で JSON でない本文(SyntaxError)、想定外の値。
  return {
    kind: 'invalid_response',
    ...(status !== undefined && { status }),
  } satisfies ApiError
}
