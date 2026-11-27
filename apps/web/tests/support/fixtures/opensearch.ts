// EP-12 `GET /opensearch/cluster` のフィクスチャ(F 7.3)。応答に `unavailable` はない。
// インデックス・シャードの並びは API と同じ(インデックスは 状態の悪い順 → 名前の昇順、シャードは インデックス・番号・役割の順)。
import type { ClusterResponse, ClusterSummary, IndexEntry, ShardEntry } from '@/admin/api'

const FETCHED_AT = '2026-11-22T10:48:03.000Z'

function summary(overrides: Partial<ClusterSummary> = {}): ClusterSummary {
  return {
    name: 'loreley',
    status: 'green',
    node_count: 1,
    active_shards: 2,
    relocating_shards: 0,
    initializing_shards: 0,
    unassigned_shards: 0,
    ...overrides,
  }
}

function shard(index: string, overrides: Partial<ShardEntry> = {}): ShardEntry {
  return { index, shard: 0, role: 'primary', state: 'started', node: 'node-1', ...overrides }
}

function index(name: string, overrides: Partial<IndexEntry> = {}): IndexEntry {
  return { name, status: 'green', document_count: 12846, ...overrides }
}

function response(overrides: Partial<ClusterResponse> = {}): ClusterResponse {
  return {
    fetched_at: FETCHED_AT,
    cluster: summary(),
    nodes: [{ name: 'node-1' }],
    indices: [index('loreley-documents-000001')],
    shards: [shard('loreley-documents-000001')],
    truncated: false,
    total_indices: 1,
    ...overrides,
  } satisfies ClusterResponse
}

const STATUS_RANK: Record<string, number> = { red: 0, yellow: 1, green: 2 }

/** API と同じ並び: 状態の悪い順(red → yellow → green → その他・null)、同じ状態は名前の昇順(コードポイント順)。 */
function sortIndices(indices: IndexEntry[]): IndexEntry[] {
  const rank = (entry: IndexEntry) => STATUS_RANK[entry.status ?? ''] ?? 3
  return [...indices].sort(
    (a, b) => rank(a) - rank(b) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0),
  )
}

/** シャードの実数から概況を作る(アクティブ + 初期化中 + 未割り当て = 全シャード。移動中はアクティブの内数)。 */
function summarize(shards: ShardEntry[], nodeCount: number, status: string): ClusterSummary {
  const initializing = shards.filter((s) => s.state === 'initializing').length
  const unassigned = shards.filter((s) => s.node === null).length
  return summary({
    name: 'demo-cluster',
    status,
    node_count: nodeCount,
    active_shards: shards.length - initializing - unassigned,
    relocating_shards: shards.filter((s) => s.state === 'relocating').length,
    initializing_shards: initializing,
    unassigned_shards: unassigned,
  })
}

const NODES_3 = [{ name: 'node-1' }, { name: 'node-2' }, { name: 'node-3' }]

/** 25 件のインデックス(3 ノード。名前・状態・件数・シャードの状態がばらつく)。多数のインデックス・絞り込み・ページ送り用。 */
function manyIndices(): ClusterResponse {
  const names = [
    '.demo-sys-tasks',
    'demo-docs-000001',
    'demo-docs-000002',
    'demo-docs-000003',
    'demo-store-jobs',
    'demo-store-sources',
    'demo-store-locks',
    'demo-store-deletions',
    'demo-store-extracted',
    ...Array.from({ length: 16 }, (_, i) => `demo-logs-2026.11.${String(i + 1).padStart(2, '0')}`),
  ]
  const unassignedReplica = new Set(['demo-docs-000003', 'demo-logs-2026.11.15'])
  const relocatingPrimary = new Set(['demo-logs-2026.11.14'])
  const counts = new Map<string, number | null>([
    ['demo-docs-000003', 8402117],
    ['demo-logs-2026.11.16', null],
    ['demo-logs-2026.11.01', 1234567890],
    ['.demo-sys-tasks', 87],
    ['demo-docs-000001', 12846],
    ['demo-docs-000002', 3310552],
  ])

  const indices = names.map((name, i) =>
    index(name, {
      status: unassignedReplica.has(name) ? 'yellow' : 'green',
      document_count: counts.has(name) ? (counts.get(name) ?? null) : ((i + 3) * 104729) % 98765,
    }),
  )
  const shards = names.flatMap((name, i): ShardEntry[] => [
    shard(name, {
      node: `node-${(i % 3) + 1}`,
      state: relocatingPrimary.has(name) ? 'relocating' : 'started',
    }),
    shard(name, {
      role: 'replica',
      node: unassignedReplica.has(name) ? null : `node-${((i + 1) % 3) + 1}`,
      state: unassignedReplica.has(name) ? 'unassigned' : 'started',
    }),
  ])
  return response({
    cluster: summarize(shards, 3, 'yellow'),
    nodes: NODES_3,
    indices: sortIndices(indices),
    shards,
    total_indices: indices.length,
  })
}

export const opensearch = {
  /** green(1 ノード・1 インデックス・プライマリのみ) */
  green: () => response(),
  /** yellow(レプリカが未割り当て) */
  yellow: () =>
    response({
      cluster: summary({ status: 'yellow', active_shards: 1, unassigned_shards: 1 }),
      indices: [index('loreley-documents-000001', { status: 'yellow' })],
      shards: [
        shard('loreley-documents-000001'),
        shard('loreley-documents-000001', { role: 'replica', state: 'unassigned', node: null }),
      ],
    }),
  /** 2 ノード・green(インデックス 3 件。シャードを持たないノードはない) */
  multiNode: () => {
    const indices = [
      index('demo-docs-000001'),
      index('demo-store-jobs', { document_count: 1204 }),
      index('demo-store-sources', { document_count: 6 }),
    ]
    const shards = [
      shard('demo-docs-000001', { node: 'node-1' }),
      shard('demo-docs-000001', { role: 'replica', node: 'node-2' }),
      shard('demo-store-jobs', { role: 'replica', node: 'node-1' }),
      shard('demo-store-jobs', { node: 'node-2' }),
      shard('demo-store-sources', { node: 'node-1' }),
      shard('demo-store-sources', { role: 'replica', node: 'node-2' }),
    ]
    return response({
      cluster: summarize(shards, 2, 'green'),
      nodes: [{ name: 'node-1' }, { name: 'node-2' }],
      indices,
      shards,
      total_indices: 3,
    })
  },
  /** 2 ノード・yellow: 未割り当てのレプリカ 1、移動中のプライマリ 1、初期化中のレプリカ 1(凡例の 3 項目がすべて出る) */
  unassignedAndMoving: () => {
    const indices = sortIndices([
      index('demo-docs-000001'),
      index('demo-store-jobs', { status: 'yellow', document_count: 1204 }),
      index('demo-store-sources', { status: 'yellow', document_count: 6 }),
    ])
    const shards = [
      shard('demo-docs-000001', { node: 'node-1' }),
      shard('demo-docs-000001', { role: 'replica', node: 'node-2' }),
      shard('demo-store-jobs', { node: 'node-2' }),
      shard('demo-store-jobs', { role: 'replica', state: 'unassigned', node: null }),
      shard('demo-store-sources', { state: 'relocating', node: 'node-1' }),
      shard('demo-store-sources', { role: 'replica', state: 'initializing', node: 'node-2' }),
    ]
    return response({
      cluster: summarize(shards, 2, 'yellow'),
      nodes: [{ name: 'node-1' }, { name: 'node-2' }],
      indices,
      shards,
      total_indices: 3,
    })
  },
  /** red(未割り当てのプライマリあり。red のインデックスは件数が null) */
  red: () => {
    const indices = sortIndices([
      index('demo-docs-000001', { status: 'red', document_count: null }),
      index('demo-store-jobs', { status: 'yellow', document_count: 1204 }),
      index('demo-store-sources', { status: 'yellow', document_count: 6 }),
    ])
    const shards = [
      shard('demo-docs-000001', { state: 'unassigned', node: null }),
      shard('demo-docs-000001', { role: 'replica', state: 'unassigned', node: null }),
      shard('demo-store-jobs'),
      shard('demo-store-jobs', { role: 'replica', state: 'unassigned', node: null }),
      shard('demo-store-sources'),
      shard('demo-store-sources', { role: 'replica', state: 'unassigned', node: null }),
    ]
    return response({ cluster: summarize(shards, 1, 'red'), indices, shards, total_indices: 3 })
  },
  /** red(複数のインデックスの複数のプライマリが未割り当て。アラートが一覧になる) */
  redMultiple: () => {
    const indices = sortIndices([
      index('demo-a', { status: 'red', document_count: null }),
      index('demo-b', { status: 'red', document_count: null }),
    ])
    const shards = [
      shard('demo-a', { shard: 0, state: 'unassigned', node: null }),
      shard('demo-a', { shard: 1, state: 'unassigned', node: null }),
      shard('demo-b', { shard: 0, state: 'unassigned', node: null }),
    ]
    return response({ cluster: summarize(shards, 1, 'red'), indices, shards, total_indices: 2 })
  },
  /** 25 件のインデックス(3 ノード。yellow 2・green 23。移動中・件数 null・10 桁の件数・システムインデックスを含む) */
  many: () => manyIndices(),
  /** 状態値が未知(中立表示。X-BD2) */
  unknownValues: () =>
    response({
      cluster: summary({ status: 'purple' }),
      indices: [index('loreley-documents-000001', { status: 'purple' })],
      shards: [shard('loreley-documents-000001', { role: 'witness', state: 'moving' })],
    }),
  /** インデックスの状態・件数が null(クローズ済み・シャード一覧だけにあるインデックスを補ったもの) */
  nullIndexValues: () =>
    response({
      indices: [index('closed-index', { status: null, document_count: null })],
      shards: [shard('closed-index')],
    }),
  /** 1,000 件で切り詰め(`truncated=true`。画面は警告を出す)。全 1,500 件のうち先頭 1,000 件 */
  truncated: () => {
    const indices = Array.from({ length: 1000 }, (_, i) =>
      index(`bulk-${String(i).padStart(4, '0')}`, { document_count: i }),
    )
    return response({
      indices,
      shards: indices.map((entry) => shard(entry.name)),
      truncated: true,
      total_indices: 1500,
    })
  },
  /** インデックスなし(0 件。ノードはある) */
  empty: () =>
    response({
      cluster: summary({ active_shards: 0 }),
      indices: [],
      shards: [],
      total_indices: 0,
    }),
}
