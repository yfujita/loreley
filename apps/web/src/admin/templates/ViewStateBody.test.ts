import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref, type FunctionalComponent } from 'vue'

import type { ViewState } from '@/admin/lib/viewState'

import { mountInLayout } from '../../../tests/support/mount'
import type { StateTexts } from './types'
import ViewStateBody from './ViewStateBody.vue'
import { viewStates } from '../../../tests/support/viewStates'

async function mountBody(
  viewState: ViewState,
  options: { texts?: StateTexts; card?: boolean; testidPrefix?: string } = {},
) {
  const retries: number[] = []
  const state = ref(viewState)
  const Host = defineComponent({
    setup: () => () =>
      h(
        ViewStateBody,
        {
          viewState: state.value,
          texts: options.texts,
          card: options.card,
          testidPrefix: options.testidPrefix ?? 's1',
          onRetry: () => retries.push(1),
        },
        {
          default: () => h('div', { id: 'content' }, '本文'),
          'empty-actions': () => h('button', { id: 'empty-action' }, 'データソースを登録'),
          'notfound-actions': () => h('a', { id: 'notfound-action' }, '一覧へ戻る'),
        },
      ),
  })
  const mounted = await mountInLayout(Host)
  return { ...mounted, retries, state }
}

describe('ViewStateBody(E 6.2・DS 4.5)', () => {
  it('ready: 本文だけを描く(アラート・ブロックなし)', async () => {
    const { wrapper } = await mountBody(viewStates.ready())

    expect(wrapper.find('#content').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.find('.state-block').exists()).toBe(false)
  })

  it('loading: スケルトン(aria-busy・読み込み中)を描き、本文を出さない。testid は s1-state-loading', async () => {
    const { wrapper } = await mountBody(viewStates.loading(), {
      texts: { loadingLabel: 'データソース一覧を読み込み中' },
    })

    expect(wrapper.find('#content').exists()).toBe(false)
    const block = wrapper.find('[data-testid="s1-state-loading"]')
    expect(block.attributes('aria-busy')).toBe('true')
    expect(block.find('.sr-only').text()).toBe('データソース一覧を読み込み中')
  })

  it('empty: 空ブロック(見出し・説明)と、empty-actions のスロット。testid は s1-state-empty', async () => {
    const { wrapper } = await mountBody(viewStates.empty(), {
      texts: {
        emptyTitle: 'データソースがまだありません',
        emptyMessage: '登録すると検索できます。',
      },
    })

    const block = wrapper.find('[data-testid="s1-state-empty"]')
    expect(block.find('h2').text()).toBe('データソースがまだありません')
    expect(block.text()).toContain('登録すると検索できます。')
    expect(block.find('#empty-action').exists()).toBe(true)
    expect(wrapper.find('#content').exists()).toBe(false)
  })

  it('error: role=alert・見出し・原因と次の行動・試行時刻・「再試行」。押すと retry を通知する', async () => {
    const { wrapper, retries } = await mountBody(viewStates.error(), {
      texts: {
        errorTitle: 'データソースを取得できません',
        errorMessage: 'API に接続できませんでした。',
      },
    })

    const block = wrapper.find('[data-testid="s1-state-error"]')
    expect(block.attributes('role')).toBe('alert')
    expect(block.find('h2').text()).toBe('データソースを取得できません')
    expect(block.text()).toContain('API に接続できませんでした。')
    expect(block.text()).toMatch(/試行時刻 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/)
    const retry = block.findAll('button').find((button) => button.text().includes('再試行'))
    await retry?.trigger('click')
    expect(retries).toHaveLength(1)
  })

  it('error: 想定外のエラーは、補助文字に code と HTTP ステータス(message は出さない)', async () => {
    const { wrapper } = await mountBody(viewStates.unexpectedError())

    expect(wrapper.find('[data-testid="s1-state-error"]').text()).toContain(
      'code: internal_error / HTTP 500',
    )
  })

  it('error: 再試行できない(canRetry=false)ときは「再試行」を出さない', async () => {
    const { wrapper } = await mountBody(
      viewStates.error({
        notFound: false,
        retryable: false,
        unexpected: false,
        diagnostic: { code: null, status: null },
      }),
    )

    expect(wrapper.findAll('button')).toHaveLength(0)
  })

  it('notfound: 見つかりませんブロックと、notfound-actions のスロット(一覧へ戻る)。testid は s1-state-notfound', async () => {
    const { wrapper } = await mountBody(viewStates.notfound(), {
      texts: { notfoundTitle: 'データソースが見つかりません' },
    })

    const block = wrapper.find('[data-testid="s1-state-notfound"]')
    expect(block.find('h2').text()).toBe('データソースが見つかりません')
    expect(block.find('#notfound-action').exists()).toBe(true)
    expect(wrapper.find('#content').exists()).toBe(false)
  })

  it('stale: 前回のデータ(本文)を残し、warning アラート(role=alert)に最終更新(成功)時刻と「再読み込み」を出す', async () => {
    const { wrapper, retries } = await mountBody(viewStates.stale(), {
      texts: { staleNote: '実行中のジョブの状態が実際と異なる可能性があります。' },
    })

    expect(wrapper.find('#content').exists()).toBe(true)
    const alert = wrapper.find('[data-testid="s1-state-stale"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('最新の状態を取得できませんでした')
    expect(alert.text()).toContain('前回取得したデータ(2024-11-19')
    expect(alert.text()).toContain('実行中のジョブの状態が実際と異なる可能性があります。')
    await alert.find('button').trigger('click')
    expect(retries).toHaveLength(1)
  })

  it('stale で再試行できないときは「再読み込み」を出さない', async () => {
    const { wrapper } = await mountBody(
      viewStates.stale({
        notFound: false,
        retryable: false,
        unexpected: false,
        diagnostic: { code: null, status: null },
      }),
    )

    expect(wrapper.find('[data-testid="s1-state-stale"] button').exists()).toBe(false)
  })

  it('refreshing(再取得中): 本文のまま。アラート・ブロックは出さない(進行バーは各テンプレートが出す)', async () => {
    const { wrapper } = await mountBody(viewStates.refreshing())

    expect(wrapper.find('#content').exists()).toBe(true)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('card: ページにカードがないとき、状態ブロックをカードと同じ見た目の枠で包む(本文は包まない)', async () => {
    const carded = await mountBody(viewStates.empty(), { card: true })
    const plain = await mountBody(viewStates.empty(), { card: false })
    const ready = await mountBody(viewStates.ready(), { card: true })

    expect(carded.wrapper.find('.view-state-body__card').exists()).toBe(true)
    expect(plain.wrapper.find('.view-state-body__card').exists()).toBe(false)
    expect(ready.wrapper.find('.view-state-body__card').exists()).toBe(false)
  })

  it('状態が変わると表示が追従する(loading → ready)', async () => {
    const { wrapper, state } = await mountBody(viewStates.loading())
    expect(wrapper.find('#content').exists()).toBe(false)

    state.value = viewStates.ready()
    await nextTick()

    expect(wrapper.find('#content').exists()).toBe(true)
    expect(wrapper.find('.state-block-loading').exists()).toBe(false)
  })

  it('testidPrefix を省略すると、data-testid を付けない', async () => {
    const retries: number[] = []
    const Host: FunctionalComponent = () =>
      h(ViewStateBody, { viewState: viewStates.empty(), onRetry: () => retries.push(1) })
    const { wrapper } = await mountInLayout(Host)

    expect(wrapper.find('[data-testid]').exists()).toBe(false)
  })
})
