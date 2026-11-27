// Router の組み立て。`app/setupRouter.ts` が呼ぶ。`base` は `vite.config.ts` の `base`('/admin/')と一致する。
import { createRouter, createWebHistory, type Router, type RouterHistory } from 'vue-router'

import { installNavigationEffects } from './guards'
import { routes } from './routes'
import { scrollBehavior } from './scroll'

export { navGroups } from './navGroups'

/** `history` を渡せるのはテスト(メモリ履歴)のため。 */
export function createAdminRouter(
  history: RouterHistory = createWebHistory(import.meta.env.BASE_URL),
): Router {
  const router = createRouter({ history, routes, scrollBehavior })
  installNavigationEffects(router)
  return router
}
