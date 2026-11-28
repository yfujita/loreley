import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach } from 'vitest'
import { createMemoryHistory, createRouter, type RouteRecordRaw, type Router } from 'vue-router'
import { VLayout } from 'vuetify/components'
import { defineComponent, h, type Component } from 'vue'

import { setupVuetify } from '@/admin/app/setupVuetify'

type MountOptions = {
  props?: Record<string, unknown>
  slots?: Record<string, () => unknown>
  routes?: RouteRecordRaw[]
  initialPath?: string
  /** 履歴に先に積むパス。`initialPath` への最初の遷移は履歴を置き換えるため、「戻る」の検証(push と replace の違い)に使う */
  previousPath?: string
  /** 既定は `retry: false` の QueryClient。再試行・staleTime など本番の既定値を確かめるときに `createAppQueryClient()` を渡す */
  queryClient?: QueryClient
}

type MountResult = {
  wrapper: VueWrapper
  router: Router
  queryClient: QueryClient
}

const EMPTY_PAGE: Component = { render: () => null }

// テストが作った QueryClient は、テスト後に必ず空にする(キャッシュ・タイマーを次のテストへ持ち越さない)。
const createdQueryClients: QueryClient[] = []
afterEach(() => {
  for (const client of createdQueryClients.splice(0)) client.clear()
})

/**
 * 対象のコンポーネントを、本番に近い土台(Vuetify・VLayout・Router・QueryClient)で包んでマウントする。
 * - Vuetify は本番の `setupVuetify()`(テーマ・`defaults`・`mobileBreakpoint: 'md'`・アイコン・ロケール)
 * - QueryClient はテストごとに新しく作り、再試行しない(`retry: false`)。テスト後に `clear()` する
 * - Router はメモリ履歴。`routes` を省くと、すべてのパスが空のページに解決される
 * - VDialog などは body にテレポートするので、`attachTo: document.body` でマウントする
 */
export async function mountInLayout(
  component: Component,
  options: MountOptions = {},
): Promise<MountResult> {
  const { props = {}, slots = {}, routes, initialPath = '/' } = options

  const queryClient =
    options.queryClient ?? new QueryClient({ defaultOptions: { queries: { retry: false } } })
  createdQueryClients.push(queryClient)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: routes ?? [{ path: '/:pathMatch(.*)*', component: EMPTY_PAGE }],
  })
  if (options.previousPath !== undefined) await router.push(options.previousPath)
  await router.push(initialPath)
  await router.isReady()

  const root = defineComponent({
    render: () => h(VLayout, null, { default: () => h(component, props, slots) }),
  })
  const wrapper = mount(root, {
    attachTo: document.body,
    global: {
      plugins: [setupVuetify(), router, [VueQueryPlugin, { queryClient }]],
    },
  })

  return { wrapper, router, queryClient }
}
