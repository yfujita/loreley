// TanStack Vue Query の組み立て(E 4.1 の 3)。既定値は `createAppQueryClient`(E 5.4)。
import { VueQueryPlugin } from '@tanstack/vue-query'
import type { App } from 'vue'

import { createAppQueryClient } from '@/admin/queries/queryClient'

export function setupQuery(app: App) {
  const queryClient = createAppQueryClient()
  app.use(VueQueryPlugin, { queryClient })
  return queryClient
}
