// O1 のページ(opensearch 画面仕様)。実際の Query・生成クライアント・Router を通し、`fetch` だけを差し替える(E 10.1)。
// 1 ページの列数は ResizeObserver の偽物で駆動する(FMOD-U-6)。URL の同期は実際の Router で確かめる。
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import type { RouteRecordRaw } from 'vue-router'

import OpenSearchPage from '@/admin/features/opensearch/pages/OpenSearchPage.vue'

import {
  apiErrorResponse,
  jsonResponse,
  type MockResponse,
} from '../../../../../tests/support/apiErrors'
import { useFetchStub } from '../../../../../tests/support/fetchStub'
import { opensearch } from '../../../../../tests/support/fixtures/opensearch'
import { mountInLayout } from '../../../../../tests/support/mount'
import { useResizeObserverStub } from '../../../../../tests/support/resizeObserverStub'

const stub = useFetchStub()
const observers = useResizeObserverStub()

const STUB_PAGE = { render: () => null }
const ROUTES: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: STUB_PAGE,
    meta: { title: 'ダッシュボード', template: 'dashboard' },
  },
  {
    path: '/opensearch',
    name: 'opensearch',
    component: OpenSearchPage,
    meta: { title: 'OpenSearch', template: 'dashboard' },
  },
]

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
  window.innerWidth = 1280
})
afterEach(() => {
  vi.useRealTimers()
})

async function elapse(ms: number): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function mountOpenSearch(
  response: MockResponse = jsonResponse(opensearch.many()),
  options: { path?: string; width?: number } = {},
) {
  stub.respondWith(response)
  const mounted = await mountInLayout(OpenSearchPage, {
    routes: ROUTES,
    initialPath: options.path ?? '/opensearch',
    previousPath: '/',
  })
  await flushPromises()
  const { wrapper, router } = mounted
  if (options.width !== undefined && wrapper.find('[data-testid="o1-shards"]').exists()) {
    observers.resize('[data-testid="o1-shards"]', options.width)
    await nextTick()
  }
  return {
    ...mounted,
    card: () => wrapper.find('[data-testid="o1-cluster"]'),
    count: () => wrapper.find('[data-testid="o1-count"]').text(),
    names: () => wrapper.findAll('.shard-matrix__index-name').map((el) => el.text()),
    textbox: () => wrapper.find('input[type="text"]'),
    checkbox: (name: string) =>
      wrapper.findAll('input[type="checkbox"]').find((el) => {
        return wrapper.find(`label[for="${el.attributes('id')}"]`).text() === name
      })!,
    button: (name: string) => wrapper.findAll('button, a').find((b) => b.text() === name)!,
    query: () => router.currentRoute.value.query,
    fetches: () => stub.requests.filter((r) => r.pathname.endsWith('/opensearch/cluster')).length,
  }
}

type View = Awaited<ReturnType<typeof mountOpenSearch>>

async function typeName(view: View, value: string): Promise<void> {
  await view.textbox().setValue(value)
  await elapse(250)
}

describe('O1: 通常の表示(1 カード「クラスタ状態」)', () => {
  it('見出し(h1)・説明・カード(h2「クラスタ状態」。aria-labelledby で名前をつける)。クエリを付けずに取得する', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    expect(view.wrapper.find('h1').text()).toBe('OpenSearch')
    expect(view.wrapper.find('.page-header__description').text()).toContain(
      'この画面は読み取り専用で、インデックスの削除・シャードの再配置・設定の変更はできません。',
    )
    const h2 = view.card().find('h2')
    expect(h2.text()).toBe('クラスタ状態')
    expect(view.card().element.tagName).toBe('SECTION')
    expect(view.card().attributes('aria-labelledby')).toBe(h2.attributes('id'))
    expect(view.wrapper.findAll('h2')).toHaveLength(1)
    expect(stub.requests[0]).toMatchObject({
      pathname: '/api/admin/v1/opensearch/cluster',
      search: '',
    })
  })

  it('カードの中は、上から 概況 → 絞り込みフォーム → マトリクス(凡例 → ページ送りバー → 表)', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    const order = [
      '[data-testid="o1-summary"]',
      '[data-testid="o1-filter"]',
      '[data-testid="o1-shards"]',
    ].map((selector) => view.card().element.innerHTML.indexOf(selector.slice(1, -1)))
    expect(order).toEqual([...order].sort((a, b) => a - b))
    expect(order.every((position) => position >= 0)).toBe(true)
    const matrix = view.wrapper.find('[data-testid="o1-shards"]').element.innerHTML
    expect(matrix.indexOf('shard-legend')).toBeLessThan(matrix.indexOf('shard-matrix__bar'))
    expect(matrix.indexOf('shard-matrix__bar')).toBeLessThan(matrix.indexOf('<table'))
  })

  it('概況はクラスタ全体の値(3 ノード・アクティブ 48(うち移動中 1)・未割り当て 2。インデックス 25 件・シャード 50 の合計)', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    const summary = view.wrapper.find('[data-testid="o1-summary"]')
    expect(summary.find('.status-tag').text()).toBe('yellow(注意)')
    expect(summary.findAll('.cluster-summary__stats dd').map((dd) => dd.text())).toEqual([
      '3',
      '48 うち移動中 1',
      '2',
      '0',
    ])
  })

  it('最終更新の日時と「更新」は、見出しの右(aside)に出す', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    const aside = view.wrapper.find('.page-header__row .o1-page__acts')
    expect(aside.text()).toMatch(/^最終更新 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 更新$/)
  })

  it('ポーリングはしない(更新は手動のみ)', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await elapse(300_000)

    expect(view.fetches()).toBe(1)
  })

  it('「更新」で取り直す。条件・ページ位置は保つ。取得中に重ねて押しても取得を重ねない', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })
    await view.wrapper.find('select').setValue('2')
    expect(view.count()).toContain('8–14 /')

    stub.respondWith({ kind: 'hang' })
    await view.button('更新').trigger('click')
    await view.button('更新').trigger('click')
    await flushPromises()

    expect(view.fetches()).toBe(2)
    expect(view.count()).toContain('8–14 /')
    expect(view.wrapper.find('.top-progress').exists()).toBe(true)
  })

  it('red: ページ上部に error のアラート(role=status)「未割り当てのプライマリシャードがあります」+該当のインデックスとシャード番号', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.red()), { width: 982 })

    const alert = view.wrapper.find('.page-alert')
    expect(alert.attributes('role')).toBe('status')
    expect(alert.find('.page-alert__title').text()).toBe('未割り当てのプライマリシャードがあります')
    expect(alert.text()).toContain(
      'demo-docs-000001 のプライマリシャード(P0)が割り当てられていません。このインデックスの検索や登録に影響する可能性があります。',
    )
    // カードの外(上)に出す
    expect(view.card().find('.page-alert').exists()).toBe(false)
  })

  it('red で複数のインデックスが該当するときは、インデックスごとのシャード番号を一覧にする', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.redMultiple()), { width: 982 })

    const items = view.wrapper.findAll('.page-alert li').map((li) => li.text())
    expect(items).toEqual(['demo-a(P0、P1)', 'demo-b(P0)'])
  })

  it('yellow や、未割り当てのプライマリがなければ、アラートは出さない(説明だけ)', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.yellow()), { width: 982 })

    expect(view.wrapper.find('.page-alert').exists()).toBe(false)
    expect(view.wrapper.find('.cluster-summary__description').text()).toContain(
      '通常 yellow になります',
    )
  })

  it('truncated=true: カード上部に warning の注記「インデックスが多いため先頭 1,000 件だけを表示しています(全 1,500 件)。」', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.truncated()), { width: 982 })

    const note = view.card().find('.o1-page__truncated')
    expect(note.classes()).toContain('page-alert--warning')
    expect(note.text()).toBe(
      'インデックスが多いため先頭 1,000 件だけを表示しています(全 1,500 件)。',
    )
    expect(note.attributes('role')).toBeUndefined()
  })

  it('truncated でなければ注記を出さない', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    expect(view.card().find('.o1-page__truncated').exists()).toBe(false)
  })

  it('未知の状態値(クラスタ・インデックス・シャード): 中立の表示で値をそのまま出し、画面は壊れない', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.unknownValues()), { width: 982 })

    expect(view.wrapper.find('[data-testid="o1-summary"] .status-tag').text()).toBe('purple')
    expect(view.wrapper.find('thead .status-tag').text()).toBe('purple')
    expect(view.wrapper.find('tbody .shard-chip--unknown').exists()).toBe(true)
  })
})

describe('O1: 読み込み中・エラー・空(カードの中の領域単位)', () => {
  it('読み込み中: カードの見出しと更新は先に出し、カードの中をスケルトンにする。aria-busy・隠した「読み込み中」・無効のフォーム', async () => {
    const view = await mountOpenSearch({ kind: 'hang' })

    expect(view.card().find('h2').text()).toBe('クラスタ状態')
    expect(view.card().attributes('aria-busy')).toBe('true')
    expect(view.wrapper.find('[data-testid="o1-state-loading"]').text()).toBe(
      'OpenSearch の状態を読み込み中',
    )
    expect(view.wrapper.find('[data-testid="o1-state-loading"]').attributes('role')).toBe('status')
    expect(view.card().find('.top-progress').exists()).toBe(true)
    expect(view.button('更新').exists()).toBe(true)
    expect(view.wrapper.find('.page-header__row').text()).not.toContain('最終更新')
    expect((view.textbox().element as HTMLInputElement).disabled).toBe(true)
    expect(view.wrapper.find('[data-testid="o1-summary"]').exists()).toBe(false)
  })

  it('読み込み中の無効のフォームにも、URL から復元した条件を表示する', async () => {
    const view = await mountOpenSearch(
      { kind: 'hang' },
      { path: '/opensearch?q=logs&state=yellow' },
    )

    expect((view.textbox().element as HTMLInputElement).value).toBe('logs')
    expect((view.checkbox('yellow').element as HTMLInputElement).checked).toBe(true)
    expect((view.checkbox('yellow').element as HTMLInputElement).disabled).toBe(true)
  })

  it('エラー(データなし): カードは残して(h2 あり)、中にエラーブロック(role=alert)「OpenSearch の状態を取得できません」+再試行+ダッシュボードへの導線', async () => {
    const view = await mountOpenSearch(apiErrorResponse(503, 'unavailable', { retryable: true }))
    await elapse(1000) // 1 回だけの再試行(retryable)

    const error = view.card().find('[data-testid="o1-state-error"]')
    expect(error.attributes('role')).toBe('alert')
    expect(view.card().find('h2').text()).toBe('クラスタ状態')
    expect(error.find('h3').text()).toBe('OpenSearch の状態を取得できません')
    expect(error.text()).toContain('OpenSearch に接続できなかったか、応答が返りませんでした。')
    expect(error.text()).toContain('試行時刻')
    const link = error.find('a')
    expect(link.text()).toBe('ダッシュボードを開く')
    expect(link.attributes('href')).toBe('/')
    expect(view.wrapper.find('[data-testid="o1-summary"]').exists()).toBe(false)
    expect(document.querySelector('.v-snackbar')).toBeNull()
  })

  it('「再試行」で取り直し、成功すれば通常の表示に戻る', async () => {
    const view = await mountOpenSearch(apiErrorResponse(500, 'internal_error'))
    stub.respondWith(jsonResponse(opensearch.many()))

    await view.card().find('[data-testid="o1-state-error"] button').trigger('click')
    await flushPromises()

    expect(view.wrapper.find('[data-testid="o1-summary"]').exists()).toBe(true)
    expect(view.wrapper.find('[data-testid="o1-state-error"]').exists()).toBe(false)
  })

  it('空(インデックス 0 件): 概況は出し、絞り込みフォームは出さず、マトリクスの領域に空のブロック', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.empty()))

    expect(view.wrapper.find('[data-testid="o1-summary"]').exists()).toBe(true)
    expect(view.wrapper.find('[data-testid="o1-filter"]').exists()).toBe(false)
    expect(view.wrapper.find('[data-testid="o1-shards"]').exists()).toBe(false)
    const empty = view.card().find('[data-testid="o1-state-empty"]')
    expect(empty.find('h3').text()).toBe('インデックスがありません')
    expect(empty.text()).toContain('インデックスが作成されると')
  })

  it('インデックス 0 件でも、URL の条件は消さない(インデックスが戻れば再び絞り込まれる)', async () => {
    const view = await mountOpenSearch(jsonResponse(opensearch.empty()), {
      path: '/opensearch?q=logs&state=yellow',
    })

    expect(view.query()).toEqual({ q: 'logs', state: 'yellow' })
  })
})

describe('O1: 取得失敗(前回データあり)', () => {
  async function mountStale() {
    const view = await mountOpenSearch(undefined, { width: 982 })
    stub.respondWith(apiErrorResponse(500, 'internal_error'))
    await view.button('更新').trigger('click')
    await flushPromises()
    return view
  }

  it('ページ上部に warning のアラート(role=alert)と「再読み込み」。カード全体を前回の値のまま出す', async () => {
    const view = await mountStale()

    const alert = view.wrapper.find('.page-alert[role="alert"]')
    expect(alert.find('.page-alert__title').text()).toBe('最新の状態を取得できませんでした')
    expect(alert.text()).toContain('クラスタの現在の状態と異なる可能性があります。')
    expect(alert.text()).toContain('再読み込み')
    expect(view.wrapper.find('[data-testid="o1-summary"]').exists()).toBe(true)
    expect(view.wrapper.find('table').exists()).toBe(true)
  })

  it('カードの見出し行の右(h2 の外の別要素)に「前回取得時の値 · 最終更新(成功)…」(o1-state-stale)。h2 の名前は変わらない', async () => {
    const view = await mountStale()

    const note = view.wrapper.find('[data-testid="o1-state-stale"]')
    expect(note.text()).toMatch(/^前回取得時の値 · 最終更新\(成功\) \d{4}-\d{2}-\d{2}/)
    expect(view.card().find('h2').text()).toBe('クラスタ状態')
    expect(view.card().find('h2').element.contains(note.element)).toBe(false)
    // アラートには o1-state-stale を付けない(testid の重複を避ける)
    expect(view.wrapper.findAll('[data-testid="o1-state-stale"]')).toHaveLength(1)
  })

  it('概況の説明に「前回取得時の値です。」を添える', async () => {
    const view = await mountStale()

    expect(view.wrapper.find('.cluster-summary__description').text()).toContain(
      '前回取得時の値です。',
    )
  })

  it('stale でも絞り込める(条件・入力は保つ)', async () => {
    const view = await mountStale()

    await typeName(view, 'docs')

    expect(view.count()).toContain('絞り込み後 3 件のインデックス(全 25 件中)')
  })

  it('「再読み込み」で取り直し、成功すれば通常の表示に戻る', async () => {
    const view = await mountStale()
    stub.respondWith(jsonResponse(opensearch.many()))

    await view.button('再読み込み').trigger('click')
    await flushPromises()

    expect(view.wrapper.find('.page-alert[role="alert"]').exists()).toBe(false)
    expect(view.wrapper.find('[data-testid="o1-state-stale"]').exists()).toBe(false)
  })
})

describe('O1: 絞り込みと URL(q・state。replace)', () => {
  it('名前: 250ms の debounce の後に URL(q)へ反映し、一致したインデックスだけを列にする。件数表示は「絞り込み後 N 件のインデックス(全 M 件中)」', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await view.textbox().setValue('docs')
    await elapse(249)
    expect(view.query()).toEqual({})
    await elapse(1)

    expect(view.query()).toEqual({ q: 'docs' })
    expect(view.names()).toEqual(['demo-docs-000003', 'demo-docs-000001', 'demo-docs-000002'])
    expect(view.count()).toBe('絞り込み後 3 件のインデックス(全 25 件中)')
    expect(view.wrapper.find('.shard-matrix__note').text()).toContain(
      '適用中の条件: 名前に「docs」を含む。概況はクラスタ全体の値で、絞り込みの対象外。',
    )
  })

  it('Enter(フォームの送信)は待たずに反映する', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })
    await view.textbox().setValue('docs')

    await view.wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(view.query()).toEqual({ q: 'docs' })
  })

  it('状態: チェックの切替ですぐ URL(state=カンマ区切り)へ反映する。OR', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await view.checkbox('yellow').setValue(true)
    await flushPromises()
    expect(view.query()).toEqual({ state: 'yellow' })
    expect(view.count()).toBe('絞り込み後 2 件のインデックス(全 25 件中)')

    await view.checkbox('green').setValue(true)
    await flushPromises()
    expect(view.query()).toEqual({ state: 'yellow,green' })
    expect(view.count()).toContain('絞り込み後 25 件のインデックス')
  })

  it('3 つとも選ぶと「すべて」と同じ(件数表示・補足は絞り込み前の文言)。チェックは 3 つ選んだまま・解除は無効のまま', async () => {
    const view = await mountOpenSearch(undefined, {
      path: '/opensearch?state=red,yellow,green',
      width: 982,
    })

    expect(view.count()).toBe('1–7 / 全 25 件のインデックス(ページ 1 / 4)')
    expect(view.wrapper.find('.shard-matrix__note').text()).not.toContain('適用中の条件')
    for (const name of ['red', 'yellow', 'green']) {
      expect((view.checkbox(name).element as HTMLInputElement).checked).toBe(true)
    }
    expect(view.button('条件を解除').attributes('aria-disabled')).toBe('true')
    // URL もそのまま(3 つ選んだ表示を保つ)
    expect(view.query()).toEqual({ state: 'red,yellow,green' })
  })

  it('履歴を増やさない(replace)。条件を変えても「戻る」で元の画面に戻れる', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await typeName(view, 'docs')
    await view.checkbox('red').setValue(true)
    await flushPromises()
    view.router.back()
    await flushPromises()

    expect(view.router.currentRoute.value.path).toBe('/')
  })

  it('URL の条件(q・state)で開くと、入力・チェック・絞り込みを復元する。page は URL に入れない', async () => {
    const view = await mountOpenSearch(undefined, {
      path: '/opensearch?q=logs&state=yellow,green',
      width: 982,
    })

    expect((view.textbox().element as HTMLInputElement).value).toBe('logs')
    expect((view.checkbox('yellow').element as HTMLInputElement).checked).toBe(true)
    expect((view.checkbox('green').element as HTMLInputElement).checked).toBe(true)
    expect((view.checkbox('red').element as HTMLInputElement).checked).toBe(false)
    expect(view.count()).toBe('1–7 / 絞り込み後 16 件のインデックス(全 25 件中)(ページ 1 / 3)')
    await view.wrapper.find('select').setValue('2')
    expect(Object.keys(view.query())).not.toContain('page')
  })

  it('不正な URL(未知の state・空白だけの q)は正規化して replace する', async () => {
    const view = await mountOpenSearch(undefined, {
      path: '/opensearch?q=%20%20&state=purple,yellow',
      width: 982,
    })

    expect(view.query()).toEqual({ state: 'yellow' })
  })

  it('条件を変えると 1 ページ目に戻る。同じ条件のままなら、ページを保つ', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })
    await view.wrapper.find('select').setValue('3')
    expect(view.count()).toContain('15–21 /')

    // 条件が変わらない(空白だけを入れる)
    await typeName(view, '   ')
    expect(view.count()).toContain('15–21 /')

    await typeName(view, 'logs')
    expect(view.count()).toBe('1–7 / 絞り込み後 16 件のインデックス(全 25 件中)(ページ 1 / 3)')
  })

  it('3 つ選んだ表示は条件なしと同じ条件。URL がそうなっても、1 ページ目に戻らない(ページを保つ)', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })
    await view.wrapper.find('select').setValue('2')
    expect(view.count()).toContain('8–14 /')

    await view.router.replace({ query: { state: 'red,yellow,green' } })
    await flushPromises()

    expect(view.count()).toContain('8–14 /')
  })

  it('一致 0 件: ブロック(o1-state-nomatch)と、「絞り込み後 0 件のインデックス(全 25 件中)」。フォームはそのまま使える', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await typeName(view, 'zzz')

    expect(view.count()).toBe('絞り込み後 0 件のインデックス(全 25 件中)')
    expect(view.wrapper.find('[data-testid="o1-state-nomatch"] h3').text()).toBe(
      '条件に合うインデックスがありません',
    )
    expect(view.wrapper.find('table').exists()).toBe(false)
    expect(view.wrapper.findAll('button').filter((b) => b.text() === '条件を解除')).toHaveLength(1)
    // 概況は絞り込みの対象外
    expect(view.wrapper.find('[data-testid="o1-summary"]').exists()).toBe(true)
  })

  it('「条件を解除」: すべての条件を外し、名前の入力欄へフォーカスを移す。条件がないときは何も起きない', async () => {
    const view = await mountOpenSearch(undefined, {
      path: '/opensearch?q=logs&state=yellow',
      width: 982,
    })
    expect(view.button('条件を解除').attributes('aria-disabled')).toBe('false')

    await view.button('条件を解除').trigger('click')
    await flushPromises()

    expect(view.query()).toEqual({})
    expect((view.textbox().element as HTMLInputElement).value).toBe('')
    expect((view.checkbox('yellow').element as HTMLInputElement).checked).toBe(false)
    expect(document.activeElement).toBe(view.textbox().element)
    expect(view.count()).toContain('1–7 / 全 25 件のインデックス')
    expect(view.button('条件を解除').attributes('aria-disabled')).toBe('true')
  })

  it('絞り込んでも、API は 1 回だけ(条件を API に送らない)', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await typeName(view, 'docs')
    await view.checkbox('red').setValue(true)
    await flushPromises()

    expect(view.fetches()).toBe(1)
    expect(stub.requests[0]?.search).toBe('')
  })

  it('絞り込み後のインデックスだけで、行見出しの「シャード n」・未割り当ての行・凡例を数え直す', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })

    await typeName(view, 'docs-000001')

    // docs-000001 は green(未割り当て・移動中なし)
    expect(view.wrapper.find('.shard-matrix__unassigned').exists()).toBe(false)
    expect(view.wrapper.findAll('.shard-legend li')).toHaveLength(2)
    expect(view.wrapper.find('tbody th').text()).toContain('(絞り込み後のインデックスの合計)')
  })
})

describe('O1: 1 ページの列数(カードの幅から)', () => {
  it('幅の変化に追随する(982px で 7 列、742px で 5 列)', async () => {
    const view = await mountOpenSearch(undefined, { width: 982 })
    expect(view.names()).toHaveLength(7)

    observers.resize('[data-testid="o1-shards"]', 742)
    await nextTick()

    expect(view.names()).toHaveLength(5)
  })
})
