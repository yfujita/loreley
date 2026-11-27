import { describe, expect, it } from 'vitest'

import { mountInLayout } from '../../../tests/support/mount'
import StateBlock from './StateBlock.vue'

describe('StateBlock(DS 4.5)', () => {
  it('読み込み中: aria-busy・視覚的に隠した「読み込み中」(role=status)・スケルトンの行', async () => {
    const { wrapper } = await mountInLayout(StateBlock, { props: { kind: 'loading', rows: 4 } })

    expect(wrapper.find('.state-block-loading').attributes('aria-busy')).toBe('true')
    const status = wrapper.find('[role="status"]')
    expect(status.find('.sr-only').text()).toBe('読み込み中')
    expect(wrapper.findAll('.skeleton-line')).toHaveLength(4)
  })

  it('読み込み中の文言は差し替えられる(「データソース一覧を読み込み中」)', async () => {
    const { wrapper } = await mountInLayout(StateBlock, {
      props: { kind: 'loading', loadingLabel: 'データソース一覧を読み込み中' },
    })

    expect(wrapper.find('.sr-only').text()).toBe('データソース一覧を読み込み中')
  })

  it('エラー(データなし): role=alert・見出し・原因と次の行動・補助文字・操作のスロット', async () => {
    const { wrapper } = await mountInLayout(StateBlock, {
      props: {
        kind: 'error',
        title: 'データソースを取得できません',
        message: 'API に接続できませんでした。',
        note: '試行時刻 2026-11-27 10:00:00',
      },
      slots: { default: () => '再試行' },
    })

    expect(wrapper.find('.state-block').attributes('role')).toBe('alert')
    expect(wrapper.find('h2').text()).toBe('データソースを取得できません')
    expect(wrapper.text()).toContain('API に接続できませんでした。')
    expect(wrapper.text()).toContain('試行時刻 2026-11-27 10:00:00')
    expect(wrapper.text()).toContain('再試行')
    expect(wrapper.find('.state-block').classes()).toContain('state-block--error')
  })

  it('空・見つかりません: role=alert を付けない(静的な状態)。見つかりませんは、エラーと同じ赤系のアイコン枠', async () => {
    const { wrapper: empty } = await mountInLayout(StateBlock, {
      props: { kind: 'empty', title: 'データソースがまだありません' },
    })
    const { wrapper: notfound } = await mountInLayout(StateBlock, {
      props: { kind: 'notfound', title: 'データソースが見つかりません' },
    })

    expect(empty.find('.state-block').attributes('role')).toBeUndefined()
    expect(empty.find('.state-block').classes()).not.toContain('state-block--error')
    expect(notfound.find('.state-block').attributes('role')).toBeUndefined()
    expect(notfound.find('.state-block').classes()).toContain('state-block--error')
  })

  it('見出しのレベルを選べる(カード内に h2 があるときは 3。階層を飛ばさない)', async () => {
    const { wrapper } = await mountInLayout(StateBlock, {
      props: { kind: 'empty', title: '空', headingLevel: 3 },
    })

    expect(wrapper.find('h3').text()).toBe('空')
    expect(wrapper.find('h2').exists()).toBe(false)
  })

  it('メッセージ・補助文字・操作がなければ、その要素を出さない', async () => {
    const { wrapper } = await mountInLayout(StateBlock, {
      props: { kind: 'empty', title: '空' },
    })

    expect(wrapper.findAll('p')).toHaveLength(0)
    expect(wrapper.find('.state-block__actions').exists()).toBe(false)
  })
})
