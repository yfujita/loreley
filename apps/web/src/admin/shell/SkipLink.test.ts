import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'

import { mountInLayout } from '../../../tests/support/mount'
import SkipLink from './SkipLink.vue'

describe('SkipLink(DS 8)', () => {
  it('「メインコンテンツへ移動」を、本文(#main)へのリンクとして持つ', async () => {
    const { wrapper } = await mountInLayout(SkipLink)

    const link = wrapper.find('a')
    expect(link.text()).toBe('メインコンテンツへ移動')
    expect(link.attributes('href')).toBe('#main')
  })

  it('押すと、URL のハッシュを変えずに、本文にフォーカスを移す', async () => {
    const Host = defineComponent({
      setup: () => () => [h(SkipLink), h('main', { id: 'main', tabindex: -1 }, 'content')],
    })
    const { wrapper } = await mountInLayout(Host)

    await wrapper.find('a').trigger('click')

    expect(document.activeElement).toBe(wrapper.find('main').element)
    expect(window.location.hash).toBe('')
  })

  it('移動先の id を変えられる', async () => {
    const { wrapper } = await mountInLayout(SkipLink, { props: { targetId: 'content' } })

    expect(wrapper.find('a').attributes('href')).toBe('#content')
  })
})
