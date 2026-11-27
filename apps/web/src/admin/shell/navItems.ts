// ナビ項目の抽出と並び(DS 5.3・E 4.2)。**ナビ項目の定義は route `meta.nav` にだけ持つ**(別のナビ定義ファイルを持たない)。
// `router.getRoutes()` から `meta.nav` を持つ route を取り出し、「グループの順(`navGroups`)→ `nav.order`」に並べる。
// 純関数にして、Vue・Router なしでテストできるようにする。
import type { RouteRecordNormalized } from 'vue-router'

import type { RouteName } from '@/admin/lib/routeNames'

/** `router/navGroups.ts` の 1 行。型は構造で受ける(`shell` は `router` を import しない。層の向き)。 */
export type NavGroupDefinition = { readonly id: string; readonly label: string }

export type NavItem = {
  routeName: RouteName
  label: string
  icon: string
  order: number
}

export type NavGroup = {
  id: string
  label: string
  items: NavItem[]
}

type NavRoute = Pick<RouteRecordNormalized, 'name' | 'meta'>

export type BuildNavOptions = {
  /** `meta.featureFlag` を持つ route を出すか。評価はナビ(SideNav)だけ(E 4.5。I-89) */
  isFeatureEnabled: (flag: string) => boolean
  /** 未定義のグループ ID を見つけたときの通知(開発時の警告) */
  onUnknownGroup?: (groupId: string) => void
}

/**
 * ナビのグループと項目を作る。項目のないグループは返さない。
 * 未定義のグループ ID の項目は、開発時に警告し、末尾のグループとして出す(DS 5.3)。
 */
export function buildNavGroups(
  routes: readonly NavRoute[],
  groups: readonly NavGroupDefinition[],
  options: BuildNavOptions,
): NavGroup[] {
  const itemsByGroup = new Map<string, NavItem[]>()
  for (const route of routes) {
    const nav = route.meta.nav
    if (nav === undefined || typeof route.name !== 'string') continue
    if (route.meta.featureFlag !== undefined && !options.isFeatureEnabled(route.meta.featureFlag)) {
      continue
    }
    const items = itemsByGroup.get(nav.group) ?? []
    items.push({
      routeName: route.name as RouteName,
      label: nav.label,
      icon: nav.icon,
      order: nav.order,
    })
    itemsByGroup.set(nav.group, items)
  }

  const knownIds = new Set(groups.map((group) => group.id))
  const unknownGroups: NavGroupDefinition[] = []
  for (const groupId of itemsByGroup.keys()) {
    if (knownIds.has(groupId)) continue
    options.onUnknownGroup?.(groupId)
    unknownGroups.push({ id: groupId, label: groupId })
  }

  return [...groups, ...unknownGroups]
    .map((group) => ({
      id: group.id,
      label: group.label,
      items: (itemsByGroup.get(group.id) ?? []).sort((a, b) => a.order - b.order),
    }))
    .filter((group) => group.items.length > 0)
}

type ParentRoute = Pick<RouteRecordNormalized, 'name' | 'meta'>

/**
 * 現在地の判定(DS 5.3): 現在の route か、`meta.parent` を辿った祖先のどれかがナビ項目の route なら、その項目を強調する
 * (詳細・編集の画面でも、親のナビ項目が現在地になる)。`'page'` は現在の route そのもの、`'ancestor'` は祖先。
 */
export function navItemCurrent(
  itemRouteName: string,
  currentName: string | symbol | null | undefined,
  routes: readonly ParentRoute[],
): 'page' | 'ancestor' | null {
  const byName = new Map(routes.map((route) => [route.name, route]))
  const visited = new Set<unknown>()
  let name: string | symbol | null | undefined = currentName
  let isSelf = true
  while (name !== null && name !== undefined && !visited.has(name)) {
    if (name === itemRouteName) return isSelf ? 'page' : 'ancestor'
    visited.add(name)
    name = byName.get(name)?.meta.parent
    isSelf = false
  }
  return null
}
