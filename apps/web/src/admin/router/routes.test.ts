import { describe, expect, it } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { ROUTE_NAMES } from '@/admin/lib/routeNames'
import {
  mdiDatabaseOutline,
  mdiFileSearchOutline,
  mdiPlaylistCheck,
  mdiServer,
  mdiViewDashboardOutline,
} from '@/shared/theme/icons'

import { createAdminRouter, navGroups } from './index'
import { routes } from './routes'

/** admin-view 4.2「route meta の一覧」の表(正)。実装がこの表からずれたら落ちる。 */
const SPEC = [
  {
    name: 'dashboard',
    path: '/',
    title: 'ダッシュボード',
    template: 'dashboard',
    parent: undefined,
  },
  { name: 'sources', path: '/sources', title: 'データソース', template: 'list', parent: undefined },
  {
    name: 'source-new',
    path: '/sources/new',
    title: 'データソースを登録',
    template: 'form',
    parent: 'sources',
  },
  {
    name: 'source-detail',
    path: '/sources/:sourceId',
    title: null,
    template: 'detail',
    parent: 'sources',
  },
  {
    name: 'source-edit',
    path: '/sources/:sourceId/edit',
    title: '編集',
    template: 'form',
    parent: 'source-detail',
  },
  { name: 'jobs', path: '/jobs', title: 'ジョブ', template: 'list', parent: undefined },
  { name: 'job-detail', path: '/jobs/:jobId', title: null, template: 'detail', parent: 'jobs' },
  {
    name: 'documents',
    path: '/documents',
    title: '文書の確認',
    template: 'list',
    parent: undefined,
  },
  {
    name: 'opensearch',
    path: '/opensearch',
    title: 'OpenSearch',
    template: 'dashboard',
    parent: undefined,
  },
  {
    name: 'not-found',
    path: '/:pathMatch(.*)*',
    title: 'ページが見つかりません',
    template: 'list',
    parent: undefined,
  },
] as const

describe('routes(admin-view 4.2 の表のとおり)', () => {
  it('name・path・template・parent が表と一致し、定義の順序も表のとおり', () => {
    expect(
      routes.map((route) => ({
        name: route.name,
        path: route.path,
        template: route.meta?.template,
        parent: route.meta?.parent,
      })),
    ).toEqual(
      [...SPEC].map(({ name, path, template, parent }) => ({ name, path, template, parent })),
    )
  })

  it('title: 固定の見出しは表のとおり。S2・J2 は識別子を見出しにする関数', () => {
    for (const spec of SPEC) {
      const title = routes.find((route) => route.name === spec.name)?.meta?.title
      if (spec.title === null) expect(typeof title).toBe('function')
      else expect(title).toBe(spec.title)
    }
  })

  it('route 名は lib/routeNames の定数と一致する(features が routes.ts を import せずに遷移できる)', () => {
    expect(routes.map((route) => route.name).sort()).toEqual(Object.values(ROUTE_NAMES).sort())
  })

  it('/sources/new は /sources/:sourceId より先に定義する(new を識別子と取り違えない)', async () => {
    const router = createAdminRouter(createMemoryHistory())

    await router.push('/sources/new')

    expect(router.currentRoute.value.name).toBe('source-new')
    await router.push('/sources/newsletter')
    expect(router.currentRoute.value.name).toBe('source-detail')
  })

  it('ナビに出す route は D1・S1・J1・X1・O1 だけ(S2〜S4・J2・404 は nav を持たない)。ダミー項目なし', () => {
    const withNav = routes.filter((route) => route.meta?.nav !== undefined).map((r) => r.name)

    expect(withNav).toEqual(['dashboard', 'sources', 'jobs', 'documents', 'opensearch'])
  })

  it('nav のラベル・アイコン・グループ・順序は admin-view 3 章・4.2 のとおり', () => {
    const navOf = (name: string) => routes.find((route) => route.name === name)?.meta?.nav

    expect(navOf('dashboard')).toEqual({
      label: 'ダッシュボード',
      icon: mdiViewDashboardOutline,
      group: 'overview',
      order: 0,
    })
    expect(navOf('sources')).toEqual({
      label: 'データソース',
      icon: mdiDatabaseOutline,
      group: 'operate',
      order: 0,
    })
    expect(navOf('jobs')).toEqual({
      label: 'ジョブ',
      icon: mdiPlaylistCheck,
      group: 'operate',
      order: 1,
    })
    expect(navOf('documents')).toEqual({
      label: '文書の確認',
      icon: mdiFileSearchOutline,
      group: 'inspect',
      order: 0,
    })
    expect(navOf('opensearch')).toEqual({
      label: 'OpenSearch',
      icon: mdiServer,
      group: 'inspect',
      order: 1,
    })
  })

  it('nav.group はすべて navGroups(overview・operate・inspect)に定義がある', () => {
    const groupIds = new Set<string>(navGroups.map((group) => group.id))

    for (const route of routes) {
      if (route.meta?.nav !== undefined) expect(groupIds.has(route.meta.nav.group)).toBe(true)
    }
    expect(navGroups.map((group) => group.id)).toEqual(['overview', 'operate', 'inspect'])
  })

  it('meta.parent は、すべて実在する route 名を指す', () => {
    const names = new Set(routes.map((route) => route.name))

    for (const route of routes) {
      if (route.meta?.parent !== undefined) expect(names.has(route.meta.parent)).toBe(true)
    }
  })

  it('MVP で featureFlag を持つ route はない(評価はナビだけ。E 4.5)', () => {
    expect(routes.some((route) => route.meta?.featureFlag !== undefined)).toBe(false)
  })

  it('すべての route が開く。未定義のパスは 404 の route になる', async () => {
    const router = createAdminRouter(createMemoryHistory())

    const cases: [string, string][] = [
      ['/', 'dashboard'],
      ['/sources', 'sources'],
      ['/sources/new', 'source-new'],
      ['/sources/demo-handbook', 'source-detail'],
      ['/sources/demo-handbook/edit', 'source-edit'],
      ['/jobs', 'jobs'],
      ['/jobs/job-0001', 'job-detail'],
      ['/documents', 'documents'],
      ['/opensearch', 'opensearch'],
      ['/no/such/page', 'not-found'],
      ['/sources/a/b/c', 'not-found'],
    ]
    for (const [path, name] of cases) {
      await router.push(path)
      expect(router.currentRoute.value.name, path).toBe(name)
    }
  })
})
