import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import AdminDataTableServer from './AdminDataTableServer.vue'
import type { AdminColumn, AdminSort } from './tableModel'

type Row = { job_id: string; status: string } & Record<string, unknown>

const COLUMNS: AdminColumn[] = [
  { key: 'job_id', title: 'ジョブ ID' },
  { key: 'status', title: '状態' },
  { key: 'queued_at', title: '開始', sortable: true },
]
const ITEMS: Row[] = [
  { job_id: 'job-0001', status: '成功', queued_at: '2026-11-21' },
  { job_id: 'job-0002', status: '失敗', queued_at: '2026-11-20' },
]

async function mountServerTable(
  options: { total?: number; page?: number; itemsPerPage?: 25 | 50 | 100; loading?: boolean } = {},
) {
  const events: string[] = []
  const page = ref(options.page ?? 1)
  const itemsPerPage = ref<25 | 50 | 100>(options.itemsPerPage ?? 25)
  const sort = ref<AdminSort>({ key: 'queued_at', order: 'desc' })
  const Host = defineComponent({
    setup: () => () =>
      h(AdminDataTableServer<Row>, {
        columns: COLUMNS,
        items: ITEMS,
        itemsLength: options.total ?? 120,
        itemKey: 'job_id',
        caption: 'ジョブ一覧',
        page: page.value,
        itemsPerPage: itemsPerPage.value,
        sort: sort.value,
        loading: options.loading,
        rowTestid: (item: Row) => `j1-row-${item.job_id}`,
        'onUpdate:page': (next: number) => {
          events.push(`page=${next}`)
          page.value = next
        },
        'onUpdate:itemsPerPage': (next: 25 | 50 | 100) => {
          events.push(`itemsPerPage=${next}`)
          itemsPerPage.value = next
        },
        'onUpdate:sort': (next: AdminSort) => {
          events.push(`sort=${JSON.stringify(next)}`)
          sort.value = next
        },
      }),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, events, page, itemsPerPage, sort }
}

describe('AdminDataTableServer(FMOD-U-4。DS 4.3)', () => {
  it('初期表示では、ページ・件数・並べ替えの更新を通知しない(@update:options の初期発火を吸収する。二重に取得しない)', async () => {
    const { events } = await mountServerTable()
    await nextTick()

    expect(events).toEqual([])
  })

  it('サーバー側の件数(itemsLength)で「1–25 / 120 件」を出す。表示する行は渡された items だけ', async () => {
    const { wrapper } = await mountServerTable({ total: 120 })

    expect(wrapper.find('.v-data-table-footer').text()).toContain('1–25 / 120 件')
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.find('[data-testid="j1-row-job-0001"]').exists()).toBe(true)
  })

  it('「次のページ」で page だけを通知する(並べ替え・件数は通知しない)', async () => {
    const { wrapper, events } = await mountServerTable()

    await wrapper.find('button[aria-label="次のページ"]').trigger('click')
    await nextTick()

    expect(events).toEqual(['page=2'])
  })

  it('最後のページでは「次のページ」が無効、最初のページでは「前のページ」が無効', async () => {
    const first = await mountServerTable({ total: 60, page: 1 })
    const last = await mountServerTable({ total: 60, page: 3 })

    expect(
      first.wrapper.find('button[aria-label="前のページ"]').attributes('disabled'),
    ).toBeDefined()
    expect(
      last.wrapper.find('button[aria-label="次のページ"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('単一ソート: 並べ替えできる列の現在の並びを aria-sort で伝え、押すと 降順 → 解除(null)→ 昇順 の順に通知する(page は通知しない)', async () => {
    const { wrapper, events } = await mountServerTable()
    const header = () => wrapper.findAll('thead th')[2]
    expect(header()?.attributes('aria-sort')).toBe('descending')

    await header()?.trigger('click')
    await nextTick()
    expect(events).toEqual(['sort=null'])
    expect(header()?.attributes('aria-sort')).toBe('none')

    await header()?.trigger('click')
    await nextTick()
    expect(events).toEqual(['sort=null', 'sort={"key":"queued_at","order":"asc"}'])
    expect(header()?.attributes('aria-sort')).toBe('ascending')
  })

  it('3 ページ目で並べ替えを変えると、1 ページ目へ戻る通知が出る(page=1)', async () => {
    const { wrapper, events } = await mountServerTable({ total: 120, page: 3 })

    await wrapper.findAll('thead th')[2]?.trigger('click')
    await nextTick()

    expect(events).toContain('sort=null')
    expect(events).toContain('page=1')
  })

  it('1 ページの件数は 25・50・100 から選べ、変更を通知する', async () => {
    const { wrapper, events } = await mountServerTable({ total: 200 })

    await wrapper.find('.v-data-table-footer .v-select .v-field').trigger('mousedown')
    await nextTick()
    const options = [...document.querySelectorAll('.v-list-item')].map((item) =>
      item.textContent?.trim(),
    )
    expect(options).toEqual(['25', '50', '100'])
    const fifty = [...document.querySelectorAll<HTMLElement>('.v-list-item')].find(
      (item) => item.textContent?.trim() === '50',
    )
    fifty?.click()
    await nextTick()

    expect(events).toContain('itemsPerPage=50')
  })

  it('ホバーあり・<caption> は視覚的に隠す・初回読み込み中はスケルトン行(ページングなし)', async () => {
    const { wrapper } = await mountServerTable({ loading: true })

    expect(wrapper.find('.v-table--hover').exists()).toBe(true)
    expect(wrapper.find('caption.sr-only').text()).toBe('ジョブ一覧')
    expect(wrapper.findAll('tr.skeleton-rows__row')).toHaveLength(5)
    expect(wrapper.find('.v-data-table-footer').exists()).toBe(false)
  })
})
