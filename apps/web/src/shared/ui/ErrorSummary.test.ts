import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import ErrorSummary, { type ErrorSummaryItem } from './ErrorSummary.vue'

const ITEMS: ErrorSummaryItem[] = [
  { fieldId: 'f1', message: '識別子を入力してください' },
  { fieldId: 'f2', message: '0 以上 100 未満で入力してください' },
]

describe('ErrorSummary(DS 4.6)', () => {
  it('件数つきの見出しと、各項目へのリンクを role=alert で出す', async () => {
    const { wrapper } = await mountInLayout(ErrorSummary, { props: { items: ITEMS } })

    expect(wrapper.find('.error-summary').attributes('role')).toBe('alert')
    expect(wrapper.text()).toContain('入力内容を確認してください(2 件)')
    const links = wrapper.findAll('a')
    expect(links.map((link) => link.text())).toEqual(ITEMS.map((item) => item.message))
    expect(links.map((link) => link.attributes('href'))).toEqual(['#f1', '#f2'])
  })

  it('エラーがなければ何も描かない', async () => {
    const { wrapper } = await mountInLayout(ErrorSummary, { props: { items: [] } })

    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('focus() で要約にフォーカスを移せる(送信時。tabindex=-1)', async () => {
    const { wrapper } = await mountInLayout(ErrorSummary, { props: { items: ITEMS } })

    wrapper.findComponent(ErrorSummary).vm.focus()

    expect(document.activeElement).toBe(wrapper.find('[role="alert"]').element)
    expect(wrapper.find('[role="alert"]').attributes('tabindex')).toBe('-1')
  })

  it('リンクを押すと、select を通知してから項目にフォーカスを移す(URL のハッシュは変えない)', async () => {
    const selected: string[] = []
    const { wrapper } = await mountInLayout(ErrorSummary, {
      props: {
        items: ITEMS,
        // 折りたたみの中の項目は、ここで開く(開いた後にフォーカスする)。
        onSelect: (item: ErrorSummaryItem) => {
          selected.push(item.fieldId)
          const input = document.createElement('input')
          input.id = item.fieldId
          document.body.append(input)
        },
      },
    })

    await wrapper.findAll('a')[1]?.trigger('click')
    await new Promise((resolve) => window.setTimeout(resolve, 0))

    expect(selected).toEqual(['f2'])
    expect(document.activeElement?.id).toBe('f2')
    expect(window.location.hash).toBe('')
    document.getElementById('f2')?.remove()
  })
})
