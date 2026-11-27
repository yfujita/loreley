import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { resolveRouteTitle } from './routeTitle'

const EMPTY = { render: () => null }

async function resolveAt(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/sources', component: EMPTY, meta: { title: 'データソース', template: 'list' } },
      {
        path: '/sources/:sourceId',
        component: EMPTY,
        // 動的な見出し(識別子)は route を受ける関数(I-83)
        meta: { title: (route) => String(route.params.sourceId), template: 'detail' },
      },
    ],
  })
  await router.push(path)
  return router.currentRoute.value
}

describe('resolveRouteTitle(FMOD-U-10。meta.title の解決)', () => {
  it('文字列の title はそのまま返す', async () => {
    expect(resolveRouteTitle(await resolveAt('/sources'))).toBe('データソース')
  })

  it('関数の title は、route(params)を渡して解決する。復号済みの識別子になる', async () => {
    expect(resolveRouteTitle(await resolveAt('/sources/demo-handbook'))).toBe('demo-handbook')
    expect(resolveRouteTitle(await resolveAt('/sources/%E6%97%A5%E6%9C%AC%20a%2Fb'))).toBe(
      '日本 a/b',
    )
  })
})
