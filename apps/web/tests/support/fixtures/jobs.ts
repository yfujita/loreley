// EP-05〜10 のフィクスチャ(F 7.3): ジョブ(`JobBrief`・一覧・詳細・受付・取消・ロック解放)。
// 状態ごとの関数として集め、Vitest と Playwright で共有する。生成した型(スキーマ名の型)で `satisfies` する。
import type {
  CancelJobResponse,
  Deletion,
  ExistingJob,
  JobAccepted,
  JobBrief,
  JobDetailResponse,
  JobListItem,
  JobListResponse,
  Registration,
  ReleaseLockResponse,
} from '@/admin/api'

export const QUEUED_AT = '2026-11-22T01:00:00.000Z'
export const STARTED_AT = '2026-11-22T01:00:05.000Z'
export const FINISHED_AT = '2026-11-22T01:05:00.000Z'
/** 番兵の日時(Crawler が日時として読めないリース期限。B 2.11・I-73) */
export const SENTINEL_LEASE_EXPIRES_AT = '0001-01-01T00:00:00.000Z'

export function jobBrief(overrides: Partial<JobBrief> = {}): JobBrief {
  return {
    job_id: 'job-20261122T010000Z-aaaa0001',
    source_id: 'demo-handbook',
    job_type: 'crawl',
    trigger: 'manual',
    status: 'succeeded',
    force_delete: false,
    rewrite_mode: false,
    queued_at: QUEUED_AT,
    started_at: STARTED_AT,
    finished_at: FINISHED_AT,
    failure_reason: null,
    stalled: false,
    cancellable: false,
    ...overrides,
  } satisfies JobBrief
}

export function jobListItem(overrides: Partial<JobListItem> = {}): JobListItem {
  return { ...jobBrief(), unavailable: {}, ...overrides } satisfies JobListItem
}

export function existingJob(overrides: Partial<ExistingJob> = {}): ExistingJob {
  return {
    job_id: 'job-20261122T010000Z-bbbb0002',
    job_type: 'crawl',
    status: 'running',
    trigger: 'schedule',
    lease_expires_at: '2026-11-22T01:07:03.456Z',
    ...overrides,
  } satisfies ExistingJob
}

function listResponse(
  items: JobListItem[],
  overrides: Partial<JobListResponse> = {},
): JobListResponse {
  return {
    items,
    page: 1,
    items_per_page: 25,
    total: items.length,
    window_limit: 10_000,
    unavailable: {},
    ...overrides,
  } satisfies JobListResponse
}

/** EP-09 の一覧。 */
export const jobList = {
  /** 状態の混在(成功・実行中・失敗・取消・一部成功) */
  normal: () =>
    listResponse([
      jobListItem({
        job_id: 'job-3',
        status: 'running',
        started_at: STARTED_AT,
        finished_at: null,
        cancellable: true,
      }),
      jobListItem({ job_id: 'job-2', status: 'failed', failure_reason: 'config_invalid' }),
      jobListItem({ job_id: 'job-1', status: 'succeeded' }),
      jobListItem({ job_id: 'job-4', status: 'partially_succeeded' }),
      jobListItem({ job_id: 'job-5', status: 'cancelled' }),
    ]),
  empty: () => listResponse([]),
  /** 大量(ページング。`page × items_per_page ≤ 10,000` の窓の手前) */
  manyPages: () =>
    listResponse(
      Array.from({ length: 25 }, (_, index) => jobListItem({ job_id: `job-${index + 1}` })),
      { total: 240 },
    ),
  /** `status=null`(保存値が読めない行。タグも取消も出さない) */
  statusNull: () =>
    listResponse([
      jobListItem({
        job_id: 'job-unreadable',
        status: null,
        job_type: null,
        trigger: null,
        queued_at: null,
        stalled: false,
        cancellable: false,
      }),
    ]),
  /** リース切れ(保存上は running。`stalled=true`・取消できない) */
  stalled: () =>
    listResponse([jobListItem({ job_id: 'job-stalled', status: 'running', stalled: true })]),
  /** その行だけ `stalled` を取得できない(`stalled=null`・`cancellable=false`。他の行には影響しない) */
  oneRowStalledUnavailable: () =>
    listResponse([
      jobListItem({
        job_id: 'job-unknown-lease',
        status: 'running',
        stalled: null,
        cancellable: false,
        unavailable: { stalled: 'store_unavailable' },
      }),
      jobListItem({ job_id: 'job-ok', status: 'running', stalled: false, cancellable: true }),
    ]),
  /** 起動時の指定が `null`(記録にない)の失敗ジョブ */
  nullFlags: () =>
    listResponse([
      jobListItem({
        job_id: 'job-null-flags',
        status: 'failed',
        force_delete: null,
        rewrite_mode: null,
      }),
    ]),
}

function registration(overrides: Partial<Registration> = {}): Registration {
  return {
    enumerated_count: 120,
    created_count: 2,
    updated_count: 12,
    unchanged_count: 100,
    skipped_count: 3,
    oversize_count: 1,
    error_count: 2,
    invalid_id_count: 0,
    partial: false,
    phase: 'final',
    ...overrides,
  } satisfies Registration
}

function deletion(overrides: Partial<Deletion> = {}): Deletion {
  return {
    current_state: 'available',
    fetched_at: '2026-11-22T01:06:00.000Z',
    current: {
      status: 'running',
      target_count: 10,
      deleted_count: 4,
      denominator: 1000,
      forced: false,
      reason: null,
      reason_detail: null,
      ended_at: null,
    },
    summary: null,
    settings: { ttl_seconds: 2_592_000, ratio_threshold_percent: 20, min_delete_count: 10 },
    confirmation: 'unconfirmed',
    ...overrides,
  } satisfies Deletion
}

export function jobDetail(overrides: Partial<JobDetailResponse> = {}): JobDetailResponse {
  return {
    ...jobBrief(),
    failure_detail: null,
    lease_expires_at: null,
    latest_for_source: true,
    rerunnable: false,
    rerun_blocked_reason: 'not_failed',
    cancel_after_finish_notice: false,
    registration: registration(),
    deletion: null,
    warnings: [],
    unavailable: {},
    ...overrides,
  } satisfies JobDetailResponse
}

/** EP-10 の詳細。 */
export const jobDetails = {
  succeeded: () => jobDetail(),
  /** 実行中(10 秒ごとにポーリング。集計の途中) */
  running: () =>
    jobDetail({
      status: 'running',
      finished_at: null,
      cancellable: true,
      lease_expires_at: '2026-11-22T01:07:03.456Z',
      registration: registration({ partial: true, phase: 'in_progress' }),
    }),
  queued: () =>
    jobDetail({
      status: 'queued',
      started_at: null,
      finished_at: null,
      cancellable: true,
      lease_expires_at: null,
      registration: null,
    }),
  /** 失敗(再実行できる。最新のジョブ) */
  failedRerunnable: () =>
    jobDetail({
      status: 'failed',
      failure_reason: 'config_invalid',
      failure_detail: 'root: `/` で始まる絶対パスでない',
      rerunnable: true,
      rerun_blocked_reason: null,
      force_delete: true,
      rewrite_mode: false,
    }),
  /** 失敗だが、起動時の指定が `null`(DLG-4 は `false` で送り「記録なし」と表示する。E 7.5) */
  failedNullFlags: () =>
    jobDetail({
      status: 'failed',
      rerunnable: true,
      rerun_blocked_reason: null,
      force_delete: null,
      rewrite_mode: null,
    }),
  /** より新しいジョブがある(再実行できない) */
  failedSuperseded: () =>
    jobDetail({
      status: 'failed',
      latest_for_source: false,
      rerunnable: false,
      rerun_blocked_reason: 'superseded',
    }),
  /** データソースの設定がない(削除済み。再実行を出さない) */
  failedSourceMissing: () =>
    jobDetail({
      status: 'failed',
      rerunnable: false,
      rerun_blocked_reason: 'source_missing',
    }),
  /** リース切れ(ロック未解放。期限あり) */
  stalledWithLeaseExpiry: () =>
    jobDetail({
      status: 'running',
      stalled: true,
      cancellable: false,
      lease_expires_at: '2026-11-22T01:03:00.000Z',
      rerunnable: false,
      rerun_blocked_reason: 'stalled',
    }),
  /** `stalled=true` かつ `lease_expires_at=null`(「期限を確認できません(期限切れ)」。J-E5) */
  stalledWithoutLeaseExpiry: () =>
    jobDetail({
      status: 'running',
      stalled: true,
      cancellable: false,
      lease_expires_at: null,
      rerunnable: false,
      rerun_blocked_reason: 'stalled',
    }),
  /** `stalled`・`rerunnable`・`latest_for_source` が取得できない(取消・再実行を出さない) */
  flagsUnavailable: () =>
    jobDetail({
      status: 'failed',
      stalled: null,
      rerunnable: null,
      rerun_blocked_reason: null,
      latest_for_source: null,
      cancellable: false,
      unavailable: {
        stalled: 'store_unavailable',
        rerunnable: 'store_unavailable',
        latest_for_source: 'store_unavailable',
      },
    }),
  /** `status=null`(保存値が読めない。タグ・操作を出さず、件数・`partial` は「—」) */
  statusNull: () =>
    jobDetail({
      status: null,
      job_type: null,
      trigger: null,
      queued_at: null,
      cancellable: false,
      registration: registration({
        created_count: null,
        updated_count: null,
        partial: null,
        phase: null,
      }),
    }),
  /** 警告(既知のコード・未知のコード・`code` が文字列でない要素) */
  warnings: () =>
    jobDetail({
      status: 'partially_succeeded',
      warnings: [
        { code: 'invalid_external_id', count: 3 },
        { code: 'brand_new_warning' },
        { code: 42 },
        { note: 'no code' },
      ],
    }),
  /** 削除ジョブ(`source_delete`)。現在値あり */
  sourceDelete: () =>
    jobDetail({
      job_type: 'source_delete',
      status: 'running',
      registration: null,
      deletion: deletion(),
      cancellable: false,
    }),
  /** 削除の現在値を読めない(`unavailable`。`fetched_at` が入っていても取得時刻として出さない。J-E10) */
  deletionUnavailable: () =>
    jobDetail({
      job_type: 'source_delete',
      status: 'failed',
      registration: null,
      deletion: deletion({ current_state: 'unavailable', current: null }),
      unavailable: { 'deletion.current': 'store_unavailable' },
    }),
  /** 削除の現在値がない(`not_found`) */
  deletionNotFound: () =>
    jobDetail({
      job_type: 'source_delete',
      status: 'succeeded',
      registration: null,
      deletion: deletion({ current_state: 'not_found', current: null }),
    }),
  /** 取消が終了通知の後に受け付けられた(「取消は削除を止めていません」) */
  cancelledAfterFinishNotice: () =>
    jobDetail({ status: 'cancelled', cancel_after_finish_notice: true }),
}

/** EP-05・06 の 202。 */
export const jobAccepted = {
  crawl: (overrides: Partial<JobAccepted> = {}) =>
    ({
      job_id: 'job-20261122T020000Z-cccc0003',
      job_type: 'crawl',
      source_id: 'demo-handbook',
      status: 'queued',
      trigger: 'manual',
      force_delete: false,
      rewrite_mode: false,
      queued_at: '2026-11-22T02:00:00.000Z',
      ...overrides,
    }) satisfies JobAccepted,
  sourceDelete: (overrides: Partial<JobAccepted> = {}) =>
    ({
      job_id: 'job-20261122T020100Z-dddd0004',
      job_type: 'source_delete',
      source_id: 'demo-handbook',
      status: 'queued',
      trigger: 'manual',
      force_delete: null,
      rewrite_mode: null,
      queued_at: '2026-11-22T02:01:00.000Z',
      ...overrides,
    }) satisfies JobAccepted,
}

/** EP-07 の 200・202。 */
export const cancelJobResponses = {
  /** 202(取消を要求した。終端はまだ) */
  requested: () => ({ job_id: 'job-3', status: 'running' }) satisfies CancelJobResponse,
  /** 200(取り消した) */
  cancelled: () => ({ job_id: 'job-3', status: 'cancelled' }) satisfies CancelJobResponse,
}

/** EP-08 の 200。 */
export const releaseLockResponses = {
  released: () =>
    ({
      source_id: 'demo-handbook',
      released: true,
      failed_job_id: 'job-stalled',
    }) satisfies ReleaseLockResponse,
  /** ロック文書がなく解放するものがなかった(`released=false`。成功の文言にしない。J-E6) */
  notReleased: () =>
    ({
      source_id: 'demo-handbook',
      released: false,
      failed_job_id: null,
    }) satisfies ReleaseLockResponse,
}
