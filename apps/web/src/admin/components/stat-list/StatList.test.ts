import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import StatList, { type StatItem } from './StatList.vue'

const ROUTES = [
  { path: '/', component: { render: () => null } },
  { path: '/jobs', name: 'jobs', component: { render: () => null } },
]

describe('StatList(DS 4.10)', () => {
  it('項目名の下に値を並べる。3 桁区切り・補足は値の下', async () => {
    const items: StatItem[] = [
      { key: 'registered', label: '登録', value: 1284, note: '新規 2 · 更新 12' },
      { key: 'skipped', label: 'スキップ', value: 3 },
    ]
    const { wrapper } = await mountInLayout(StatList, { props: { items }, routes: ROUTES })

    const groups = wrapper.findAll('.stat-list__item')
    expect(groups[0]?.find('dt').text()).toBe('登録')
    expect(groups[0]?.find('dd').text()).toBe('1,284')
    expect(groups[0]?.text()).toContain('新規 2 · 更新 12')
    expect(groups[1]?.find('dd').text()).toBe('3')
  })

  it('件数が 0 でも「0」を出す(空欄にしない)', async () => {
    const { wrapper } = await mountInLayout(StatList, {
      props: { items: [{ key: 'errors', label: 'エラー', value: 0 }] },
      routes: ROUTES,
    })

    expect(wrapper.find('dd').text()).toBe('0')
  })

  it('値が取得できない(null)ときは「—」を出し、読み上げ用に「取得できません」を添える', async () => {
    const { wrapper } = await mountInLayout(StatList, {
      props: { items: [{ key: 'errors', label: 'エラー', value: null }] },
      routes: ROUTES,
    })

    expect(wrapper.find('dd').text()).toContain('—')
    expect(wrapper.find('dd .sr-only').text()).toBe('(取得できません)')
  })

  it('`to` を渡した件数は、値がリンクになる(他画面の一覧へつながる件数)。0 でもリンクにする', async () => {
    const { wrapper } = await mountInLayout(StatList, {
      props: {
        items: [
          { key: 'skipped', label: 'スキップ', value: 0, to: { name: 'jobs' } },
          { key: 'registered', label: '登録', value: 5 },
        ],
      },
      routes: ROUTES,
    })

    const link = wrapper.find('a')
    expect(link.text()).toBe('0')
    expect(link.attributes('href')).toBe('/jobs')
    expect(wrapper.findAll('a')).toHaveLength(1)
  })
})
