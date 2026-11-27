import { describe, expect, it } from 'vitest'

import { formatDate, formatDateTime, parseIsoDateTime } from './datetime'

// TZ は Asia/Tokyo(vite.config.ts の test.env)。UTC の 0 時が JST の 9 時。
describe('formatDateTime', () => {
  it('ブラウザのローカル時刻で YYYY-MM-DD HH:mm にする(タイムゾーンの略称は付けない)', () => {
    expect(formatDateTime('2026-11-22T00:05:00.000Z')).toBe('2026-11-22 09:05')
  })

  it('withSeconds のときだけ秒を付ける', () => {
    expect(formatDateTime('2026-11-22T00:05:09.123Z', { withSeconds: true })).toBe(
      '2026-11-22 09:05:09',
    )
  })

  it('24 時間表記で、0 時は 00 になる(24 にならない)', () => {
    expect(formatDateTime('2026-11-21T15:00:00.000Z')).toBe('2026-11-22 00:00')
  })

  it('日付をまたぐ変換と、月・日・時・分の 0 埋め', () => {
    expect(formatDateTime('2026-01-01T00:00:00.000Z')).toBe('2026-01-01 09:00')
    expect(formatDateTime('2025-12-31T23:59:59.999Z')).toBe('2026-01-01 08:59')
  })

  it('日時として読めない文字列は null', () => {
    expect(formatDateTime('not a date')).toBeNull()
    expect(formatDateTime('')).toBeNull()
  })
})

describe('parseIsoDateTime', () => {
  it('ISO 8601 を Date にする', () => {
    expect(parseIsoDateTime('2026-11-22T00:05:00.000Z')?.getTime()).toBe(
      Date.UTC(2026, 10, 22, 0, 5, 0),
    )
  })

  it('読めなければ null', () => {
    expect(parseIsoDateTime('xxx')).toBeNull()
  })
})

describe('formatDate', () => {
  it('Date をそのまま整形する', () => {
    expect(formatDate(new Date(Date.UTC(2026, 10, 22, 0, 5, 9)), { withSeconds: true })).toBe(
      '2026-11-22 09:05:09',
    )
  })
})
