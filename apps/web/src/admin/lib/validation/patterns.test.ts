import { describe, expect, it } from 'vitest'

import {
  hasSurroundingWhitespace,
  PATTERN_MESSAGES,
  patternBytesMessage,
  shouldShowPatternByteCount,
  utf8ByteLength,
  validatePattern,
  validatePatternList,
  validateRoot,
} from './patterns'
import { MAX_PATTERN_BYTES, MAX_PATTERNS } from './limits'

describe('validateRoot(取得元のパス。sources 2.3.2 の表)', () => {
  it.each(['/data/handbook', '/', '/a/b.c/d', '/日本語/パス', '/data/..foo', '/data/a..b'])(
    '許可: %s',
    (value) => {
      expect(validateRoot(value)).toBeNull()
    },
  )

  it.each([
    ['', PATTERN_MESSAGES.rootEmpty],
    ['data/handbook', PATTERN_MESSAGES.rootNotAbsolute],
    ['./data', PATTERN_MESSAGES.rootNotAbsolute],
    ['/data//handbook', PATTERN_MESSAGES.rootDoubleSlash],
    ['//data', PATTERN_MESSAGES.rootDoubleSlash],
    ['/data/./handbook', PATTERN_MESSAGES.dotSegment],
    ['/data/../etc', PATTERN_MESSAGES.dotSegment],
    ['/..', PATTERN_MESSAGES.dotSegment],
    ['/data/.', PATTERN_MESSAGES.dotSegment],
    ['/data\u0000x', PATTERN_MESSAGES.nul],
    ['/data/\ud800', PATTERN_MESSAGES.loneSurrogate],
    ['/data/\udc00x', PATTERN_MESSAGES.loneSurrogate],
  ])('拒否: %j → %s', (value, message) => {
    expect(validateRoot(value)).toBe(message)
  })

  it('対になったサロゲート(絵文字)は許可する', () => {
    expect(validateRoot('/data/😀')).toBeNull()
  })
})

describe('validatePattern(パターンの 1 行。sources 2.3.2 の表)', () => {
  it.each([
    'docs/**',
    '**/*.draft.md',
    '**/node_modules/**',
    '*.md',
    'a?.txt',
    '**',
    'a/**/b',
    '日本語/*.md',
    '[x]{y}',
    'a.b',
    '..a/b',
    ' leading-space',
  ])('許可: %s', (value) => {
    expect(validatePattern(value)).toBeNull()
  })

  it.each([
    ['', PATTERN_MESSAGES.patternEmpty],
    ['docs\\*.md', PATTERN_MESSAGES.patternBackslash],
    ['/docs', PATTERN_MESSAGES.patternEmptySegment],
    ['docs/', PATTERN_MESSAGES.patternEmptySegment],
    ['a//b', PATTERN_MESSAGES.patternEmptySegment],
    ['a/./b', PATTERN_MESSAGES.dotSegment],
    ['a/../b', PATTERN_MESSAGES.dotSegment],
    ['..', PATTERN_MESSAGES.dotSegment],
    ['**.md', PATTERN_MESSAGES.patternDoubleStarNotAlone],
    ['a**/b', PATTERN_MESSAGES.patternDoubleStarNotAlone],
    ['docs/**x', PATTERN_MESSAGES.patternDoubleStarNotAlone],
    ['**/**', PATTERN_MESSAGES.patternDoubleStarAdjacent],
    ['a/**/**/b', PATTERN_MESSAGES.patternDoubleStarAdjacent],
    ['a\u0000b', PATTERN_MESSAGES.nul],
    ['a\ud800b', PATTERN_MESSAGES.loneSurrogate],
  ])('拒否: %j → %s', (value, message) => {
    expect(validatePattern(value)).toBe(message)
  })

  it('バイト数は UTF-8 で数える。1,024 バイトちょうどは許可、1,025 バイトは拒否(現在のバイト数を示す)', () => {
    const ok = 'a'.repeat(MAX_PATTERN_BYTES)
    const tooLong = 'a'.repeat(MAX_PATTERN_BYTES + 1)

    expect(validatePattern(ok)).toBeNull()
    expect(validatePattern(tooLong)).toBe(patternBytesMessage(1025))
    expect(patternBytesMessage(1025)).toBe(
      '1 つのパターンは 1〜1,024 バイト(UTF-8)です(現在 1,025 バイト)',
    )
  })

  it('文字数ではなくバイト数: 日本語 1 文字は 3 バイト(342 文字 = 1,026 バイトで拒否、341 文字 = 1,023 バイトで許可)', () => {
    expect(validatePattern('あ'.repeat(341))).toBeNull()
    expect(validatePattern('あ'.repeat(342))).toBe(patternBytesMessage(1026))
    expect(utf8ByteLength('あ')).toBe(3)
    expect(utf8ByteLength('a')).toBe(1)
    expect(utf8ByteLength('😀')).toBe(4)
  })

  it('前後の空白もパターンの一部として扱う(Crawler は除かない)ので、`** ` は単独の `**` ではない', () => {
    expect(validatePattern(' docs/** ')).toBe(PATTERN_MESSAGES.patternDoubleStarNotAlone)
  })

  it('検証の順序: 空 → バイト数 → NUL・サロゲート → バックスラッシュ → セグメント', () => {
    // バックスラッシュと空セグメントの両方があるとき、バックスラッシュが先
    expect(validatePattern('\\//')).toBe(PATTERN_MESSAGES.patternBackslash)
  })
})

describe('validatePatternList', () => {
  it('行ごとに検証し、空の行も除かない(サーバーの添字と画面の行を 1 対 1 にする)', () => {
    const result = validatePatternList(['docs/**', '', '**/**'])

    expect(result.rowMessages).toEqual([
      null,
      PATTERN_MESSAGES.patternEmpty,
      PATTERN_MESSAGES.patternDoubleStarAdjacent,
    ])
    expect(result.listMessage).toBeNull()
  })

  it('100 件までは件数のエラーなし、101 件でエラー(一覧の下に出す)', () => {
    const valid = (count: number) => Array.from({ length: count }, () => 'a')

    expect(validatePatternList(valid(MAX_PATTERNS)).listMessage).toBeNull()
    expect(validatePatternList(valid(MAX_PATTERNS + 1)).listMessage).toBe(
      'パターンは 100 件までです',
    )
  })

  it('0 件は有効(既定の拡張子だけが対象)', () => {
    expect(validatePatternList([])).toEqual({ listMessage: null, rowMessages: [] })
  })
})

describe('注意の表示(エラーにしない)', () => {
  it('前後の空白: 検証はエラーにせず、注意の対象にする', () => {
    expect(validatePattern(' docs/*.md ')).toBeNull()
    expect(hasSurroundingWhitespace(' docs/*.md ')).toBe(true)
    expect(hasSurroundingWhitespace('docs/*.md\t')).toBe(true)
    expect(hasSurroundingWhitespace('docs/*.md')).toBe(false)
    expect(hasSurroundingWhitespace('a b')).toBe(false)
  })

  it('800 バイトを超えた行の下にバイト数を出す(800 ちょうどは出さない)', () => {
    expect(shouldShowPatternByteCount('a'.repeat(800))).toBe(false)
    expect(shouldShowPatternByteCount('a'.repeat(801))).toBe(true)
  })
})
