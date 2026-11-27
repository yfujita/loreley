// フィクスチャの名前が主張する状態を、実際に持っていることの確認(F 7.3)。
// 名前と中身がずれると、それを使うテスト(特に E2E)が、意図した状態を見ないまま通ってしまうため。
import { describe, expect, it } from 'vitest'

import type { ErrorResponse } from '@/admin/api'

import { hasMoreThanTwoDecimals } from '../../../src/admin/lib/units'
import { lockRefusals, type MockResponse } from '../apiErrors'
import { dashboard } from './dashboard'
import { documents } from './documents'
import { cancelJobResponses, jobAccepted, jobDetails, jobList, releaseLockResponses } from './jobs'
import { SENTINEL_LEASE_EXPIRES_AT } from './jobs'
import { meta } from './meta'
import { opensearch } from './opensearch'
import { savedSettings, sourceDetails, sourceList } from './sources'

function bodyOf(mock: MockResponse): ErrorResponse {
  if (mock.kind !== 'response') throw new Error('not a response')
  return JSON.parse(mock.body) as ErrorResponse
}

describe('meta', () => {
  it('normal は URL とタイムゾーンあり、noDashboards は URL なし、noTimezone はタイムゾーンなし', () => {
    expect(meta.normal()).toMatchObject({
      cron_timezone: 'Asia/Tokyo',
      dashboards_url: expect.any(String),
    })
    expect(meta.noDashboards()).toEqual({ cron_timezone: 'Asia/Tokyo', dashboards_url: null })
    expect(meta.noTimezone()).toMatchObject({
      cron_timezone: null,
      dashboards_url: expect.any(String),
    })
  })
})

describe('dashboard', () => {
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
  const stateOf = (response: ReturnType<typeof dashboard.allNormal>, id: string) =>
    response.components.find((component) => component.id === id)

  it('すべて、8 コンポーネントが固定の順で並ぶ', () => {
    for (const make of Object.values(dashboard)) {
      expect(make().components.map((component) => component.id)).toEqual(ids)
    }
  })

  it('allNormal: 必須は正常、任意は未設定', () => {
    const response = dashboard.allNormal()

    expect(
      ['crawler', 'indexer', 'opensearch', 'api', 'web'].map((id) => stateOf(response, id)?.state),
    ).toEqual(['normal', 'normal', 'normal', 'normal', 'normal'])
    expect(
      ['opensearch-dashboards', 'embedding', 'llm'].map((id) => stateOf(response, id)?.state),
    ).toEqual(['not_configured', 'not_configured', 'not_configured'])
  })

  it('abnormal: crawler が異常(接続拒否)、ほかは変わらない', () => {
    expect(stateOf(dashboard.abnormal(), 'crawler')).toMatchObject({
      state: 'abnormal',
      reason: 'connection_refused',
    })
    expect(stateOf(dashboard.abnormal(), 'indexer')?.state).toBe('normal')
  })

  it('undetermined: indexer が判定不能(タイムアウト)', () => {
    expect(stateOf(dashboard.undetermined(), 'indexer')).toMatchObject({
      state: 'undetermined',
      reason: 'timeout',
    })
  })

  it('mixed: crawler が異常・indexer が判定不能(接続エラー)', () => {
    expect(stateOf(dashboard.mixed(), 'crawler')?.state).toBe('abnormal')
    expect(stateOf(dashboard.mixed(), 'indexer')).toMatchObject({
      state: 'undetermined',
      reason: 'connection_error',
    })
  })

  it('allConfigured: 任意のコンポーネントも正常', () => {
    expect(
      dashboard.allConfigured().components.every((component) => component.state === 'normal'),
    ).toBe(true)
  })

  it('unknownReason: 未知の reason を持つ', () => {
    expect(stateOf(dashboard.unknownReason(), 'crawler')?.reason).toBe('brand_new_reason')
  })
})

describe('opensearch', () => {
  it('green・yellow(未割り当てのレプリカ)', () => {
    expect(opensearch.green().cluster).toMatchObject({ status: 'green', unassigned_shards: 0 })
    const yellow = opensearch.yellow()
    expect(yellow.cluster).toMatchObject({ status: 'yellow', unassigned_shards: 1 })
    expect(yellow.shards.find((shard) => shard.role === 'replica')).toMatchObject({
      state: 'unassigned',
      node: null,
    })
  })

  it('unknownValues: クラスタ・インデックス・シャードの状態値がすべて未知', () => {
    const response = opensearch.unknownValues()

    expect(response.cluster.status).toBe('purple')
    expect(response.indices[0]?.status).toBe('purple')
    expect(response.shards[0]).toMatchObject({ role: 'witness', state: 'moving' })
  })

  it('nullIndexValues: 状態・件数が null のインデックス', () => {
    expect(opensearch.nullIndexValues().indices[0]).toMatchObject({
      status: null,
      document_count: null,
    })
  })

  it('truncated: truncated=true で、先頭 1,000 件のインデックスと全 1,500 件。empty: 0 件', () => {
    const truncated = opensearch.truncated()
    expect(truncated.truncated).toBe(true)
    expect(truncated.indices).toHaveLength(1000)
    expect(truncated.total_indices).toBe(1500)
    expect(opensearch.empty()).toMatchObject({ indices: [], shards: [], total_indices: 0 })
  })

  /** アクティブ + 初期化中 + 未割り当て = 全シャード(移動中はアクティブの内数。opensearch 3.0) */
  const expectSummaryMatchesShards = (response: ReturnType<typeof opensearch.many>) => {
    const { cluster, shards } = response
    expect(cluster.active_shards + cluster.initializing_shards + cluster.unassigned_shards).toBe(
      shards.length,
    )
    expect(cluster.relocating_shards).toBeLessThanOrEqual(cluster.active_shards)
  }

  it('unassignedAndMoving: 未割り当て・移動中・初期化中が 1 つずつ(アクティブ 4・うち移動中 1)', () => {
    const response = opensearch.unassignedAndMoving()

    expect(response.cluster).toMatchObject({
      active_shards: 4,
      relocating_shards: 1,
      unassigned_shards: 1,
      initializing_shards: 1,
    })
    expectSummaryMatchesShards(response)
  })

  it('red: 未割り当てのプライマリがあり、red のインデックスの件数は null。redMultiple: 2 インデックスの 3 シャード', () => {
    const red = opensearch.red()
    expect(red.cluster.status).toBe('red')
    expect(red.shards.some((s) => s.role === 'primary' && s.state === 'unassigned')).toBe(true)
    expect(red.indices[0]).toMatchObject({ status: 'red', document_count: null })
    expectSummaryMatchesShards(red)
    expect(
      opensearch
        .redMultiple()
        .shards.filter((s) => s.role === 'primary' && s.state === 'unassigned'),
    ).toHaveLength(3)
  })

  it('multiNode: 2 ノード・green・未割り当てなし', () => {
    const response = opensearch.multiNode()

    expect(response.nodes).toHaveLength(2)
    expect(response.cluster).toMatchObject({ status: 'green', unassigned_shards: 0 })
    expectSummaryMatchesShards(response)
  })

  it('many: 25 件・3 ノード。API と同じ並び(yellow が先、同じ状態は名前の昇順)で、件数 null・10 桁・システムインデックスを含む', () => {
    const response = opensearch.many()

    expect(response.indices).toHaveLength(25)
    expect(response.total_indices).toBe(25)
    expect(response.nodes).toHaveLength(3)
    expect(response.indices.slice(0, 2).map((entry) => entry.status)).toEqual(['yellow', 'yellow'])
    const greens = response.indices.filter((entry) => entry.status === 'green')
    expect(greens.map((entry) => entry.name)).toEqual([...greens.map((entry) => entry.name)].sort())
    expect(greens[0]?.name).toBe('.demo-sys-tasks')
    expect(response.indices.find((entry) => entry.document_count === null)?.name).toBe(
      'demo-logs-2026.11.16',
    )
    expect(response.indices.some((entry) => (entry.document_count ?? 0) >= 1_000_000_000)).toBe(
      true,
    )
    expect(response.shards.some((s) => s.state === 'relocating')).toBe(true)
    expectSummaryMatchesShards(response)
  })
})

describe('sourceList(EP-01)', () => {
  it('normal は 2 行、empty は 0 行。最上位の unavailable は常に空', () => {
    expect(sourceList.normal().items).toHaveLength(2)
    expect(sourceList.empty().items).toEqual([])
    for (const make of Object.values(sourceList)) expect(make().unavailable).toEqual({})
  })

  it('neverCrawledAndFailedMixed: source-a は未実行(キーなし)、source-b は読み取り失敗(キーあり)。どちらも last_crawl は null', () => {
    const [a, b] = sourceList.neverCrawledAndFailedMixed().items

    expect(a).toMatchObject({ source_id: 'source-a', last_crawl: null, unavailable: {} })
    expect(b).toMatchObject({ source_id: 'source-b', last_crawl: null })
    expect(Object.keys(b!.unavailable)).toEqual(['last_crawl', 'last_completed_at'])
  })

  it('allRowsUnavailable: すべての行の document_count が null で、同じキーが行ごとにある', () => {
    const rows = sourceList.allRowsUnavailable().items

    expect(rows.length).toBeGreaterThan(1)
    for (const row of rows) {
      expect(row.document_count).toBeNull()
      expect(row.unavailable).toEqual({ document_count: 'search_index_unavailable' })
    }
  })

  it('oneRowUnavailable: 2 行目だけが失敗している', () => {
    const [ok, failed] = sourceList.oneRowUnavailable().items

    expect(ok?.unavailable).toEqual({})
    expect(ok?.document_count).not.toBeNull()
    expect(failed?.document_count).toBeNull()
    expect(failed?.unavailable).toEqual({ document_count: 'timeout' })
  })

  it('statusNull: status・connector_type が null(unavailable にキーなし)', () => {
    const [row] = sourceList.statusNull().items

    expect(row).toMatchObject({ status: null, connector_type: null, unavailable: {} })
  })

  it('deleting: 削除ジョブが実行中の行と失敗した行', () => {
    const [running, failed] = sourceList.deleting().items

    expect(running).toMatchObject({
      status: 'deleting',
      delete_job: { job_type: 'source_delete', status: 'running' },
    })
    expect(failed).toMatchObject({
      status: 'deleting',
      delete_job: { job_type: 'source_delete', status: 'failed' },
    })
  })

  it('lastCrawlStalled: last_crawl.stalled が true。…Unavailable は stalled が null で、行の unavailable に相対パスのキー', () => {
    expect(sourceList.lastCrawlStalled().items[0]?.last_crawl).toMatchObject({
      status: 'running',
      stalled: true,
    })
    const [row] = sourceList.lastCrawlStalledUnavailable().items
    expect(row?.last_crawl?.stalled).toBeNull()
    expect(row?.unavailable).toEqual({ 'last_crawl.stalled': 'store_unavailable' })
  })
})

describe('sourceDetails(EP-02)', () => {
  it('withLock: 7 値の state を持つ。孤児・取得直後はジョブ記録なし、リース切れ・保持は既存ジョブあり', () => {
    const states = [
      'none',
      'held_crawl',
      'held_delete',
      'lease_expired',
      'orphan',
      'just_acquired',
      'unknown',
    ] as const
    for (const state of states) {
      expect(sourceDetails.withLock(state).lock?.state).toBe(state)
    }
    expect(sourceDetails.withLock('none').lock?.job).toBeNull()
    expect(sourceDetails.withLock('held_delete').lock?.job).toMatchObject({
      job_type: 'source_delete',
    })
    expect(sourceDetails.withLock('lease_expired').lock?.job).toMatchObject({ status: 'running' })
    for (const state of ['orphan', 'just_acquired'] as const) {
      expect(sourceDetails.withLock(state).lock?.job).toMatchObject({
        job_type: null,
        status: null,
      })
    }
  })

  it('leaseExpiredWithoutExpiry: lease_expired で lock.job.lease_expires_at が null', () => {
    const detail = sourceDetails.leaseExpiredWithoutExpiry()

    expect(detail.lock?.state).toBe('lease_expired')
    expect(detail.lock?.job?.lease_expires_at).toBeNull()
  })

  it('lockUnavailable: lock が null で unavailable に lock', () => {
    const detail = sourceDetails.lockUnavailable()

    expect(detail.lock).toBeNull()
    expect(detail.unavailable).toEqual({ lock: 'store_unavailable' })
  })

  it('deleting: status=deleting・held_delete のロック・実行中の削除ジョブ', () => {
    const detail = sourceDetails.deleting()

    expect(detail).toMatchObject({ status: 'deleting', lock: { state: 'held_delete' } })
    expect(detail.delete_job).toMatchObject({ job_type: 'source_delete', status: 'running' })
  })

  it('statusNull / neverCrawled', () => {
    expect(sourceDetails.statusNull().status).toBeNull()
    expect(sourceDetails.neverCrawled()).toMatchObject({
      last_crawl: null,
      last_completed_at: null,
    })
    expect(sourceDetails.neverCrawled().unavailable).toEqual({})
  })

  it('ttlNotInWholeDays: ttl_days が null で、ttl_seconds は日で割り切れない', () => {
    const detail = sourceDetails.ttlNotInWholeDays()

    expect(detail.ttl_days).toBeNull()
    expect(detail.ttl_seconds! % 86_400).not.toBe(0)
  })

  it('thresholdWithManyDecimals: しきい値が小数第 3 位以下を持つ', () => {
    expect(
      hasMoreThanTwoDecimals(sourceDetails.thresholdWithManyDecimals().ratio_threshold_percent!),
    ).toBe(true)
    expect(hasMoreThanTwoDecimals(sourceDetails.normal().ratio_threshold_percent!)).toBe(false)
  })

  it('malformedSettings: 読めない項目が null で、unavailable に malformed。ほかは値を持つ', () => {
    const detail = sourceDetails.malformedSettings()

    expect(detail.ttl_seconds).toBeNull()
    expect(detail.min_delete_count).toBeNull()
    expect(detail.unavailable).toEqual({ ttl_seconds: 'malformed', min_delete_count: 'malformed' })
    expect(detail.connector_config).not.toBeNull()
  })

  it('malformedConnectorConfig: connector_config が null で malformed(S4 はフォームを出さない)', () => {
    const detail = sourceDetails.malformedConnectorConfig()

    expect(detail.connector_config).toBeNull()
    expect(detail.unavailable).toEqual({ connector_config: 'malformed' })
  })

  it('withPatterns: パターンとスイッチ(オン)を持つ', () => {
    expect(sourceDetails.withPatterns().connector_config).toMatchObject({
      include_patterns: ['docs/**'],
      follow_symlinks: true,
      include_hidden: true,
    })
    expect(sourceDetails.withPatterns().connector_config?.exclude_patterns).toHaveLength(2)
  })

  it('documentCountUnavailable: index.document_count が null で、unavailable にそのパス', () => {
    const detail = sourceDetails.documentCountUnavailable()

    expect(detail.index.document_count).toBeNull()
    expect(detail.unavailable).toEqual({ 'index.document_count': 'search_index_unavailable' })
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
    expect(new Set(items.map((item) => item.status))).toEqual(
      new Set(['running', 'failed', 'succeeded', 'partially_succeeded', 'cancelled']),
    )
  })

  it('empty は 0 件、manyPages は 25 行で total が上回る', () => {
    expect(jobList.empty()).toMatchObject({ items: [], total: 0 })
    const many = jobList.manyPages()
    expect(many.items).toHaveLength(25)
    expect(many.total).toBeGreaterThan(many.items_per_page)
  })

  it('statusNull: status・job_type・trigger・queued_at が null で、取消できない', () => {
    expect(jobList.statusNull().items[0]).toMatchObject({
      status: null,
      job_type: null,
      trigger: null,
      queued_at: null,
      cancellable: false,
      unavailable: {},
    })
  })

  it('stalled: running で stalled=true・取消できない', () => {
    expect(jobList.stalled().items[0]).toMatchObject({
      status: 'running',
      stalled: true,
      cancellable: false,
    })
  })

  it('oneRowStalledUnavailable: 1 行目だけ stalled=null・取消不可・行の unavailable に stalled、2 行目は影響を受けない', () => {
    const [unknown, ok] = jobList.oneRowStalledUnavailable().items

    expect(unknown).toMatchObject({
      stalled: null,
      cancellable: false,
      unavailable: { stalled: 'store_unavailable' },
    })
    expect(ok).toMatchObject({ stalled: false, cancellable: true, unavailable: {} })
  })

  it('nullFlags: failed で force_delete・rewrite_mode が null', () => {
    expect(jobList.nullFlags().items[0]).toMatchObject({
      status: 'failed',
      force_delete: null,
      rewrite_mode: null,
    })
  })
})

describe('jobDetails(EP-10)', () => {
  it('running: 取消でき、リース期限あり。集計は途中(partial=true・in_progress)', () => {
    expect(jobDetails.running()).toMatchObject({
      status: 'running',
      cancellable: true,
      registration: { partial: true, phase: 'in_progress' },
    })
    expect(jobDetails.running().lease_expires_at).not.toBeNull()
  })

  it('queued: 取消でき、開始前(started_at=null)・登録結果なし', () => {
    expect(jobDetails.queued()).toMatchObject({
      status: 'queued',
      cancellable: true,
      started_at: null,
      registration: null,
    })
  })

  it('failedRerunnable: 再実行できる最新のジョブ。force_delete=true', () => {
    expect(jobDetails.failedRerunnable()).toMatchObject({
      status: 'failed',
      rerunnable: true,
      rerun_blocked_reason: null,
      latest_for_source: true,
      force_delete: true,
    })
  })

  it('failedNullFlags: 再実行できるが、force_delete・rewrite_mode が null', () => {
    expect(jobDetails.failedNullFlags()).toMatchObject({
      rerunnable: true,
      force_delete: null,
      rewrite_mode: null,
    })
  })

  it('failedSuperseded / failedSourceMissing: 再実行できない理由', () => {
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

  it('stalledWithLeaseExpiry: stalled=true・期限あり。…Without は stalled=true かつ lease_expires_at=null', () => {
    expect(jobDetails.stalledWithLeaseExpiry()).toMatchObject({ stalled: true, cancellable: false })
    expect(jobDetails.stalledWithLeaseExpiry().lease_expires_at).not.toBeNull()
    const without = jobDetails.stalledWithoutLeaseExpiry()
    expect(without.stalled).toBe(true)
    expect(without.lease_expires_at).toBeNull()
    expect(without.status).toBe('running')
  })

  it('flagsUnavailable: stalled・rerunnable・latest_for_source が null で、unavailable に 3 つのキー', () => {
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

  it('statusNull: status・job_type・trigger・queued_at が null、登録結果の件数・partial・phase も null', () => {
    const detail = jobDetails.statusNull()

    expect([detail.status, detail.job_type, detail.trigger, detail.queued_at]).toEqual([
      null,
      null,
      null,
      null,
    ])
    expect(detail.registration).toMatchObject({
      created_count: null,
      updated_count: null,
      partial: null,
      phase: null,
    })
  })

  it('warnings: 既知のコード・未知のコード・code が文字列でない要素・code のない要素', () => {
    const warnings = jobDetails.warnings().warnings

    expect(warnings).toEqual([
      { code: 'invalid_external_id', count: 3 },
      { code: 'brand_new_warning' },
      { code: 42 },
      { note: 'no code' },
    ])
  })

  it('sourceDelete: 削除ジョブ(登録結果なし・現在値あり)', () => {
    expect(jobDetails.sourceDelete()).toMatchObject({
      job_type: 'source_delete',
      registration: null,
      deletion: { current_state: 'available', current: expect.any(Object) },
    })
  })

  it('deletionUnavailable: current_state=unavailable・current=null だが fetched_at は入っている(J-E10)。unavailable に deletion.current', () => {
    const detail = jobDetails.deletionUnavailable()

    expect(detail.deletion).toMatchObject({ current_state: 'unavailable', current: null })
    expect(detail.deletion?.fetched_at).not.toBeNull()
    expect(detail.unavailable).toEqual({ 'deletion.current': 'store_unavailable' })
  })

  it('deletionNotFound: current_state=not_found・current=null(fetched_at は入っている)', () => {
    const detail = jobDetails.deletionNotFound()

    expect(detail.deletion).toMatchObject({ current_state: 'not_found', current: null })
    expect(detail.deletion?.fetched_at).not.toBeNull()
  })

  it('cancelledAfterFinishNotice: cancelled で cancel_after_finish_notice=true', () => {
    expect(jobDetails.cancelledAfterFinishNotice()).toMatchObject({
      status: 'cancelled',
      cancel_after_finish_notice: true,
    })
  })
})

describe('受付・取消・ロック解放の応答', () => {
  it('jobAccepted: crawl は指定を記録、sourceDelete は指定が null', () => {
    expect(jobAccepted.crawl()).toMatchObject({
      job_type: 'crawl',
      status: 'queued',
      force_delete: false,
    })
    expect(jobAccepted.sourceDelete()).toMatchObject({
      job_type: 'source_delete',
      status: 'queued',
      force_delete: null,
      rewrite_mode: null,
    })
  })

  it('cancelJobResponses: requested は running のまま(202)、cancelled は取消済み(200)', () => {
    expect(cancelJobResponses.requested().status).toBe('running')
    expect(cancelJobResponses.cancelled().status).toBe('cancelled')
  })

  it('releaseLockResponses: released=true は失敗にしたジョブ ID あり、notReleased は released=false・failed_job_id=null', () => {
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
    expect(documents.skipped().tab).toBe('skipped')
    expect(documents.extractFailed().tab).toBe('extract_failed')
    expect(documents.oversize().tab).toBe('oversize')
    expect(documents.summaryPending().tab).toBe('summary_pending')
  })

  it('skipped: existing・new が混在', () => {
    expect(documents.skipped().items.map((item) => 'existence' in item && item.existence)).toEqual([
      'existing',
      'new',
    ])
  })

  it('skippedExistenceUnavailable: 全行 existence=unknown で、各行の unavailable に existence', () => {
    for (const item of documents.skippedExistenceUnavailable().items) {
      expect(item).toMatchObject({
        existence: 'unknown',
        unavailable: { existence: 'search_index_unavailable' },
      })
    }
    expect(documents.skippedExistenceUnavailable().unavailable).toEqual({})
  })

  it('skippedUnreadableDocumentId: document_id が null で existence=unknown(キーなし)', () => {
    expect(documents.skippedUnreadableDocumentId().items[0]).toMatchObject({
      document_id: null,
      existence: 'unknown',
      unavailable: {},
    })
  })

  it('extractFailed: タイトルなしの行を含む。oversize: size なし(indexer 検出)の行を含む', () => {
    expect(
      documents.extractFailed().items.some((item) => 'title' in item && item.title === null),
    ).toBe(true)
    expect(documents.oversize().items.some((item) => 'size' in item && item.size === null)).toBe(
      true,
    )
  })

  it('summaryPending: summary_pending の件数が 1', () => {
    expect(documents.summaryPending().tab_counts.summary_pending).toBe(1)
  })

  it('empty: 0 件(total=0)で、すべてのタブの件数が 0', () => {
    const response = documents.empty()

    expect(response).toMatchObject({ items: [], total: 0 })
    expect(Object.values(response.tab_counts)).toEqual([0, 0, 0, 0])
  })

  it('countsUnavailable: summary_pending の件数と document_count が null で、最上位の unavailable に両方', () => {
    const response = documents.countsUnavailable()

    expect(response.document_count).toBeNull()
    expect(response.tab_counts.summary_pending).toBeNull()
    expect(response.unavailable).toEqual({
      document_count: 'search_index_unavailable',
      'tab_counts.summary_pending': 'search_index_unavailable',
    })
  })

  it('overWindow: total が window_limit(10,000)を超える', () => {
    const response = documents.overWindow()

    expect(response.total).toBeGreaterThan(response.window_limit)
    expect(response.window_limit).toBe(10_000)
  })
})

describe('lockRefusals(409 lock_held・lock_in_use の拒否)', () => {
  const details = (mock: MockResponse) => bodyOf(mock).error.details!

  it('lock_held と lock_in_use の code・HTTP ステータス・retryable=false', () => {
    const held = bodyOf(lockRefusals.heldCrawl())
    const inUse = bodyOf(lockRefusals.releaseInUseRunning())

    expect(held.error).toMatchObject({ code: 'lock_held', retryable: false })
    expect(inUse.error).toMatchObject({ code: 'lock_in_use', retryable: false })
    expect(lockRefusals.heldCrawl()).toMatchObject({ status: 409 })
    expect(lockRefusals.releaseInUseRunning()).toMatchObject({ status: 409 })
  })

  it('EP-06 の拒否は、指定が反映されていない(options_applied=false)ことと requested を持つ。EP-05(heldDelete)・EP-08 は持たない', () => {
    expect(details(lockRefusals.heldCrawl())).toMatchObject({
      options_applied: false,
      requested: { force_delete: true, rewrite_mode: false },
    })
    expect(details(lockRefusals.heldDelete())).not.toHaveProperty('requested')
    expect(details(lockRefusals.heldDelete())).not.toHaveProperty('options_applied')
    expect(details(lockRefusals.releaseInUseRunning())).not.toHaveProperty('requested')
  })

  it('lock_state と既存ジョブ: 実行中・実行待ち・削除・リース切れ・孤児・取得直後・unknown', () => {
    expect(details(lockRefusals.heldCrawl())).toMatchObject({
      lock_state: 'held_crawl',
      existing_job: { status: 'running' },
    })
    expect(details(lockRefusals.heldCrawlQueued())).toMatchObject({
      existing_job: { status: 'queued', lease_expires_at: null },
    })
    expect(details(lockRefusals.heldDelete())).toMatchObject({
      lock_state: 'held_delete',
      existing_job: { job_type: 'source_delete' },
    })
    expect(details(lockRefusals.leaseExpired())).toMatchObject({ lock_state: 'lease_expired' })
    expect(details(lockRefusals.orphan())).toMatchObject({
      lock_state: 'orphan',
      existing_job: { status: null, job_type: null },
    })
    expect(details(lockRefusals.justAcquired())).toMatchObject({
      lock_state: 'just_acquired',
      existing_job: { status: null, job_type: null },
    })
    expect(details(lockRefusals.unknown())).toMatchObject({
      lock_state: 'unknown',
      existing_job: null,
    })
  })

  it('leaseExpiredSentinel: リース期限が番兵(0001-01-01T00:00:00.000Z)', () => {
    expect(details(lockRefusals.leaseExpiredSentinel())).toMatchObject({
      lock_state: 'lease_expired',
      existing_job: { lease_expires_at: SENTINEL_LEASE_EXPIRES_AT },
    })
    expect(SENTINEL_LEASE_EXPIRES_AT).toBe('0001-01-01T00:00:00.000Z')
  })

  it('existingJobUnknownStatus: 既存ジョブの status が未知の文字列', () => {
    expect(details(lockRefusals.existingJobUnknownStatus())).toMatchObject({
      existing_job: { status: 'paused' },
    })
  })

  it('EP-08 の lock_in_use: 実行中・削除・取得直後・unknown', () => {
    expect(details(lockRefusals.releaseInUseRunning())).toMatchObject({ lock_state: 'held_crawl' })
    expect(details(lockRefusals.releaseInUseDelete())).toMatchObject({
      lock_state: 'held_delete',
      existing_job: { job_type: 'source_delete' },
    })
    expect(details(lockRefusals.releaseInUseJustAcquired())).toMatchObject({
      lock_state: 'just_acquired',
      existing_job: { status: null },
    })
    expect(details(lockRefusals.releaseInUseUnknown())).toMatchObject({
      lock_state: 'unknown',
      existing_job: null,
    })
  })
})
