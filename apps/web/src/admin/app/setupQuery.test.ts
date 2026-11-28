import { describe, expect, it } from 'vitest'
import { createApp, h } from 'vue'

import { setupQuery } from './setupQuery'

describe('setupQuery(E 4.1 の 3)', () => {
  it('アプリの QueryClient(既定値は E 5.4: マウント時に再取得・フォーカスでは再取得しない・書き込みは再送しない)を作り、アプリに登録する', () => {
    const app = createApp({ render: () => h('div') })

    const queryClient = setupQuery(app)

    const defaults = queryClient.getDefaultOptions()
    expect(defaults.queries).toMatchObject({
      staleTime: 0,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
      networkMode: 'always',
    })
    expect(defaults.mutations).toMatchObject({ retry: 0, networkMode: 'always' })
    queryClient.clear()
  })
})
