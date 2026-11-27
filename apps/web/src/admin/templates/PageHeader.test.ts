import { describe, expect, it } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'

import type { ActionSpec } from '@/admin/lib/actions'
import { breadcrumbsKey, type BreadcrumbItem } from '@/admin/lib/injectionKeys'

import { mountInLayout } from '../../../tests/support/mount'
import PageHeader from './PageHeader.vue'

const ROUTES = [{ path: '/:p(.*)*', component: { render: () => null } }]

/** AppShell と同じく、パンくずを provide する土台。 */
async function mountHeader(
  props: Record<string, unknown>,
  options: { breadcrumbs?: BreadcrumbItem[]; slots?: Record<string, () => unknown> } = {},
) {
  const emitted: string[] = []
  const Host = defineComponent({
    setup() {
      if (options.breadcrumbs !== undefined) provide(breadcrumbsKey, ref(options.breadcrumbs))
      return () =>
        h(
          PageHeader,
          { onAction: (id: string) => emitted.push(id), ...props } as never,
          options.slots,
        )
    },
  })
  const mounted = await mountInLayout(Host, { routes: ROUTES })
  return { ...mounted, emitted }
}

describe('PageHeader(DS 5.1・6)', () => {
  it('h1 は tabindex=-1(遷移後のフォーカス先)。1 画面に 1 つ', async () => {
    const { wrapper } = await mountHeader({ title: 'データソース' })

    const headings = wrapper.findAll('h1')
    expect(headings).toHaveLength(1)
    expect(headings[0]?.text()).toBe('データソース')
    expect(headings[0]?.attributes('tabindex')).toBe('-1')
  })

  it('識別子を見出しにするときは、等幅(monoTitle)', async () => {
    const { wrapper } = await mountHeader({ title: 'demo-handbook', monoTitle: true })

    expect(wrapper.find('h1 span').classes()).toContain('page-header__mono')
  })

  it('状態タグ(tag スロット)は h1 の中に置く', async () => {
    const { wrapper } = await mountHeader(
      { title: 'demo-handbook' },
      { slots: { tag: () => h('span', { class: 'tag' }, '成功') } },
    )

    expect(wrapper.find('h1 .tag').text()).toBe('成功')
  })

  it('説明(description)を出す。なければ出さない', async () => {
    const withDescription = await mountHeader({
      title: 'ジョブ',
      description: 'クロールの履歴です。',
    })
    const without = await mountHeader({ title: 'ジョブ' })

    expect(withDescription.wrapper.find('.page-header__description').text()).toBe(
      'クロールの履歴です。',
    )
    expect(without.wrapper.find('.page-header__description').exists()).toBe(false)
  })

  it('パンくずは inject で受ける(AppShell が provide)。なければ出さない', async () => {
    const withCrumbs = await mountHeader(
      { title: 'データソースを登録' },
      {
        breadcrumbs: [
          { title: 'データソース', to: '/sources' },
          { title: 'データソースを登録', to: null },
        ],
      },
    )
    const without = await mountHeader({ title: 'データソース' })

    expect(withCrumbs.wrapper.find('nav[aria-label="パンくず"]').text()).toContain('データソース')
    expect(without.wrapper.find('nav[aria-label="パンくず"]').exists()).toBe(false)
  })

  it('操作(actions)を PageActions で描き、押すと action を通知する', async () => {
    const actions: ActionSpec[] = [
      {
        id: 'create',
        label: 'データソースを登録',
        visible: true,
        disabledReason: null,
        level: 'normal',
      },
    ]
    const { wrapper, emitted } = await mountHeader({
      title: 'データソース',
      actions,
      primaryActionId: 'create',
    })

    await wrapper.find('button').trigger('click')

    expect(wrapper.find('button').text()).toBe('データソースを登録')
    expect(wrapper.find('button').classes()).toContain('bg-primary')
    expect(emitted).toEqual(['create'])
  })

  it('actions を渡さなければ、操作領域を出さない', async () => {
    const { wrapper } = await mountHeader({ title: 'ダッシュボード' })

    expect(wrapper.find('.page-actions').exists()).toBe(false)
  })
})
