import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import FilterBar, { type FilterField } from './FilterBar.vue'

const FIELDS = (source: string, status: string): FilterField[] => [
  {
    key: 'source',
    label: 'データソース',
    options: [
      { title: 'すべて', value: '' },
      { title: 'demo-handbook', value: 'demo-handbook' },
    ],
    value: source,
    testid: 'j1-filter-source',
  },
  {
    key: 'status',
    label: '状態',
    options: [
      { title: 'すべて', value: '' },
      { title: '失敗', value: 'failed' },
    ],
    value: status,
    testid: 'j1-filter-status',
  },
]

async function mountBar(options: { showReset?: boolean; source?: string } = {}) {
  const events: string[] = []
  const source = ref(options.source ?? '')
  const Host = defineComponent({
    setup: () => () =>
      h(FilterBar, {
        fields: FIELDS(source.value, ''),
        showReset: options.showReset,
        onChange: (key: string, value: string) => events.push(`change:${key}=${value}`),
        onReset: () => events.push('reset'),
      }),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, events, source }
}

describe('FilterBar(DS 4.12)', () => {
  it('絞り込みのフォーム(aria-label)に、ラベル付きのセレクトを横に並べる。送信しても何も起きない', async () => {
    const { wrapper } = await mountBar()

    const form = wrapper.find('form')
    expect(form.attributes('aria-label')).toBe('絞り込み')
    expect(wrapper.findAll('label').map((label) => label.text())).toEqual(['データソース', '状態'])
    await form.trigger('submit')
  })

  it('ラベルがセレクトの入力に結ばれ、DS 9 の data-testid が付く', async () => {
    const { wrapper } = await mountBar()

    const label = wrapper.findAll('label')[0]
    const field = wrapper.find('[data-testid="j1-filter-source"]')
    expect(field.exists()).toBe(true)
    expect(wrapper.find(`#${label?.attributes('for')}`).exists()).toBe(true)
  })

  it('現在の値(「すべて」を含む)を表示する', async () => {
    const { wrapper } = await mountBar({ source: 'demo-handbook' })

    const texts = wrapper.findAll('.v-select__selection-text').map((el) => el.text())
    expect(texts).toEqual(['demo-handbook', 'すべて'])
  })

  it('選択肢を選ぶと、key と値で change を通知する', async () => {
    const { wrapper, events } = await mountBar()

    await wrapper.findAll('.v-field')[1]?.trigger('mousedown')
    await nextTick()
    const failed = [...document.querySelectorAll<HTMLElement>('.v-list-item')].find(
      (item) => item.textContent?.trim() === '失敗',
    )
    failed?.click()
    await nextTick()

    expect(events).toEqual(['change:status=failed'])
  })

  it('「条件を解除」は showReset のときだけ出し、押すと reset を通知する', async () => {
    const hidden = await mountBar()
    const shown = await mountBar({ showReset: true })

    expect(hidden.wrapper.text()).not.toContain('条件を解除')
    await shown.wrapper.find('button').trigger('click')
    expect(shown.events).toEqual(['reset'])
  })
})
