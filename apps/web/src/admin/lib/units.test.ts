import { describe, expect, it } from 'vitest'

import {
  daysToSeconds,
  hasMoreThanTwoDecimals,
  roundToTwoDecimals,
  secondsToDays,
  SECONDS_PER_DAY,
} from './units'

describe('日 ↔ 秒', () => {
  it('1 日 = 86,400 秒', () => {
    expect(SECONDS_PER_DAY).toBe(86_400)
    expect(daysToSeconds(30)).toBe(2_592_000)
  })

  it('日で割り切れるときだけ日にする(それ以外は null。S4 が「N 秒」表示に切り替える)', () => {
    expect(secondsToDays(2_592_000)).toBe(30)
    expect(secondsToDays(86_400)).toBe(1)
    expect(secondsToDays(90_061)).toBeNull()
    expect(secondsToDays(86_399)).toBeNull()
    expect(secondsToDays(1)).toBeNull()
  })

  it('境界: 0 秒は 0 日(割り切れる)、9 桁の日数でも往復できる', () => {
    expect(secondsToDays(0)).toBe(0)
    expect(secondsToDays(daysToSeconds(999_999_999))).toBe(999_999_999)
  })
})

describe('hasMoreThanTwoDecimals(しきい値の小数第 3 位以下の判定。E 7.7)', () => {
  it.each([12.35, 99.99, 12, 0, 0.1, 0.01, 20, 99.9, 1.5])('%s は小数第 2 位まで', (value) => {
    expect(hasMoreThanTwoDecimals(value)).toBe(false)
  })

  it.each([12.345, 1e-7, 0.12345, 2.675, 1.005, 99.999, 0.001, 0.1 + 0.2])(
    '%s は小数第 3 位以下を持つ',
    (value) => {
      expect(hasMoreThanTwoDecimals(value)).toBe(true)
    },
  )

  it('極小値は指数表記(String(1e-7) は "1e-7")になるが、桁を数え誤らない', () => {
    expect(String(1e-7)).toBe('1e-7')
    expect(hasMoreThanTwoDecimals(1e-7)).toBe(true)
  })
})

describe('roundToTwoDecimals(十進での四捨五入。toFixed(2) をそのまま使わない)', () => {
  it('toFixed(2) の 2 進の誤差: (2.675).toFixed(2) は "2.67"、(1.005).toFixed(2) は "1.00"', () => {
    expect((2.675).toFixed(2)).toBe('2.67')
    expect((1.005).toFixed(2)).toBe('1.00')
  })

  it.each([
    [2.675, 2.68],
    [1.005, 1.01],
    [12.345, 12.35],
    [0.12345, 0.12],
    [0.125, 0.13],
    [0.124, 0.12],
    [99.995, 100],
    [99.994, 99.99],
    [0.005, 0.01],
    [0.004, 0],
    [1.0049999, 1],
  ])('%s → %s(境界値)', (input, expected) => {
    expect(roundToTwoDecimals(input)).toBe(expected)
  })

  it('小数第 2 位までの値はそのまま返す', () => {
    for (const value of [12, 12.3, 12.35, 0, 99.99]) {
      expect(roundToTwoDecimals(value)).toBe(value)
    }
  })

  it('指数表記になる極小値も丸められる(1e-7 → 0)', () => {
    expect(roundToTwoDecimals(1e-7)).toBe(0)
    expect(roundToTwoDecimals(4.9e-3)).toBe(0)
    expect(roundToTwoDecimals(5e-3)).toBe(0.01)
  })

  it('丸めた値は小数第 3 位以下を持たない', () => {
    for (const value of [12.345, 2.675, 1.005, 0.12345, 99.999]) {
      expect(hasMoreThanTwoDecimals(roundToTwoDecimals(value))).toBe(false)
    }
  })

  it('負の値は 0 から遠ざかる向きに丸める(対称)', () => {
    expect(roundToTwoDecimals(-2.675)).toBe(-2.68)
  })
})
