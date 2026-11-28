import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import PageAlert from './PageAlert.vue'

describe('PageAlert(DS 4.7)', () => {
  it('role は props で切り替える。既定は付けない(role を持たない注記を作れる)', async () => {
    const { wrapper: none } = await mountInLayout(PageAlert, { props: { type: 'info' } })
    const { wrapper: alert } = await mountInLayout(PageAlert, {
      props: { type: 'error', role: 'alert' },
    })
    const { wrapper: status } = await mountInLayout(PageAlert, {
      props: { type: 'warning', role: 'status' },
    })

    expect(none.find('.page-alert').attributes('role')).toBeUndefined()
    expect(alert.find('.page-alert').attributes('role')).toBe('alert')
    expect(status.find('.page-alert').attributes('role')).toBe('status')
  })

  it('種類ごとに、色の組(page-alert--<type>)とアイコンが違う(色・形・文言で区別する)', async () => {
    const icons = new Set<string>()
    for (const type of ['info', 'warning', 'error', 'success'] as const) {
      const { wrapper } = await mountInLayout(PageAlert, { props: { type } })

      expect(wrapper.find('.page-alert').classes()).toContain(`page-alert--${type}`)
      icons.add(wrapper.find('.page-alert__icon path').attributes('d') ?? '')
    }
    expect(icons.size).toBe(4)
  })

  it('見出し・本文・操作(actions スロット)を描く', async () => {
    const { wrapper } = await mountInLayout(PageAlert, {
      props: { type: 'warning', title: '最新の状態を取得できませんでした' },
      slots: { default: () => '前回取得したデータを表示しています。', actions: () => '再読み込み' },
    })

    expect(wrapper.find('.page-alert__title').text()).toBe('最新の状態を取得できませんでした')
    expect(wrapper.text()).toContain('前回取得したデータを表示しています。')
    expect(wrapper.find('.page-alert__actions').text()).toBe('再読み込み')
  })

  it('見出し・操作がなければ、その要素を出さない', async () => {
    const { wrapper } = await mountInLayout(PageAlert, { props: { type: 'info' } })

    expect(wrapper.find('.page-alert__title').exists()).toBe(false)
    expect(wrapper.find('.page-alert__actions').exists()).toBe(false)
  })
})
