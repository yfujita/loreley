import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import IdText from './IdText.vue'
import TimeText from './TimeText.vue'

describe('TimeText(DS 4.9)', () => {
  it('ISO 8601 を、ブラウザのローカル時刻(テストは Asia/Tokyo)の YYYY-MM-DD HH:mm で出し、<time> で意味づける', async () => {
    const { wrapper } = await mountInLayout(TimeText, {
      props: { value: '2026-11-21T01:02:03.000Z' },
    })

    const time = wrapper.find('time')
    expect(time.text()).toBe('2026-11-21 10:02')
    expect(time.attributes('datetime')).toBe('2026-11-21T01:02:03.000Z')
  })

  it('秒が必要な箇所だけ :ss(with-seconds)', async () => {
    const { wrapper } = await mountInLayout(TimeText, {
      props: { value: '2026-11-21T01:02:03.000Z', withSeconds: true },
    })

    expect(wrapper.text()).toBe('2026-11-21 10:02:03')
  })

  it('ミリ秒(Query の dataUpdatedAt)と Date も受ける', async () => {
    const at = Date.parse('2026-11-21T01:02:03.000Z')
    const { wrapper: fromNumber } = await mountInLayout(TimeText, { props: { value: at } })
    const { wrapper: fromDate } = await mountInLayout(TimeText, { props: { value: new Date(at) } })

    expect(fromNumber.text()).toBe('2026-11-21 10:02')
    expect(fromDate.text()).toBe('2026-11-21 10:02')
  })

  it.each([null, undefined, '', 'not a date', 0])(
    '値がない・日時として読めない(%j)ときは「—」を出し、読み上げ用の「なし」を添える',
    async (value) => {
      const { wrapper } = await mountInLayout(TimeText, { props: { value } })

      expect(wrapper.find('time').exists()).toBe(false)
      expect(wrapper.text()).toBe('—なし')
      expect(wrapper.find('.sr-only').text()).toBe('なし')
    },
  )

  it('読み上げ用の文言を選べる', async () => {
    const { wrapper } = await mountInLayout(TimeText, {
      props: { value: null, emptyLabel: '未実行' },
    })

    expect(wrapper.find('.sr-only').text()).toBe('未実行')
  })
})

describe('IdText(DS 2.2)', () => {
  it('識別子を等幅のクラスで出す', async () => {
    const { wrapper } = await mountInLayout(IdText, { props: { value: 'demo-handbook' } })

    expect(wrapper.text()).toBe('demo-handbook')
    expect(wrapper.find('.text-id').text()).toBe('demo-handbook')
  })
})
