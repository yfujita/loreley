// 起動の順序(E 4.1): configureApiClient → Vuetify → Router → Vue Query → マウント。
// `configureApiClient()` は、`admin/app` の起動より前に 1 回だけ呼ぶ。
import { describe, expect, it, vi } from 'vitest'

const order: string[] = []

vi.mock('vuetify/styles', () => {
  order.push('vuetify/styles')
  return {}
})
vi.mock('@/shared/theme/global.css', () => {
  order.push('global.css')
  return {}
})
vi.mock('@/admin/api', () => ({ configureApiClient: () => order.push('configureApiClient') }))
vi.mock('@/admin/app/App.vue', () => ({ default: { name: 'App' } }))
vi.mock('@/admin/app/setupVuetify', () => ({
  setupVuetify: () => {
    order.push('setupVuetify')
    return { name: 'vuetify' }
  },
}))
vi.mock('@/admin/app/setupRouter', () => ({ setupRouter: () => order.push('setupRouter') }))
vi.mock('@/admin/app/setupQuery', () => ({ setupQuery: () => order.push('setupQuery') }))
vi.mock('vue', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue')>()),
  createApp: () => ({
    use: () => order.push('use(vuetify)'),
    mount: (selector: string) => order.push(`mount(${selector})`),
  }),
}))

describe('main.ts(起動の組み立て。E 4.1)', () => {
  it('API クライアントの設定を最初に 1 回だけ行い、Vuetify → Router → Vue Query → マウントの順に組み立てる', async () => {
    await import('./main')

    expect(order).toEqual([
      // CSS: vuetify/styles の後に global.css(Vuetify の後に読む必要がある)
      'vuetify/styles',
      'global.css',
      'configureApiClient',
      'setupVuetify',
      'use(vuetify)',
      'setupRouter',
      'setupQuery',
      'mount(#app)',
    ])
  })
})
