// API の失敗応答を作るビルダー(Vitest と Playwright で共有。型付き。F 7.3・E 10.2)。
// フレームワークに依存しない記述(MockResponse)を返し、Vitest は fetchStub が、Playwright は mockApi が実際の応答にする。
import type {
  ErrorDetails,
  ErrorResponse,
  ExistingJob,
  LockState,
  RequestedOptions,
} from '@/admin/api'

import { existingJob, SENTINEL_LEASE_EXPIRES_AT } from './fixtures/jobs'

export type MockResponse =
  // 通常の応答(JSON・HTML・空の本文)
  | {
      kind: 'response'
      status: number
      contentType: string
      body: string
      /** 追加のヘッダー(`content-length` など。プロキシが付けるものの再現用) */
      headers?: Record<string, string>
    }
  // 通信断(接続できない・切断)。Vitest は fetch の TypeError、Playwright は route.abort() になる
  | { kind: 'network-error' }
  // 応答しない(接続したまま返ってこない)。タイムアウト・中断の検証用。Vitest は解決しない Promise、Playwright は route を履行しない
  | { kind: 'hang' }

/** 200 などの JSON の応答。 */
export function jsonResponse(body: unknown, status = 200): MockResponse {
  return {
    kind: 'response',
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

type ApiErrorOptions = {
  retryable?: boolean
  details?: ErrorDetails
}

/** A 5.2 の形のエラー応答(`api` が返す JSON)。`message` は固定の英語文(診断用)で、画面は使わない。 */
export function apiErrorResponse(
  status: number,
  code: string,
  options: ApiErrorOptions = {},
): MockResponse {
  const body = {
    error: {
      code,
      message: `fixed message for ${code}`,
      retryable: options.retryable ?? false,
      ...(options.details !== undefined && { details: options.details }),
    },
  } satisfies ErrorResponse
  return jsonResponse(body, status)
}

/** Nginx(プロキシ)が返す HTML のエラー。`api` の JSON とは違い、`error.code` を持たない(FARC-P-43)。 */
export function nginxHtmlResponse(status: 413 | 502 | 503 | 504): MockResponse {
  const title = `${status} Error`
  return {
    kind: 'response',
    status,
    contentType: 'text/html',
    body: `<html><head><title>${title}</title></head><body><center><h1>${title}</h1></center><hr><center>nginx</center></body></html>`,
  }
}

/** 空の本文のエラー(上流が本文を返さなかったとき)。 */
export function emptyBodyResponse(status: number): MockResponse {
  return { kind: 'response', status, contentType: 'text/plain', body: '' }
}

/** 2xx なのに JSON でない本文(誤配信の HTML など)。 */
export function htmlOkResponse(): MockResponse {
  return {
    kind: 'response',
    status: 200,
    contentType: 'text/html',
    body: '<html><body>index</body></html>',
  }
}

/** 通信断(接続できない・切断)。 */
export function networkErrorResponse(): MockResponse {
  return { kind: 'network-error' }
}

/** 応答しない(接続したまま返ってこない)。タイムアウト・中断の検証に使う。 */
export function hangResponse(): MockResponse {
  return { kind: 'hang' }
}

/** 400 `invalid_request` の項目別エラー(`details.errors`)。 */
export function fieldErrorsResponse(
  errors: ReadonlyArray<{ field: string; reason: string; detail?: string }>,
  code: 'invalid_request' | 'config_invalid' = 'invalid_request',
): MockResponse {
  return apiErrorResponse(400, code, { details: { errors: [...errors] } as ErrorDetails })
}

type LockRefusalOptions = {
  lockState: LockState
  /** `details.existing_job`。ジョブ記録がない・読めないときの値(`status`・`job_type` が null)も、ここで作る */
  existingJob: ExistingJob | null
  /** EP-06(クロール起動)だけ。指定した `force_delete`・`rewrite_mode`(EP-05 には `requested` がない。B 2.7) */
  requested?: RequestedOptions
}

/** 409 `lock_held`(EP-05・06): 既存ジョブと「指定は反映されていない」(`options_applied=false`)を返す。 */
export function lockHeldResponse(options: LockRefusalOptions): MockResponse {
  return apiErrorResponse(409, 'lock_held', {
    details: {
      lock_state: options.lockState,
      existing_job: options.existingJob,
      ...(options.requested !== undefined && {
        options_applied: false,
        requested: options.requested,
      }),
    },
  })
}

/** 409 `lock_in_use`(EP-08): 解放できないロック。`existing_job`・`lock_state` を持つ。 */
export function lockInUseResponse(options: LockRefusalOptions): MockResponse {
  return apiErrorResponse(409, 'lock_in_use', {
    details: { lock_state: options.lockState, existing_job: options.existingJob },
  })
}

const REQUESTED: RequestedOptions = { force_delete: true, rewrite_mode: false }
/** ジョブ記録がない・読めない既存ジョブ(孤児ロック・取得直後)。 */
const NO_JOB_RECORD = existingJob({
  job_type: null,
  status: null,
  trigger: null,
  lease_expires_at: null,
})

/**
 * DLG-1・DLG-4(EP-06)・DLG-2・削除の再実行(EP-05)・DLG-5(EP-08)の拒否(E 6.3。`lock_state` と `existing_job` の組み合わせ)。
 * Vitest と Playwright で共有する。
 */
export const lockRefusals = {
  /** 実行中のジョブが保持(リース期限内)。指定は反映されていない */
  heldCrawl: () =>
    lockHeldResponse({ lockState: 'held_crawl', existingJob: existingJob(), requested: REQUESTED }),
  /** 実行待ちのジョブが保持 */
  heldCrawlQueued: () =>
    lockHeldResponse({
      lockState: 'held_crawl',
      existingJob: existingJob({ status: 'queued', lease_expires_at: null }),
      requested: REQUESTED,
    }),
  /** 削除ジョブが保持(EP-05。`requested` なし) */
  heldDelete: () =>
    lockHeldResponse({
      lockState: 'held_delete',
      existingJob: existingJob({ job_type: 'source_delete' }),
    }),
  /** リース切れのジョブが保持(warning。J2 → DLG-5 へ導く) */
  leaseExpired: () =>
    lockHeldResponse({
      lockState: 'lease_expired',
      existingJob: existingJob({ lease_expires_at: '2026-11-22T01:03:00.000Z' }),
      requested: REQUESTED,
    }),
  /** リース期限が日時として読めない(番兵。「期限切れ」と扱い、日時として整形しない。B 2.11・I-73) */
  leaseExpiredSentinel: () =>
    lockHeldResponse({
      lockState: 'lease_expired',
      existingJob: existingJob({ lease_expires_at: SENTINEL_LEASE_EXPIRES_AT }),
      requested: REQUESTED,
    }),
  /** 孤児ロック(ジョブ記録がない。warning。S2 のロック状態カードへ導く) */
  orphan: () =>
    lockHeldResponse({ lockState: 'orphan', existingJob: NO_JOB_RECORD, requested: REQUESTED }),
  /** ロック取得の直後(受付の途中の可能性。「ジョブを表示」を出さない) */
  justAcquired: () =>
    lockHeldResponse({
      lockState: 'just_acquired',
      existingJob: NO_JOB_RECORD,
      requested: REQUESTED,
    }),
  /** ロック状態を読めない(`unknown`。理由を断定しない) */
  unknown: () =>
    lockHeldResponse({ lockState: 'unknown', existingJob: null, requested: REQUESTED }),
  /** 既存ジョブの `status` が未知の文字列(Crawler の文字列をそのまま通すため。J-E9)。「ジョブを表示」を出さない */
  existingJobUnknownStatus: () =>
    lockHeldResponse({
      lockState: 'held_crawl',
      existingJob: { ...existingJob(), status: 'paused' as ExistingJob['status'] },
      requested: REQUESTED,
    }),
  /** EP-08: 実行中のジョブが保持(解放できない。取消を使う) */
  releaseInUseRunning: () =>
    lockInUseResponse({ lockState: 'held_crawl', existingJob: existingJob() }),
  /** EP-08: 削除ジョブが保持(解放できない。完了を待つ) */
  releaseInUseDelete: () =>
    lockInUseResponse({
      lockState: 'held_delete',
      existingJob: existingJob({ job_type: 'source_delete' }),
    }),
  /** EP-08: 取得直後(解放できない。しばらく待つ) */
  releaseInUseJustAcquired: () =>
    lockInUseResponse({ lockState: 'just_acquired', existingJob: NO_JOB_RECORD }),
  /** EP-08: ロック文書・ジョブ記録を読めない(`unknown`。理由を断定しない) */
  releaseInUseUnknown: () => lockInUseResponse({ lockState: 'unknown', existingJob: null }),
}
