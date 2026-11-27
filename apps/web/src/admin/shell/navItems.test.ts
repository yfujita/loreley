import { describe, expect, it, vi } from 'vitest'
import type { RouteMeta } from 'vue-router'

import { routes } from '@/admin/router/routes'
import { navGroups } from '@/admin/router/navGroups'

import { buildNavGroups, navItemCurrent, type NavGroupDefinition } from './navItems'

type NavRoute = { name: string; meta: Partial<RouteMeta> }
const route = (name: string, nav?: RouteMeta['nav'], extra: Partial<RouteMeta> = {}): NavRoute => ({
  name,
  meta: { title: name, template: 'list', ...(nav && { nav }), ...extra },
})
const nav = (label: string, group: string, order: number): RouteMeta['nav'] => ({
  label,
  icon: `icon-${label}`,
  group,
  order,
})
const asRoutes = (list: NavRoute[]) => list as unknown as Parameters<typeof buildNavGroups>[0]
const OPTIONS = { isFeatureEnabled: () => true }

const GROUPS: NavGroupDefinition[] = [
  { id: 'overview', label: '全体' },
  { id: 'operate', label: '運用' },
  { id: 'inspect', label: '確認' },
]

describe('buildNavGroups(DS 5.3: meta.nav から抽出し、グループの順 → nav.order に並べる)', () => {
  it('meta.nav を持つ route だけを抽出する(詳細・編集などは nav を持たず出ない)', () => {
    const groups = buildNavGroups(
      asRoutes([
        route('sources', nav('データソース', 'operate', 0)),
        route('source-detail'),
        route('source-edit'),
      ]),
      GROUPS,
      OPTIONS,
    )

    expect(groups.flatMap((group) => group.items.map((item) => item.routeName))).toEqual([
      'sources',
    ])
  })

  it('グループは navGroups の順(定義順。route の定義順ではない)、グループ内は nav.order の昇順', () => {
    const groups = buildNavGroups(
      asRoutes([
        route('opensearch', nav('OpenSearch', 'inspect', 1)),
        route('jobs', nav('ジョブ', 'operate', 1)),
        route('dashboard', nav('ダッシュボード', 'overview', 0)),
        route('documents', nav('文書の確認', 'inspect', 0)),
        route('sources', nav('データソース', 'operate', 0)),
      ]),
      GROUPS,
      OPTIONS,
    )

    expect(groups.map((group) => [group.id, group.items.map((item) => item.label)])).toEqual([
      ['overview', ['ダッシュボード']],
      ['operate', ['データソース', 'ジョブ']],
      ['inspect', ['文書の確認', 'OpenSearch']],
    ])
  })

  it('項目のないグループは返さない(区切り線を余分に出さない)', () => {
    const groups = buildNavGroups(
      asRoutes([route('sources', nav('データソース', 'operate', 0))]),
      GROUPS,
      OPTIONS,
    )

    expect(groups.map((group) => group.id)).toEqual(['operate'])
  })

  it('未定義のグループ ID の項目は、通知してから、末尾のグループとして出す', () => {
    const onUnknownGroup = vi.fn()

    const groups = buildNavGroups(
      asRoutes([
        route('x', nav('X', 'reindex-group', 0)),
        route('sources', nav('データソース', 'operate', 0)),
      ]),
      GROUPS,
      { ...OPTIONS, onUnknownGroup },
    )

    expect(onUnknownGroup).toHaveBeenCalledWith('reindex-group')
    expect(groups.map((group) => group.id)).toEqual(['operate', 'reindex-group'])
  })

  it('新しい画面は route を足すだけで項目が出る(将来機能。ダミー項目は置かない)', () => {
    const groups = buildNavGroups(
      asRoutes([
        route('sources', nav('データソース', 'operate', 0)),
        route('reindex', nav('再インデックス', 'operate', 2)),
      ]),
      GROUPS,
      OPTIONS,
    )

    expect(groups[0]?.items.map((item) => item.label)).toEqual(['データソース', '再インデックス'])
  })

  it('featureFlag を持つ route は、フラグが有効なときだけ出す(評価はナビだけ)', () => {
    const flagged = [
      route('beta', nav('ベータ', 'operate', 0), { featureFlag: 'beta' }),
      route('sources', nav('データソース', 'operate', 1)),
    ]

    const off = buildNavGroups(asRoutes(flagged), GROUPS, { isFeatureEnabled: () => false })
    const on = buildNavGroups(asRoutes(flagged), GROUPS, {
      isFeatureEnabled: (flag) => flag === 'beta',
    })

    expect(off[0]?.items.map((item) => item.label)).toEqual(['データソース'])
    expect(on[0]?.items.map((item) => item.label)).toEqual(['ベータ', 'データソース'])
  })

  it('name のない route は項目にしない', () => {
    const groups = buildNavGroups(
      asRoutes([
        { name: undefined as unknown as string, meta: { nav: nav('名前なし', 'operate', 0) } },
      ]),
      GROUPS,
      OPTIONS,
    )

    expect(groups).toEqual([])
  })

  it('本番の route 定義と navGroups から作ると、DS 5.1・admin-view 3 章の並び(D1 | S1・J1 | X1・O1)になる', () => {
    const groups = buildNavGroups(asRoutes(routes as unknown as NavRoute[]), navGroups, OPTIONS)

    expect(groups.map((group) => group.items.map((item) => item.label))).toEqual([
      ['ダッシュボード'],
      ['データソース', 'ジョブ'],
      ['文書の確認', 'OpenSearch'],
    ])
    expect(groups.flatMap((group) => group.items.map((item) => item.routeName))).toEqual([
      'dashboard',
      'sources',
      'jobs',
      'documents',
      'opensearch',
    ])
  })
})

describe('navItemCurrent(DS 5.3: 現在のルートとその子ルートで、親のナビ項目を強調する)', () => {
  const asParents = routes as unknown as Parameters<typeof navItemCurrent>[2]

  it.each([
    ['sources', 'sources', 'page'],
    ['sources', 'source-detail', 'ancestor'],
    ['sources', 'source-new', 'ancestor'],
    // 編集は、親の詳細のさらに親(2 段)
    ['sources', 'source-edit', 'ancestor'],
    ['jobs', 'job-detail', 'ancestor'],
    ['jobs', 'jobs', 'page'],
    ['dashboard', 'dashboard', 'page'],
  ])('ナビ項目 %s は、現在の route が %s のとき %s', (item, current, expected) => {
    expect(navItemCurrent(item, current, asParents)).toBe(expected)
  })

  it.each([
    ['jobs', 'source-detail'],
    ['sources', 'jobs'],
    ['sources', 'not-found'],
    ['dashboard', 'sources'],
  ])('ナビ項目 %s は、現在の route が %s のときは強調しない', (item, current) => {
    expect(navItemCurrent(item, current, asParents)).toBeNull()
  })

  it('現在の route に name がない(null・undefined)ときは強調しない。親が循環しても止まる', () => {
    expect(navItemCurrent('sources', null, asParents)).toBeNull()
    expect(navItemCurrent('sources', undefined, asParents)).toBeNull()
    const cyclic = [
      { name: 'a', meta: { parent: 'b' } },
      { name: 'b', meta: { parent: 'a' } },
    ] as unknown as Parameters<typeof navItemCurrent>[2]
    expect(navItemCurrent('zzz', 'a', cyclic)).toBeNull()
  })
})
