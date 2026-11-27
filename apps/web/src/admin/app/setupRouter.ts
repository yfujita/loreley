// Router の組み立て(E 4.1 の 2)。route 定義・ガード・スクロールは `admin/router`。
import type { App } from 'vue'

import { createAdminRouter } from '@/admin/router'

export function setupRouter(app: App) {
  const router = createAdminRouter()
  app.use(router)
  return router
}
