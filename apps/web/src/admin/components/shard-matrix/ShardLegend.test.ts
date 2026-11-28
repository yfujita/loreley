import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import ShardLegend from './ShardLegend.vue'
import type { MatrixLegend } from './types'

async function mountLegend(legend: MatrixLegend) {
  const { wrapper } = await mountInLayout(ShardLegend, { props: { legend } })
  return wrapper.findAll('li').map((item) => item.find('span:last-child').text())
}

const NONE: MatrixLegend = { unassignedReplica: false, unassignedPrimary: false, inTransit: false }

describe('ShardLegend(凡例)', () => {
  it('プライマリ・レプリカは常に出す。ほかは、表示対象にあるときだけ', async () => {
    expect(await mountLegend(NONE)).toEqual(['プライマリ', 'レプリカ'])
  })

  it('未割り当てのレプリカ・プライマリ・初期化中/移動中を、この順で足す', async () => {
    expect(
      await mountLegend({ unassignedReplica: true, unassignedPrimary: true, inTransit: true }),
    ).toEqual([
      'プライマリ',
      'レプリカ',
      '未割り当てのレプリカ(点線)',
      '未割り当てのプライマリ(点線・赤)',
      '初期化中・移動中',
    ])
  })

  it('ラベルつきのリスト(aria-label=凡例)。見本のチップには読み上げの文を付けない(説明と重複するため)', async () => {
    const { wrapper } = await mountInLayout(ShardLegend, {
      props: { legend: { ...NONE, unassignedReplica: true } },
    })

    expect(wrapper.find('ul').attributes('aria-label')).toBe('凡例')
    expect(wrapper.find('.sr-only').exists()).toBe(false)
  })
})
