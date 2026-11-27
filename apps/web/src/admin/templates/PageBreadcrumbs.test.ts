import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import PageBreadcrumbs from './PageBreadcrumbs.vue'

const ROUTES = [
  { path: '/sources', component: { render: () => null } },
  { path: '/sources/:id', component: { render: () => null } },
]

describe('PageBreadcrumbs(DS 5.2)', () => {
  it('nav aria-label="パンくず"。親はリンク、末尾は現在のページ(リンクにせず aria-current="page")', async () => {
    const { wrapper } = await mountInLayout(PageBreadcrumbs, {
      props: {
        items: [
          { title: 'データソース', to: '/sources' },
          { title: 'demo-handbook', to: '/sources/demo-handbook' },
          { title: '編集', to: null },
        ],
      },
      routes: ROUTES,
    })

    expect(wrapper.find('nav').attributes('aria-label')).toBe('パンくず')
    expect(wrapper.findAll('a').map((a) => [a.text(), a.attributes('href')])).toEqual([
      ['データソース', '/sources'],
      ['demo-handbook', '/sources/demo-handbook'],
    ])
    const current = wrapper.find('[aria-current="page"]')
    expect(current.text()).toBe('編集')
    expect(current.element.tagName).toBe('SPAN')
  })

  it('区切りは項目の間だけ(末尾の後にはない)。装飾なので読み上げない', async () => {
    const { wrapper } = await mountInLayout(PageBreadcrumbs, {
      props: {
        items: [
          { title: 'データソース', to: '/sources' },
          { title: 'a', to: null },
        ],
      },
      routes: ROUTES,
    })

    const dividers = wrapper.findAll('.page-breadcrumbs__divider')
    expect(dividers).toHaveLength(1)
    expect(dividers[0]?.attributes('aria-hidden')).toBe('true')
  })

  it('項目がなければ何も描かない(1 階層の画面)', async () => {
    const { wrapper } = await mountInLayout(PageBreadcrumbs, {
      props: { items: [] },
      routes: ROUTES,
    })

    expect(wrapper.find('nav').exists()).toBe(false)
  })
})
