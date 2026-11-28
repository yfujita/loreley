// フィクスチャの名前が主張する状態のうち、画面側のテストでは検出しにくいものだけを確認する(F 7.3)。
// 名前と中身がずれると、それを使うテスト(特に E2E)が意図した状態を見ないまま通ってしまうため。
// 値をそのまま写すだけの確認(正常・単純な null など)は、使う側の画面テストが見るので置かない。
import { describe, expect, it } from 'vitest'

import type { ErrorResponse } from '@/admin/api'

import { hasMoreThanTwoDecimals } from '../../../src/admin/lib/units'
import { lockRefusals, type MockResponse } from '../apiErrors'
import { dashboard } from './dashboard'
import { documents } from './documents'
import { jobDetails, jobList, releaseLockResponses, SENTINEL_LEASE_EXPIRES_AT } from './jobs'
import { opensearch } from './opensearch'
import { savedSettings, sourceDetails, sourceList } from './sources'

function bodyOf(mock: MockResponse): ErrorResponse {
  if (mock.kind !== 'response') throw new Error('not a response')
  return JSON.parse(mock.body) as ErrorResponse
}

describe('dashboard', () => {
  it('どのフィクスチャも、8 コンポーネントが固定の順で並ぶ', () => {
    const ids = [
      'crawler',
      'indexer',
      'opensearch',
      'api',
      'web',
      'opensearch-dashboards',
      'embedding',
      'llm',
    ]
    for (const make of Object.values(dashboard)) {
      expect(make().components.map((component) => component.id)).toEqual(ids)
    }
  })

  it('状態の組み合わせ(abnormal=crawler 異常、undetermined=indexer 判定不能、mixed=両方)', () => {
    const states = (make: () => ReturnType<typeof dashboard.allNormal>) =>
      make().components.map((component) => component.state)

    expect(states(dashboard.allNormal)).toEqual([
      ...Array(5).fill('normal'),
      ...Array(3).fill('not_configured'),
    ])
    expect(states(dashboard.abnormal)[0]).toBe('abnormal')
    expect(states(dashboard.undetermined)[1]).toBe('undetermined')
    expect(states(dashboard.mixed).slice(0, 2)).toEqual(['abnormal', 'undetermined'])
    expect(states(dashboard.allUndetermined).filter((state) => state === 'abnormal')).toEqual([])
    expect(states(dashboard.allUndetermined).slice(0, 5)).toEqual(Array(5).fill('undetermined'))
  })
})

describe('opensearch', () => {
  /** アクティブ + 初期化中 + 未割り当て = 全シャード(移動中はアクティブの内数。opensearch 3.0) */
  it('クラスタの集計が、シャードの一覧と矛盾しない(シャード一覧を全件持つフィクスチャ)', () => {
    const names = ['unassignedAndMoving', 'red', 'redMany', 'multiNode', 'many'] as const
    for (const name of names) {
      const { cluster, shards } = opensearch[name]()
      expect(
        cluster.active_shards + cluster.initializing_shards + cluster.unassigned_shards,
        name,
      ).toBe(shards.length)
      expect(cluster.relocating_shards, name).toBeLessThanOrEqual(cluster.active_shards)
    }
  })

  it('red 系: 未割り当てのプライマリの数(red=1・redMultiple=3・redMany=12)', () => {
    const count = (response: ReturnType<typeof opensearch.red>) =>
      response.shards.filter((s) => s.role === 'primary' && s.state === 'unassigned').length

    expect([
      count(opensearch.red()),
      count(opensearch.redMultiple()),
      count(opensearch.redMany()),
    ]).toEqual([1, 3, 12])
  })

  it('truncated: 先頭 1,000 件のインデックスと全 1,500 件', () => {
    const response = opensearch.truncated()
    expect(response).toMatchObject({ truncated: true, total_indices: 1500 })
    expect(response.indices).toHaveLength(1000)
  })

  it('many: API と同じ並び(yellow が先、同じ状態は名前の昇順)で、件数 null・10 桁を含む', () => {
    const response = opensearch.many()

    expect(response.indices).toHaveLength(25)
    expect(response.indices.slice(0, 2).map((entry) => entry.status)).toEqual(['yellow', 'yellow'])
    const greens = response.indices
      .filter((entry) => entry.status === 'green')
      .map((entry) => entry.name)
    expect(greens).toEqual([...greens].sort())
    expect(response.indices.some((entry) => entry.document_count === null)).toBe(true)
    expect(response.indices.some((entry) => (entry.document_count ?? 0) >= 1_000_000_000)).toBe(
      true,
    )
  })
})

describe('sourceList(EP-01)', () => {
  it('最上位の unavailable は、どのフィクスチャでも空', () => {
    for (const make of Object.values(sourceList)) expect(make().unavailable).toEqual({})
  })

  it('neverCrawledAndFailedMixed: 未実行(キーなし)と読み取り失敗(キーあり)を区別できる', () => {
    const [a, b] = sourceList.neverCrawledAndFailedMixed().items

    expect(a).toMatchObject({ last_crawl: null, unavailable: {} })
    expect(b?.last_crawl).toBeNull()
    expect(Object.keys(b!.unavailable)).toEqual(['last_crawl', 'last_completed_at'])
  })

  it('oneRowUnavailable: 2 行目だけが失敗している', () => {
    const [ok, failed] = sourceList.oneRowUnavailable().items

    expect(ok).toMatchObject({ unavailable: {} })
    expect(ok?.document_count).not.toBeNull()
    expect(failed).toMatchObject({
      document_count: null,
      unavailable: { document_count: 'timeout' },
    })
  })

  it('lastCrawlStalledUnavailable: stalled が null で、行の unavailable に相対パスのキー', () => {
    const [row] = sourceList.lastCrawlStalledUnavailable().items

    expect(row?.last_crawl?.stalled).toBeNull()
    expect(row?.unavailable).toEqual({ 'last_crawl.stalled': 'store_unavailable' })
  })
})

describe('sourceDetails(EP-02)', () => {
  it('withLock: 7 値の state。孤児・取得直後はジョブ記録なし、リース切れは既存ジョブあり', () => {
    const states = [
      'none',
      'held_crawl',
      'held_delete',
      'lease_expired',
      'orphan',
      'just_acquired',
      'unknown',
    ] as const
    for (const state of states) expect(sourceDetails.withLock(state).lock?.state).toBe(state)

    expect(sourceDetails.withLock('none').lock?.job).toBeNull()
    expect(sourceDetails.withLock('lease_expired').lock?.job).toMatchObject({ status: 'running' })
    for (const state of ['orphan', 'just_acquired'] as const) {
      expect(sourceDetails.withLock(state).lock?.job).toMatchObject({
        job_type: null,
        status: null,
      })
    }
  })

  it('leaseExpiredWithoutExpiry: lease_expired で期限が null', () => {
    const detail = sourceDetails.leaseExpiredWithoutExpiry()

    expect(detail.lock?.state).toBe('lease_expired')
    expect(detail.lock?.job?.lease_expires_at).toBeNull()
  })

  it('値の境界: ttl が日で割り切れない・しきい値が小数第 3 位以下を持つ', () => {
    const ttl = sourceDetails.ttlNotInWholeDays()
    expect(ttl.ttl_days).toBeNull()
    expect(ttl.ttl_seconds! % 86_400).not.toBe(0)
    expect(
      hasMoreThanTwoDecimals(sourceDetails.thresholdWithManyDecimals().ratio_threshold_percent!),
    ).toBe(true)
    expect(hasMoreThanTwoDecimals(sourceDetails.normal().ratio_threshold_percent!)).toBe(false)
  })

  it('unavailable のキー: lock・connector_config・設定値・index.document_count', () => {
    expect(sourceDetails.lockUnavailable()).toMatchObject({
      lock: null,
      unavailable: { lock: 'store_unavailable' },
    })
    expect(sourceDetails.malformedConnectorConfig()).toMatchObject({
      connector_config: null,
      unavailable: { connector_config: 'malformed' },
    })
    expect(sourceDetails.malformedSettings()).toMatchObject({
      ttl_seconds: null,
      min_delete_count: null,
      unavailable: { ttl_seconds: 'malformed', min_delete_count: 'malformed' },
    })
    expect(sourceDetails.documentCountUnavailable().unavailable).toEqual({
      'index.document_count': 'search_index_unavailable',
    })
  })

  it('EP-03・04 の応答(SourceSettings)は active で、EP-02 とは別の型(unavailable・lock を持たない)', () => {
    for (const settings of [savedSettings.registered(), savedSettings.updated()]) {
      expect(settings.status).toBe('active')
      expect(settings).not.toHaveProperty('unavailable')
      expect(settings).not.toHaveProperty('lock')
    }
  })
})

describe('jobList(EP-09)', () => {
  it('normal: 実行中の行だけ取消できる', () => {
    const items = jobList.normal().items

    expect(items.filter((item) => item.cancellable).map((item) => item.status)).toEqual(['running'])
  })

  it('oneRowStalledUnavailable: 1 行目だけ stalled=null・取消不可、2 行目は影響を受けない', () => {
    const [unknown, ok] = jobList.oneRowStalledUnavailable().items

    expect(unknown).toMatchObject({
      stalled: null,
      cancellable: false,
      unavailable: { stalled: 'store_unavailable' },
    })
    expect(ok).toMatchObject({ stalled: false, cancellable: true, unavailable: {} })
  })
})

describe('jobDetails(EP-10)', () => {
  it('再実行の可否と理由', () => {
    expect(jobDetails.failedRerunnable()).toMatchObject({
      rerunnable: true,
      rerun_blocked_reason: null,
      latest_for_source: true,
    })
    expect(jobDetails.failedSuperseded()).toMatchObject({
      rerunnable: false,
      latest_for_source: false,
      rerun_blocked_reason: 'superseded',
    })
    expect(jobDetails.failedSourceMissing()).toMatchObject({
      rerunnable: false,
      rerun_blocked_reason: 'source_missing',
    })
  })

  it('stalledWithoutLeaseExpiry: running・stalled=true で期限が null(With は期限あり)', () => {
    expect(jobDetails.stalledWithLeaseExpiry().lease_expires_at).not.toBeNull()
    expect(jobDetails.stalledWithoutLeaseExpiry()).toMatchObject({
      status: 'running',
      stalled: true,
      lease_expires_at: null,
    })
  })

  it('flagsUnavailable: 3 つのフラグが null で、unavailable に 3 つのキー。取消できない', () => {
    const detail = jobDetails.flagsUnavailable()

    expect([detail.stalled, detail.rerunnable, detail.latest_for_source]).toEqual([
      null,
      null,
      null,
    ])
    expect(Object.keys(detail.unavailable).sort()).toEqual([
      'latest_for_source',
      'rerunnable',
      'stalled',
    ])
    expect(detail.cancellable).toBe(false)
  })

  it('warnings: 既知・未知のコード、code が文字列でない要素、code のない要素', () => {
    expect(jobDetails.warnings().warnings).toEqual([
      { code: 'invalid_external_id', count: 3 },
      { code: 'brand_new_warning' },
      { code: 42 },
      { note: 'no code' },
    ])
  })

  it('削除ジョブの現在値: unavailable・not_found でも fetched_at は入っている(J-E10)', () => {
    const unavailable = jobDetails.deletionUnavailable()
    expect(unavailable.deletion).toMatchObject({ current_state: 'unavailable', current: null })
    expect(unavailable.deletion?.fetched_at).not.toBeNull()
    expect(unavailable.unavailable).toEqual({ 'deletion.current': 'store_unavailable' })

    const notFound = jobDetails.deletionNotFound()
    expect(notFound.deletion).toMatchObject({ current_state: 'not_found', current: null })
    expect(notFound.deletion?.fetched_at).not.toBeNull()
  })
})

describe('ロック解放の応答', () => {
  it('released=true は失敗にしたジョブ ID あり、notReleased は released=false・failed_job_id=null', () => {
    expect(releaseLockResponses.released()).toMatchObject({
      released: true,
      failed_job_id: expect.any(String),
    })
    expect(releaseLockResponses.notReleased()).toMatchObject({
      released: false,
      failed_job_id: null,
    })
  })
})

describe('documents(EP-11)', () => {
  it('4 つのタブの行型は、他の型にない必須のキー(判別のキー)を持つ', () => {
    expect(documents.skipped().items[0]).toHaveProperty('existence')
    expect(documents.extractFailed().items[0]).toHaveProperty('last_seen_at')
    expect(documents.oversize().items[0]).toHaveProperty('detected_by')
    expect(documents.summaryPending().items[0]).toHaveProperty('indexed_at')
  })

  it('skipped 系: existing・new の混在、全行 unknown(行の unavailable)、document_id が null', () => {
    expect(documents.skipped().items.map((item) => 'existence' in item && item.existence)).toEqual([
      'existing',
      'new',
    ])
    for (const item of documents.skippedExistenceUnavailable().items) {
      expect(item).toMatchObject({
        existence: 'unknown',
        unavailable: { existence: 'search_index_unavailable' },
      })
    }
    expect(documents.skippedUnreadableDocumentId().items[0]).toMatchObject({
      document_id: null,
      existence: 'unknown',
      unavailable: {},
    })
  })

  it('件数の境界: empty は全タブ 0、countsUnavailable は 2 項目が null、overWindow は total が上限超過', () => {
    expect(Object.values(documents.empty().tab_counts)).toEqual([0, 0, 0, 0])
    const counts = documents.countsUnavailable()
    expect([counts.document_count, counts.tab_counts.summary_pending]).toEqual([null, null])
    expect(counts.unavailable).toEqual({
      document_count: 'search_index_unavailable',
      'tab_counts.summary_pending': 'search_index_unavailable',
    })
    const over = documents.overWindow()
    expect(over.window_limit).toBe(10_000)
    expect(over.total).toBeGreaterThan(over.window_limit)
  })
})

describe('lockRefusals(409 lock_held・lock_in_use の拒否)', () => {
  const details = (mock: MockResponse) => bodyOf(mock).error.details!

  it('code・HTTP ステータス・retryable=false', () => {
    expect(bodyOf(lockRefusals.heldCrawl()).error).toMatchObject({
      code: 'lock_held',
      retryable: false,
    })
    expect(bodyOf(lockRefusals.releaseInUseRunning()).error).toMatchObject({
      code: 'lock_in_use',
      retryable: false,
    })
    expect(lockRefusals.heldCrawl()).toMatchObject({ status: 409 })
    expect(lockRefusals.releaseInUseRunning()).toMatchObject({ status: 409 })
  })

  it('EP-06 の拒否だけが、指定が反映されていないこと(options_applied=false)と requested を持つ', () => {
    expect(details(lockRefusals.heldCrawl())).toMatchObject({
      options_applied: false,
      requested: { force_delete: true, rewrite_mode: false },
    })
    for (const mock of [lockRefusals.heldDelete(), lockRefusals.releaseInUseRunning()]) {
      expect(details(mock)).not.toHaveProperty('requested')
      expect(details(mock)).not.toHaveProperty('options_applied')
    }
  })

  it('lock_state と既存ジョブの組み合わせ', () => {
    expect(details(lockRefusals.heldCrawlQueued())).toMatchObject({
      existing_job: { status: 'queued', lease_expires_at: null },
    })
    expect(details(lockRefusals.heldDelete())).toMatchObject({
      lock_state: 'held_delete',
      existing_job: { job_type: 'source_delete' },
    })
    for (const [mock, state] of [
      [lockRefusals.orphan(), 'orphan'],
      [lockRefusals.justAcquired(), 'just_acquired'],
      [lockRefusals.releaseInUseJustAcquired(), 'just_acquired'],
    ] as const) {
      expect(details(mock)).toMatchObject({
        lock_state: state,
        existing_job: { status: null, job_type: null },
      })
    }
    for (const mock of [lockRefusals.unknown(), lockRefusals.releaseInUseUnknown()]) {
      expect(details(mock)).toMatchObject({ lock_state: 'unknown', existing_job: null })
    }
    expect(details(lockRefusals.existingJobUnknownStatus())).toMatchObject({
      existing_job: { status: 'paused' },
    })
  })

  it('leaseExpiredSentinel: リース期限が番兵(0001-01-01T00:00:00.000Z)', () => {
    expect(SENTINEL_LEASE_EXPIRES_AT).toBe('0001-01-01T00:00:00.000Z')
    expect(details(lockRefusals.leaseExpiredSentinel())).toMatchObject({
      lock_state: 'lease_expired',
      existing_job: { lease_expires_at: SENTINEL_LEASE_EXPIRES_AT },
    })
  })
})
