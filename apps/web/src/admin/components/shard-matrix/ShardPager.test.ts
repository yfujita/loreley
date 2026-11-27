import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import ShardPager from './ShardPager.vue'

async function mountPager(page: number, pageCount = 4) {
  const events: number[] = []
  const { wrapper } = await mountInLayout(ShardPager, {
    props: { page, pageCount, 'onUpdate:page': (value: number) => events.push(value) },
  })
  const prev = () => wrapper.find('button[aria-label^="前へ"]')
  const next = () => wrapper.find('button[aria-label^="次へ"]')
  return { wrapper, events, prev, next }
}

describe('ShardPager(DS 4.15・opensearch 3.4)', () => {
  it('role=group(シャードの配置のページ送り)に、前へ・ページ選択・次へ。ボタンの名前は見える文字を含む', async () => {
    const { wrapper, prev, next } = await mountPager(2)

    expect(wrapper.find('[role="group"]').attributes('aria-label')).toBe(
      'シャードの配置のページ送り',
    )
    expect(prev().attributes('aria-label')).toBe('前へ。シャードの配置の前のページ')
    expect(next().attributes('aria-label')).toBe('次へ。シャードの配置の次のページ')
    expect(prev().text()).toBe('前へ')
    expect(next().text()).toBe('次へ')
  })

  it('ページ選択は <label>「ページ」付きの select。選択肢は「n / 全ページ数」', async () => {
    const { wrapper } = await mountPager(2)

    const select = wrapper.find('select')
    expect(wrapper.find(`label[for="${select.attributes('id')}"]`).text()).toBe('ページ')
    expect(select.findAll('option').map((option) => option.text())).toEqual([
      '1 / 4',
      '2 / 4',
      '3 / 4',
      '4 / 4',
    ])
    expect((select.element as HTMLSelectElement).value).toBe('2')
  })

  it('中間のページ: 前へ・次へともに使え、押すと隣のページを通知する', async () => {
    const { events, prev, next } = await mountPager(2)

    expect(prev().attributes('aria-disabled')).toBe('false')
    expect(next().attributes('aria-disabled')).toBe('false')
    await prev().trigger('click')
    await next().trigger('click')
    expect(events).toEqual([1, 3])
  })

  it('1 ページ目の「前へ」は aria-disabled=true(disabled にしない)。押しても何も起きない', async () => {
    const { events, prev, next } = await mountPager(1)

    expect(prev().attributes('aria-disabled')).toBe('true')
    expect(prev().attributes('disabled')).toBeUndefined()
    await prev().trigger('click')
    expect(events).toEqual([])
    expect(next().attributes('aria-disabled')).toBe('false')
  })

  it('最終ページの「次へ」は aria-disabled=true。押しても何も起きない', async () => {
    const { events, next } = await mountPager(4)

    expect(next().attributes('aria-disabled')).toBe('true')
    expect(next().attributes('disabled')).toBeUndefined()
    await next().trigger('click')
    expect(events).toEqual([])
  })

  it('ページ選択で、選んだページを通知する。いまと同じページを選んでも通知しない', async () => {
    const { wrapper, events } = await mountPager(2)
    const select = wrapper.find('select')

    await select.setValue('4')
    await select.setValue('2')

    expect(events).toEqual([4])
  })

  it('ページが 1 つだけなら、前へ・次へとも aria-disabled', async () => {
    const { prev, next } = await mountPager(1, 1)

    expect(prev().attributes('aria-disabled')).toBe('true')
    expect(next().attributes('aria-disabled')).toBe('true')
  })
})
