import { describe, expect, it } from 'vitest'
import { createApp, h } from 'vue'

import { setupRouter } from './setupRouter'

describe('setupRouter(E 4.1 の 2)', () => {
  it('route 定義・ガード・スクロールを持つルーターを、アプリに登録して返す', () => {
    const app = createApp({ render: () => h('div') })

    const router = setupRouter(app)

    expect(router.getRoutes().map((route) => route.name)).toEqual(
      expect.arrayContaining([
        'dashboard',
        'sources',
        'source-new',
        'jobs',
        'documents',
        'opensearch',
        'not-found',
      ]),
    )
    expect(router.options.scrollBehavior).toBeTypeOf('function')
    expect(app.config.globalProperties.$router).toBe(router)
  })
})
