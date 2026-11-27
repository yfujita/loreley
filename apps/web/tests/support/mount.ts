import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type RouteRecordRaw, type Router } from 'vue-router'
import { createVuetify } from 'vuetify'
import { VLayout } from 'vuetify/components'
import { defineComponent, h, type Component } from 'vue'

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

/**
 * 対象のコンポーネントを、本番に近い土台(Vuetify・VLayout・Router・QueryClient)で包んでマウントする。
 * - QueryClient はテストごとに新しく作り、再試行しない(`retry: false`)
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
      plugins: [
        createVuetify({ display: { mobileBreakpoint: 'md' } }),
        router,
        [VueQueryPlugin, { queryClient }],
      ],
    },
  })

  return { wrapper, router, queryClient }
}
