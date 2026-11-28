import { describe, expect, it } from 'vitest'

import {
  matchesTypedConfirmation,
  parseMinDeleteCount,
  parseRatioThreshold,
  parseSourceId,
  parseTtl,
  RULE_MESSAGES,
} from './rules'

describe('parseSourceId(S3 の識別子)', () => {
  it.each(['demo-handbook', 'a', 'A0', '0abc', 'my.source', 'a_b-c.d', 'a'.repeat(256)])(
    '許可: %s',
    (text) => {
      expect(parseSourceId(text)).toEqual({ ok: true, value: text })
    },
  )

  it('空は必須のエラー', () => {
    expect(parseSourceId('')).toEqual({ ok: false, message: RULE_MESSAGES.sourceIdRequired })
  })

  it.each([
    ['先頭が . ', '.abc'],
    ['先頭が - ', '-abc'],
    ['先頭が _', '_abc'],
    ['空白を含む', 'a b'],
    ['前後の空白(除かない)', ' abc'],
    ['日本語', '日本語'],
    ['/ を含む', 'a/b'],
    ['257 文字', 'a'.repeat(257)],
    ['全角英数字', 'ＡＢＣ'],
  ])('形式の違反: %s', (_name, text) => {
    expect(parseSourceId(text)).toEqual({ ok: false, message: RULE_MESSAGES.sourceIdFormat })
  })
})

describe('parseTtl(1 以上の整数・9 桁まで。日・秒モード共通)', () => {
  it.each([
    ['1', 1],
    ['30', 30],
    ['999999999', 999_999_999],
    [' 30 ', 30],
    ['007', 7],
  ])('許可: %j → %d', (text, value) => {
    expect(parseTtl(text)).toEqual({ ok: true, value })
  })

  it('空・空白だけは必須のエラー', () => {
    expect(parseTtl('')).toEqual({ ok: false, message: RULE_MESSAGES.ttlRequired })
    expect(parseTtl('   ')).toEqual({ ok: false, message: RULE_MESSAGES.ttlRequired })
  })

  it.each([
    ['0(1 以上)', '0'],
    ['00', '00'],
    ['負の数', '-1'],
    ['小数', '1.5'],
    ['小数点だけ違う整数', '30.0'],
    ['文字', 'abc'],
    ['全角数字', '３０'],
    ['10 桁(9 桁まで)', '1000000000'],
    ['指数表記', '1e3'],
    ['符号', '+5'],
    ['桁区切り', '1,000'],
  ])('拒否: %s', (_name, text) => {
    expect(parseTtl(text)).toEqual({ ok: false, message: RULE_MESSAGES.ttl })
  })
})

describe('parseRatioThreshold(0 以上 100 未満・小数第 2 位まで)', () => {
  it.each([
    ['0', 0],
    ['20', 20],
    ['12.5', 12.5],
    ['12.34', 12.34],
    ['99.99', 99.99],
    ['0.01', 0.01],
    ['0.0', 0],
    ['099', 99],
    [' 20 ', 20],
  ])('許可: %j → %d', (text, value) => {
    expect(parseRatioThreshold(text)).toEqual({ ok: true, value })
  })

  it('空は必須のエラー', () => {
    expect(parseRatioThreshold('')).toEqual({ ok: false, message: RULE_MESSAGES.ratioRequired })
  })

  it.each([
    ['100(未満)', '100'],
    ['100.00', '100.00'],
    ['100.01', '100.01'],
    ['999', '999'],
    ['小数第 3 位', '12.345'],
    ['負の数', '-1'],
    ['末尾の小数点', '12.'],
    ['先頭の小数点', '.5'],
    ['文字', 'abc'],
    ['4 桁の整数部', '1000'],
    ['指数表記', '1e1'],
    ['パーセント記号つき', '20%'],
  ])('拒否: %s', (_name, text) => {
    expect(parseRatioThreshold(text)).toEqual({ ok: false, message: RULE_MESSAGES.ratio })
  })
})

describe('parseMinDeleteCount(0 以上の整数・9 桁まで)', () => {
  it.each([
    ['0', 0],
    ['10', 10],
    ['999999999', 999_999_999],
  ])('許可: %j → %d', (text, value) => {
    expect(parseMinDeleteCount(text)).toEqual({ ok: true, value })
  })

  it('空は必須のエラー', () => {
    expect(parseMinDeleteCount('')).toEqual({
      ok: false,
      message: RULE_MESSAGES.minDeleteCountRequired,
    })
  })

  it.each(['-1', '1.5', 'abc', '1000000000', '1e2'])('拒否: %s', (text) => {
    expect(parseMinDeleteCount(text)).toEqual({
      ok: false,
      message: RULE_MESSAGES.minDeleteCount,
    })
  })
})

describe('9 桁の上限は JavaScript の安全整数に収まる', () => {
  it('最大値 999,999,999 は安全整数', () => {
    expect(Number.isSafeInteger(999_999_999)).toBe(true)
  })
})

describe('matchesTypedConfirmation(要入力確認。DS 4.8)', () => {
  it('前後の空白を無視した完全一致', () => {
    expect(matchesTypedConfirmation('demo-handbook', 'demo-handbook')).toBe(true)
    expect(matchesTypedConfirmation('  demo-handbook \n', 'demo-handbook')).toBe(true)
  })

  it('大文字小文字を区別する', () => {
    expect(matchesTypedConfirmation('Demo-Handbook', 'demo-handbook')).toBe(false)
  })

  it('途中の空白・前方一致・空は一致しない', () => {
    expect(matchesTypedConfirmation('demo handbook', 'demo-handbook')).toBe(false)
    expect(matchesTypedConfirmation('demo', 'demo-handbook')).toBe(false)
    expect(matchesTypedConfirmation('', 'demo-handbook')).toBe(false)
    expect(matchesTypedConfirmation('demo-handbook-2', 'demo-handbook')).toBe(false)
  })
})
