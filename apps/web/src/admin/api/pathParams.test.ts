import { describe, expect, it } from 'vitest'

import { assertValidPathParams, InvalidPathParamError, isValidPathId } from './pathParams'

describe('isValidPathId', () => {
  it.each([
    ['通常の識別子', 'demo-handbook'],
    ['ジョブ ID', 'job-20261122T010203Z-3fa9c2d1'],
    ['`.` を含むだけの値', 'my.source'],
    ['`a.b`', 'a.b'],
    ['`..` で始まる値', '..a'],
    ['`..` で終わる値', 'a..'],
    ['`...`(値全体が `.`・`..` ではない)', '...'],
    ['`%` を含む値(SDK のエンコードに任せる)', 'a%b'],
    ['`?` `#` を含む値', 'a?b#c'],
    ['`/` を含む値(API が 404 にする)', 'a/b'],
    ['空白を含む値', 'a b'],
    ['日本語', '日本語'],
    ['対になったサロゲート(絵文字)', 'a😀b'],
    ['エンコード済みのドット(二重にエンコードされる)', '%2e%2e'],
  ])('許可する: %s', (_name, value) => {
    expect(isValidPathId(value)).toBe(true)
  })

  it.each([
    ['`.` だけ', '.'],
    ['`..` だけ', '..'],
    ['空文字', ''],
    ['NUL', 'a\u0000b'],
    ['U+001F', 'a\u001fb'],
    ['改行', 'a\nb'],
    ['タブ', '\tabc'],
    ['DEL(U+007F)', 'abc\u007f'],
    ['孤児サロゲート(上位だけ。encodeURIComponent が URIError を投げる)', 'a\ud800b'],
    ['孤児サロゲート(下位だけ)', '\udc00'],
    ['undefined', undefined],
    ['null', null],
    ['数値', 123],
    ['真偽値', true],
    ['オブジェクト', { toString: () => 'a' }],
    ['配列', ['a']],
  ])('拒否する: %s', (_name, value) => {
    expect(isValidPathId(value)).toBe(false)
  })

  it('境界: U+0020(空白)は制御文字ではない・U+0080 以降も拒否しない', () => {
    expect(isValidPathId(' ')).toBe(true)
    expect(isValidPathId('\u0080')).toBe(true)
  })
})

describe('assertValidPathParams', () => {
  it('path がないときは何もしない', () => {
    expect(() => assertValidPathParams(undefined)).not.toThrow()
    expect(() => assertValidPathParams(null)).not.toThrow()
  })

  it('すべての値が有効なら何もしない', () => {
    expect(() => assertValidPathParams({ source_id: 'a', job_id: 'b.c' })).not.toThrow()
  })

  it('どれか 1 つでも不正なら、そのパラメータ名つきの例外を投げる(値は含めない)', () => {
    expect(() => assertValidPathParams({ source_id: 'a', job_id: '..' })).toThrow(
      InvalidPathParamError,
    )
    try {
      assertValidPathParams({ source_id: 'a', job_id: '..' })
    } catch (error) {
      expect((error as InvalidPathParamError).paramName).toBe('job_id')
      expect((error as Error).message).not.toContain('..')
    }
  })

  it('値が undefined のキーも拒否する(プレースホルダが残るため)', () => {
    expect(() => assertValidPathParams({ job_id: undefined })).toThrow(InvalidPathParamError)
  })

  it('path がオブジェクトでなければ拒否する', () => {
    expect(() => assertValidPathParams('x')).toThrow(InvalidPathParamError)
  })
})
