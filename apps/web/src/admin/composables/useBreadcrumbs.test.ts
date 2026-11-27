import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter, type RouteRecordRaw } from 'vue-router'

import { routes } from '@/admin/router/routes'
import { ROUTE_NAMES } from '@/admin/lib/routeNames'

import { runComposable } from '../../../tests/support/composableTesting'
import { buildBreadcrumbs, useBreadcrumbs } from './useBreadcrumbs'

async function breadcrumbsAt(path: string) {
  const { result, router } = await runComposable(() => useBreadcrumbs(), {
    routes,
    initialPath: path,
  })
  return { items: () => result.value, router }
}

describe('useBreadcrumbs(DS 5.2。FMOD-U-10)', () => {
  it('トップレベルの一覧・ダッシュボード(親なし)は、パンくずを出さない', async () => {
    for (const path of ['/', '/sources', '/jobs', '/documents', '/opensearch']) {
      expect((await breadcrumbsAt(path)).items()).toEqual([])
    }
  })

  it('データソース詳細(S2): 「データソース › 識別子」。末尾は現在のページ(リンクにしない)', async () => {
    const { items } = await breadcrumbsAt('/sources/demo-handbook')

    expect(items()).toEqual([
      { title: 'データソース', to: '/sources' },
      { title: 'demo-handbook', to: null },
    ])
  })

  it('登録(S3): 「データソース › データソースを登録」(/sources/new は識別子ではない)', async () => {
    const { items } = await breadcrumbsAt('/sources/new')

    expect(items()).toEqual([
      { title: 'データソース', to: '/sources' },
      { title: 'データソースを登録', to: null },
    ])
  })

  it('編集(S4): 親の S2 に、現在の params(sourceId)を引き継いだ URL を作る「データソース › 識別子 › 編集」', async () => {
    const { items } = await breadcrumbsAt('/sources/demo-handbook/edit')

    expect(items()).toEqual([
      { title: 'データソース', to: '/sources' },
      { title: 'demo-handbook', to: '/sources/demo-handbook' },
      { title: '編集', to: null },
    ])
  })

  it('識別子に URL で特別な文字を含んでも、エンコードされた URL と、復号された見出しになる', async () => {
    const { items } = await breadcrumbsAt('/sources/a%2Fb%3F/edit')

    expect(items()).toEqual([
      { title: 'データソース', to: '/sources' },
      { title: 'a/b?', to: '/sources/a%2Fb%3F' },
      { title: '編集', to: null },
    ])
  })

  it('ジョブ詳細(J2): 「ジョブ › ジョブ ID」。親(一覧)には不要な params(jobId)を渡さない', async () => {
    const { items } = await breadcrumbsAt('/jobs/job-0001')

    expect(items()).toEqual([
      { title: 'ジョブ', to: '/jobs' },
      { title: 'job-0001', to: null },
    ])
  })

  it('不要な params を親の URL 解決に渡さない(vue-router の「Discarded invalid param」警告を出さない)', async () => {
    const warnings: string[] = []
    const original = console.warn
    console.warn = (...args: unknown[]) => warnings.push(args.join(' '))
    try {
      await breadcrumbsAt('/jobs/job-0001')
      await breadcrumbsAt('/sources/demo-handbook/edit')
    } finally {
      console.warn = original
    }

    expect(warnings.filter((w) => w.includes('Discarded invalid param'))).toEqual([])
  })

  it('SPA 内の 404 は親がなく、パンくずを出さない', async () => {
    const { items } = await breadcrumbsAt('/no/such/page')

    expect(items()).toEqual([])
  })

  it('同じコンポーネントのまま遷移すると、項目が追従する(S2 → S4)', async () => {
    const { items, router } = await breadcrumbsAt('/sources/a')
    expect(items().map((item) => item.title)).toEqual(['データソース', 'a'])

    await router.push({ name: ROUTE_NAMES.sourceEdit, params: { sourceId: 'b' } })
    await nextTick()

    expect(items().map((item) => item.title)).toEqual(['データソース', 'b', '編集'])
  })
})

describe('buildBreadcrumbs の防御', () => {
  const EMPTY = { render: () => null }

  it('親が見つからない定義でも落ちない(見つかった祖先までと、現在のページ)', async () => {
    const odd: RouteRecordRaw[] = [
      {
        path: '/x',
        name: 'x',
        component: EMPTY,
        // meta.parent は RouteName の型だが、定義ミスの防御を確かめる
        meta: { title: 'X', template: 'list', parent: 'ghost' as never },
      },
    ]
    const router = createRouter({ history: createMemoryHistory(), routes: odd })
    await router.push('/x')

    expect(buildBreadcrumbs(router, router.currentRoute.value)).toEqual([{ title: 'X', to: null }])
  })

  it('親が循環していても止まる', async () => {
    const cyclic: RouteRecordRaw[] = [
      {
        path: '/a',
        name: 'a',
        component: EMPTY,
        meta: { title: 'A', template: 'list', parent: 'b' as never },
      },
      {
        path: '/b',
        name: 'b',
        component: EMPTY,
        meta: { title: 'B', template: 'list', parent: 'a' as never },
      },
    ]
    const router = createRouter({ history: createMemoryHistory(), routes: cyclic })
    await router.push('/a')

    const items = buildBreadcrumbs(router, router.currentRoute.value)

    expect(items.map((item) => item.title)).toEqual(['A', 'B', 'A'].slice(0, items.length))
    expect(items.length).toBeLessThanOrEqual(3)
    expect(items[items.length - 1]).toEqual({ title: 'A', to: null })
  })
})
