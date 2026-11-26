import { test as base } from '@playwright/test'

import { guardUnmockedApi } from './unmockedApi'

export { expect } from '@playwright/test'

/** E2E 用の `test`。モックしていない `/api/` への要求があれば、テストを失敗させる(E 10.2)。 */
export const test = base.extend({
  page: async ({ page }, use) => {
    const guard = await guardUnmockedApi(page)

    await use(page)

    guard.assertNone()
  },
})
