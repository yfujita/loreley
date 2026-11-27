import { describe, expect, it } from 'vitest'

import { getMetaOptions } from '@/admin/api'
import { isApiError } from '@/shared/api/apiError'

import {
  apiErrorResponse,
  emptyBodyResponse,
  htmlOkResponse,
  jsonResponse,
  networkErrorResponse,
  nginxHtmlResponse,
  type MockResponse,
} from '../../../../tests/support/apiErrors'
import { useFetchStub } from '../../../../tests/support/fetchStub'
import { createTestQueryClient } from '../../../../tests/support/queryTesting'
import { InvalidPathParamError } from '../pathParams'
import { isAbortError, isTimeoutError, toApiError } from './toApiError'

function responseOf(status: number): Response {
  return new Response(null, { status: status === 204 ? 204 : status })
}

describe('toApiError(E 5.3 の表の各行)', () => {
  it('4xx・5xx で本文が A 5.2 の JSON → kind=api(status・code・retryable・details・outcomeUnknown)', () => {
    const body = {
      error: {
        code: 'lock_held',
        message: 'x',
        retryable: false,
        details: { lock_state: 'held_crawl' },
      },
    }

    expect(toApiError(body, responseOf(409))).toEqual({
      kind: 'api',
      status: 409,
      code: 'lock_held',
      retryable: false,
      details: { lock_state: 'held_crawl' },
      outcomeUnknown: false,
    })
  })

  it('details.outcome_unknown=true → outcomeUnknown=true(crawler_response_lost)', () => {
    const body = {
      error: {
        code: 'crawler_response_lost',
        message: 'x',
        retryable: false,
        details: { outcome_unknown: true },
      },
    }

    expect(toApiError(body, responseOf(504))).toMatchObject({
      kind: 'api',
      status: 504,
      outcomeUnknown: true,
    })
  })

  it('details がなければ details のキーを持たない', () => {
    const result = toApiError({ error: { code: 'unavailable', retryable: true } }, responseOf(503))

    expect(result).toEqual({
      kind: 'api',
      status: 503,
      code: 'unavailable',
      retryable: true,
      outcomeUnknown: false,
    })
    expect(result).not.toHaveProperty('details')
  })

  it('JSON だが error.code を持たない → invalid_response(status)', () => {
    expect(toApiError({ detail: 'Not Found' }, responseOf(404))).toEqual({
      kind: 'invalid_response',
      status: 404,
    })
    expect(toApiError({ error: { message: 'x' } }, responseOf(500))).toEqual({
      kind: 'invalid_response',
      status: 500,
    })
  })

  it.each([502, 503, 504, 413])('Nginx の HTML(string)%i → invalid_response(status)', (status) => {
    expect(toApiError('<html>error</html>', responseOf(status))).toEqual({
      kind: 'invalid_response',
      status,
    })
  })

  it('空の本文(空文字)→ invalid_response(status)', () => {
    expect(toApiError('', responseOf(502))).toEqual({ kind: 'invalid_response', status: 502 })
  })

  it('2xx で本文が JSON でない(SyntaxError)→ invalid_response(status 200)', () => {
    expect(toApiError(new SyntaxError('Unexpected token <'), responseOf(200))).toEqual({
      kind: 'invalid_response',
      status: 200,
    })
  })

  it('接続できない・切断(TypeError。応答なし)→ network', () => {
    expect(toApiError(new TypeError('Failed to fetch'), undefined)).toEqual({ kind: 'network' })
  })

  it('クライアントのタイムアウト(TimeoutError)→ timeout', () => {
    expect(toApiError(new DOMException('timed out', 'TimeoutError'), undefined)).toEqual({
      kind: 'timeout',
    })
  })

  it('利用者側の中断(AbortError)→ ApiError にせず、同じ値をそのまま通す', () => {
    const abortError = new DOMException('aborted', 'AbortError')

    expect(toApiError(abortError, undefined)).toBe(abortError)
  })

  it('AbortError と TimeoutError は区別される', () => {
    const abortError = new DOMException('aborted', 'AbortError')
    const timeoutError = new DOMException('timed out', 'TimeoutError')

    expect([isAbortError(abortError), isTimeoutError(abortError)]).toEqual([true, false])
    expect([isAbortError(timeoutError), isTimeoutError(timeoutError)]).toEqual([false, true])
  })

  it('パス値の検証の拒否(request interceptor の例外)→ 合成の 400 invalid_request', () => {
    expect(toApiError(new InvalidPathParamError('job_id'), undefined)).toEqual({
      kind: 'api',
      status: 400,
      code: 'invalid_request',
      retryable: false,
      outcomeUnknown: false,
    })
  })

  it.each([
    ['undefined', undefined],
    ['null', null],
    ['数値', 42],
    ['想定外の Error', new Error('boom')],
  ])('想定外の値(%s・応答なし)→ invalid_response(status なし)', (_name, value) => {
    expect(toApiError(value, undefined)).toEqual({ kind: 'invalid_response' })
  })

  it('応答があるとき、想定外の値でも status を付ける', () => {
    expect(toApiError(new Error('boom'), responseOf(500))).toEqual({
      kind: 'invalid_response',
      status: 500,
    })
  })

  it('応答がなければ、JSON のエラーでも kind=api にしない(status が取れない)', () => {
    expect(toApiError({ error: { code: 'x', retryable: false } }, undefined)).toEqual({
      kind: 'invalid_response',
    })
  })
})

describe('生成 SDK を通した実際の失敗(error interceptor 経由で ApiError として投げられる)', () => {
  const stub = useFetchStub()

  async function failureFor(mock: MockResponse): Promise<unknown> {
    stub.respondWith(mock)
    return createTestQueryClient()
      .fetchQuery(getMetaOptions())
      .then(
        () => 'resolved',
        (error: unknown) => error,
      )
  }

  it('JSON のエラー(404)', async () => {
    expect(await failureFor(apiErrorResponse(404, 'job_not_found'))).toEqual({
      kind: 'api',
      status: 404,
      code: 'job_not_found',
      retryable: false,
      outcomeUnknown: false,
    })
  })

  it('JSON のエラー(503 retryable)', async () => {
    expect(await failureFor(apiErrorResponse(503, 'unavailable', { retryable: true }))).toEqual({
      kind: 'api',
      status: 503,
      code: 'unavailable',
      retryable: true,
      outcomeUnknown: false,
    })
  })

  it('JSON のエラー(504 結果不明)', async () => {
    const error = await failureFor(
      apiErrorResponse(504, 'crawler_response_lost', { details: { outcome_unknown: true } }),
    )

    expect(error).toMatchObject({ kind: 'api', status: 504, outcomeUnknown: true })
  })

  it.each([502, 503, 504, 413] as const)('Nginx の HTML の %i', async (status) => {
    expect(await failureFor(nginxHtmlResponse(status))).toEqual({
      kind: 'invalid_response',
      status,
    })
  })

  it('空の本文の 502', async () => {
    expect(await failureFor(emptyBodyResponse(502))).toEqual({
      kind: 'invalid_response',
      status: 502,
    })
  })

  it('error.code を持たない JSON の 500', async () => {
    expect(await failureFor(jsonResponse({ detail: 'x' }, 500))).toEqual({
      kind: 'invalid_response',
      status: 500,
    })
  })

  it('200 だが JSON でない本文(誤配信の HTML)', async () => {
    expect(await failureFor(htmlOkResponse())).toEqual({ kind: 'invalid_response', status: 200 })
  })

  it('通信断', async () => {
    expect(await failureFor(networkErrorResponse())).toEqual({ kind: 'network' })
  })

  it('すべて isApiError を満たす(Query の error を unknown として確認できる)', async () => {
    const error = await failureFor(nginxHtmlResponse(502))

    expect(isApiError(error)).toBe(true)
  })
})
