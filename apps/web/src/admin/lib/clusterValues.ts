// OpenSearch の状態値(E 5.9・F 3.5。X-BD2)。
//
// `cluster.status`・`indices[].status`・`shards[].role`・`shards[].state` は OpenAPI で素の string(列挙なし)。
// 画面側で既知の値の union と型ガードを**ここ 1 か所**に定義し、未知の値は中立表示にする
// (`StatusTag` の未登録の扱い。`indexFilter` では未知の状態値は除外)。値の一覧は B 7.1・opensearch 画面仕様に従う。

export const CLUSTER_STATUSES = ['green', 'yellow', 'red'] as const
export type ClusterStatus = (typeof CLUSTER_STATUSES)[number]

export const SHARD_ROLES = ['primary', 'replica'] as const
export type ShardRole = (typeof SHARD_ROLES)[number]

export const SHARD_STATES = ['started', 'initializing', 'relocating', 'unassigned'] as const
export type ShardState = (typeof SHARD_STATES)[number]

function narrow<T extends string>(
  values: readonly T[],
  value: string | null | undefined,
): T | null {
  return values.find((known) => known === value) ?? null
}

/** `cluster.status`・`indices[].status`。既知でなければ(`null` を含む)`null`(中立表示)。 */
export function toClusterStatus(value: string | null | undefined): ClusterStatus | null {
  return narrow(CLUSTER_STATUSES, value)
}

export function toShardRole(value: string | null | undefined): ShardRole | null {
  return narrow(SHARD_ROLES, value)
}

export function toShardState(value: string | null | undefined): ShardState | null {
  return narrow(SHARD_STATES, value)
}

/**
 * シャードのチップの種類(O1。opensearch 3.3)。`role`・`state` の組から決める。
 * - 未割り当て: プライマリは error、それ以外(レプリカ・未知の役割)は warning の点線
 * - 初期化中・移動中: info(見た目は同じ。読み上げだけ分ける)
 * - 割り当て済み(`started`): プライマリ・レプリカ。役割が未知なら unknown
 * - 状態が未知: unknown(中立表示。値はそのまま出す)
 */
export type ShardChipKind =
  | 'primary'
  | 'replica'
  | 'unassigned-primary'
  | 'unassigned-replica'
  | 'initializing'
  | 'relocating'
  | 'unknown'

export function classifyShard(role: string, state: string): ShardChipKind {
  const knownRole = toShardRole(role)
  switch (toShardState(state)) {
    case 'unassigned':
      return knownRole === 'primary' ? 'unassigned-primary' : 'unassigned-replica'
    case 'initializing':
      return 'initializing'
    case 'relocating':
      return 'relocating'
    case 'started':
      return knownRole ?? 'unknown'
    case null:
      return 'unknown'
  }
}
