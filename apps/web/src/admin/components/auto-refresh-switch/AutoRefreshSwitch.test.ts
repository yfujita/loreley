import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import AutoRefreshSwitch from './AutoRefreshSwitch.vue'

async function mountSwitch(initial = true) {
  const value = ref(initial)
  const Host = defineComponent({
    setup: () => () =>
      h(AutoRefreshSwitch, {
        modelValue: value.value,
        intervalSeconds: 30,
        'onUpdate:modelValue': (next: boolean) => (value.value = next),
      }),
  })
  const { wrapper } = await mountInLayout(Host)
  return { wrapper, value, input: () => wrapper.find('input') }
}

describe('AutoRefreshSwitch(DS 4.17。D1 の自動更新の一時停止)', () => {
  it('role=switch の checkbox。ラベル「自動更新(30 秒ごと)」(間隔は props)', async () => {
    const { wrapper, input } = await mountSwitch()

    // `VSwitch` の `<input>` は role を持たない(Vuetify 4.3.4)ので、明示している
    expect(input().attributes('type')).toBe('checkbox')
    expect(input().attributes('role')).toBe('switch')
    expect(wrapper.find(`label[for="${input().attributes('id')}"]`).text()).toBe(
      '自動更新(30 秒ごと)',
    )
  })

  it('オンのときは checked。オフの案内は出さない', async () => {
    const { wrapper, input } = await mountSwitch(true)

    expect((input().element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.text()).not.toContain('自動更新は停止中です')
  })

  it('切り替えると v-model が変わり、オフのときは近くに「自動更新は停止中です。「更新」で最新の状態を取得します。」を出す', async () => {
    const { wrapper, value, input } = await mountSwitch(true)

    await input().setValue(false)

    expect(value.value).toBe(false)
    expect(wrapper.text()).toContain('自動更新は停止中です。「更新」で最新の状態を取得します。')

    await input().setValue(true)
    expect(value.value).toBe(true)
    expect(wrapper.text()).not.toContain('自動更新は停止中です')
  })

  it('初期値がオフなら、最初から停止中の案内を出す', async () => {
    const { wrapper, input } = await mountSwitch(false)

    expect((input().element as HTMLInputElement).checked).toBe(false)
    expect(wrapper.text()).toContain('自動更新は停止中です')
  })
})
