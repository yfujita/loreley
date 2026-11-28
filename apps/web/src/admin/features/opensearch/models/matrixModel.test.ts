import { describe, expect, it } from 'vitest'

import type { IndexEntry } from '@/admin/api'

import { opensearch } from '../../../../../tests/support/fixtures/opensearch'
import { buildMatrixModel } from './matrixModel'

function modelOf(response: ReturnType<typeof opensearch.many>, indices?: readonly IndexEntry[]) {
  return buildMatrixModel(response, indices ?? response.indices)
}
const chipsAt = (column: ReturnType<typeof buildMatrixModel>['columns'][number], node: string) =>
  column.shardsByNode.get(node)?.map((chip) => `${chip.role}${chip.number}:${chip.state}`)

describe('buildMatrixModel(行=ノード・列=インデックス)', () => {
  it('列は、渡したインデックスの順(API の並びのまま。並べ替え・補完しない)', () => {
    const response = opensearch.many()

    const model = modelOf(response)

    expect(model.columns.map((column) => column.name)).toEqual(
      response.indices.map((index) => index.name),
    )
  })

  it('並べ替えない: 名前の昇順でない順で渡しても、そのまま', () => {
    const response = opensearch.multiNode()
    const reversed = [...response.indices].reverse()

    expect(buildMatrixModel(response, reversed).columns.map((column) => column.name)).toEqual(
      reversed.map((index) => index.name),
    )
  })

  it('行は nodes[] の順(シャードを持たないノードも行にする)。補完しない', () => {
    const response = opensearch.green()
    response.nodes = [{ name: 'node-1' }, { name: 'node-idle' }]

    const model = buildMatrixModel(response, response.indices)

    expect(model.nodes).toEqual([
      { name: 'node-1', shardCount: 1 },
      { name: 'node-idle', shardCount: 0 },
    ])
  })

  it('nodes[] にないノード名のシャードは、チップが消えないよう、末尾に行を足す(安全網)', () => {
    const response = opensearch.green()
    response.shards = [
      {
        index: 'loreley-documents-000001',
        shard: 0,
        role: 'primary',
        state: 'started',
        node: 'node-ghost',
      },
    ]

    const model = buildMatrixModel(response, response.indices)

    expect(model.nodes.map((node) => node.name)).toEqual(['node-1', 'node-ghost'])
    expect(model.nodes[1]?.shardCount).toBe(1)
  })

  it('列に、名前・状態・件数(null はそのまま)を持つ', () => {
    const response = opensearch.red()

    const [first] = modelOf(response).columns

    expect(first).toMatchObject({ name: 'demo-docs-000001', status: 'red', documentCount: null })
    expect(modelOf(response).columns[1]).toMatchObject({ status: 'yellow', documentCount: 1204 })
  })

  it('セルの並び: プライマリ → レプリカ → それ以外、同じ役割は番号の昇順', () => {
    const response = opensearch.green()
    const index = 'loreley-documents-000001'
    response.shards = [
      { index, shard: 1, role: 'replica', state: 'started', node: 'node-1' },
      { index, shard: 0, role: 'witness', state: 'started', node: 'node-1' },
      { index, shard: 1, role: 'primary', state: 'started', node: 'node-1' },
      { index, shard: 0, role: 'replica', state: 'started', node: 'node-1' },
      { index, shard: 0, role: 'primary', state: 'started', node: 'node-1' },
    ]

    const model = buildMatrixModel(response, response.indices)

    expect(chipsAt(model.columns[0]!, 'node-1')).toEqual([
      'primary0:started',
      'primary1:started',
      'replica0:started',
      'replica1:started',
      'witness0:started',
    ])
  })

  it('未割り当て(node=null)は、ノードの行ではなく未割り当ての行(columns[].unassigned)に入る', () => {
    const model = buildMatrixModel(opensearch.yellow(), opensearch.yellow().indices)

    expect(model.unassignedShardCount).toBe(1)
    expect(model.columns[0]?.unassigned).toEqual([
      { number: 0, role: 'replica', state: 'unassigned' },
    ])
    expect(chipsAt(model.columns[0]!, 'node-1')).toEqual(['primary0:started'])
  })

  it('ノードごとの「シャード n」は、表示対象のインデックス(全ページ)の合計。未割り当ては数えない', () => {
    const response = opensearch.many()

    const all = modelOf(response)

    expect(
      all.nodes.reduce((sum, node) => sum + node.shardCount, 0) + all.unassignedShardCount,
    ).toBe(response.shards.length)
  })

  it('絞り込み後のインデックスだけを数える(行見出しの合計・未割り当て・凡例・列)', () => {
    const response = opensearch.many()
    const greens = response.indices.filter((index) => index.status === 'green')

    const model = modelOf(response, greens)

    // green のインデックスにだけ絞ると、未割り当て(yellow のレプリカ)は消え、移動中だけが残る
    expect(model.unassignedShardCount).toBe(0)
    expect(model.legend).toEqual({
      unassignedReplica: false,
      unassignedPrimary: false,
      inTransit: true,
    })
    expect(model.columns).toHaveLength(greens.length)
    expect(model.nodes.reduce((sum, node) => sum + node.shardCount, 0)).toBe(greens.length * 2)
  })

  it('凡例: 未割り当てのレプリカ・プライマリ・初期化中/移動中は、表示対象にあるときだけ', () => {
    expect(modelOf(opensearch.multiNode()).legend).toEqual({
      unassignedReplica: false,
      unassignedPrimary: false,
      inTransit: false,
    })
    expect(modelOf(opensearch.yellow()).legend.unassignedReplica).toBe(true)
    expect(modelOf(opensearch.red()).legend).toMatchObject({
      unassignedReplica: true,
      unassignedPrimary: true,
    })
    expect(modelOf(opensearch.unassignedAndMoving()).legend).toEqual({
      unassignedReplica: true,
      unassignedPrimary: false,
      inTransit: true,
    })
  })

  it('初期化中だけ(移動中なし)でも、凡例の「初期化中・移動中」を出す', () => {
    const response = opensearch.green()
    response.shards = [
      {
        index: 'loreley-documents-000001',
        shard: 0,
        role: 'replica',
        state: 'initializing',
        node: 'node-1',
      },
    ]

    expect(buildMatrixModel(response, response.indices).legend).toEqual({
      unassignedReplica: false,
      unassignedPrimary: false,
      inTransit: true,
    })
  })

  it('同じセルに同じ役割・番号のシャードが 2 つあっても、どちらも残す(重複を落とさない)', () => {
    const response = opensearch.green()
    const shard = {
      index: 'loreley-documents-000001',
      shard: 1,
      role: 'replica',
      state: 'started',
      node: 'node-1',
    }
    response.shards = [shard, { ...shard }]

    const model = buildMatrixModel(response, response.indices)

    expect(chipsAt(model.columns[0]!, 'node-1')).toEqual(['replica1:started', 'replica1:started'])
  })

  it('インデックスが 0 件なら、列も数も 0。ノードの行だけが残る', () => {
    const model = modelOf(opensearch.empty())

    expect(model.columns).toEqual([])
    expect(model.nodes).toEqual([{ name: 'node-1', shardCount: 0 }])
    expect(model.unassignedShardCount).toBe(0)
  })

  it('シャードを持たないインデックスも列にする(セルは空)', () => {
    const response = opensearch.green()
    response.indices.push({ name: 'no-shards', status: 'green', document_count: 0 })

    const model = buildMatrixModel(response, response.indices)

    expect(model.columns[1]).toMatchObject({ name: 'no-shards', documentCount: 0 })
    expect(model.columns[1]?.shardsByNode.size).toBe(0)
    expect(model.columns[1]?.unassigned).toEqual([])
  })

  it('未知の役割・状態は API の値のままチップに持つ(描画側が中立表示にする)', () => {
    const model = modelOf(opensearch.unknownValues())

    expect(model.columns[0]?.shardsByNode.get('node-1')).toEqual([
      { number: 0, role: 'witness', state: 'moving' },
    ])
  })
})
