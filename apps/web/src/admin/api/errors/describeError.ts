// error(`unknown`)と文脈から、画面が表示するための記述を作る純関数(E 6.1・F 3.3)。
// 画面は結果を表示するだけで、`error.error.code` を直接読まない。
// ダイアログごとの拒否の組み立て(`lock_held` の既存ジョブ・次の行動など)は、ダイアログの純関数(refusal.ts)が担う。
import { isApiError, type ApiError, type ApiErrorDetails } from '@/shared/api/apiError'

import {
  ERROR_TABLE,
  isKnownErrorCode,
  isLockState,
  LOCK_REFUSAL_VARIANT,
  type AlertVariant,
} from '@/admin/api/errors/errorTable'
import type { LockState } from '@/admin/api/generated/types.gen'

/** 書き込みの操作(EP-03〜08。mutation の名前)。 */
export type WriteOperation =
  | 'registerSource'
  | 'updateSource'
  | 'startSourceDelete'
  | 'startCrawl'
  | 'cancelJob'
  | 'releaseLock'

/** 文脈: 読み取り(Query)か、書き込み(mutation)の操作。 */
export type ErrorContext = { operation: 'read' } | { operation: WriteOperation }

/**
 * 表示先。`field` は暫定: 表にない `field`・対応できない `reason`・`detail` は、features の `fieldMap`
 * (F 3.5。フェーズ 6)が `form-alert`(想定外の応答+診断)に落とす。ここは `details.errors` が返ってきたかだけで決める。
 */
export type DisplayTarget =
  // 読み取りの失敗(状態ブロック。E 6.2)
  | 'state-block'
  // 項目別(フォームの入力欄の下。DS 4.6)
  | 'field'
  // フォーム上部のアラート(S3・S4。消えない)
  | 'form-alert'
  // ダイアログ内アラート(操作の失敗・拒否。閉じるまで残る。DS 4.7)
  | 'dialog-alert'
  // 成功扱い(`job_already_finished`)
  | 'success'

/** `details.errors[]` の 1 件。サーバーの値は信用せず、`reason` は文字列のまま持つ。 */
export type FieldErrorEntry = {
  field: string
  reason: string
  detail: string | null
}

export type ErrorDescription = {
  target: DisplayTarget
  variant: AlertVariant
  /** 読み取りの「見つかりません」(前回データがあっても stale にしない。E 6.2) */
  notFound: boolean
  /** 「再試行」を出すか。書き込みは `retryable=true` のときだけ(結果不明では出さない) */
  retryable: boolean
  /** 操作が実行されたか確認できない(E 6.5)。再試行を出さず、状態を確認する導線を出す */
  outcomeUnknown: boolean
  /** 結果不明のうち、保存系(EP-03・04)は再送が安全なので「もう一度保存」を出してよい */
  resendSafe: boolean
  /** 想定外: 一般的な文言+診断(code と HTTP ステータス)を出す。`message` は出さない */
  unexpected: boolean
  fieldErrors: readonly FieldErrorEntry[]
  /** `config_invalid` の `details.crawler_message`(Crawler の固定文。入力値・パスを含まない) */
  crawlerMessage: string | null
  /** `lock_held`・`lock_in_use` の `details.lock_state` */
  lockState: LockState | null
  /** 診断用の補助文字。入力値・パスは含まない */
  diagnostic: { code: string | null; status: number | null }
}

const SAVE_OPERATIONS: ReadonlySet<WriteOperation> = new Set(['registerSource', 'updateSource'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function readFieldErrors(details: ApiErrorDetails | undefined): FieldErrorEntry[] {
  const errors = details?.errors
  if (!Array.isArray(errors)) return []
  return errors.flatMap((item: unknown): FieldErrorEntry[] => {
    if (!isRecord(item)) return []
    if (typeof item.field !== 'string' || typeof item.reason !== 'string') return []
    return [
      {
        field: item.field,
        reason: item.reason,
        detail: typeof item.detail === 'string' ? item.detail : null,
      },
    ]
  })
}

function statusOf(error: ApiError): number | null {
  if (error.kind === 'api') return error.status
  if (error.kind === 'invalid_response') return error.status ?? null
  return null
}

function codeOf(error: ApiError): string | null {
  return error.kind === 'api' ? error.code : null
}

function isFormOperation(operation: WriteOperation): boolean {
  return SAVE_OPERATIONS.has(operation)
}

/**
 * `error` を `unknown` として受け、ApiError でなければ `invalid_response`(status なし)として扱う
 * (生成型の `ErrorResponse` を信用しない二重の備え。E 5.3)。
 */
export function describeError(error: unknown, context: ErrorContext): ErrorDescription {
  const apiError: ApiError = isApiError(error) ? error : { kind: 'invalid_response' }
  return context.operation === 'read'
    ? describeReadError(apiError)
    : describeWriteError(apiError, context.operation)
}

function describeReadError(error: ApiError): ErrorDescription {
  const base = {
    outcomeUnknown: false,
    resendSafe: false,
    fieldErrors: [],
    crawlerMessage: null,
    lockState: null,
    diagnostic: { code: codeOf(error), status: statusOf(error) },
  } satisfies Partial<ErrorDescription>

  // network・timeout・invalid_response(Nginx の HTML を含む)は、エラーブロックまたは stale(E 6.5)。
  if (error.kind !== 'api') {
    return {
      ...base,
      target: 'state-block',
      variant: 'error',
      notFound: false,
      retryable: true,
      unexpected: error.kind === 'invalid_response',
    }
  }

  const treatment = isKnownErrorCode(error.code) ? ERROR_TABLE[error.code].read : 'unexpected'
  return {
    ...base,
    target: 'state-block',
    variant: 'error',
    notFound: treatment === 'not-found',
    retryable: treatment !== 'not-found',
    unexpected: treatment === 'unexpected',
  }
}

function describeWriteError(error: ApiError, operation: WriteOperation): ErrorDescription {
  const isForm = isFormOperation(operation)
  const alertTarget: DisplayTarget = isForm ? 'form-alert' : 'dialog-alert'
  const diagnostic = { code: codeOf(error), status: statusOf(error) }

  // 結果不明(E 6.5): invalid_response は status を問わず、network・timeout も含む(書き込みでは送信後の切断と区別できない)。
  if (error.kind !== 'api') {
    return {
      target: alertTarget,
      variant: 'warning',
      notFound: false,
      retryable: false,
      outcomeUnknown: true,
      resendSafe: isForm,
      unexpected: false,
      fieldErrors: [],
      crawlerMessage: null,
      lockState: null,
      diagnostic,
    }
  }

  const entry = isKnownErrorCode(error.code) ? ERROR_TABLE[error.code] : null
  const treatment = entry?.write ?? { target: 'alert', variant: 'error', expected: false }
  const details = error.details
  const fieldErrors = readFieldErrors(details)
  const outcomeUnknown = error.outcomeUnknown || treatment.outcomeUnknown === true
  const rawLockState = details?.lock_state
  const lockState = isLockState(rawLockState) ? rawLockState : null
  const crawlerMessage =
    typeof details?.crawler_message === 'string' ? details.crawler_message : null

  let target: DisplayTarget
  let expected = treatment.expected
  if (treatment.target === 'success') {
    target = 'success'
  } else if (treatment.target === 'field') {
    // 項目別は S3・S4 で、`details.errors` があるときだけ。
    // - invalid_request: `details`・`errors` がないものは想定外(本文が JSON として読めない・1 MiB 超など。S-E4)
    // - config_invalid: `errors` が空(分解不能)のときは上部アラートに `crawler_message` を出す(想定外ではない)
    // - source_already_exists: 識別子の項目の下(`details.errors` はない)
    const hasFieldInformation = fieldErrors.length > 0 || error.code === 'source_already_exists'
    target = isForm && hasFieldInformation ? 'field' : alertTarget
    if (error.code === 'invalid_request' && !(isForm && hasFieldInformation)) expected = false
  } else {
    target = alertTarget
  }

  const isLockRefusal = error.code === 'lock_held' || error.code === 'lock_in_use'
  const variant =
    isLockRefusal && lockState !== null ? LOCK_REFUSAL_VARIANT[lockState] : treatment.variant

  return {
    target,
    variant,
    notFound: false,
    retryable: error.retryable && !outcomeUnknown,
    outcomeUnknown,
    resendSafe: outcomeUnknown && isForm,
    unexpected: !expected,
    fieldErrors,
    crawlerMessage,
    lockState,
    diagnostic,
  }
}
