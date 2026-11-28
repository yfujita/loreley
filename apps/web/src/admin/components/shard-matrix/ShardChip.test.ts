import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import ShardChip from './ShardChip.vue'
import type { ShardChipModel } from './types'

async function mountChip(chip: ShardChipModel, readout?: boolean) {
  const { wrapper } = await mountInLayout(ShardChip, {
    props: { chip, ...(readout !== undefined && { readout }) },
  })
  return wrapper.find('.shard-chip')
}

describe('ShardChip(DS 4.15・opensearch 3.3)', () => {
  it.each([
    ['primary', 'started', 'P0', 'primary', '(プライマリ。割り当て済み)', false],
    ['replica', 'started', 'R0', 'replica', '(レプリカ。割り当て済み)', false],
    ['replica', 'unassigned', 'R0', 'unassigned-replica', '(レプリカ。未割り当て)', true],
    ['primary', 'unassigned', 'P0', 'unassigned-primary', '(プライマリ。未割り当て)', true],
    ['primary', 'initializing', 'P0', 'initializing', '(プライマリ。初期化中)', true],
    ['replica', 'relocating', 'R0', 'relocating', '(レプリカ。移動中)', true],
  ] as const)(
    '%s・%s: 文字 %s・種類 %s・読み上げ「%s」・アイコン=%s',
    async (role, state, letter, kind, readout, hasIcon) => {
      const wrapper = await mountChip({ number: 0, role, state })

      expect(wrapper.classes()).toContain(`shard-chip--${kind}`)
      expect(wrapper.text()).toBe(`${letter} ${readout}`)
      expect(wrapper.find('.sr-only').text()).toBe(readout)
      expect(wrapper.find('.v-icon').exists()).toBe(hasIcon)
    },
  )

  it('文字(P / R)にシャード番号が続く', async () => {
    const wrapper = await mountChip({ number: 12, role: 'primary', state: 'started' })

    expect(wrapper.text()).toContain('P12')
  })

  it('初期化中と移動中は見た目(アイコン・色の class)が同一で、読み上げだけが違う', async () => {
    const initializing = await mountChip({ number: 0, role: 'primary', state: 'initializing' })
    const relocating = await mountChip({ number: 0, role: 'primary', state: 'relocating' })

    expect(initializing.find('.v-icon').html()).toBe(relocating.find('.v-icon').html())
    expect(initializing.find('.sr-only').text()).not.toBe(relocating.find('.sr-only').text())
  })

  it('未割り当てのプライマリは八角形・レプリカは三角(アイコンの形で区別する。色だけにしない)', async () => {
    const primary = await mountChip({ number: 0, role: 'primary', state: 'unassigned' })
    const replica = await mountChip({ number: 0, role: 'replica', state: 'unassigned' })

    expect(primary.find('.v-icon').html()).not.toBe(replica.find('.v-icon').html())
  })

  it('未知の役割: 文字は ?、割り当て済みなら中立。読み上げに役割の値をそのまま出す', async () => {
    const wrapper = await mountChip({ number: 0, role: 'witness', state: 'started' })

    expect(wrapper.classes()).toContain('shard-chip--unknown')
    expect(wrapper.text()).toBe('?0 (witness。started)')
  })

  it('未知の状態: 役割の文字のまま中立。読み上げに状態の値をそのまま出す', async () => {
    const wrapper = await mountChip({ number: 3, role: 'replica', state: 'moving' })

    expect(wrapper.classes()).toContain('shard-chip--unknown')
    expect(wrapper.text()).toBe('R3 (レプリカ。moving)')
  })

  it('未知の役割の未割り当ては warning の点線(プライマリと断定しない)', async () => {
    const wrapper = await mountChip({ number: 0, role: 'witness', state: 'unassigned' })

    expect(wrapper.classes()).toContain('shard-chip--unassigned-replica')
    expect(wrapper.find('.sr-only').text()).toBe('(witness。未割り当て)')
  })

  it('readout=false(凡例の見本)は、読み上げの文を付けない', async () => {
    const wrapper = await mountChip({ number: 0, role: 'primary', state: 'started' }, false)

    expect(wrapper.find('.sr-only').exists()).toBe(false)
  })
})
