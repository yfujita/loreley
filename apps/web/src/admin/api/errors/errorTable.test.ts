import { describe, expect, it } from 'vitest'

import {
  ADMIN_ERROR_CODES,
  COMMON_ERROR_CODES,
  ERROR_TABLE,
  isKnownErrorCode,
  isLockState,
  LOCK_REFUSAL_VARIANT,
  type ErrorTableEntry,
  type KnownErrorCode,
} from './errorTable'

// E 6.2・6.3 の表を、実装とは別に手で書いた期待値。code を足すと、ここと errorTable の両方を直すまでテストが落ちる。
type Expected = {
  scope: ErrorTableEntry['scope']
  httpStatus: number | null
  read: ErrorTableEntry['read']
  writeTarget: ErrorTableEntry['write']['target']
  writeVariant: ErrorTableEntry['write']['variant']
  writeExpected: boolean
  outcomeUnknown: boolean
}

const EXPECTED: Record<KnownErrorCode, Expected> = {
  // Admin 固有 14 種(B 2.3)
  config_invalid: row('admin', 400, 'unexpected', 'field', 'error', true),
  source_config_not_found: row('admin', 404, 'not-found', 'alert', 'error', true),
  job_not_found: row('admin', 404, 'not-found', 'alert', 'error', true),
  lock_held: row('admin', 409, 'unexpected', 'alert', 'error', true),
  lock_in_use: row('admin', 409, 'unexpected', 'alert', 'error', true),
  source_deleting: row('admin', 409, 'unexpected', 'alert', 'error', true),
  maintenance_enabled: row('admin', 409, 'unexpected', 'alert', 'error', true),
  source_already_exists: row('admin', 409, 'unexpected', 'field', 'error', true),
  job_not_cancellable: row('admin', 409, 'unexpected', 'alert', 'error', false),
  job_already_finished: row('admin', 409, 'unexpected', 'success', 'info', true),
  crawler_error: row('admin', 502, 'unexpected', 'alert', 'error', false),
  crawler_unavailable: row('admin', 503, 'unexpected', 'alert', 'error', true),
  crawler_unreachable: row('admin', 503, 'unexpected', 'alert', 'error', true),
  crawler_response_lost: row('admin', 504, 'unexpected', 'alert', 'warning', true, true),
  // 共通 6 種(A 5.2)
  invalid_request: row('common', 400, 'not-found', 'field', 'error', true),
  not_found: row('common', 404, 'not-found', 'alert', 'error', false),
  method_not_allowed: row('common', 405, 'unexpected', 'alert', 'error', false),
  http_error: row('common', null, 'unexpected', 'alert', 'error', false),
  internal_error: row('common', 500, 'unexpected', 'alert', 'error', false),
  unavailable: row('common', 503, 'error', 'alert', 'error', false),
}

function row(
  scope: Expected['scope'],
  httpStatus: Expected['httpStatus'],
  read: Expected['read'],
  writeTarget: Expected['writeTarget'],
  writeVariant: Expected['writeVariant'],
  writeExpected: boolean,
  outcomeUnknown = false,
): Expected {
  return { scope, httpStatus, read, writeTarget, writeVariant, writeExpected, outcomeUnknown }
}

describe('エラー変換表の網羅(Admin 固有 14 種 + 共通 6 種)', () => {
  it('code は 14 + 6 = 20 種で、重複がない', () => {
    const all = [...ADMIN_ERROR_CODES, ...COMMON_ERROR_CODES]

    expect(ADMIN_ERROR_CODES).toHaveLength(14)
    expect(COMMON_ERROR_CODES).toHaveLength(6)
    expect(new Set(all).size).toBe(20)
  })

  it('表のキーは 20 種の code と過不足なく一致する(code を足すとテストが落ちる)', () => {
    expect(Object.keys(ERROR_TABLE).sort()).toEqual(
      [...ADMIN_ERROR_CODES, ...COMMON_ERROR_CODES].sort(),
    )
    expect(Object.keys(EXPECTED).sort()).toEqual(Object.keys(ERROR_TABLE).sort())
  })

  it.each(Object.keys(EXPECTED) as KnownErrorCode[])('%s の扱いが E 6.2・6.3 のとおり', (code) => {
    const expected = EXPECTED[code]
    const entry = ERROR_TABLE[code]

    expect({
      scope: entry.scope,
      httpStatus: entry.httpStatus,
      read: entry.read,
      writeTarget: entry.write.target,
      writeVariant: entry.write.variant,
      writeExpected: entry.write.expected,
      outcomeUnknown: entry.write.outcomeUnknown === true,
    }).toEqual(expected)
  })

  it('scope が admin の code は ADMIN_ERROR_CODES、common は COMMON_ERROR_CODES', () => {
    for (const code of ADMIN_ERROR_CODES) expect(ERROR_TABLE[code].scope).toBe('admin')
    for (const code of COMMON_ERROR_CODES) expect(ERROR_TABLE[code].scope).toBe('common')
  })

  it('isKnownErrorCode は表にある code だけ true(未知の code・Object のプロトタイプのキーは false)', () => {
    expect(isKnownErrorCode('lock_held')).toBe(true)
    expect(isKnownErrorCode('unavailable')).toBe(true)
    expect(isKnownErrorCode('something_new')).toBe(false)
    expect(isKnownErrorCode('toString')).toBe(false)
    expect(isKnownErrorCode('__proto__')).toBe(false)
  })
})

describe('lock_state ごとの拒否の variant', () => {
  it.each([
    ['none', 'error'],
    ['held_crawl', 'error'],
    ['held_delete', 'error'],
    ['lease_expired', 'warning'],
    ['orphan', 'warning'],
    ['just_acquired', 'error'],
    ['unknown', 'error'],
  ] as const)('%s → %s', (lockState, variant) => {
    expect(LOCK_REFUSAL_VARIANT[lockState]).toBe(variant)
  })

  it('7 値を網羅する(LockState の 7 値)', () => {
    expect(Object.keys(LOCK_REFUSAL_VARIANT).sort()).toEqual([
      'held_crawl',
      'held_delete',
      'just_acquired',
      'lease_expired',
      'none',
      'orphan',
      'unknown',
    ])
  })

  it('isLockState は 7 値だけ true(未知の文字列・文字列でない値は false)', () => {
    expect(isLockState('orphan')).toBe(true)
    expect(isLockState('hold')).toBe(false)
    expect(isLockState(null)).toBe(false)
    expect(isLockState(undefined)).toBe(false)
    expect(isLockState('constructor')).toBe(false)
  })
})
