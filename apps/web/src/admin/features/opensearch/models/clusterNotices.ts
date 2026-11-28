// O1 のページ上部・カード上部の通知の元になる値(純関数。opensearch 3.1・E 6.7)。
// 通知はクラスタ全体の値から作る(絞り込みの対象外)。
import type { ShardEntry } from '@/admin/api'
import { classifyShard } from '@/admin/lib/clusterValues'

export type UnassignedPrimaryItem = {
  index: string
  /** 未割り当てのプライマリのシャード番号(昇順・重複なし) */
  shardNumbers: readonly number[]
}

/** 未割り当てのプライマリシャードを、インデックスごとに集める(red のアラートが、該当するインデックスとシャード番号を出す)。 */
export function findUnassignedPrimaries(shards: readonly ShardEntry[]): UnassignedPrimaryItem[] {
  const byIndex = new Map<string, Set<number>>()
  for (const shard of shards) {
    if (classifyShard(shard.role, shard.state) !== 'unassigned-primary') continue
    const numbers = byIndex.get(shard.index)
    if (numbers === undefined) byIndex.set(shard.index, new Set([shard.shard]))
    else numbers.add(shard.shard)
  }
  return [...byIndex].map(([index, numbers]) => ({
    index,
    shardNumbers: [...numbers].sort((a, b) => a - b),
  }))
}

/** `P0、P1` のように、シャード番号をプライマリのチップの表記にする。 */
export function formatShardNumbers(numbers: readonly number[]): string {
  return numbers.map((number) => `P${number}`).join('、')
}
