// 実 `useListParams` と実 `AdminDataTableServer` の結合(A3): Vuetify は並べ替え・件数の変更の直後に、同期的に
// `page = 1` も通知する。画面がそれぞれを `update()` に流しても、URL が「古い値 + page=1」にならないこと。
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import type { LocationQuery } from 'vue-router'

import { useListParams, type ListParamsDefinition } from '@/admin/composables/useListParams'

import { mountInLayout } from '../../../../tests/support/mount'
import AdminDataTableServer from './AdminDataTableServer.vue'
import type { AdminColumn, AdminSort } from './tableModel'

type Params = { page: number; itemsPerPage: 25 | 50 | 100; sort: AdminSort }

const first = (value: LocationQuery[string]): string | undefined =>
  Array.isArray(value) ? (value[0] ?? undefined) : (value ?? undefined)

const definition: ListParamsDefinition<Params> = {
  parse(query) {
    const page = Number(first(query.page) ?? 1)
    const size = Number(first(query.size) ?? 25)
    const sortText = first(query.sort)
    return {
      page: Number.isInteger(page) && page >= 1 ? page : 1,
      itemsPerPage: size === 50 || size === 100 ? size : 25,
      sort:
        sortText === undefined
          ? null
          : { key: sortText.replace(/^-/, ''), order: sortText.startsWith('-') ? 'desc' : 'asc' },
    }
  },
  serialize(params) {
    return {
      ...(params.page !== 1 && { page: String(params.page) }),
      ...(params.itemsPerPage !== 25 && { size: String(params.itemsPerPage) }),
      ...(params.sort !== null && {
        sort: `${params.sort.order === 'desc' ? '-' : ''}${params.sort.key}`,
      }),
    }
  },
  navigation: 'push',
  pageKey: 'page',
  resetPageOn: ['itemsPerPage'],
}

type Row = { job_id: string } & Record<string, unknown>
const COLUMNS: AdminColumn[] = [
  { key: 'job_id', title: 'ジョブ ID' },
  { key: 'queued_at', title: '開始', sortable: true },
]
const ITEMS: Row[] = [{ job_id: 'job-1', queued_at: 'a' }]

/** vue-router の遷移(複数回の push・キャンセルを含む)が落ち着くまで待つ。 */
async function settle(): Promise<void> {
  await flushPromises()
  await new Promise((resolve) => window.setTimeout(resolve, 50))
  await flushPromises()
}

async function mountList(initialQuery: string) {
  const Host = defineComponent({
    setup() {
      const { params, update } = useListParams(definition)
      return () =>
        h(AdminDataTableServer<Row>, {
          columns: COLUMNS,
          items: ITEMS,
          itemsLength: 500,
          itemKey: 'job_id',
          caption: 'ジョブ一覧',
          page: params.value.page,
          itemsPerPage: params.value.itemsPerPage,
          sort: params.value.sort,
          'onUpdate:page': (page: number) => void update({ page }),
          'onUpdate:itemsPerPage': (itemsPerPage: 25 | 50 | 100) => void update({ itemsPerPage }),
          'onUpdate:sort': (sort: AdminSort) => void update({ sort }),
        })
    },
  })
  const mounted = await mountInLayout(Host, {
    routes: [{ path: '/jobs', component: { render: () => null } }],
    initialPath: `/jobs${initialQuery}`,
  })
  await flushPromises()
  return mounted
}

describe('AdminDataTableServer × useListParams(2 ページ目以降の変更)', () => {
  it('3 ページ目で並べ替えを変えると、URL は「新しい並び + 1 ページ目」になる(古い並びのまま 1 ページ目へ戻らない)', async () => {
    const { wrapper, router } = await mountList('?page=3&sort=-queued_at')

    await wrapper.findAll('thead th')[1]?.trigger('click')
    await settle()

    // 降順から押すと並べ替えの解除。解除された URL(sort なし)で、page も 1(省略)になる。
    expect(router.currentRoute.value.query).toEqual({})
  })

  it('並べ替えなしの 3 ページ目から並べ替えを足すと、URL は sort のみ(page は 1 に戻る)', async () => {
    const { wrapper, router } = await mountList('?page=3')

    await wrapper.findAll('thead th')[1]?.trigger('click')
    await settle()

    expect(router.currentRoute.value.query).toEqual({ sort: 'queued_at' })
  })

  it('3 ページ目で 1 ページの件数を変えると、URL は「新しい件数 + 1 ページ目」になる', async () => {
    const { wrapper, router } = await mountList('?page=3&sort=queued_at')

    await wrapper.find('.v-data-table-footer .v-select .v-field').trigger('mousedown')
    await settle()
    const fifty = [...document.querySelectorAll<HTMLElement>('.v-list-item')].find(
      (item) => item.textContent?.trim() === '50',
    )
    fifty?.click()
    await settle()

    expect(router.currentRoute.value.query).toEqual({ size: '50', sort: 'queued_at' })
  })

  it('ページだけを変える(次のページ)と、並びと件数は保たれる', async () => {
    const { wrapper, router } = await mountList('?page=2&size=50&sort=-queued_at')

    await wrapper.find('button[aria-label="次のページ"]').trigger('click')
    await settle()

    expect(router.currentRoute.value.query).toEqual({ page: '3', size: '50', sort: '-queued_at' })
  })
})
