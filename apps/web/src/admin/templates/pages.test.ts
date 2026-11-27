// 4 型のテンプレート(DS 6): ページ見出し領域・カード・状態の出し分け。型ごとの骨格の違いを確かめる。
import { describe, expect, it } from 'vitest'
import { defineComponent, h, type Component } from 'vue'

import type { ViewState } from '@/admin/lib/viewState'

import { mountInLayout } from '../../../tests/support/mount'
import DashboardPage from './DashboardPage.vue'
import DetailPage from './DetailPage.vue'
import FormPage from './FormPage.vue'
import ListPage from './ListPage.vue'
import { viewStates } from '../../../tests/support/viewStates'

const ROUTES = [{ path: '/:p(.*)*', component: { render: () => null } }]

async function mountPage(
  page: Component,
  viewState: ViewState,
  slots: Record<string, () => unknown> = {},
  props: Record<string, unknown> = {},
) {
  const events: string[] = []
  const Host = defineComponent({
    setup: () => () =>
      h(
        page,
        {
          title: '画面',
          viewState,
          testidPrefix: 'x',
          onRetry: () => events.push('retry'),
          ...props,
        },
        { default: () => h('p', { id: 'body' }, '本文'), ...slots },
      ),
  })
  const mounted = await mountInLayout(Host, { routes: ROUTES })
  return { ...mounted, events }
}

describe.each([
  ['ListPage(一覧)', ListPage],
  ['DetailPage(詳細)', DetailPage],
  ['FormPage(フォーム)', FormPage],
  ['DashboardPage(ダッシュボード)', DashboardPage],
] as const)('%s の共通の振る舞い', (_name, page) => {
  it('ページ見出し領域(h1)と本文を描く', async () => {
    const { wrapper } = await mountPage(page, viewStates.ready())

    expect(wrapper.find('h1').text()).toBe('画面')
    expect(wrapper.find('#body').exists()).toBe(true)
  })

  it('loading: 本文を出さず、スケルトンを出す(x-state-loading)', async () => {
    const { wrapper } = await mountPage(page, viewStates.loading())

    expect(wrapper.find('#body').exists()).toBe(false)
    expect(wrapper.find('[data-testid="x-state-loading"]').attributes('aria-busy')).toBe('true')
    // 見出しは先に出る
    expect(wrapper.find('h1').exists()).toBe(true)
  })

  it('error: エラーブロック(role=alert)と「再試行」。本文は出さない(取得できなければ出さない)', async () => {
    const { wrapper, events } = await mountPage(page, viewStates.error())

    expect(wrapper.find('[data-testid="x-state-error"]').attributes('role')).toBe('alert')
    expect(wrapper.find('#body').exists()).toBe(false)
    const retry = wrapper.findAll('button').find((b) => b.text().includes('再試行'))
    await retry?.trigger('click')
    expect(events).toEqual(['retry'])
  })

  it('stale: 前回のデータ(本文)を残し、warning アラートを出す', async () => {
    const { wrapper } = await mountPage(page, viewStates.stale())

    expect(wrapper.find('#body').exists()).toBe(true)
    expect(wrapper.find('[data-testid="x-state-stale"]').exists()).toBe(true)
  })

  it('再取得中(refreshing): 本文を消さず、上端の進行バー(FormPage は取得中の表示を持たない)', async () => {
    const { wrapper } = await mountPage(page, viewStates.refreshing())

    expect(wrapper.find('#body').exists()).toBe(true)
  })
})

describe('ListPage(DS 6.1)', () => {
  it('カード(aria-label)に、ツールバー・本文(表)・ページング(footer)の順に並べる', async () => {
    const { wrapper } = await mountPage(
      ListPage,
      viewStates.ready(),
      {
        toolbar: () => h('div', { id: 'toolbar' }, '3 件'),
        footer: () => h('div', { id: 'footer' }, 'paging'),
      },
      { cardLabel: 'データソース一覧' },
    )

    const card = wrapper.find('.list-page__card')
    expect(card.attributes('aria-label')).toBe('データソース一覧')
    const ids = [...card.element.querySelectorAll('[id]')].map((element) => element.id)
    expect(ids).toEqual(['toolbar', 'body', 'footer'])
  })

  it('カードは、cardLabel があるとき region(aria-label)になる。なければ role を付けない', async () => {
    const labeled = await mountPage(ListPage, viewStates.ready(), {}, { cardLabel: 'ジョブ一覧' })
    const plain = await mountPage(ListPage, viewStates.ready())

    expect(labeled.wrapper.find('.list-page__card').attributes('role')).toBe('region')
    expect(labeled.wrapper.find('[role="region"]').attributes('aria-label')).toBe('ジョブ一覧')
    expect(plain.wrapper.find('.list-page__card').attributes('role')).toBeUndefined()
    expect(plain.wrapper.find('.list-page__card').attributes('aria-label')).toBeUndefined()
  })

  it('再取得中は、カード上端に進行バーを出す。本文は消えない', async () => {
    const { wrapper } = await mountPage(ListPage, viewStates.refreshing())

    expect(wrapper.find('.list-page__card .top-progress').attributes('aria-label')).toBe('更新中')
    expect(wrapper.find('#body').exists()).toBe(true)
  })

  it('再取得中でなければ、進行バーを出さない', async () => {
    const { wrapper } = await mountPage(ListPage, viewStates.ready())

    expect(wrapper.find('.top-progress').exists()).toBe(false)
  })

  it('空・エラー・読み込み中は、ページング(footer)を出さない。ツールバーは出す(更新ボタンが要る)', async () => {
    const slots = {
      toolbar: () => h('div', { id: 'toolbar' }, '更新'),
      footer: () => h('div', { id: 'footer' }, 'paging'),
    }
    for (const state of [viewStates.empty(), viewStates.error(), viewStates.loading()]) {
      const { wrapper } = await mountPage(ListPage, state, slots)

      expect(wrapper.find('#footer').exists()).toBe(false)
      expect(wrapper.find('#toolbar').exists()).toBe(true)
    }
  })

  it('stale のときは、ページングを出す(前回の表のまま操作できる)', async () => {
    const { wrapper } = await mountPage(ListPage, viewStates.stale(), {
      footer: () => h('div', { id: 'footer' }, 'paging'),
    })

    expect(wrapper.find('#footer').exists()).toBe(true)
  })

  it('empty: 空ブロックの中に empty-actions を出す(主操作は見出しに残る)', async () => {
    const { wrapper } = await mountPage(ListPage, viewStates.empty(), {
      'empty-actions': () => h('button', { id: 'create' }, 'データソースを登録'),
    })

    expect(wrapper.find('[data-testid="x-state-empty"] #create').exists()).toBe(true)
  })

  it('loading のスロットで、表と同じ列構成のスケルトンに差し替えられる', async () => {
    const { wrapper } = await mountPage(ListPage, viewStates.loading(), {
      loading: () => h('div', { id: 'table-skeleton' }, 'skeleton'),
    })

    expect(wrapper.find('#table-skeleton').exists()).toBe(true)
  })
})

describe('DetailPage(DS 6.2)', () => {
  it('識別子の見出しに状態タグ(tag)・補足(description)・カードの縦並び', async () => {
    const { wrapper } = await mountPage(
      DetailPage,
      viewStates.ready(),
      {
        tag: () => h('span', { id: 'tag' }, '成功'),
        description: () => h('p', { id: 'sub' }, '最終クロール'),
      },
      { monoTitle: true },
    )

    expect(wrapper.find('h1 #tag').exists()).toBe(true)
    expect(wrapper.find('#sub').exists()).toBe(true)
    expect(wrapper.find('.detail-page__stack #body').exists()).toBe(true)
  })

  it('notfound: 「見つかりません」ブロックに、一覧へ戻る導線(notfound-actions)', async () => {
    const { wrapper } = await mountPage(DetailPage, viewStates.notfound(), {
      'notfound-actions': () => h('a', { id: 'back' }, '一覧へ戻る'),
    })

    const block = wrapper.find('[data-testid="x-state-notfound"]')
    expect(block.find('#back').exists()).toBe(true)
    expect(wrapper.find('#body').exists()).toBe(false)
  })

  it('再取得中(ポーリング)は、本文を消さず、進行バーを出す', async () => {
    const { wrapper } = await mountPage(DetailPage, viewStates.refreshing())

    expect(wrapper.find('.detail-page__body .top-progress').exists()).toBe(true)
    expect(wrapper.find('#body').exists()).toBe(true)
  })

  it('エラーブロックはカードで包む(ページにカードがない)', async () => {
    const { wrapper } = await mountPage(DetailPage, viewStates.error())

    expect(wrapper.find('.view-state-body__card [data-testid="x-state-error"]').exists()).toBe(true)
  })
})

describe('FormPage(DS 6.3)', () => {
  it('フォーム本体は最大幅 640px の 1 列のカードに置く', async () => {
    const { wrapper } = await mountPage(FormPage, viewStates.ready())

    expect(wrapper.find('.form-page__body .form-page__card #body').exists()).toBe(true)
  })

  it('取得できない(error・notfound)ときは、フォームを出さない', async () => {
    for (const state of [viewStates.error(), viewStates.notfound()]) {
      const { wrapper } = await mountPage(FormPage, state)

      expect(wrapper.find('.form-page__card').exists()).toBe(false)
      expect(wrapper.find('#body').exists()).toBe(false)
    }
  })
})

describe('DashboardPage(DS 6.4)', () => {
  it('操作行(toolbar)は、すべての状態で見出しの下に置く(loading でも出る)', async () => {
    for (const state of [viewStates.ready(), viewStates.loading(), viewStates.error()]) {
      const { wrapper } = await mountPage(DashboardPage, state, {
        toolbar: () => h('div', { id: 'toolbar' }, '最終取得 10:00'),
      })

      expect(wrapper.find('#toolbar').exists()).toBe(true)
      const html = wrapper.html()
      expect(html.indexOf('id="toolbar"')).toBeGreaterThan(html.indexOf('<h1'))
    }
  })

  it('再取得中(更新・自動更新)は、本文を消さず、進行バーを出す', async () => {
    const { wrapper } = await mountPage(DashboardPage, viewStates.refreshing())

    expect(wrapper.find('.dashboard-page__body .top-progress').exists()).toBe(true)
    expect(wrapper.find('#body').exists()).toBe(true)
  })

  it('カード・タイルの縦並び。loading のスロットで、タイルのスケルトンに差し替えられる', async () => {
    const ready = await mountPage(DashboardPage, viewStates.ready())
    const loading = await mountPage(DashboardPage, viewStates.loading(), {
      loading: () => h('div', { id: 'tile-skeleton' }, 'tiles'),
    })

    expect(ready.wrapper.find('.dashboard-page__stack #body').exists()).toBe(true)
    expect(loading.wrapper.find('#tile-skeleton').exists()).toBe(true)
  })
})
