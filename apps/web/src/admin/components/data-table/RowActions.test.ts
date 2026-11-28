import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'

import type { ActionSpec } from '@/admin/lib/actions'

import { mountInLayout } from '../../../../tests/support/mount'
import RowActions from './RowActions.vue'

const action = (overrides: Partial<ActionSpec> & Pick<ActionSpec, 'id' | 'label'>): ActionSpec => ({
  visible: true,
  disabledReason: null,
  level: 'normal',
  ...overrides,
})

const ACTIONS: ActionSpec[] = [
  action({ id: 'crawl', label: 'クロール起動', level: 'confirm' }),
  action({ id: 'edit', label: '編集' }),
  action({ id: 'delete', label: '削除…', level: 'confirm-typed' }),
]

async function mountRow(props: Record<string, unknown> = {}) {
  const emitted: string[] = []
  const Host = defineComponent({
    setup: () => () =>
      h(RowActions, {
        actions: ACTIONS,
        target: 'demo-handbook',
        primaryId: 'crawl',
        onAction: (id: string) => emitted.push(id),
        ...props,
      }),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, emitted }
}

function menuItems(): HTMLElement[] {
  return [...document.querySelectorAll<HTMLElement>('.v-list-item')]
}

describe('RowActions(DS 4.3)', () => {
  it('主操作ボタンの名前に、対象の識別子を含める(視覚的に隠した「(識別子)」)', async () => {
    const { wrapper } = await mountRow()

    const primary = wrapper.find('button.bg-primary-container')
    expect(primary.text()).toContain('クロール起動')
    expect(primary.find('.sr-only').text()).toBe('(demo-handbook)')
    expect(primary.text()).toBe('クロール起動(demo-handbook)')
  })

  it('主操作を押すと、その id を通知する', async () => {
    const { wrapper, emitted } = await mountRow()

    await wrapper.find('button.bg-primary-container').trigger('click')

    expect(emitted).toEqual(['crawl'])
  })

  it('その他の操作は「⋮」のメニュー(aria-label に識別子)。危険な操作(要入力確認)は下段で区切り線の下・赤字', async () => {
    const { wrapper } = await mountRow()

    const menuButton = wrapper.find('button[aria-label="その他の操作(demo-handbook)"]')
    await menuButton.trigger('click')
    await new Promise((resolve) => window.setTimeout(resolve, 50))

    expect(menuItems().map((item) => item.textContent?.trim())).toEqual(['編集', '削除…'])
    expect(menuItems()[1]?.classList).toContain('row-actions__danger')
    expect(menuItems()[0]?.classList).not.toContain('row-actions__danger')
    expect(document.querySelectorAll('.v-divider').length).toBeGreaterThan(0)
  })

  it('メニューの項目を押すと、その id を通知する', async () => {
    const { wrapper, emitted } = await mountRow()
    await wrapper.find('button[aria-label="その他の操作(demo-handbook)"]').trigger('click')
    await new Promise((resolve) => window.setTimeout(resolve, 50))

    menuItems()[1]?.click()

    expect(emitted).toEqual(['delete'])
  })

  it('visible が false の操作は出さない。その他の操作がなければ「⋮」も出さない', async () => {
    const { wrapper } = await mountRow({
      actions: [
        action({ id: 'crawl', label: 'クロール起動' }),
        action({ id: 'delete', label: '削除…', visible: false }),
      ],
    })

    expect(wrapper.find('button.bg-primary-container').exists()).toBe(true)
    expect(wrapper.find('button[aria-label^="その他の操作"]').exists()).toBe(false)
  })

  it('主操作がなければ(出さない状態)、メニューだけを出す', async () => {
    const { wrapper } = await mountRow({
      actions: [action({ id: 'rerun', label: '削除を再実行' })],
      primaryId: null,
    })

    expect(wrapper.find('button.bg-primary-container').exists()).toBe(false)
    expect(wrapper.find('button[aria-label^="その他の操作"]').exists()).toBe(true)
  })

  it('無効の主操作は、無効にし、理由を視覚的に隠した文言として aria-describedby で結ぶ(title は補助)', async () => {
    const { wrapper } = await mountRow({
      actions: [action({ id: 'crawl', label: 'クロール起動', disabledReason: '削除中です' })],
    })

    const primary = wrapper.find('button.v-btn--disabled')
    const reason = wrapper.find('.row-actions > .sr-only')
    expect(primary.attributes('disabled')).toBeDefined()
    expect(primary.attributes('title')).toBe('削除中です')
    expect(reason.text()).toBe('削除中です')
    expect(primary.attributes('aria-describedby')).toBe(reason.attributes('id'))
  })

  it('有効な主操作には、理由の文言も aria-describedby も付けない', async () => {
    const { wrapper } = await mountRow()

    expect(
      wrapper.find('button.bg-primary-container').attributes('aria-describedby'),
    ).toBeUndefined()
    expect(wrapper.find('.row-actions > .sr-only').exists()).toBe(false)
  })

  it('アイコンのみ(表のカード幅が 720px 未満): アクセシブルネームに「操作名(識別子)」を残し、ツールチップ(title)で操作名を出す', async () => {
    const { wrapper } = await mountRow({ iconOnly: true, primaryIcon: 'M0 0h24v24H0z' })

    const primary = wrapper.find('button[aria-label="クロール起動(demo-handbook)"]')
    expect(primary.exists()).toBe(true)
    expect(primary.attributes('title')).toBe('クロール起動')
    expect(primary.text()).toBe('')
  })

  it('アイコンのみでも、アイコンが渡されなければ文言のままにする(操作名を失わない)', async () => {
    const { wrapper } = await mountRow({ iconOnly: true })

    expect(wrapper.find('button.bg-primary-container').text()).toContain('クロール起動')
  })
})
