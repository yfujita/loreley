import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../../tests/support/mount'
import SummaryBand from './SummaryBand.vue'
import type { SummaryModel } from './types'

async function mountBand(model: SummaryModel) {
  const { wrapper } = await mountInLayout(SummaryBand, { props: { model } })
  return wrapper.find('[data-testid="d1-summary"]')
}

const NORMAL: SummaryModel = {
  tone: 'success',
  title: 'すべてのコンポーネントが正常です',
  items: [
    { key: 'normal', label: '正常', value: '6' },
    { key: 'abnormal', label: '異常', value: '0' },
  ],
}

describe('SummaryBand(DS 4.16。D1 の概況)', () => {
  it('1 行の文と件数行。ラベルつきの領域(aria-label=全体の状態)で、role=status ではない(自動更新を読み上げない)', async () => {
    const band = await mountBand(NORMAL)

    expect(band.attributes('aria-label')).toBe('全体の状態')
    expect(band.attributes('role')).toBeUndefined()
    expect(band.find('.summary-band__title').text()).toBe('すべてのコンポーネントが正常です')
    expect(band.findAll('.summary-band__items > span').map((el) => el.text())).toEqual([
      '正常 6',
      '異常 0',
    ])
  })

  it('名前つきの項目は「ラベル: 名前」(名前は等幅)。複数の名前は「、」で区切る', async () => {
    const band = await mountBand({
      tone: 'error',
      title: '異常のコンポーネントがあります(2 件)',
      items: [{ key: 'abnormal-names', label: '異常', names: ['crawler', 'api'] }],
    })

    expect(band.find('.summary-band__items').text()).toBe('異常: crawler、api')
    expect(band.find('.summary-band__name').text()).toBe('crawler、api')
  })

  it('値のない項目はラベルだけ', async () => {
    const band = await mountBand({
      tone: 'warning',
      title: 't',
      items: [{ key: 'x', label: '前回の構成と同じ' }],
    })

    expect(band.find('.summary-band__items').text()).toBe('前回の構成と同じ')
  })

  it.each([
    ['success', 'summary-band--success'],
    ['error', 'summary-band--error'],
    ['warning', 'summary-band--warning'],
  ] as const)('%s は意味色の class(%s)。アイコンの形でも区別する', async (tone, className) => {
    const band = await mountBand({ ...NORMAL, tone })

    expect(band.classes()).toContain(className)
    expect(band.find('.v-icon').exists()).toBe(true)
  })

  it('アイコンは tone ごとに別の形(円・八角形・疑問符。色だけにしない)', async () => {
    const icons = await Promise.all(
      (['success', 'error', 'warning'] as const).map(async (tone) =>
        (await mountBand({ ...NORMAL, tone })).find('.v-icon').html(),
      ),
    )

    expect(new Set(icons).size).toBe(3)
  })
})
