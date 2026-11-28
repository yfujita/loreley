import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import FormField from './FormField.vue'

const INPUT_SLOT = (props: {
  inputId: string
  describedBy: string | undefined
  invalid: boolean
}) => `${props.inputId}|${props.describedBy ?? ''}|${props.invalid}`

async function mountField(props: Record<string, unknown>) {
  return mountInLayout(FormField, {
    props: { label: 'データソース ID', inputId: 'f1', ...props },
    // スロットの値を、描画された文字として確かめる。
    slots: { default: INPUT_SLOT as unknown as () => unknown },
  })
}

describe('FormField(DS 4.6)', () => {
  it('ラベルは項目の上にあり、入力欄の id に結ばれる(for)', async () => {
    const { wrapper } = await mountField({})

    const label = wrapper.find('label')
    expect(label.text()).toBe('データソース ID')
    expect(label.attributes('for')).toBe('f1')
  })

  it('必須は「必須」の表示(アスタリスクだけにしない)。任意の項目には印を付けない', async () => {
    const { wrapper: required } = await mountField({ required: true })
    const { wrapper: optional } = await mountField({})

    expect(required.find('.form-field__required').text()).toBe('必須')
    expect(optional.find('.form-field__required').exists()).toBe(false)
  })

  it('エラー: アイコン+文言を入力欄の下に出し、スロットへ invalid と aria-describedby(エラーが先・ヘルプが後)を渡す', async () => {
    const { wrapper } = await mountField({ error: '識別子を入力してください', help: '英数字のみ' })

    expect(wrapper.find('#f1-error').text()).toBe('識別子を入力してください')
    expect(wrapper.find('#f1-error svg').exists()).toBe(true)
    expect(wrapper.find('#f1-help').text()).toBe('英数字のみ')
    expect(wrapper.text()).toContain('f1|f1-error f1-help|true')
    expect(wrapper.find('.form-field').classes()).toContain('form-field--error')
  })

  it('エラーもヘルプもなければ、存在しない id を指さない(describedby なし・invalid=false)', async () => {
    const { wrapper } = await mountField({})

    expect(wrapper.text()).toContain('f1||false')
    expect(wrapper.find('#f1-error').exists()).toBe(false)
    expect(wrapper.find('#f1-help').exists()).toBe(false)
  })

  it('ヘルプだけのときは、ヘルプの id だけを結ぶ', async () => {
    const { wrapper } = await mountField({ help: '英数字のみ' })

    expect(wrapper.text()).toContain('f1|f1-help|false')
  })

  it('error が null・undefined ならエラーなし', async () => {
    const { wrapper } = await mountField({ error: null })

    expect(wrapper.find('.form-field__error').exists()).toBe(false)
  })

  it('inputId を省略すると、自動で作り、ラベルと結ぶ', async () => {
    const { wrapper } = await mountInLayout(FormField, {
      props: { label: 'ラベル' },
      slots: { default: INPUT_SLOT as unknown as () => unknown },
    })

    const inputId = wrapper.find('label').attributes('for')
    expect(inputId).toMatch(/^field-/)
    expect(wrapper.text()).toContain(`${inputId}||false`)
  })
})
