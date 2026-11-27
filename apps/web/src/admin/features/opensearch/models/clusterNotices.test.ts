import { describe, expect, it } from 'vitest'

import { opensearch } from '../../../../../tests/support/fixtures/opensearch'
import { findUnassignedPrimaries, formatShardNumbers } from './clusterNotices'

describe('findUnassignedPrimaries(red のアラートの元)', () => {
  it('未割り当てのプライマリだけを、インデックスごとにシャード番号(昇順)で集める。レプリカは含めない', () => {
    expect(findUnassignedPrimaries(opensearch.red().shards)).toEqual([
      { index: 'demo-docs-000001', shardNumbers: [0] },
    ])
  })

  it('複数のインデックス・複数のシャード', () => {
    const shards = opensearch.redMultiple().shards.reverse()

    expect(findUnassignedPrimaries(shards)).toEqual([
      { index: 'demo-b', shardNumbers: [0] },
      { index: 'demo-a', shardNumbers: [0, 1] },
    ])
  })

  it('未割り当てのプライマリがなければ空(yellow・green・移動中)', () => {
    expect(findUnassignedPrimaries(opensearch.yellow().shards)).toEqual([])
    expect(findUnassignedPrimaries(opensearch.unassignedAndMoving().shards)).toEqual([])
    expect(findUnassignedPrimaries(opensearch.green().shards)).toEqual([])
  })

  it('役割が未知の未割り当てはプライマリとして数えない(断定しない)', () => {
    const shards = opensearch.green().shards.map((shard) => ({
      ...shard,
      role: 'witness',
      state: 'unassigned',
      node: null,
    }))

    expect(findUnassignedPrimaries(shards)).toEqual([])
  })
})

describe('formatShardNumbers', () => {
  it('P0、P1 のように並べる', () => {
    expect(formatShardNumbers([0, 1, 12])).toBe('P0、P1、P12')
  })
})
