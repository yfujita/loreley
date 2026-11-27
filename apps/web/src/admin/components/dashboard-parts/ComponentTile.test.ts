import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import ComponentTile from './ComponentTile.vue'
import type { ComponentTileModel } from './types'

const ROUTES = [
  { path: '/', component: { render: () => null } },
  { path: '/jobs', name: 'jobs', component: { render: () => null } },
]

const BASE: ComponentTileModel = {
  id: 'crawler',
  role: '文書の取得とジョブの実行',
  status: 'normal',
  detail: '応答しています · 確認 10:48:02',
  emphasized: false,
  link: null,
}

async function mountTile(overrides: Partial<ComponentTileModel> = {}) {
  const { wrapper } = await mountInLayout(ComponentTile, {
    props: { model: { ...BASE, ...overrides } },
    routes: ROUTES,
  })
  return wrapper.find('li')
}

describe('ComponentTile(DS 4.16。D1 のタイル)', () => {
  it('1 行目に名前(h3・等幅)とタグ、2 行目に役割、3 行目に補足。data-testid=d1-tile-{id}', async () => {
    const tile = await mountTile()

    expect(tile.attributes('data-testid')).toBe('d1-tile-crawler')
    expect(tile.find('h3').text()).toBe('crawler')
    expect(tile.find('h3').classes()).toContain('text-tile-name')
    expect(tile.find('.status-tag').text()).toBe('正常')
    expect(tile.findAll('p').map((p) => p.text())).toEqual([
      '文書の取得とジョブの実行',
      '応答しています · 確認 10:48:02',
    ])
  })

  it.each([
    ['normal', '正常', 'component-tile--normal'],
    ['abnormal', '異常', 'component-tile--abnormal'],
    ['undetermined', '判定不能', 'component-tile--undetermined'],
    ['not_configured', '未設定', 'component-tile--not_configured'],
  ] as const)(
    'status=%s は タグ「%s」と class(%s)。状態を文言と形でも示す',
    async (status, label, className) => {
      const tile = await mountTile({ status })

      expect(tile.find('.status-tag').text()).toBe(label)
      expect(tile.classes()).toContain(className)
      expect(tile.find('.status-tag .v-icon').exists()).toBe(true)
    },
  )

  it('補足は、emphasized のとき本文色、そうでなければ補助色(on-surface-variant)', async () => {
    const muted = await mountTile({ emphasized: false })
    const strong = await mountTile({ emphasized: true })

    expect(muted.find('.component-tile__detail').classes()).toContain('text-on-surface-variant')
    expect(strong.find('.component-tile__detail').classes()).not.toContain(
      'text-on-surface-variant',
    )
  })

  it('導線があれば末尾にリンク(route 名から URL を作る)。なければ出さない', async () => {
    const withLink = await mountTile({
      link: { label: 'ジョブの状態を確認', routeName: 'jobs' },
    })
    const withoutLink = await mountTile()

    const link = withLink.find('a')
    expect(link.text()).toBe('ジョブの状態を確認')
    expect(link.attributes('href')).toBe('/jobs')
    expect(withoutLink.find('a').exists()).toBe(false)
  })
})
