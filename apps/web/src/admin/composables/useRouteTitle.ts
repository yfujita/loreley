// 現在の route の見出し(`meta.title`。動的な見出しも解決する)。ページの `h1` に渡す。
import { computed, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'

import { resolveRouteTitle } from './routeTitle'

export function useRouteTitle(): ComputedRef<string> {
  const route = useRoute()
  return computed(() => resolveRouteTitle(route))
}
