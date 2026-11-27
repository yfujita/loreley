import { describe, expect, it } from 'vitest'

import { formatLeaseExpiry, LEASE_EXPIRY_SENTINEL, LEASE_EXPIRY_TEXT } from './leaseExpiry'

describe('formatLeaseExpiry(E 5.9。リース期限の整形)', () => {
  it('通常の日時は、ブラウザのローカル時刻(YYYY-MM-DD HH:mm)に整形する', () => {
    // TZ は Asia/Tokyo(UTC の 01:07 が JST の 10:07)
    expect(formatLeaseExpiry('2026-11-22T01:07:03.456Z', { expired: false })).toEqual({
      kind: 'datetime',
      iso: '2026-11-22T01:07:03.456Z',
      text: '2026-11-22 10:07',
    })
  })

  it('番兵(0001-01-01T00:00:00.000Z)は日時として整形せず「期限切れ」', () => {
    const result = formatLeaseExpiry(LEASE_EXPIRY_SENTINEL, { expired: true })

    expect(result).toEqual({ kind: 'expired', text: '期限切れ' })
    expect(result.text).not.toContain('0001')
  })

  it('番兵は expired の指定によらず「期限切れ」(409 の existing_job は呼び出し側が状態を知らない)', () => {
    expect(formatLeaseExpiry(LEASE_EXPIRY_SENTINEL, { expired: false })).toMatchObject({
      kind: 'expired',
    })
  })

  it('番兵の表記ゆれ(ミリ秒なし)も番兵として扱う', () => {
    expect(formatLeaseExpiry('0001-01-01T00:00:00Z', { expired: false })).toMatchObject({
      kind: 'expired',
    })
  })

  it('stalled=true(expired)で null は「期限を確認できません(期限切れ)」', () => {
    expect(formatLeaseExpiry(null, { expired: true })).toEqual({
      kind: 'unknown-expired',
      text: '期限を確認できません(期限切れ)',
    })
    expect(formatLeaseExpiry(undefined, { expired: true })).toMatchObject({
      kind: 'unknown-expired',
    })
  })

  it('expired でない null は「期限なし(実行待ち)」(番兵とは別)', () => {
    expect(formatLeaseExpiry(null, { expired: false })).toEqual({
      kind: 'none',
      text: LEASE_EXPIRY_TEXT.none,
    })
  })

  it('日時として読めない文字列は、null と同じに扱う(整形しない)', () => {
    expect(formatLeaseExpiry('garbage', { expired: true })).toMatchObject({
      kind: 'unknown-expired',
    })
    expect(formatLeaseExpiry('garbage', { expired: false })).toMatchObject({ kind: 'none' })
  })
})
