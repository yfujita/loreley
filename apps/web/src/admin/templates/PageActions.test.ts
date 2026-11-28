import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'

import type { ActionSpec } from '@/admin/lib/actions'

import { mountInLayout } from '../../../tests/support/mount'
import PageActions from './PageActions.vue'

const action = (overrides: Partial<ActionSpec> & Pick<ActionSpec, 'id' | 'label'>): ActionSpec => ({
  visible: true,
  disabledReason: null,
  level: 'confirm',
  ...overrides,
})

async function mountActions(actions: ActionSpec[], primaryId?: string | null) {
  const emitted: string[] = []
  const Host = defineComponent({
    setup: () => () =>
      h(PageActions, { actions, primaryId, onAction: (id: string) => emitted.push(id) }),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, emitted }
}

describe('PageActions(DS 4.13)', () => {
  it('主操作は primary(1 つ)、ほかは outlined(副次)', async () => {
    const { wrapper } = await mountActions(
      [action({ id: 'edit', label: '編集' }), action({ id: 'crawl', label: 'クロール起動' })],
      'crawl',
    )

    const buttons = wrapper.findAll('button')
    expect(buttons.map((b) => b.text())).toEqual(['編集', 'クロール起動'])
    expect(buttons[0]?.classes()).toContain('v-btn--variant-outlined')
    expect(buttons[1]?.classes()).toContain('bg-primary')
    expect(wrapper.findAll('.bg-primary')).toHaveLength(1)
  })

  it('primaryId を省略すると、すべて副次の見た目', async () => {
    const { wrapper } = await mountActions([action({ id: 'a', label: 'A' })])

    expect(wrapper.find('button').classes()).toContain('v-btn--variant-outlined')
  })

  it('visible が false の操作は出さない(実行の見込みがない)。全部 false なら何も描かない', async () => {
    const some = await mountActions([
      action({ id: 'a', label: 'A' }),
      action({ id: 'b', label: 'B', visible: false }),
    ])
    const none = await mountActions([action({ id: 'b', label: 'B', visible: false })])

    expect(some.wrapper.findAll('button').map((b) => b.text())).toEqual(['A'])
    expect(none.wrapper.find('.page-actions').exists()).toBe(false)
  })

  it('無効の操作は、無効にして理由を近くに出し、aria-describedby で結ぶ(状況が変われば実行できる)', async () => {
    const { wrapper } = await mountActions([
      action({
        id: 'rerun',
        label: '再実行',
        disabledReason: 'ロックを解放すると再実行できます。',
      }),
      action({ id: 'edit', label: '編集' }),
    ])

    const [rerun, edit] = wrapper.findAll('button')
    const reason = wrapper.find('.page-actions__reason')
    expect(rerun?.attributes('disabled')).toBeDefined()
    expect(reason.text()).toBe('ロックを解放すると再実行できます。')
    expect(rerun?.attributes('aria-describedby')).toBe(reason.attributes('id'))
    // 有効な操作には、理由も aria-describedby もない
    expect(edit?.attributes('disabled')).toBeUndefined()
    expect(edit?.attributes('aria-describedby')).toBeUndefined()
    expect(wrapper.findAll('.page-actions__reason')).toHaveLength(1)
  })

  it('押すと、操作の id を通知する(ダイアログを開くのは画面)', async () => {
    const { wrapper, emitted } = await mountActions([
      action({ id: 'edit', label: '編集' }),
      action({ id: 'crawl', label: 'クロール起動' }),
    ])

    await wrapper.findAll('button')[1]?.trigger('click')

    expect(emitted).toEqual(['crawl'])
  })

  it('無効の操作は、押しても通知しない', async () => {
    const { wrapper, emitted } = await mountActions([
      action({ id: 'rerun', label: '再実行', disabledReason: '理由' }),
    ])

    await wrapper.find('button').trigger('click')

    expect(emitted).toEqual([])
  })
})
