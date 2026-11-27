// EP-12 `GET /opensearch/cluster` のフィクスチャ(F 7.3)。応答に `unavailable` はない。
import type { ClusterResponse, IndexEntry, ShardEntry } from '@/admin/api'

const FETCHED_AT = '2026-11-22T10:48:03.000Z'

function summary(overrides: Partial<ClusterResponse['cluster']> = {}): ClusterResponse['cluster'] {
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
  /** 1,000 件で切り詰め(`truncated=true`。画面は警告を出す) */
  truncated: () => response({ truncated: true, total_indices: 1500 }),
  /** インデックスなし(0 件) */
  empty: () => response({ indices: [], shards: [], total_indices: 0 }),
}
