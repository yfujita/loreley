// route の `meta.title`(文字列、または route を受ける関数。I-83)の解決(FMOD-U-10)。
// ページ見出し・パンくず・`document.title` が同じ規則を使う。
import type { RouteLocationNormalized, RouteLocationNormalizedLoaded } from 'vue-router'

/** 動的な見出しの関数が受ける route。ガード(`afterEach`)の `to` と、`useRoute()` の値のどちらも渡せる。 */
export type RouteTitleSource = Pick<
  RouteLocationNormalizedLoaded | RouteLocationNormalized,
  'name' | 'path' | 'params' | 'query' | 'hash' | 'fullPath' | 'meta'
>

export function resolveRouteTitle(route: RouteTitleSource): string {
  const title = route.meta.title
  return typeof title === 'function' ? title(route) : title
}
