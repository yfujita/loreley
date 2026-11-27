import { describe, expect, it } from 'vitest'

import {
  CLUSTER_STATUSES,
  SHARD_ROLES,
  SHARD_STATES,
  toClusterStatus,
  toShardRole,
  toShardState,
} from './clusterValues'

describe('OpenSearch の状態値の union とガード', () => {
  it('既知の値はそのまま返す', () => {
    expect(CLUSTER_STATUSES.map((value) => toClusterStatus(value))).toEqual([
      'green',
      'yellow',
      'red',
    ])
    expect(SHARD_ROLES.map((value) => toShardRole(value))).toEqual(['primary', 'replica'])
    expect(SHARD_STATES.map((value) => toShardState(value))).toEqual([
      'started',
      'initializing',
      'relocating',
      'unassigned',
    ])
  })

  it('未知の値・null は null(中立表示)', () => {
    expect(toClusterStatus('purple')).toBeNull()
    expect(toClusterStatus(null)).toBeNull()
    expect(toClusterStatus(undefined)).toBeNull()
    expect(toClusterStatus('GREEN')).toBeNull()
    expect(toShardRole('witness')).toBeNull()
    expect(toShardState('moving')).toBeNull()
  })

  it('プロトタイプのキーを既知と誤判定しない', () => {
    expect(toClusterStatus('constructor')).toBeNull()
    expect(toShardState('toString')).toBeNull()
  })
})
