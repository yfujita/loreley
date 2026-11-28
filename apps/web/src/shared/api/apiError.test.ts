import { describe, expect, it } from 'vitest'

import { isApiError, readErrorBody } from './apiError'

describe('readErrorBody', () => {
  it('A 5.2 の形(error.code が string)なら code・retryable・details を読む', () => {
    expect(
      readErrorBody({
        error: {
          code: 'lock_held',
          message: 'the source is locked by another job',
          retryable: false,
          details: { lock_state: 'held_crawl' },
        },
      }),
    ).toEqual({ code: 'lock_held', retryable: false, details: { lock_state: 'held_crawl' } })
  })

  it('details がなければ details のキー自体を持たない', () => {
    expect(readErrorBody({ error: { code: 'unavailable', retryable: true } })).toEqual({
      code: 'unavailable',
      retryable: true,
    })
  })

  it('retryable が true でなければ false にする', () => {
    expect(readErrorBody({ error: { code: 'x' } })?.retryable).toBe(false)
    expect(readErrorBody({ error: { code: 'x', retryable: 'yes' } })?.retryable).toBe(false)
  })

  it('details がオブジェクトでなければ無視する', () => {
    expect(readErrorBody({ error: { code: 'x', details: 'text' } })).toEqual({
      code: 'x',
      retryable: false,
    })
    expect(readErrorBody({ error: { code: 'x', details: [1] } })).toEqual({
      code: 'x',
      retryable: false,
    })
  })

  it.each([
    ['null', null],
    ['文字列(Nginx の HTML)', '<html>502</html>'],
    ['空の文字列', ''],
    ['数値', 502],
    ['配列', [{ error: { code: 'x' } }]],
    ['error がない JSON', { detail: 'x' }],
    ['error が文字列', { error: 'x' }],
    ['error.code がない', { error: { message: 'x' } }],
    ['error.code が string でない', { error: { code: 500 } }],
  ])('A 5.2 の形でないものは null: %s', (_name, value) => {
    expect(readErrorBody(value)).toBeNull()
  })
})

describe('isApiError', () => {
  it('4 種の kind を判定する', () => {
    expect(
      isApiError({ kind: 'api', status: 404, code: 'x', retryable: false, outcomeUnknown: false }),
    ).toBe(true)
    expect(isApiError({ kind: 'network' })).toBe(true)
    expect(isApiError({ kind: 'timeout' })).toBe(true)
    expect(isApiError({ kind: 'invalid_response' })).toBe(true)
    expect(isApiError({ kind: 'invalid_response', status: 502 })).toBe(true)
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['文字列', 'x'],
    ['Error', new Error('x')],
    ['生成型の ErrorResponse(生の本文)', { error: { code: 'x', message: '', retryable: false } }],
    ['kind が未知', { kind: 'other' }],
    ['api で status がない', { kind: 'api', code: 'x', retryable: false, outcomeUnknown: false }],
    ['api で outcomeUnknown がない', { kind: 'api', status: 400, code: 'x', retryable: false }],
    ['invalid_response で status が文字列', { kind: 'invalid_response', status: '502' }],
  ])('ApiError でないものは false: %s', (_name, value) => {
    expect(isApiError(value)).toBe(false)
  })
})
