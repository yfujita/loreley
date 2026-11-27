import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import AdminDataTable from './AdminDataTable.vue'
import type { AdminColumn, AdminSort } from './tableModel'

type Row = { source_id: string; status: string; count: number } & Record<string, unknown>

const COLUMNS: AdminColumn[] = [
  { key: 'source_id', title: 'データソース', sortable: true },
  { key: 'status', title: '状態' },
  { key: 'count', title: '登録文書数', align: 'end', sortable: true },
]
const ITEMS: Row[] = [
  { source_id: 'demo-handbook', status: '成功', count: 1284 },
  { source_id: 'demo-shared-docs', status: '実行中', count: 56 },
]

const originalWidth = window.innerWidth
afterEach(() => {
  window.innerWidth = originalWidth
})

async function mountTable(
  options: { sort?: AdminSort; loading?: boolean; mustSort?: boolean; items?: Row[] } = {},
) {
  const sorts: AdminSort[] = []
  const sort = ref<AdminSort>(options.sort ?? null)
  const Host = defineComponent({
    setup: () => () =>
      h(
        AdminDataTable<Row>,
        {
          columns: COLUMNS,
          items: options.items ?? ITEMS,
          itemKey: 'source_id',
          caption: 'データソース一覧',
          sort: sort.value,
          mustSort: options.mustSort,
          loading: options.loading,
          rowTestid: (item: Row) => `s1-row-${item.source_id}`,
          'onUpdate:sort': (next: AdminSort) => {
            sorts.push(next)
            sort.value = next
          },
        },
        {
          'item.count': ({ item }: { item: Row }) =>
            h('span', { class: 'num' }, `${item.count} 件`),
        },
      ),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, sorts, sort }
}

describe('AdminDataTable(FMOD-U-4。DS 4.3)', () => {
  it('<caption> を視覚的に隠して持ち、見出しは列ごとに 1 つ、行はデータごとに 1 つ', async () => {
    const { wrapper } = await mountTable()

    expect(wrapper.find('caption').text()).toBe('データソース一覧')
    expect(wrapper.find('caption').classes()).toContain('sr-only')
    expect(wrapper.findAll('thead th').map((th) => th.text())).toEqual([
      'データソース',
      '状態',
      '登録文書数',
    ])
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    // 見出しは <th scope="col">(DS 8)
    expect(wrapper.findAll('thead th').map((th) => th.attributes('scope'))).toEqual([
      'col',
      'col',
      'col',
    ])
  })

  it('行に data-testid を付け、item.<key> のスロットでセルを差し替えられる', async () => {
    const { wrapper } = await mountTable()

    const row = wrapper.find('[data-testid="s1-row-demo-handbook"]')
    expect(row.exists()).toBe(true)
    expect(row.text()).toContain('demo-handbook')
    expect(row.find('.num').text()).toBe('1284 件')
  })

  it('ホバーは有効(hover)。行の区切りは境界線で、縞模様にしない', async () => {
    const { wrapper } = await mountTable()

    expect(wrapper.find('table').element.closest('.v-table')?.classList).toContain('v-table--hover')
    expect(wrapper.find('.admin-data-table').exists()).toBe(true)
  })

  it('並べ替えできる列の見出しは、現在の並びを aria-sort(ascending・descending)で伝える', async () => {
    const { wrapper: asc } = await mountTable({ sort: { key: 'source_id', order: 'asc' } })
    const { wrapper: desc } = await mountTable({ sort: { key: 'count', order: 'desc' } })

    const sortOf = (w: typeof asc) => w.findAll('thead th').map((th) => th.attributes('aria-sort'))
    expect(sortOf(asc)).toEqual(['ascending', undefined, 'none'])
    expect(sortOf(desc)).toEqual(['none', undefined, 'descending'])
  })

  it('単一ソート: 別の列を押すと、前の列の並びは外れ、更新が通知される', async () => {
    const { wrapper, sorts } = await mountTable({ sort: { key: 'source_id', order: 'asc' } })

    await wrapper.findAll('thead th')[2]?.trigger('click')
    await nextTick()

    expect(sorts).toEqual([{ key: 'count', order: 'asc' }])
    const sortOf = wrapper.findAll('thead th').map((th) => th.attributes('aria-sort'))
    expect(sortOf).toEqual(['none', undefined, 'ascending'])
  })

  it('同じ列を続けて押すと 昇順 → 降順 → 解除(null)。must-sort なら解除しない', async () => {
    const { wrapper, sorts } = await mountTable()
    const header = () => wrapper.findAll('thead th')[0]

    await header()?.trigger('click')
    await header()?.trigger('click')
    await header()?.trigger('click')

    expect(sorts).toEqual([
      { key: 'source_id', order: 'asc' },
      { key: 'source_id', order: 'desc' },
      null,
    ])

    const must = await mountTable({ mustSort: true })
    for (let i = 0; i < 3; i++) await must.wrapper.findAll('thead th')[0]?.trigger('click')
    expect(must.sorts).toEqual([
      { key: 'source_id', order: 'asc' },
      { key: 'source_id', order: 'desc' },
      { key: 'source_id', order: 'asc' },
    ])
  })

  it('並べ替えできない列の見出しを押しても、何も通知しない。初期表示でも通知しない', async () => {
    const { wrapper, sorts } = await mountTable()
    expect(sorts).toEqual([])

    await wrapper.findAll('thead th')[1]?.trigger('click')

    expect(sorts).toEqual([])
  })

  it('初回読み込み中は、同じ列数のスケルトン行を出し、ページングは出さない', async () => {
    const { wrapper } = await mountTable({ loading: true, items: [] })

    const rows = wrapper.findAll('tbody tr.skeleton-rows__row')
    expect(rows).toHaveLength(5)
    expect(rows[0]?.findAll('td')).toHaveLength(COLUMNS.length)
    expect(wrapper.find('.v-data-table-footer').exists()).toBe(false)
    expect(wrapper.find('.v-data-table').attributes('aria-busy')).toBe('true')
  })

  it('ページング: 「1–2 / 2 件」と 1 ページの件数(25・50・100)を出す。最初・最後へのボタンは出さない', async () => {
    const { wrapper } = await mountTable()

    const footer = wrapper.find('.v-data-table-footer')
    expect(footer.text()).toContain('1 ページの件数')
    expect(footer.text()).toContain('1–2 / 2 件')
    expect(footer.findAll('button[aria-label]').map((b) => b.attributes('aria-label'))).toEqual([
      '前のページ',
      '次のページ',
    ])
  })

  it('幅 840px 未満は、行をカード状に積む(各セルに項目名を付ける)。840px 以上は通常の表(サイドバーと同じ境)', async () => {
    window.innerWidth = 839
    const { wrapper: narrow } = await mountTable()
    window.innerWidth = 840
    const { wrapper: wide } = await mountTable()

    expect(narrow.find('.v-data-table__td-title').exists()).toBe(true)
    expect(narrow.find('.v-data-table__td-title').text()).toBe('データソース')
    expect(wide.find('.v-data-table__td-title').exists()).toBe(false)
    expect(wide.findAll('thead th')).toHaveLength(3)
  })
})
