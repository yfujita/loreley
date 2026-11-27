// D1 のページ(dashboard 画面仕様)。実際の Query・生成クライアントを通し、`fetch` だけを差し替える(E 10.1)。
import { flushPromises, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'

import DashboardPage from '@/admin/features/dashboard/pages/DashboardPage.vue'

import {
  apiErrorResponse,
  jsonResponse,
  type MockResponse,
} from '../../../../../tests/support/apiErrors'
import { useFetchStub } from '../../../../../tests/support/fetchStub'
import { dashboard } from '../../../../../tests/support/fixtures/dashboard'
import { mountInLayout } from '../../../../../tests/support/mount'

const stub = useFetchStub()

/** 件数行の文字(項目の間の空白は、表示の都合で 1 つか 2 つ入るので、1 つにそろえる)。 */
const itemsText = (summary: { find(selector: string): { text(): string } }) =>
  summary.find('.summary-band__items').text().replace(/\s+/g, ' ').trim()

const STUB_PAGE = { render: () => null }
const ROUTES: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: DashboardPage,
    meta: { title: 'ダッシュボード', template: 'dashboard' },
  },
  {
    path: '/jobs',
    name: 'jobs',
    component: STUB_PAGE,
    meta: { title: 'ジョブ', template: 'list' },
  },
  {
    path: '/opensearch',
    name: 'opensearch',
    component: STUB_PAGE,
    meta: { title: 'OpenSearch', template: 'dashboard' },
  },
]

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] })
})
afterEach(() => {
  vi.useRealTimers()
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
})

async function elapse(ms: number): Promise<void> {
  await vi.advanceTimersByTimeAsync(ms)
  await flushPromises()
}

async function mountDashboard(response: MockResponse = jsonResponse(dashboard.allNormal())) {
  stub.respondWith(response)
  const mounted = await mountInLayout(DashboardPage, { routes: ROUTES })
  await flushPromises()
  const { wrapper } = mounted
  return {
    ...mounted,
    summary: () => wrapper.find('[data-testid="d1-summary"]'),
    tile: (id: string) => wrapper.find(`[data-testid="d1-tile-${id}"]`),
    button: (name: string) => wrapper.findAll('button').find((b) => b.text() === name)!,
    switchInput: () => wrapper.find('input[role="switch"]'),
    polls: () => stub.requests.filter((r) => r.pathname.endsWith('/dashboard')).length,
    manualStatus: () => wrapper.findAll('[role="status"].sr-only').at(-1)!.text(),
  }
}

type View = Awaited<ReturnType<typeof mountDashboard>>

async function clickUpdate(view: View): Promise<void> {
  await view.button('更新').trigger('click')
  await flushPromises()
}

describe('D1: 通常の表示', () => {
  it('見出し(h1)・説明・概況・必須 5 と任意 3 のタイル・「この表示について」を、この順に出す', async () => {
    const { wrapper } = await mountDashboard()

    expect(wrapper.find('h1').text()).toBe('ダッシュボード')
    expect(wrapper.find('.page-header__description').text()).toBe(
      '各コンポーネントが起動して応答できるかを確認します。現在の状態だけを表示し、履歴や推移は記録しません。',
    )
    expect(wrapper.findAll('h2').map((h) => h.text())).toEqual([
      'コンポーネント',
      '任意のコンポーネント',
      'この表示について',
    ])
    expect(wrapper.findAll('h3').map((h) => h.text())).toEqual([
      'crawler',
      'indexer',
      'opensearch',
      'api',
      'web',
      'opensearch-dashboards',
      'embedding',
      'llm',
    ])
    const lists = wrapper.findAll('ul[aria-label]')
    expect(lists.map((ul) => ul.attributes('aria-label'))).toEqual([
      'コンポーネントの状態',
      '任意のコンポーネントの状態',
    ])
  })

  it('概況: すべて正常(任意は未設定を許す)。件数行は 正常 5・異常 0・判定不能 0・未設定 3', async () => {
    const { summary } = await mountDashboard()

    expect(summary().find('.summary-band__title').text()).toBe('すべてのコンポーネントが正常です')
    expect(itemsText(summary())).toBe('正常 5 異常 0 判定不能 0 未設定 3')
    expect(summary().classes()).toContain('summary-band--success')
  })

  it('タイル: 正常は「応答しています · 確認 hh:mm:ss」、未設定は点線のタイル。クエリを付けずに取得する', async () => {
    const { tile } = await mountDashboard()

    expect(tile('crawler').text()).toContain('応答しています · 確認 10:00:00')
    expect(tile('embedding').classes()).toContain('component-tile--not_configured')
    expect(tile('embedding').text()).toContain('設定されていません(任意)。')
    expect(stub.requests[0]).toMatchObject({ pathname: '/api/admin/v1/dashboard', search: '' })
  })

  it('導線: crawler・indexer は J1、opensearch は O1。api・web・任意にはない', async () => {
    const { tile } = await mountDashboard()

    expect(tile('crawler').find('a').attributes('href')).toBe('/jobs')
    expect(tile('indexer').find('a').attributes('href')).toBe('/jobs')
    expect(tile('opensearch').find('a').attributes('href')).toBe('/opensearch')
    for (const id of ['api', 'web', 'opensearch-dashboards', 'embedding', 'llm']) {
      expect(tile(id).find('a').exists()).toBe(false)
    }
  })

  it('異常あり: 概況は error、異常のタイルは「応答がありません。…」。タグは「異常」', async () => {
    const { summary, tile } = await mountDashboard(jsonResponse(dashboard.abnormal()))

    expect(summary().classes()).toContain('summary-band--error')
    expect(summary().find('.summary-band__title').text()).toBe(
      '異常のコンポーネントがあります(1 件)',
    )
    expect(itemsText(summary())).toBe('異常: crawler 正常 4 判定不能 0 未設定 3')
    expect(tile('crawler').find('.status-tag').text()).toBe('異常')
    expect(tile('crawler').text()).toContain(
      '応答がありません。コンテナが停止している可能性があります。',
    )
  })

  it('判定不能あり: 概況は warning、タイルは理由つきの「状態を取得できませんでした(時間内に応答がありませんでした)。」', async () => {
    const { summary, tile } = await mountDashboard(jsonResponse(dashboard.undetermined()))

    expect(summary().classes()).toContain('summary-band--warning')
    expect(summary().find('.summary-band__title').text()).toBe(
      '状態を確認できないコンポーネントがあります(1 件)',
    )
    expect(tile('indexer').find('.status-tag').text()).toBe('判定不能')
    expect(tile('indexer').text()).toContain(
      '状態を取得できませんでした(時間内に応答がありませんでした)。',
    )
  })

  it('最終取得成功の日時を、見出しの下の操作行に出す(取得できたとき)', async () => {
    const { wrapper } = await mountDashboard()

    expect(wrapper.find('.dashboard-page__toolbar').text()).toMatch(
      /^最終取得成功 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}/,
    )
  })

  it('取得に使ったクエリキーは ["dashboard"](画面を離れても同じ。key factory)', async () => {
    const { queryClient } = await mountDashboard()

    expect(queryClient.getQueryData(['dashboard'])).toEqual(dashboard.allNormal())
  })
})

describe('D1: 読み込み中', () => {
  it('見出しと操作行(自動更新・更新)は先に出し、概況・タイルはスケルトン。aria-busy と隠した「読み込み中」', async () => {
    const { wrapper, switchInput } = await mountDashboard({ kind: 'hang' })

    expect(wrapper.find('h1').text()).toBe('ダッシュボード')
    expect(switchInput().exists()).toBe(true)
    expect(wrapper.findAll('button').some((b) => b.text() === '更新')).toBe(true)
    const loading = wrapper.find('[data-testid="d1-state-loading"]')
    expect(loading.attributes('aria-busy')).toBe('true')
    expect(loading.find('.sr-only').text()).toBe('コンポーネントの状態を読み込み中')
    expect(wrapper.find('[data-testid="d1-summary"]').exists()).toBe(false)
    // まだ取得成功がないので、最終取得成功は出さない
    expect(wrapper.find('.dashboard-page__toolbar').text()).not.toContain('最終取得成功')
  })

  it('スケルトンは外側をカードで包まない(タイルのスケルトンが自分のカードを持つ)', async () => {
    const { wrapper } = await mountDashboard({ kind: 'hang' })

    expect(wrapper.find('.view-state-body__card').exists()).toBe(false)
    expect(wrapper.findAll('.dashboard-page__skeleton').length).toBeGreaterThan(1)
  })
})

describe('D1: 初回から取得できない(データなし)', () => {
  it('エラーブロック(role=alert)「コンポーネントの状態を取得できません」+「再試行」。通知は出さない', async () => {
    const { wrapper } = await mountDashboard(apiErrorResponse(500, 'internal_error'))

    const error = wrapper.find('[data-testid="d1-state-error"]')
    expect(error.attributes('role')).toBe('alert')
    expect(error.find('h2').text()).toBe('コンポーネントの状態を取得できません')
    expect(error.text()).toContain('Admin API に接続できませんでした。')
    expect(error.text()).toContain('api コンテナが起動しているかを確認してください。')
    expect(wrapper.find('[data-testid="d1-summary"]').exists()).toBe(false)
    expect(document.querySelector('.v-snackbar')).toBeNull()
  })

  it('見出しの下の操作行(自動更新・更新)は、エラーでも出す', async () => {
    const { wrapper, switchInput } = await mountDashboard(apiErrorResponse(500, 'internal_error'))

    expect(switchInput().exists()).toBe(true)
    expect(wrapper.find('.dashboard-page__toolbar').exists()).toBe(true)
  })

  it('「再試行」で取り直し、成功すれば通常の表示に戻る', async () => {
    const view = await mountDashboard(apiErrorResponse(500, 'internal_error'))
    stub.respondWith(jsonResponse(dashboard.allNormal()))

    await view.wrapper.find('[data-testid="d1-state-error"] button').trigger('click')
    await flushPromises()

    expect(view.summary().exists()).toBe(true)
    expect(view.wrapper.find('[data-testid="d1-state-error"]').exists()).toBe(false)
  })
})

describe('D1: 取得失敗(前回データあり)。dashboard 4.3・#25', () => {
  async function mountStale(first: MockResponse = jsonResponse(dashboard.allNormal())) {
    const view = await mountDashboard(first)
    stub.respondWith(apiErrorResponse(500, 'internal_error'))
    await clickUpdate(view)
    return view
  }

  it('warning のアラート(role=alert)「最新の状態を取得できませんでした」+「再読み込み」。概況は「現在の状態を確認できません」', async () => {
    const { wrapper, summary } = await mountStale()

    const alert = wrapper.find('[role="alert"]')
    expect(alert.find('.page-alert__title').text()).toBe('最新の状態を取得できませんでした')
    expect(alert.text().replace(/\s+/g, ' ')).toMatch(
      /^最新の状態を取得できませんでした Admin API に接続できないため、どのコンポーネントの現在の状態も確認できません。前回取得した状態\(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} 時点\)を、タイルに添えています。/,
    )
    expect(alert.text()).toContain('再読み込み')
    expect(summary().classes()).toContain('summary-band--warning')
    expect(summary().find('.summary-band__title').text()).toBe('現在の状態を確認できません')
    expect(itemsText(summary())).toBe('判定不能 5 未設定 3(前回取得時の設定) 前回の構成と同じ 8 件')
  })

  it('前回「正常」「異常」だったタイルを判定不能に降格し、前回の状態を添える。未設定は維持。全 8 タイルを出す', async () => {
    const { wrapper, tile } = await mountStale(jsonResponse(dashboard.abnormal()))

    expect(wrapper.findAll('h3')).toHaveLength(8)
    expect(tile('crawler').find('.status-tag').text()).toBe('判定不能')
    expect(tile('crawler').text()).toMatch(/前回の状態: 異常\(\d{2}:\d{2}:\d{2} 時点\)/)
    expect(tile('indexer').find('.status-tag').text()).toBe('判定不能')
    expect(tile('indexer').text()).toMatch(/前回の状態: 正常\(\d{2}:\d{2}:\d{2} 時点\)/)
    expect(tile('embedding').find('.status-tag').text()).toBe('未設定')
    expect(tile('embedding').text()).toContain('前回取得時は、設定されていませんでした(任意)。')
    expect(wrapper.findAll('h2').map((h) => h.text())).toContain('任意のコンポーネント')
  })

  it('前回の「正常」を表示し続けない(降格後のタイルに「正常」のタグはない)。導線も出さない', async () => {
    const { wrapper } = await mountStale()

    const tags = wrapper.findAll('[data-testid^="d1-tile-"] .status-tag').map((t) => t.text())
    expect(tags).not.toContain('正常')
    expect(wrapper.find('[data-testid^="d1-tile-"] a').exists()).toBe(false)
  })

  it('最終取得成功の日時は、取得失敗が続いても更新しない', async () => {
    const view = await mountDashboard()
    const lastSuccess = view.wrapper.find('.dashboard-page__toolbar').text().split(' ')[1]
    stub.respondWith(apiErrorResponse(500, 'internal_error'))
    await elapse(60_000) // 30 秒ごとの自動更新が失敗する(2 回)

    expect(view.wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(view.wrapper.find('.dashboard-page__toolbar').text()).toContain(
      `最終取得成功 ${lastSuccess}`,
    )
    expect(view.polls()).toBeGreaterThan(2)
  })

  it('自動更新は続け、成功したら通常の表示に戻る(アラートが消え、概況・タイルが現在の状態に戻る)', async () => {
    const view = await mountStale()
    expect(view.wrapper.find('[role="alert"]').exists()).toBe(true)

    stub.respondWith(jsonResponse(dashboard.allNormal()))
    await elapse(30_000)

    expect(view.wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(view.summary().find('.summary-band__title').text()).toBe(
      'すべてのコンポーネントが正常です',
    )
    expect(view.tile('crawler').find('.status-tag').text()).toBe('正常')
  })

  it('「再読み込み」で取り直す', async () => {
    const view = await mountStale()
    const before = view.polls()
    stub.respondWith(jsonResponse(dashboard.allNormal()))

    await view.button('再読み込み').trigger('click')
    await flushPromises()

    expect(view.polls()).toBe(before + 1)
    expect(view.wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('自動更新の失敗では、通知(スナックバー)を出さない。ページ内の警告に留める', async () => {
    await mountStale()
    await elapse(30_000)

    expect(document.querySelector('.v-snackbar')).toBeNull()
  })
})

describe('D1: 手動の更新と自動更新', () => {
  it('「更新」で取り直す。更新中も表示は消さない', async () => {
    const view = await mountDashboard()
    expect(view.polls()).toBe(1)

    stub.respondWith({ kind: 'hang' })
    await view.button('更新').trigger('click')
    await flushPromises()

    expect(view.polls()).toBe(2)
    expect(view.summary().exists()).toBe(true)
    expect(view.wrapper.find('.top-progress').attributes('aria-label')).toBe('更新中')
  })

  it('取得済みの画面でも、更新中に「更新」を重ねて押して、進行中の取得をやり直さない(キャンセルして取り直さない)', async () => {
    const view = await mountDashboard()
    stub.respondWith({ kind: 'hang' })

    await view.button('更新').trigger('click')
    await view.button('更新').trigger('click')
    await view.button('更新').trigger('click')
    await flushPromises()

    expect(view.polls()).toBe(2)
  })

  it('初回の取得中に「更新」を押しても、取得を重ねない(二重送信しない)', async () => {
    const view = await mountDashboard({ kind: 'hang' })
    expect(view.polls()).toBe(1)

    await view.button('更新').trigger('click')
    await view.button('更新').trigger('click')
    await flushPromises()

    expect(view.polls()).toBe(1)
  })

  it('30 秒ごとに取り直す(29.999 秒では取り直さない)', async () => {
    const view = await mountDashboard()

    await elapse(29_999)
    expect(view.polls()).toBe(1)
    await elapse(1)
    expect(view.polls()).toBe(2)
    await elapse(30_000)
    expect(view.polls()).toBe(3)
  })

  it('スイッチをオフにすると止まり、「自動更新は停止中です。…」を出す。オンに戻すと再開する', async () => {
    const view = await mountDashboard()

    await view.switchInput().setValue(false)
    expect(view.wrapper.text()).toContain(
      '自動更新は停止中です。「更新」で最新の状態を取得します。',
    )
    await elapse(120_000)
    expect(view.polls()).toBe(1)

    await view.switchInput().setValue(true)
    expect(view.wrapper.text()).not.toContain('自動更新は停止中です')
    await elapse(30_000)
    expect(view.polls()).toBe(2)
  })

  it('オフでも、手動の「更新」は取得する', async () => {
    const view = await mountDashboard()
    await view.switchInput().setValue(false)

    await clickUpdate(view)

    expect(view.polls()).toBe(2)
  })

  it('タブが見えない間は止める。見えるようになったら再開する', async () => {
    const view = await mountDashboard()

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
    await elapse(90_000)
    expect(view.polls()).toBe(1)

    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
    await elapse(30_000)
    expect(view.polls()).toBeGreaterThan(1)
  })

  it('スイッチの状態は保存しない(画面を作り直すと、既定のオン)', async () => {
    const first = await mountDashboard()
    await first.switchInput().setValue(false)
    first.wrapper.unmount()

    const second = await mountDashboard()

    expect((second.switchInput().element as HTMLInputElement).checked).toBe(true)
  })
})

describe('D1: 手動の更新の結果の読み上げ(dashboard 3.4・DS 8)', () => {
  const statusOf = (wrapper: VueWrapper) => wrapper.findAll('p[role="status"]').map((p) => p.text())

  it('「更新」を押した直後だけ、隠した role=status に「更新しました。異常 N 件、判定不能 M 件」を出す', async () => {
    const view = await mountDashboard(jsonResponse(dashboard.mixed()))
    expect(statusOf(view.wrapper).join('')).toBe('')

    await clickUpdate(view)

    expect(statusOf(view.wrapper)).toContain('更新しました。異常 1 件、判定不能 1 件')
    expect(view.wrapper.findAll('p[role="status"]').at(-1)!.classes()).toContain('sr-only')
  })

  it('自動更新の結果は読み上げない(次の取得が成功したら消える)', async () => {
    const view = await mountDashboard(jsonResponse(dashboard.abnormal()))
    await clickUpdate(view)
    expect(statusOf(view.wrapper)).toContain('更新しました。異常 1 件、判定不能 0 件')

    await elapse(30_000)

    expect(statusOf(view.wrapper).join('')).toBe('')
  })

  it('更新に失敗したときは読み上げない(警告のほうが変わる)', async () => {
    const view = await mountDashboard()
    stub.respondWith(apiErrorResponse(500, 'internal_error'))

    await clickUpdate(view)

    expect(statusOf(view.wrapper).join('')).toBe('')
  })

  it('概況そのものは role=status ではない(自動更新のたびに読み上げさせない)', async () => {
    const { summary } = await mountDashboard()

    expect(summary().attributes('role')).toBeUndefined()
    expect(summary().find('[role="status"]').exists()).toBe(false)
  })
})
