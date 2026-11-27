import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import ConfirmCheck from './ConfirmCheck.vue'

async function mountCheck(props: { disabled?: boolean } = {}) {
  const checked = ref(false)
  const Host = defineComponent({
    setup: () => () =>
      h(ConfirmCheck, {
        modelValue: checked.value,
        'onUpdate:modelValue': (value: boolean) => (checked.value = value),
        label: 'ジョブが動いていないことを確認しました',
        ...props,
      }),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, checked }
}

describe('ConfirmCheck(DS 4.8)', () => {
  it('<label> 付きのチェックボックス。押すと値が変わる', async () => {
    const { wrapper, checked } = await mountCheck()

    const input = wrapper.find('input[type="checkbox"]')
    expect(wrapper.find('label').text()).toBe('ジョブが動いていないことを確認しました')
    expect(wrapper.find('label').attributes('for')).toBe(input.attributes('id'))

    await input.setValue(true)

    expect(checked.value).toBe(true)
  })

  it('実行中(disabled)は入力を無効にする(二重送信を防ぐ)', async () => {
    const { wrapper } = await mountCheck({ disabled: true })

    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
  })
})
