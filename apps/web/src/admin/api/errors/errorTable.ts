// エラー変換表(E 6.1・6.3・F 3.3): `code` → 表示先・variant・想定内か。画面は describeError の結果を表示するだけ。
//
// OpenAPI では `ErrorBody.code` は string で列挙がない(どの code が返るかは各 EP の説明文にしか出ない)ため、
// この手書きの表が正本。Admin 固有 14 種(B 2.3)と共通 6 種(A 5.2)を網羅する。
// OpenAPI の説明文との突き合わせは errorTable.contract.test.ts。
import type { LockState } from '@/admin/api/generated/types.gen'

/** Admin 固有の code(B 2.3)。 */
export const ADMIN_ERROR_CODES = [
  'config_invalid',
  'source_config_not_found',
  'job_not_found',
  'lock_held',
  'lock_in_use',
  'source_deleting',
  'maintenance_enabled',
  'source_already_exists',
  'job_not_cancellable',
  'job_already_finished',
  'crawler_error',
  'crawler_unavailable',
  'crawler_unreachable',
  'crawler_response_lost',
] as const

/** 共通の code(A 5.2)。 */
export const COMMON_ERROR_CODES = [
  'invalid_request',
  'not_found',
  'method_not_allowed',
  'http_error',
  'internal_error',
  'unavailable',
] as const

export type KnownErrorCode =
  (typeof ADMIN_ERROR_CODES)[number] | (typeof COMMON_ERROR_CODES)[number]

export type AlertVariant = 'error' | 'warning' | 'info'

/**
 * 読み取りの失敗の扱い(E 6.2)。
 * - not-found: 「見つかりません」(前回データがあっても stale にしない)
 * - error: 取得できません(エラーブロックまたは stale)
 * - unexpected: 想定外。一般的な文言+診断(code と HTTP ステータス)
 */
export type ReadTreatment = 'not-found' | 'error' | 'unexpected'

/**
 * 書き込みの失敗の扱い(E 6.3)。
 * - target `alert`: ダイアログ内アラート(DLG)またはフォーム上部のアラート(S3・S4)。describeError が操作から決める
 * - target `field`: 項目別(フォームの入力欄の下)。S3・S4 以外・項目の情報がないときは `alert` に落ちる
 * - target `success`: 成功扱い(`job_already_finished`)
 */
export type WriteTreatment = {
  target: 'alert' | 'field' | 'success'
  variant: AlertVariant
  /** false は想定外: 一般的な文言+診断(code と HTTP ステータス)。`message` は出さない */
  expected: boolean
  /** true は操作の結果が不明(E 6.5)。`details.outcome_unknown` がなくても結果不明として扱う */
  outcomeUnknown?: true
}

export type ErrorTableEntry = {
  scope: 'admin' | 'common'
  /** A 5.2・B 2.3 の HTTP ステータス。`http_error` は 4xx・5xx のうち上記以外なので固定できない */
  httpStatus: number | null
  read: ReadTreatment
  write: WriteTreatment
}

const UNEXPECTED_WRITE: WriteTreatment = { target: 'alert', variant: 'error', expected: false }
const EXPECTED_ALERT: WriteTreatment = { target: 'alert', variant: 'error', expected: true }

export const ERROR_TABLE: Readonly<Record<KnownErrorCode, ErrorTableEntry>> = {
  // ── Admin 固有 14 種
  config_invalid: {
    scope: 'admin',
    httpStatus: 400,
    read: 'unexpected',
    write: { target: 'field', variant: 'error', expected: true },
  },
  source_config_not_found: {
    scope: 'admin',
    httpStatus: 404,
    read: 'not-found',
    write: EXPECTED_ALERT,
  },
  job_not_found: { scope: 'admin', httpStatus: 404, read: 'not-found', write: EXPECTED_ALERT },
  // variant は lock_state で決まる(LOCK_REFUSAL_VARIANT)。
  lock_held: { scope: 'admin', httpStatus: 409, read: 'unexpected', write: EXPECTED_ALERT },
  lock_in_use: { scope: 'admin', httpStatus: 409, read: 'unexpected', write: EXPECTED_ALERT },
  source_deleting: { scope: 'admin', httpStatus: 409, read: 'unexpected', write: EXPECTED_ALERT },
  maintenance_enabled: {
    scope: 'admin',
    httpStatus: 409,
    read: 'unexpected',
    write: EXPECTED_ALERT,
  },
  source_already_exists: {
    scope: 'admin',
    httpStatus: 409,
    read: 'unexpected',
    write: { target: 'field', variant: 'error', expected: true },
  },
  // 画面は cancellable=false の行に操作を出さないため、通常は出ない(想定外の扱い)。
  job_not_cancellable: {
    scope: 'admin',
    httpStatus: 409,
    read: 'unexpected',
    write: UNEXPECTED_WRITE,
  },
  job_already_finished: {
    scope: 'admin',
    httpStatus: 409,
    read: 'unexpected',
    write: { target: 'success', variant: 'info', expected: true },
  },
  crawler_error: { scope: 'admin', httpStatus: 502, read: 'unexpected', write: UNEXPECTED_WRITE },
  crawler_unavailable: {
    scope: 'admin',
    httpStatus: 503,
    read: 'unexpected',
    write: EXPECTED_ALERT,
  },
  crawler_unreachable: {
    scope: 'admin',
    httpStatus: 503,
    read: 'unexpected',
    write: EXPECTED_ALERT,
  },
  crawler_response_lost: {
    scope: 'admin',
    httpStatus: 504,
    read: 'unexpected',
    write: { target: 'alert', variant: 'warning', expected: true, outcomeUnknown: true },
  },

  // ── 共通 6 種
  // 読み取りでは、パスの ID の形式違反(送信前のパス値の検証の拒否を含む)を「見つかりません」と同じに扱う(E 6.2)。
  // 書き込みの項目別(S3・S4。`details.errors` あり)は表のとおり。ダイアログ系・`details` なしは describeError が想定外にする。
  invalid_request: {
    scope: 'common',
    httpStatus: 400,
    read: 'not-found',
    write: { target: 'field', variant: 'error', expected: true },
  },
  // `/` を含む ID は Admin API のルーティングで 404 `not_found`(B 2.12)。読み取りでは「見つかりません」。
  not_found: { scope: 'common', httpStatus: 404, read: 'not-found', write: UNEXPECTED_WRITE },
  method_not_allowed: {
    scope: 'common',
    httpStatus: 405,
    read: 'unexpected',
    write: UNEXPECTED_WRITE,
  },
  http_error: { scope: 'common', httpStatus: null, read: 'unexpected', write: UNEXPECTED_WRITE },
  internal_error: {
    scope: 'common',
    httpStatus: 500,
    read: 'unexpected',
    write: UNEXPECTED_WRITE,
  },
  unavailable: { scope: 'common', httpStatus: 503, read: 'error', write: UNEXPECTED_WRITE },
}

export function isKnownErrorCode(code: string): code is KnownErrorCode {
  return Object.hasOwn(ERROR_TABLE, code)
}

/**
 * `lock_held`・`lock_in_use` の拒否の variant(`details.lock_state` 別。E 6.3・admin-view 7.7)。
 * リース切れ・孤児ロックは「止まったロックが残っている」ので warning、それ以外は error。
 * `just_acquired`(取得の直後。受付の途中の可能性)の variant は設計に明記がなく、error とする(案)。
 */
export const LOCK_REFUSAL_VARIANT: Readonly<Record<LockState, AlertVariant>> = {
  none: 'error',
  held_crawl: 'error',
  held_delete: 'error',
  lease_expired: 'warning',
  orphan: 'warning',
  just_acquired: 'error',
  unknown: 'error',
}

/** 未知の `lock_state` 文字列を LockState に絞る。 */
export function isLockState(value: unknown): value is LockState {
  return typeof value === 'string' && Object.hasOwn(LOCK_REFUSAL_VARIANT, value)
}
