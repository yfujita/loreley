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
