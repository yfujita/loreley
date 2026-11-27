import { describe, expect, it } from 'vitest'
import { h } from 'vue'

import { mountInLayout } from '../../../../tests/support/mount'
import KeyValueList, { type KeyValueItem } from './KeyValueList.vue'

const ITEMS: KeyValueItem[] = [
  { key: 'id', label: '識別子', value: 'demo-handbook' },
  { key: 'cron', label: '実行周期', value: '0 3 * * *', note: 'Asia/Tokyo' },
  { key: 'desc', label: '説明', value: null },
  { key: 'empty', label: '備考', value: '', emptyLabel: 'なし' },
]

describe('KeyValueList(DS 4.4)', () => {
  it('<dl> に、項目名(dt)と値(dd)を 1 対 1 で並べる', async () => {
    const { wrapper } = await mountInLayout(KeyValueList, { props: { items: ITEMS } })

    expect(wrapper.find('dl').exists()).toBe(true)
    expect(wrapper.findAll('dt').map((dt) => dt.text())).toEqual([
      '識別子',
      '実行周期',
      '説明',
      '備考',
    ])
    expect(wrapper.findAll('dd')).toHaveLength(4)
    expect(wrapper.findAll('dd')[0]?.text()).toBe('demo-handbook')
  })

  it('補足(タイムゾーンなど)は値の下に添える', async () => {
    const { wrapper } = await mountInLayout(KeyValueList, { props: { items: ITEMS } })

    const dd = wrapper.findAll('dd')[1]
    expect(dd?.text()).toContain('0 3 * * *')
    expect(dd?.find('.key-value-list__note').text()).toBe('Asia/Tokyo')
  })

  it('値がない(null・空文字)項目は「—」を出し、読み上げ用の「未設定」(または指定の文言)を視覚的に隠して添える', async () => {
    const { wrapper } = await mountInLayout(KeyValueList, { props: { items: ITEMS } })

    const nullDd = wrapper.findAll('dd')[2]
    const emptyDd = wrapper.findAll('dd')[3]
    expect(nullDd?.text()).toBe('—(未設定)')
    expect(nullDd?.find('.sr-only').text()).toBe('(未設定)')
    expect(emptyDd?.find('.sr-only').text()).toBe('(なし)')
  })

  it('value-<key> のスロットで、値の見た目(識別子・状態タグなど)を差し替えられる', async () => {
    const { wrapper } = await mountInLayout(KeyValueList, {
      props: { items: ITEMS },
      slots: { 'value-id': () => h('code', { class: 'custom' }, 'CUSTOM') },
    })

    expect(wrapper.findAll('dd')[0]?.find('code.custom').text()).toBe('CUSTOM')
    // スロットを渡さない項目は既定の表示
    expect(wrapper.findAll('dd')[1]?.text()).toContain('0 3 * * *')
  })
})
