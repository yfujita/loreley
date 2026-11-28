// パス値の送信前検証(E 5.3・F 3.3。FMOD-P-4)。
//
// 生成 SDK はパスの値を `encodeURIComponent` で送る(`a%b?c#d`・`a/b`・日本語は正しく送られる)が、
// 値全体が `.` なら一覧の EP(`/jobs/`)、`..` なら 1 階層上、空文字なら `/jobs/` に、ブラウザの URL の正規化で
// 化けて別の EP を叩く。`undefined` はプレースホルダ(`{job_id}`)が残る。このため送る前に弾く。

import { hasLoneSurrogate } from '@/shared/api/unicode'

const DOT_SEGMENTS: ReadonlySet<string> = new Set(['.', '..'])

function hasControlCharacter(value: string): boolean {
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    // U+0000〜U+001F・U+007F
    if (code <= 0x1f || code === 0x7f) return true
  }
  return false
}

/**
 * パスに入れてよい値か。次のどれかに当たる値を拒否する:
 * 文字列でない・空・値全体が `.` か `..`・制御文字(U+0000〜U+001F・U+007F)を 1 文字でも含む・孤児サロゲートを含む。
 *
 * `.` を含むだけの値(`my.source`・`a.b`・`..a`・`a..`)は拒否しない。URL の `.`・`..` の正規化が働くのは、
 * パスの 1 区間が値全体として `.`・`..` のときだけで、正当な `source_id` がありうるため。
 * `%`・`?`・`#`・`/`・空白・日本語は SDK のエンコードと API の判断(400・404)に任せる。
 */
export function isValidPathId(value: unknown): value is string {
  if (typeof value !== 'string') return false
  if (value === '') return false
  if (DOT_SEGMENTS.has(value)) return false
  // 孤児サロゲートは `encodeURIComponent` が URIError を投げ、別の経路(network 扱い)に落ちるため、ここで弾く。
  if (hasLoneSurrogate(value)) return false
  return !hasControlCharacter(value)
}

/** パス値の検証に失敗したときに request interceptor が投げる例外。error interceptor が合成の 400 `invalid_request` にする。 */
export class InvalidPathParamError extends Error {
  constructor(readonly paramName: string) {
    // 値は含めない(入力値・パスを診断に出さない。A 2.3・5.2)。
    super(`invalid path parameter: ${paramName}`)
    this.name = 'InvalidPathParamError'
  }
}

/** `opts.path` のすべての値を検証し、不正なら送信せずに InvalidPathParamError を投げる。 */
export function assertValidPathParams(path: unknown): void {
  if (path === undefined || path === null) return
  if (typeof path !== 'object') throw new InvalidPathParamError('path')

  for (const [name, value] of Object.entries(path)) {
    if (!isValidPathId(value)) throw new InvalidPathParamError(name)
  }
}
