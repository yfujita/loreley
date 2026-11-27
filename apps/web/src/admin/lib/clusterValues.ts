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
