import { describe, expect, it } from 'vitest'

import { hasLoneSurrogate } from './unicode'

describe('hasLoneSurrogate', () => {
  it.each(['', 'abc', '日本語', '😀', 'a😀b', '\ud83d\ude00'])(
    '対になっている・サロゲートなし: %j',
    (value) => {
      expect(hasLoneSurrogate(value)).toBe(false)
    },
  )

  it.each([
    ['上位だけ', '\ud800'],
    ['下位だけ', '\udc00'],
    ['上位の後ろが通常の文字', '\ud800a'],
    ['下位の前に通常の文字', 'a\udc00'],
    ['上位が 2 つ続く', '\ud800\ud800'],
    ['末尾の上位', 'abc\ud83d'],
    ['下位が先、上位が後(順序が逆)', '\ude00\ud83d'],
  ])('孤児サロゲート: %s', (_name, value) => {
    expect(hasLoneSurrogate(value)).toBe(true)
  })
})

describe('hasLoneSurrogate の境界(UTF-16 のコードユニット)', () => {
  const units = (...codes: number[]) => String.fromCharCode(...codes)

  it.each([
    ['U+10000(最小の補助文字: D800 DC00)', '𐀀'],
    ['U+10FFFF(最大: DBFF DFFF)', '\u{10FFFF}'],
    ['上位の最小(D800)+下位の最大(DFFF)', units(0xd800, 0xdfff)],
    ['上位の最大(DBFF)+下位の最小(DC00)', units(0xdbff, 0xdc00)],
    ['サロゲートの直前(D7FF)・直後(E000)の通常の文字', units(0xd7ff, 0xe000)],
  ])('対になっている・サロゲートではない: %s', (_name, value) => {
    expect(hasLoneSurrogate(value)).toBe(false)
  })

  it.each([
    ['上位の最小(D800)だけ', units(0xd800)],
    ['上位の最大(DBFF)だけ', units(0xdbff)],
    ['下位の最小(DC00)だけ', units(0xdc00)],
    ['下位の最大(DFFF)だけ', units(0xdfff)],
    ['上位(DBFF)+下位の範囲外の直前(DBFF)', units(0xdbff, 0xdbff)],
    ['上位+下位の範囲外の直後(E000)', units(0xd800, 0xe000)],
    ['上位+通常の文字', units(0xd800, 0x61)],
    ['下位(DC00)が先で、上位(DBFF)が後', units(0xdc00, 0xdbff)],
    ['上位が 2 つ続いてから下位(D800 DBFF DC00)', units(0xd800, 0xdbff, 0xdc00) + units(0xdc00)],
    ['対になった後ろに下位が余る', units(0xd800, 0xdc00, 0xdc00)],
  ])('孤児サロゲート: %s', (_name, value) => {
    expect(hasLoneSurrogate(value)).toBe(true)
  })
})
