// EP-01〜04 のフィクスチャ(F 7.3): データソース(一覧・詳細・設定)。
// 状態ごとの関数として集め、Vitest と Playwright で共有する。生成した型(スキーマ名の型)で `satisfies` する。
// EP-02 の応答(`SourceDetailResponse`)と EP-03・04 の応答(`SourceSettings`)は別の型(5.2 の 2)。
import type {
  Lock,
  LockState,
  SourceDetailResponse,
  SourceListItem,
  SourceListResponse,
  SourceSettings,
} from '@/admin/api'

import { existingJob, jobBrief, FINISHED_AT } from './jobs'

const UPDATED_AT = '2026-11-20T00:00:00.000Z'

export const FILE_SYSTEM_CONFIG = {
  root: '/data/handbook',
  include_patterns: [] as string[],
  exclude_patterns: [] as string[],
  follow_symlinks: false,
  include_hidden: false,
}

export function sourceListItem(overrides: Partial<SourceListItem> = {}): SourceListItem {
  return {
    source_id: 'demo-handbook',
    connector_type: 'file_system',
    schedule_cron: '0 3 * * *',
    status: 'active',
    last_crawl: jobBrief(),
    last_completed_at: FINISHED_AT,
    delete_job: null,
    document_count: 1284,
    unavailable: {},
    ...overrides,
  } satisfies SourceListItem
}

function listResponse(items: SourceListItem[]): SourceListResponse {
  // 一覧の EP の最上位 `unavailable` は常に `{}`(行に属さない項目がない。B 2.2)
  return { items, unavailable: {} } satisfies SourceListResponse
}

/** EP-01 の一覧。 */
export const sourceList = {
  normal: () =>
    listResponse([
      sourceListItem(),
      sourceListItem({ source_id: 'demo-wiki', schedule_cron: null, document_count: 52 }),
    ]),
  empty: () => listResponse([]),
  /** 未実行(`last_crawl=null`・キーなし)の行と、読み取りに失敗した行(キーあり)。2 つは行の `unavailable` で区別できる */
  neverCrawledAndFailedMixed: () =>
    listResponse([
      sourceListItem({
        source_id: 'source-a',
        last_crawl: null,
        last_completed_at: null,
        document_count: 0,
      }),
      sourceListItem({
        source_id: 'source-b',
        last_crawl: null,
        last_completed_at: null,
        document_count: 12,
        unavailable: {
          last_crawl: 'store_unavailable',
          last_completed_at: 'store_unavailable',
        },
      }),
    ]),
  /** 全行が失敗(一括の読み取りの失敗は、全行の `unavailable` に同じキーを付ける。最上位ではなく行に) */
  allRowsUnavailable: () =>
    listResponse(
      ['source-a', 'source-b'].map((source_id) =>
        sourceListItem({
          source_id,
          document_count: null,
          unavailable: { document_count: 'search_index_unavailable' },
        }),
      ),
    ),
  /** 1 行だけ失敗(他の行には影響しない) */
  oneRowUnavailable: () =>
    listResponse([
      sourceListItem({ source_id: 'source-a' }),
      sourceListItem({
        source_id: 'source-b',
        document_count: null,
        unavailable: { document_count: 'timeout' },
      }),
    ]),
  /** `status=null`・`connector_type=null`(保存値が読めない行。削除中の判定も操作も出さない。S-D2) */
  statusNull: () =>
    listResponse([
      sourceListItem({ source_id: 'source-unreadable', status: null, connector_type: null }),
    ]),
  /** 削除中(削除ジョブが実行中・失敗) */
  deleting: () =>
    listResponse([
      sourceListItem({
        source_id: 'source-deleting-running',
        status: 'deleting',
        delete_job: jobBrief({
          job_id: 'job-del-1',
          job_type: 'source_delete',
          status: 'running',
          cancellable: false,
          finished_at: null,
        }),
      }),
      sourceListItem({
        source_id: 'source-deleting-failed',
        status: 'deleting',
        delete_job: jobBrief({
          job_id: 'job-del-2',
          job_type: 'source_delete',
          status: 'failed',
          failure_reason: 'internal_error',
        }),
      }),
    ]),
  /** 直近のクロールがリース切れ(`last_crawl.stalled=true`) */
  lastCrawlStalled: () =>
    listResponse([
      sourceListItem({
        last_crawl: jobBrief({ status: 'running', stalled: true, finished_at: null }),
      }),
    ]),
  /** `last_crawl.stalled` を取得できない(`stalled=null`。行の `unavailable` の相対パス) */
  lastCrawlStalledUnavailable: () =>
    listResponse([
      sourceListItem({
        last_crawl: jobBrief({ status: 'running', stalled: null, finished_at: null }),
        unavailable: { 'last_crawl.stalled': 'store_unavailable' },
      }),
    ]),
}

export function sourceSettings(overrides: Partial<SourceSettings> = {}): SourceSettings {
  return {
    source_id: 'demo-handbook',
    connector_type: 'file_system',
    connector_config: { ...FILE_SYSTEM_CONFIG },
    ttl_seconds: 2_592_000,
    ttl_days: 30,
    ratio_threshold_percent: 20,
    min_delete_count: 10,
    schedule_cron: '0 3 * * *',
    status: 'active',
    updated_at: UPDATED_AT,
    ...overrides,
  } satisfies SourceSettings
}

export function lock(state: LockState, overrides: Partial<Lock> = {}): Lock {
  const jobByState: Record<LockState, Lock['job']> = {
    none: null,
    held_crawl: existingJob({ status: 'running' }),
    held_delete: existingJob({ job_type: 'source_delete', status: 'running' }),
    lease_expired: existingJob({ status: 'running', lease_expires_at: '2026-11-22T01:03:00.000Z' }),
    // 孤児ロック: ジョブ記録がない(`job_type`・`status` が null)
    orphan: existingJob({ job_type: null, status: null, trigger: null, lease_expires_at: null }),
    just_acquired: existingJob({
      job_type: null,
      status: null,
      trigger: null,
      lease_expires_at: null,
    }),
    unknown: null,
  }
  return {
    state,
    acquired_at: state === 'none' ? null : '2026-11-22T01:00:00.000Z',
    job: jobByState[state],
    ...overrides,
  } satisfies Lock
}

export function sourceDetail(overrides: Partial<SourceDetailResponse> = {}): SourceDetailResponse {
  return {
    ...sourceSettings(),
    last_crawl: jobBrief(),
    last_completed_at: FINISHED_AT,
    delete_job: null,
    index: { document_count: 1284 },
    lock: lock('none'),
    unavailable: {},
    ...overrides,
  } satisfies SourceDetailResponse
}

/** EP-02 の詳細。 */
export const sourceDetails = {
  normal: () => sourceDetail(),
  /** 未実行(直近のジョブなし) */
  neverCrawled: () => sourceDetail({ last_crawl: null, last_completed_at: null }),
  /** ロック状態 7 値(`none`・`held_crawl`・`held_delete`・`lease_expired`・`orphan`・`just_acquired`・`unknown`) */
  withLock: (state: LockState) => sourceDetail({ lock: lock(state) }),
  /** リース切れだが `lock.job.lease_expires_at` が `null`(「期限を確認できません(期限切れ)」。J-E5) */
  leaseExpiredWithoutExpiry: () =>
    sourceDetail({
      lock: lock('lease_expired', {
        job: existingJob({ status: 'running', lease_expires_at: null }),
      }),
    }),
  /** ロック状態を取得できない(`lock=null`・`unavailable.lock`) */
  lockUnavailable: () => sourceDetail({ lock: null, unavailable: { lock: 'store_unavailable' } }),
  /** 削除中(`status=deleting`。ロックは `held_delete`) */
  deleting: () =>
    sourceDetail({
      status: 'deleting',
      lock: lock('held_delete'),
      delete_job: jobBrief({ job_type: 'source_delete', status: 'running', finished_at: null }),
    }),
  /** `status=null`(保存値が読めない。削除中の判定も操作の出し分けもしない) */
  statusNull: () => sourceDetail({ status: null }),
  /** 日で割り切れない TTL(`ttl_days=null`。S4 が「N 秒」の表示に切り替える) */
  ttlNotInWholeDays: () => sourceDetail({ ttl_seconds: 90_061, ttl_days: null }),
  /** 保存値のしきい値が小数第 3 位以下を持つ(Crawler API を直接使って登録した値。7.7) */
  thresholdWithManyDecimals: () => sourceDetail({ ratio_threshold_percent: 12.345 }),
  /** 設定の項目が読めない(`unavailable.<項目名>=malformed`。S4 が空欄・必須にする。7.6) */
  malformedSettings: () =>
    sourceDetail({
      ttl_seconds: null,
      ttl_days: null,
      min_delete_count: null,
      unavailable: { ttl_seconds: 'malformed', min_delete_count: 'malformed' },
    }),
  /** `connector_config` が読めない(S4 はフォームを出さない) */
  malformedConnectorConfig: () =>
    sourceDetail({
      connector_config: null,
      unavailable: { connector_config: 'malformed' },
    }),
  /** 取得設定にパターン・スイッチ(オン)がある */
  withPatterns: () =>
    sourceDetail({
      connector_config: {
        ...FILE_SYSTEM_CONFIG,
        include_patterns: ['docs/**'],
        exclude_patterns: ['**/*.draft.md', '**/node_modules/**'],
        follow_symlinks: true,
        include_hidden: true,
      },
    }),
  /** 登録文書数を取得できない(`index.document_count`) */
  documentCountUnavailable: () =>
    sourceDetail({
      index: { document_count: null },
      unavailable: { 'index.document_count': 'search_index_unavailable' },
    }),
}

/** EP-03・04 の応答(`SourceSettings`。EP-02 とは別の型)。 */
export const savedSettings = {
  registered: () => sourceSettings(),
  updated: () => sourceSettings({ ratio_threshold_percent: 25 }),
}
