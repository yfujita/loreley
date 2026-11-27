// 「同じ画面か」の判定。route の `name` と `params`(パス)が同じで、クエリ・ハッシュだけが違う遷移は同じ画面とみなす。
// 遷移後のフォーカス移動(guards.ts)とスクロール(scroll.ts)が使う(E 4.5)。
import type { RouteLocationNormalized } from 'vue-router'

function sameParams(a: RouteLocationNormalized['params'], b: RouteLocationNormalized['params']) {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)])
  return [...keys].every((key) => String(a[key]) === String(b[key]))
}

export function isSamePage(to: RouteLocationNormalized, from: RouteLocationNormalized): boolean {
  return to.name === from.name && sameParams(to.params, from.params)
}
