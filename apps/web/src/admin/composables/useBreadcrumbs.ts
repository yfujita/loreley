// パンくずの項目の組み立て(DS 5.2・E 4.2・FMOD-P-28)。`AppShell` が呼んで provide し、`PageHeader` が inject する。
// 2 階層以上(`meta.parent` を持つ route)の画面だけ項目を返す。親の URL は、親の route に**現在の `params` を引き継いで**作る
// (S4 の親 S2 に `sourceId` が要る)。末尾は現在のページ(`to` は null: リンクにしない)。
import { computed, type ComputedRef } from 'vue'
import { useRoute, useRouter, type RouteLocationNormalizedLoaded, type Router } from 'vue-router'

import type { BreadcrumbItem } from '@/admin/lib/injectionKeys'
import type { RouteName } from '@/admin/lib/routeNames'

import { resolveRouteTitle } from './routeTitle'

const PARAM_PATTERN = /:([A-Za-z0-9_]+)/g

/** route の path に出てくるパラメータ名。親の URL を作るとき、不要なパラメータを渡さない(vue-router が警告するため)。 */
function paramNames(path: string): string[] {
  return Array.from(path.matchAll(PARAM_PATTERN), (match) => match[1] ?? '')
}

function parentLocation(
  router: Router,
  parentName: RouteName,
  route: RouteLocationNormalizedLoaded,
) {
  const parent = router.getRoutes().find((record) => record.name === parentName)
  if (parent === undefined) return null
  const params = Object.fromEntries(
    paramNames(parent.path).map((name) => [name, route.params[name] ?? '']),
  )
  return { parent, location: router.resolve({ name: parentName, params }) }
}

/** `route` から `meta.parent` を辿り、現在のページを末尾にした項目を返す。親がなければ空(パンくずを出さない)。 */
export function buildBreadcrumbs(
  router: Router,
  route: RouteLocationNormalizedLoaded,
): BreadcrumbItem[] {
  if (route.meta.parent === undefined) return []

  const ancestors: BreadcrumbItem[] = []
  const visited = new Set<string>()
  let parentName: RouteName | undefined = route.meta.parent
  // 循環した定義でも止まるように、同じ route を 2 度辿らない。
  while (parentName !== undefined && !visited.has(parentName)) {
    visited.add(parentName)
    const resolved = parentLocation(router, parentName, route)
    if (resolved === null) break
    ancestors.unshift({
      // 親の見出しも現在の route(`params`)で解決する(動的な見出しは識別子など、`params` から作る)。
      title: resolveRouteTitle({ ...route, meta: resolved.parent.meta }),
      to: resolved.location.fullPath,
    })
    parentName = resolved.parent.meta.parent
  }
  return [...ancestors, { title: resolveRouteTitle(route), to: null }]
}

export function useBreadcrumbs(): ComputedRef<readonly BreadcrumbItem[]> {
  const route = useRoute()
  const router = useRouter()
  return computed(() => buildBreadcrumbs(router, route))
}
