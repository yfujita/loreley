// 遷移後の処理(E 4.5・DS 8): `document.title` の更新と、フォーカスの `h1` への移動。
// MVP は認証なし・`featureFlag` はルートではなくナビで評価するので、`beforeEach` のガードは置かない。
import { nextTick } from 'vue'
import { START_LOCATION, type Router } from 'vue-router'

import { formatDocumentTitle } from '@/admin/composables/useDocumentTitle'
import { resolveRouteTitle } from '@/admin/composables/routeTitle'

import { isSamePage } from './samePage'

/** 遷移の完了後に、`document.title` を「title - Loreley 管理」にし、パスが変わったときだけ `h1` にフォーカスする。 */
export function installNavigationEffects(router: Router): void {
  router.afterEach((to, from, failure) => {
    if (failure) return

    document.title = formatDocumentTitle(resolveRouteTitle(to))

    // 最初の表示(`START_LOCATION` から)では動かさない: 読み込み直後はブラウザの既定の位置(スキップリンクが先頭)に任せる。
    // クエリだけの変化(ページ・タブ・並べ替え)でもフォーカスを動かさない。
    if (from === START_LOCATION || isSamePage(to, from)) return

    void nextTick(() => {
      document.querySelector<HTMLElement>('main h1')?.focus()
    })
  })
}
