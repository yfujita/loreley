import { describe, expect, it } from 'vitest'

import { EMPTY_VALUE_MARK, formatCount, formatCountOrDash } from './number'

describe('formatCount', () => {
  it('3 桁区切りにする', () => {
    expect(formatCount(0)).toBe('0')
    expect(formatCount(999)).toBe('999')
    expect(formatCount(1284)).toBe('1,284')
    expect(formatCount(1234567)).toBe('1,234,567')
  })
})

describe('formatCountOrDash', () => {
  it('null・undefined は「—」(未取得)、0 は「0」(0 件)', () => {
    expect(formatCountOrDash(null)).toBe(EMPTY_VALUE_MARK)
    expect(formatCountOrDash(undefined)).toBe('—')
    expect(formatCountOrDash(0)).toBe('0')
    expect(formatCountOrDash(12345)).toBe('12,345')
  })
})
