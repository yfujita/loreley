import { describe, expect, it } from 'vitest'

import { matchesIdentifier } from './matchesIdentifier'

describe('matchesIdentifier(DS 4.8: 前後の空白を除いた完全一致・大文字小文字を区別)', () => {
  it.each([
    ['demo-handbook', true],
    ['  demo-handbook  ', true],
    ['\tdemo-handbook\n', true],
    ['Demo-Handbook', false],
    ['demo-handbook-2', false],
    ['demo-handboo', false],
    ['demo handbook', false],
    ['', false],
    ['   ', false],
  ])('%j → %s', (input, expected) => {
    expect(matchesIdentifier(input, 'demo-handbook')).toBe(expected)
  })

  it('識別子に空白を含むときも、内側の空白は無視しない', () => {
    expect(matchesIdentifier('a b', 'a b')).toBe(true)
    expect(matchesIdentifier('ab', 'a b')).toBe(false)
  })
})
