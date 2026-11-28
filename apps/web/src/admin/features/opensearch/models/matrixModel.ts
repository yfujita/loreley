// O1 のシャード配置マトリクスのモデル(純関数。opensearch 3.3)。
// 行=ノード(+未割り当て)、列=インデックス。**行・列の並びは API の応答の並びのまま使う**
// (状態の悪い順 → 名前の昇順は API が保証済み。画面で並べ替えない・`indices[]` にないインデックスを補わない。X-ED5)。
// 数えるのは、表示対象のインデックス(絞り込み後。全ページ)だけ(行見出しの「シャード n」・凡例・未割り当ての行)。
import type { ClusterResponse, IndexEntry, ShardEntry } from '@/admin/api'
import type {
  MatrixColumn,
  MatrixLegend,
  MatrixModel,
  ShardChipModel,
} from '@/admin/components/shard-matrix/types'
import { classifyShard } from '@/admin/lib/clusterValues'

/** セルの中の並び: プライマリ → レプリカ → それ以外、同じ役割の中は番号の昇順。 */
function roleOrder(role: string): number {
  if (role === 'primary') return 0
  if (role === 'replica') return 1
  return 2
}

function sortShards(shards: ShardEntry[]): ShardEntry[] {
  return shards.sort((a, b) => roleOrder(a.role) - roleOrder(b.role) || a.shard - b.shard)
}

function toChip(shard: ShardEntry): ShardChipModel {
  return { number: shard.shard, role: shard.role, state: shard.state }
}

function groupByIndex(shards: readonly ShardEntry[]): Map<string, ShardEntry[]> {
  const grouped = new Map<string, ShardEntry[]>()
  for (const shard of shards) {
    const list = grouped.get(shard.index)
    if (list === undefined) grouped.set(shard.index, [shard])
    else list.push(shard)
  }
  return grouped
}

function buildColumn(index: IndexEntry, shards: ShardEntry[]): MatrixColumn {
  const byNode = new Map<string, ShardEntry[]>()
  const unassigned: ShardEntry[] = []
  for (const shard of shards) {
    if (shard.node === null) {
      unassigned.push(shard)
      continue
    }
    const list = byNode.get(shard.node)
    if (list === undefined) byNode.set(shard.node, [shard])
    else list.push(shard)
  }
  return {
    name: index.name,
    status: index.status,
    documentCount: index.document_count,
    shardsByNode: new Map(
      [...byNode].map(([node, list]) => [node, sortShards(list).map(toChip)] as const),
    ),
    unassigned: sortShards(unassigned).map(toChip),
  }
}

function buildLegend(shards: readonly ShardEntry[]): MatrixLegend {
  const kinds = new Set(shards.map((shard) => classifyShard(shard.role, shard.state)))
  return {
    unassignedReplica: kinds.has('unassigned-replica'),
    unassignedPrimary: kinds.has('unassigned-primary'),
    inTransit: kinds.has('initializing') || kinds.has('relocating'),
  }
}

/**
 * `indices` は絞り込み後のインデックス(API の並びのまま)。`nodes`・`shards` は応答のまま。
 * 行は `nodes[]`(クラスタの全ノード。シャードを持たないノードも)の順。応答の `nodes[]` にないノード名のシャードがあれば、
 * チップが黙って消えないよう、末尾に行を足す(API の保証が崩れたときの安全網)。
 */
export function buildMatrixModel(
  response: Pick<ClusterResponse, 'nodes' | 'shards'>,
  indices: readonly IndexEntry[],
): MatrixModel {
  const visibleNames = new Set(indices.map((index) => index.name))
  const visibleShards = response.shards.filter((shard) => visibleNames.has(shard.index))
  const shardsByIndex = groupByIndex(visibleShards)

  const nodeNames = response.nodes.map((node) => node.name)
  for (const shard of visibleShards) {
    if (shard.node !== null && !nodeNames.includes(shard.node)) nodeNames.push(shard.node)
  }

  return {
    nodes: nodeNames.map((name) => ({
      name,
      shardCount: visibleShards.filter((shard) => shard.node === name).length,
    })),
    unassignedShardCount: visibleShards.filter((shard) => shard.node === null).length,
    columns: indices.map((index) => buildColumn(index, shardsByIndex.get(index.name) ?? [])),
    legend: buildLegend(visibleShards),
  }
}
