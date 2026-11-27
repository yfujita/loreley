// API クライアントの設定(E 5.3・F 3.3。FARC-P-7・44)。
//
// 生成された fetch クライアント(`generated/client.gen.ts` の `client`)を 1 つだけ使い、薄い設定関数 1 つで設定する。
// `baseUrl` は設定しない(生成物が spec の `servers[0].url` から `/api/admin/v1` を持つ。同一オリジンで、認証・CORS の設定は不要)。
// 自動再送・通知はしない(再試行は Query だけ。通知は画面が決める)。
import { client } from './generated/client.gen'

import { toApiError } from '@/admin/api/errors/toApiError'
import { assertValidPathParams } from '@/admin/api/pathParams'

/** 読み取り(GET)のタイムアウト。`api` 側の OpenSearch の最悪の待ち時間より先に切らない仮値(FARC-U-16)。 */
export const READ_TIMEOUT_MS = 45_000
/** 書き込みのタイムアウト。`api` が Crawler を待って返す 504(約 63 秒)より後、Nginx の `proxy_read_timeout`(90 秒以上)以内(E 5.3)。 */
export const WRITE_TIMEOUT_MS = 90_000

// 本文を持てないステータス。`new Response(body, { status })` は、これらに本文を渡すと TypeError になる。
const NULL_BODY_STATUSES: ReadonlySet<number> = new Set([101, 204, 205, 304])

function timeoutFor(method: string): number {
  return method === 'GET' || method === 'HEAD' ? READ_TIMEOUT_MS : WRITE_TIMEOUT_MS
}

/**
 * タイムアウト付きの fetch。時間切れの対象は、ヘッダー受信までではなく**本文の取得完了まで**(E 5.3)。
 *
 * `fetch` の Promise はヘッダーを受信した時点で解決し、生成クライアントはその後に本文を読む。
 * ヘッダー受信でタイマーを止めると、本文の受信が途中で止まったときに時間切れが働かない。
 * そのためここで本文を読み切ってから、読み終えた内容の Response を返す。
 *
 * - 時間切れ: `TimeoutError`(DOMException)で拒否する → toApiError が `timeout` にする
 * - 利用者側の中断(Query の破棄・キャンセルで `request.signal` が中断): そのままの理由(通常は `AbortError`)で拒否する
 * - `AbortSignal.any` は使わない(対応下限の Safari 16.4 で使えない可能性。FARC-U-22)。自前の AbortController に伝える
 *
 * fetch 本体は呼び出しのたびに `globalThis.fetch` を引く(テストが差し替えられるように。F 7.1)。
 */
export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  // 生成クライアントは常に Request を渡す。`Request` 以外・init つきのときだけ作り直す。
  const request = input instanceof Request && init === undefined ? input : new Request(input, init)
  const controller = new AbortController()
  const { signal } = controller

  // 実際の fetch が中断に応じない場合(差し替えなど)でも、中断した時点で必ず拒否されるようにする。
  const rejectedOnAbort = new Promise<never>((_resolve, reject) => {
    signal.addEventListener('abort', () => reject(signal.reason), { once: true })
  })
  // 競争に負けた側が、後から未処理の拒否にならないようにする。
  rejectedOnAbort.catch(() => {})

  const callerSignal = request.signal
  const forwardCallerAbort = () => controller.abort(callerSignal.reason)
  if (callerSignal.aborted) {
    forwardCallerAbort()
  } else {
    callerSignal.addEventListener('abort', forwardCallerAbort, { once: true })
  }

  const timer = window.setTimeout(
    () => controller.abort(new DOMException('The request timed out.', 'TimeoutError')),
    timeoutFor(request.method),
  )

  try {
    // すでに中断されていれば、リクエストを送らない。
    signal.throwIfAborted()
    const response = await Promise.race([globalThis.fetch(request, { signal }), rejectedOnAbort])
    const body = NULL_BODY_STATUSES.has(response.status)
      ? null
      : await Promise.race([response.arrayBuffer(), rejectedOnAbort])
    return new Response(body, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    })
  } finally {
    window.clearTimeout(timer)
    callerSignal.removeEventListener('abort', forwardCallerAbort)
  }
}

/**
 * クライアントを設定する。`main.ts` が 1 回呼ぶ(単体テストの setup も同じ関数を呼ぶ)。
 * 冪等: 設定済みなら何もしない(interceptor が二重に登録されない)。設定済みかは interceptor の登録で判定する。
 */
export function configureApiClient(): void {
  if (client.interceptors.error.exists(toApiError)) return

  // `parseAs: 'auto'`(生成の既定)は Content-Type で本文の読み方を決めるため、2xx で `text/html` の本文(誤配信の HTML)は
  // 失敗にならず、文字列のまま `data` に載る(FARC-U-22 の確認で判明)。JSON に固定して、JSON でない 2xx を
  // SyntaxError → error interceptor → `invalid_response`(E 5.3 の表)にする。
  client.setConfig({ fetch: fetchWithTimeout, parseAs: 'json' })
  // 最終防衛(E 5.3): パス値が不正なら送信せずに例外にする。例外は error interceptor を通って合成の 400 になる。
  client.interceptors.request.use((request, options) => {
    assertValidPathParams(options.path)
    return request
  })
  client.interceptors.error.use(toApiError)
}
