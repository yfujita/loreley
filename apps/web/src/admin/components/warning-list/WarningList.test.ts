import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import WarningList, { type WarningItem } from './WarningList.vue'

describe('WarningList(DS 4.11)', () => {
  it('1 項目 = 見出し(日本語の要約)・詳細・警告コード(補足)。コードを見出しにしない', async () => {
    const items: WarningItem[] = [
      {
        key: 'w1',
        title: '抽出に失敗した文書があります',
        detail: '原本の形式を確認してください。',
        code: 'extract_failed',
      },
    ]
    const { wrapper } = await mountInLayout(WarningList, { props: { items } })

    const item = wrapper.find('li')
    expect(item.find('.text-body-strong').text()).toBe('抽出に失敗した文書があります')
    expect(item.text()).toContain('原本の形式を確認してください。')
    expect(item.find('.warning-list__code').text()).toBe('extract_failed')
    expect(item.find('svg').exists()).toBe(true)
  })

  it('詳細・コードがない項目は、その行を出さない(未知のコードは見出しを「警告(コード)」にして詳細は空)', async () => {
    const { wrapper } = await mountInLayout(WarningList, {
      props: { items: [{ key: 'w', title: '警告(unknown_code)' }] },
    })

    expect(wrapper.findAll('li p')).toHaveLength(1)
    expect(wrapper.find('.warning-list__code').exists()).toBe(false)
  })

  it('項目が 0 件なら何も描かない(件数が 0 の警告カードは出さない)', async () => {
    const { wrapper } = await mountInLayout(WarningList, { props: { items: [] } })

    expect(wrapper.find('ul').exists()).toBe(false)
  })

  it('複数の項目を、渡された順に並べる', async () => {
    const { wrapper } = await mountInLayout(WarningList, {
      props: {
        items: [
          { key: 'a', title: 'A' },
          { key: 'b', title: 'B' },
        ],
      },
    })

    expect(wrapper.findAll('li').map((li) => li.text())).toEqual(['A', 'B'])
  })
})
