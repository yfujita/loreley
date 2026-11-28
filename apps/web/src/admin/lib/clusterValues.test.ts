import { describe, expect, it } from 'vitest'

import {
  classifyShard,
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

describe('classifyShard(チップの種類)', () => {
  it.each([
    ['primary', 'started', 'primary'],
    ['replica', 'started', 'replica'],
    ['primary', 'unassigned', 'unassigned-primary'],
    ['replica', 'unassigned', 'unassigned-replica'],
    ['primary', 'initializing', 'initializing'],
    ['replica', 'initializing', 'initializing'],
    ['primary', 'relocating', 'relocating'],
    ['replica', 'relocating', 'relocating'],
  ] as const)('%s・%s は %s', (role, state, expected) => {
    expect(classifyShard(role, state)).toBe(expected)
  })

  it('役割が未知で割り当て済みなら unknown、未割り当てならレプリカと同じ warning 側(プライマリと断定しない)', () => {
    expect(classifyShard('witness', 'started')).toBe('unknown')
    expect(classifyShard('witness', 'unassigned')).toBe('unassigned-replica')
  })

  it('状態が未知なら、役割によらず unknown', () => {
    expect(classifyShard('primary', 'moving')).toBe('unknown')
    expect(classifyShard('replica', 'constructor')).toBe('unknown')
  })
})
