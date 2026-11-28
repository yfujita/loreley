import { describe, expect, it } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import TypeToConfirm from './TypeToConfirm.vue'

async function mountTyped(initial = '', props: { disabled?: boolean } = {}) {
  const matchedEvents: boolean[] = []
  const Host = defineComponent({
    setup() {
      const value = ref(initial)
      return () =>
        h(TypeToConfirm, {
          modelValue: value.value,
          'onUpdate:modelValue': (next: string) => (value.value = next),
          'onUpdate:matched': (matched: boolean) => matchedEvents.push(matched),
          expected: 'demo-handbook',
          ...props,
        })
    },
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, matchedEvents }
}

describe('TypeToConfirm(DS 4.8)', () => {
  it('識別子を示し、入力欄にラベルが結ばれる。貼り付け可・自動補完と綴り確認は無効', async () => {
    const { wrapper } = await mountTyped()

    const input = wrapper.find('input')
    expect(wrapper.find('label').text()).toContain(
      '確認のため識別子 demo-handbook を入力してください',
    )
    expect(wrapper.find('label').attributes('for')).toBe(input.attributes('id'))
    expect(input.attributes('autocomplete')).toBe('off')
    expect(input.attributes('spellcheck')).toBe('false')
    expect(input.attributes('readonly')).toBeUndefined()
  })

  it('空のあいだは、一致も不一致も出さず、一致していないと伝える(matched=false)', async () => {
    const { wrapper, matchedEvents } = await mountTyped()

    expect(wrapper.find('.type-to-confirm__result').text()).toBe('')
    expect(matchedEvents).toEqual([false])
  })

  it('一致しない入力があれば「識別子が一致しません」を aria-live=polite で出す', async () => {
    const { wrapper } = await mountTyped()

    await wrapper.find('input').setValue('demo-hand')

    const result = wrapper.find('.type-to-confirm__result')
    expect(result.attributes('aria-live')).toBe('polite')
    expect(result.text()).toBe('識別子が一致しません')
  })

  it('完全一致(前後の空白は無視)で「識別子が一致しました」を出し、matched=true を通知する', async () => {
    const { wrapper, matchedEvents } = await mountTyped()

    await wrapper.find('input').setValue('  demo-handbook ')

    expect(wrapper.find('.type-to-confirm__result').text()).toBe('識別子が一致しました')
    expect(matchedEvents).toEqual([false, true])
  })

  it('大文字小文字を区別する。一致後に変えると、不一致に戻る', async () => {
    const { wrapper, matchedEvents } = await mountTyped('demo-handbook')

    await wrapper.find('input').setValue('Demo-handbook')

    expect(wrapper.find('.type-to-confirm__result').text()).toBe('識別子が一致しません')
    expect(matchedEvents).toEqual([true, false])
  })

  it('空白だけの入力は、不一致のメッセージを出さない(trim して空と同じ扱い)。一致もしない', async () => {
    const { wrapper } = await mountTyped()

    await wrapper.find('input').setValue('   ')

    expect(wrapper.find('.type-to-confirm__result').text()).toBe('')
  })

  it('実行中(disabled)は、入力欄を無効にする(二重送信を防ぐ)', async () => {
    const { wrapper } = await mountTyped('', { disabled: true })

    expect(wrapper.find('input').attributes('disabled')).toBeDefined()
  })
})
