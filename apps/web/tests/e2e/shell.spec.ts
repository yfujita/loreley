// シェル・ルーティングの E2E(API はモック。E 10.2・F 7.2「router・shell」): ナビ、840px の境のサイドバー、
// SPA 内の 404、遷移後の h1 へのフォーカスとタイトル、スキップリンク、外部リンク領域の表示・非表示。
// 各画面の中身は後続のフェーズ(いまはスタブページ)。
import type { Page } from '@playwright/test'

import type { MetaResponse } from '@/admin/api'

import { apiErrorResponse, jsonResponse } from '../support/apiErrors'
import { expect, test } from '../support/e2eTest'
import { E2E_BASE_URL, E2E_HOST } from '../support/e2eServer'
import { dashboard } from '../support/fixtures/dashboard'
import { meta } from '../support/fixtures/meta'
import { opensearch } from '../support/fixtures/opensearch'
import { mockApi } from '../support/mockApi'

/**
 * シェルは `GET /meta`(EP-14)を取る。外部リンク領域の出し分けを、テストごとに決める。
 * 画面(D1・O1)は、シェルのテストが移動しても要求が漏れないよう、固定の応答を返す(画面の中身はここでは確かめない)。
 */
async function mockMeta(page: Page, body: MetaResponse | null = null) {
  await mockApi(page, {
    'GET /meta': body === null ? apiErrorResponse(503, 'unavailable') : jsonResponse(body),
    ...SCREEN_RESPONSES,
  })
}

const SCREEN_RESPONSES = {
  'GET /dashboard': jsonResponse(dashboard.allNormal()),
  'GET /opensearch/cluster': jsonResponse(opensearch.green()),
} as const

const sideNav = (page: Page) => page.getByRole('navigation', { name: 'メインメニュー' })

// 一時表示(幅 840px 未満)のドロワーは、閉じていても DOM に残り、画面の外へ退く(`display: none` ではない)。
// 閉じている間は `inert` で、フォーカスも読み上げも届かない(Vuetify 4.3.4 の実挙動)。
async function expectDrawerOpen(page: Page) {
  await expect(sideNav(page)).not.toHaveAttribute('inert', '')
  await expect(sideNav(page)).toBeInViewport()
}
async function expectDrawerClosed(page: Page) {
  await expect(sideNav(page)).toHaveAttribute('inert', '')
  await expect(sideNav(page)).not.toBeInViewport()
}

test.describe('ナビ(DS 5.1・5.3)', () => {
  test('route の meta から、5 項目を 3 グループ(区切り線 2 本)で出す。現在地は aria-current', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    const items = sideNav(page).getByRole('link')
    await expect(items).toHaveText([
      'ダッシュボード',
      'データソース',
      'ジョブ',
      '文書の確認',
      'OpenSearch',
    ])
    await expect(sideNav(page).locator('hr')).toHaveCount(2)
    await expect(sideNav(page).getByRole('link', { name: 'データソース' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    await expect(sideNav(page).locator('[aria-current]')).toHaveCount(1)
  })

  test('項目を選ぶと、その画面(h1・URL・タイトル)へ移り、現在地の強調も移る', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('./')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')

    const cases: [string, string, string][] = [
      ['データソース', 'sources', 'データソース'],
      ['ジョブ', 'jobs', 'ジョブ'],
      ['文書の確認', 'documents', '文書の確認'],
      ['OpenSearch', 'opensearch', 'OpenSearch'],
      ['ダッシュボード', '', 'ダッシュボード'],
    ]
    for (const [label, path, heading] of cases) {
      await sideNav(page).getByRole('link', { name: label }).click()

      await expect(page).toHaveURL(new RegExp(`/admin/${path}$`))
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
      await expect(page).toHaveTitle(`${heading} - Loreley 管理`)
      await expect(sideNav(page).locator('[aria-current]')).toHaveText(label)
    }
  })

  test('詳細・編集の画面でも、親のナビ項目(データソース)を強調する。パンくずは 2 階層以上だけ', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    await page.goto('sources/demo-handbook/edit')
    await expect(sideNav(page).locator('[aria-current]')).toHaveText('データソース')
    const crumbs = page.getByRole('navigation', { name: 'パンくず' })
    await expect(crumbs.getByRole('link')).toHaveText(['データソース', 'demo-handbook'])
    await expect(crumbs.locator('[aria-current="page"]')).toHaveText('編集')

    await page.goto('sources')
    await expect(page.getByRole('navigation', { name: 'パンくず' })).toHaveCount(0)
  })
})

test.describe('840px の境(DS 5.1・7。FARC-U-14)', () => {
  const viewport = (width: number) => ({ width, height: 800 })

  for (const width of [840, 1024, 1144, 1280]) {
    test(`幅 ${width}px: サイドバーは常時表示で、上部バー(メニューのボタン)はない`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport(width))
      await mockMeta(page, meta.noDashboards())
      await page.goto('sources')

      await expectDrawerOpen(page)
      await expect(page.getByRole('button', { name: 'メニューを開く' })).toHaveCount(0)
      const box = await sideNav(page).boundingBox()
      expect(box?.width).toBe(232)
      // コンテンツは、サイドバーの右に置かれる(重ならない)。
      const heading = await page.getByRole('heading', { level: 1 }).boundingBox()
      expect(heading?.x).toBeGreaterThanOrEqual(232)
    })
  }

  for (const width of [839, 768, 375]) {
    test(`幅 ${width}px: 上部バーのボタンでドロワーを開く(一時表示)。Esc・メニューのボタン・項目の選択で閉じる`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport(width))
      await mockMeta(page, meta.noDashboards())
      await page.goto('sources')
      const menu = page.getByRole('button', { name: 'メニューを開く' })

      await expect(menu).toBeVisible()
      await expectDrawerClosed(page)
      await expect(menu).toHaveAttribute('aria-expanded', 'false')

      await menu.click()
      await expectDrawerOpen(page)
      await expect(menu).toHaveAttribute('aria-expanded', 'true')

      // フォーカスがドロワーの中(ナビのリンク)にある状態から Esc で閉じる。閉じたら、メニューのボタンへ戻る(DS 8)
      await page.keyboard.press('Tab')
      await expect(sideNav(page).getByRole('link', { name: 'データソース' })).toBeFocused()
      await page.keyboard.press('Escape')
      await expectDrawerClosed(page)
      await expect(menu).toBeFocused()

      await menu.click()
      await expectDrawerOpen(page)
      await menu.click()
      await expectDrawerClosed(page)

      await menu.click()
      await sideNav(page).getByRole('link', { name: 'ジョブ' }).click()
      await expect(page).toHaveURL(/\/admin\/jobs$/)
      await expectDrawerClosed(page)
    })
  }

  for (const width of [839, 768, 375]) {
    test(`幅 ${width}px: 開くとフォーカスがドロワーの中に入り、Tab・Shift+Tab はドロワーの中を循環して、本文・スキップリンクへ抜けない(DS 8)`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport(width))
      await mockMeta(page, meta.noDashboards())
      await page.goto('no/such/page')
      const links = sideNav(page).getByRole('link')
      const inDrawer = () =>
        page.evaluate(() =>
          document.querySelector('nav.v-navigation-drawer')?.contains(document.activeElement),
        )

      await page.getByRole('button', { name: 'メニューを開く' }).click()
      await expectDrawerOpen(page)
      await expect(links.first()).toBeFocused()
      // 幅は 272px(DS 5.1 のモバイル。デスクトップの 232px とは別)
      expect((await sideNav(page).boundingBox())?.width).toBeCloseTo(272, 0)

      for (let i = 0; i < 12; i++) {
        await page.keyboard.press('Tab')
        expect(await inDrawer(), `Tab ${i + 1} 回目`).toBe(true)
      }
      for (let i = 0; i < 12; i++) {
        await page.keyboard.press('Shift+Tab')
        expect(await inDrawer(), `Shift+Tab ${i + 1} 回目`).toBe(true)
      }
      // 5 つのリンクを 1 周すると、最初に戻る(循環)
      await links.first().focus()
      for (let i = 0; i < 5; i++) await page.keyboard.press('Tab')
      await expect(links.first()).toBeFocused()
    })
  }

  for (const width of [840, 1280]) {
    test(`幅 ${width}px(常時表示): Tab は奪われず、ナビを抜けて本文のリンクへ進める`, async ({
      page,
    }) => {
      await page.setViewportSize(viewport(width))
      await mockMeta(page, meta.noDashboards())
      await page.goto('no/such/page')

      await page.keyboard.press('Tab')
      await expect(page.getByRole('link', { name: 'メインコンテンツへ移動' })).toBeFocused()
      for (let i = 0; i < 5; i++) await page.keyboard.press('Tab')
      await expect(sideNav(page).getByRole('link', { name: 'OpenSearch' })).toBeFocused()
      await page.keyboard.press('Tab')

      await expect(page.getByRole('link', { name: 'ダッシュボードへ戻る' })).toBeFocused()
    })
  }

  test('スクリム(背面)を押して閉じても、フォーカスはメニューのボタンへ戻る(DS 8)', async ({
    page,
  }) => {
    await page.setViewportSize(viewport(700))
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')
    const menu = page.getByRole('button', { name: 'メニューを開く' })
    await menu.click()
    await expectDrawerOpen(page)
    await expect(sideNav(page).getByRole('link').first()).toBeFocused()

    // ドロワー(幅 272px)の外側のスクリムを押す
    await page.mouse.click(600, 400)

    await expectDrawerClosed(page)
    await expect(menu).toBeFocused()
  })

  test('Esc 以外のキー(Tab・Enter・a)では、ドロワーは閉じない', async ({ page }) => {
    await page.setViewportSize(viewport(700))
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')
    await page.getByRole('button', { name: 'メニューを開く' }).click()
    await expectDrawerOpen(page)

    await page.keyboard.press('Tab')
    await page.keyboard.press('a')
    await page.keyboard.press('Space')

    await expectDrawerOpen(page)
  })

  test('ウィンドウ幅の変化(840px 未満へのリサイズ)で、何も操作していなければ、メニューのボタンにフォーカス(リング)が移らない', async ({
    page,
  }) => {
    await page.setViewportSize(viewport(1280))
    await mockMeta(page, meta.noDashboards())
    await page.goto('no/such/page')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())

    await page.setViewportSize(viewport(700))
    await expect(page.getByRole('button', { name: 'メニューを開く' })).toBeVisible()
    await expectDrawerClosed(page)

    await expect(page.getByRole('button', { name: 'メニューを開く' })).not.toBeFocused()
    expect(await page.evaluate(() => document.activeElement === document.body)).toBe(true)
  })

  test('ウィンドウ幅の変化で閉じるとき、フォーカスがドロワーの中にあったときだけ、メニューのボタンへ戻る', async ({
    page,
  }) => {
    await page.setViewportSize(viewport(1280))
    await mockMeta(page, meta.noDashboards())
    await page.goto('no/such/page')
    await sideNav(page).getByRole('link', { name: 'ジョブ' }).focus()

    await page.setViewportSize(viewport(700))

    await expect(page.getByRole('button', { name: 'メニューを開く' })).toBeFocused()
  })

  test('ウィンドウ幅の変化(840px 未満へのリサイズ)で、入力欄など本文のフォーカスを奪わない', async ({
    page,
  }) => {
    await page.setViewportSize(viewport(1000))
    await mockMeta(page, meta.noDashboards())
    await page.goto('no/such/page')
    const back = page.getByRole('link', { name: 'ダッシュボードへ戻る' })
    await back.focus()

    await page.setViewportSize(viewport(700))
    await expect(page.getByRole('button', { name: 'メニューを開く' })).toBeVisible()

    await expect(back).toBeFocused()
  })

  test('ページ全体の横スクロールはない(375・768・840・1024・1280px)', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    for (const width of [375, 768, 840, 1024, 1280]) {
      await page.setViewportSize(viewport(width))
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow, `${width}px`).toBeLessThanOrEqual(0)
    }
  })

  test('幅を変えると、サイドバーの表示が切り替わる(839 ↔ 840)', async ({ page }) => {
    await page.setViewportSize(viewport(1000))
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')
    await expect(sideNav(page)).toBeVisible()

    await page.setViewportSize(viewport(839))
    await expect(page.getByRole('button', { name: 'メニューを開く' })).toBeVisible()
    await expectDrawerClosed(page)

    await page.setViewportSize(viewport(840))
    await expectDrawerOpen(page)
    await expect(page.getByRole('button', { name: 'メニューを開く' })).toHaveCount(0)
  })
})

test.describe('SPA 内の 404(admin-view 4.2)', () => {
  test('未定義の URL は、シェルのまま「ページが見つかりません」を出す(タイトル・ダッシュボードへの導線)', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    await page.goto('no/such/page')

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ページが見つかりません')
    await expect(page).toHaveTitle('ページが見つかりません - Loreley 管理')
    // 「ページが見つかりません」は h1 の 1 回だけ。ブロックの見出しは次の行動(同じ文を 2 回出さない)
    await expect(page.getByRole('main').getByText('ページが見つかりません')).toHaveCount(1)
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('URL を確認してください')
    await expect(sideNav(page)).toBeVisible()
    await expect(sideNav(page).locator('[aria-current]')).toHaveCount(0)
    await page.getByRole('link', { name: 'ダッシュボードへ戻る' }).click()
    await expect(page).toHaveURL(/\/admin\/$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')
  })

  test('/sources/new は識別子ではなく登録の画面。深い未定義の URL も 404', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())

    await page.goto('sources/new')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('データソースを登録')

    await page.goto('sources/a/b/c/d')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ページが見つかりません')
  })

  // route ごとに 1 件のテストにする(1 件に詰めると、負荷のかかった CI で時間切れになる)。
  const ROUTE_CASES: [string, string][] = [
    ['./', 'ダッシュボード'],
    ['sources', 'データソース'],
    ['sources/new', 'データソースを登録'],
    ['sources/demo-handbook', 'demo-handbook'],
    ['sources/demo-handbook/edit', '編集'],
    ['jobs', 'ジョブ'],
    ['jobs/job-0001', 'job-0001'],
    ['documents', '文書の確認'],
    ['opensearch', 'OpenSearch'],
  ]
  for (const [path, heading] of ROUTE_CASES) {
    test(`route「${path}」が開き、h1 は 1 つで「${heading}」`, async ({ page }) => {
      await mockMeta(page, meta.noDashboards())

      await page.goto(path)

      await expect(page.getByRole('heading', { level: 1 })).toHaveText(heading)
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    })
  }
})

test.describe('遷移後の h1 へのフォーカスとタイトル(E 4.5・DS 8。FMOD-U-10)', () => {
  test('ナビで画面が変わると、フォーカスが h1 に移り、タイトルが更新される', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('./')

    await sideNav(page).getByRole('link', { name: 'ジョブ' }).click()

    await expect(page.getByRole('heading', { level: 1, name: 'ジョブ' })).toBeFocused()
    await expect(page).toHaveTitle('ジョブ - Loreley 管理')
  })

  test('動的な見出し(識別子)も、h1 とタイトルに反映する。URL の特別な文字は復号する', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    await page.goto('sources/a%2Fb%3F%20c')

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('a/b? c')
    await expect(page).toHaveTitle('a/b? c - Loreley 管理')
  })

  test('最初の表示ではフォーカスを動かさない(スキップリンクが先頭のまま)。タイトルは更新する', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    await page.goto('jobs')

    await expect(page).toHaveTitle('ジョブ - Loreley 管理')
    await expect(page.getByRole('heading', { level: 1 })).not.toBeFocused()
    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'メインコンテンツへ移動' })).toBeFocused()
  })

  test('クエリだけの変化(ページ・並べ替え)では、フォーカスを動かさず、スクロールもしない', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 400 })
    await mockMeta(page, meta.noDashboards())
    await page.goto('jobs')
    const link = sideNav(page).getByRole('link', { name: 'ダッシュボード' })
    await link.focus()
    await page.evaluate(() => {
      document.body.style.minHeight = '3000px'
      window.scrollTo(0, 300)
    })

    // ブラウザの履歴を直接動かして、クエリだけを変える(ページ側の URL 同期と同じ遷移)。
    await page.evaluate(() => {
      history.pushState({}, '', `${location.pathname}?page=2&sort=-queued_at`)
      window.dispatchEvent(new PopStateEvent('popstate', { state: history.state }))
    })
    await expect(page).toHaveURL(/\?page=2&sort=-queued_at$/)

    await expect(link).toBeFocused()
    expect(await page.evaluate(() => window.scrollY)).toBe(300)
  })

  test('画面が変わると、先頭へスクロールする', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 400 })
    await mockMeta(page, meta.noDashboards())
    await page.goto('jobs')
    await page.evaluate(() => {
      document.body.style.minHeight = '3000px'
      window.scrollTo(0, 500)
    })
    expect(await page.evaluate(() => window.scrollY)).toBe(500)

    await sideNav(page).getByRole('link', { name: 'ダッシュボード' }).click()

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
  })
})

test.describe('スキップリンクとランドマーク(DS 8)', () => {
  test('先頭の Tab でスキップリンクが現れ、Enter で本文(main)にフォーカスが移る', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')
    const skip = page.getByRole('link', { name: 'メインコンテンツへ移動' })

    // フォーカスされるまでは、画面の外にある。
    expect((await skip.boundingBox())?.y).toBeLessThan(0)
    await page.keyboard.press('Tab')

    await expect(skip).toBeFocused()
    expect((await skip.boundingBox())?.y).toBeGreaterThanOrEqual(0)

    await page.keyboard.press('Enter')

    await expect(page.getByRole('main')).toBeFocused()
    await expect(page).toHaveURL(/\/admin\/sources$/)
  })

  test('main は 1 つ。ナビは「メインメニュー」。<html lang="ja">', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    await expect(page.getByRole('main')).toHaveCount(1)
    await expect(sideNav(page)).toHaveCount(1)
    await expect(page.locator('html')).toHaveAttribute('lang', 'ja')
  })

  test('フォーカスの順序: スキップリンク → ナビ → 本文', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    await page.keyboard.press('Tab')
    await expect(page.getByRole('link', { name: 'メインコンテンツへ移動' })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(sideNav(page).getByRole('link', { name: 'ダッシュボード' })).toBeFocused()
  })
})

test.describe('favicon', () => {
  test('<link rel="icon"> はインライン(data URI)。/favicon.ico を要求せず、コンソールエラー・失敗した要求がない', async ({
    page,
  }) => {
    const consoleErrors: string[] = []
    const failedRequests: string[] = []
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text())
    })
    page.on('requestfailed', (request) => failedRequests.push(request.url()))
    page.on('response', (response) => {
      if (response.status() >= 400) failedRequests.push(`${response.status()} ${response.url()}`)
    })
    const requested: string[] = []
    page.on('request', (request) => requested.push(new URL(request.url()).pathname))
    await mockMeta(page, meta.noDashboards())

    await page.goto('./')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await page.waitForLoadState('networkidle')

    await expect(page.locator('link[rel="icon"]')).toHaveAttribute('href', /^data:image\/svg\+xml,/)
    expect(requested).not.toContain('/favicon.ico')
    expect(failedRequests).toEqual([])
    expect(consoleErrors).toEqual([])
  })
})

test.describe('外部リンク領域(AF-20)', () => {
  test('Dashboards が設定されていれば、下端に表示する(別タブ・noopener・視覚的に隠した「別タブで開く」)', async ({
    page,
  }) => {
    await mockMeta(page, meta.normal())
    await page.goto('./')

    const link = sideNav(page).getByRole('link', { name: /OpenSearch Dashboards/ })

    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute('href', 'http://localhost:5601')
    await expect(link).toHaveAttribute('target', '_blank')
    await expect(link).toHaveAttribute('rel', 'noopener')
    await expect(link).toContainText('(別タブで開く)')
    // ほかのナビ項目の下にある(下端)
    const nav = await sideNav(page).boundingBox()
    const box = await link.boundingBox()
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeGreaterThan(
      (nav?.y ?? 0) + (nav?.height ?? 0) - 40,
    )
  })

  test('未設定(null)なら、領域ごと出さない', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('./')

    await expect(sideNav(page).getByRole('link')).toHaveCount(5)
    await expect(page.getByText('OpenSearch Dashboards')).toHaveCount(0)
  })

  test('EP-14 が失敗しても、領域を出さず、ナビは止めない', async ({ page }) => {
    await mockMeta(page, null)
    await page.goto('./')

    await expect(sideNav(page).getByRole('link')).toHaveCount(5)
    await expect(page.getByText('OpenSearch Dashboards')).toHaveCount(0)
  })

  test('/meta は、どの画面でも 1 回だけ取る(シェルの EP-14。画面を移っても取り直さない)', async ({
    page,
  }) => {
    const api = await mockApi(page, {
      'GET /meta': jsonResponse(meta.normal()),
      ...SCREEN_RESPONSES,
    })
    await page.goto('./')
    await expect(sideNav(page).getByRole('link', { name: /OpenSearch Dashboards/ })).toBeVisible()

    await sideNav(page).getByRole('link', { name: 'ジョブ' }).click()
    await sideNav(page).getByRole('link', { name: 'データソース' }).click()

    expect(api.callCount('GET /meta')).toBe(1)
  })
})

test.describe('外部通信と相対パス', () => {
  for (const path of ['./', 'sources', 'jobs/job-0001', 'opensearch', 'no/such/page']) {
    test(`同一オリジン以外への要求は 0 件(外部フォント・CDN を使わない。DS 3.1): ${path}`, async ({
      page,
    }) => {
      const external: string[] = []
      page.on('request', (request) => {
        const url = new URL(request.url())
        if (url.host !== E2E_HOST && url.protocol.startsWith('http')) external.push(request.url())
      })
      await mockMeta(page, meta.normal())

      await page.goto(path)
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()

      expect(external).toEqual([])
    })
  }

  test('FARC-U-8: 先頭にスラッシュのない相対パスの goto は、baseURL(/admin/)の下に解決される', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    await page.goto('sources')

    expect(page.url()).toBe(`${E2E_BASE_URL}sources`)
  })

  test('FARC-U-8: スラッシュで始まるパスは、/admin を落として origin 直下に解決される(使わない)', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    const response = await page.goto('/sources')

    expect(page.url()).toBe(`http://${E2E_HOST}/sources`)
    // dev サーバーは /admin/ の外を配信しない(Vite の base)
    expect(response?.status()).not.toBe(200)
  })

  test('FARC-U-8: request フィクスチャの相対パスも、baseURL(/admin/)の下に解決される', async ({
    request,
  }) => {
    const response = await request.get('src/shared/theme/global.css')

    expect(response.url()).toBe(`${E2E_BASE_URL}src/shared/theme/global.css`)
    expect(response.status()).toBe(200)
  })
})

/** `getComputedStyle` の色は `rgb(…)` と `color(srgb …)` の両方がありうる。`rgb(r, g, b)` にそろえる。 */
function toRgb(value: string): string {
  const srgb = value.match(/^color\(srgb ([\d.]+) ([\d.]+) ([\d.]+)/)
  if (srgb === null) return value
  const [r, g, b] = [srgb[1], srgb[2], srgb[3]].map((channel) => Math.round(Number(channel) * 255))
  return `rgb(${r}, ${g}, ${b})`
}

test.describe('スタイル(global.css・scoped CSS の優先関係)', () => {
  /** 画面にまだない部品(進行バー・スケルトン)の scoped CSS を、ページの CSS から探して、同じ属性を付けた要素で検査する。 */
  async function animationNameOf(page: Page, className: string): Promise<string> {
    return page.evaluate((name) => {
      const css = [...document.styleSheets].flatMap((sheet) =>
        [...sheet.cssRules].map((rule) => rule.cssText),
      )
      const scoped = css.join('\n').match(new RegExp(`\\.${name}\\[(data-v-[a-z0-9]+)\\]`))
      const element = document.createElement('div')
      element.className = name
      if (scoped?.[1] !== undefined) element.setAttribute(scoped[1], '')
      const parent = document.createElement('div')
      parent.className = 'top-progress'
      if (scoped?.[1] !== undefined) parent.setAttribute(scoped[1], '')
      parent.append(element)
      document.body.append(parent)
      return getComputedStyle(element).animationName
    }, className)
  }

  test('prefers-reduced-motion: reduce で、進行バーのアニメーションが止まり、静止した帯になる', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')
    expect(await animationNameOf(page, 'top-progress__bar')).not.toBe('none')

    await page.emulateMedia({ reducedMotion: 'reduce' })

    expect(await animationNameOf(page, 'top-progress__bar')).toBe('none')
  })

  test('prefers-reduced-motion: reduce で、スケルトンの光沢が止まる', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')
    const shimmer = () =>
      page.evaluate(() => {
        const element = document.createElement('span')
        element.className = 'skeleton-line'
        document.body.append(element)
        return getComputedStyle(element).animationName
      })
    expect(await shimmer()).not.toBe('none')

    await page.emulateMedia({ reducedMotion: 'reduce' })

    expect(await shimmer()).toBe('none')
  })

  test('リンクの色(DS 2.1): ナビは本文色、現在地は本文色の太字、パンくずと本文中のリンクは primary', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources/demo-handbook')
    const color = (locator: ReturnType<Page['locator']>) =>
      locator.evaluate((element) => getComputedStyle(element).color)

    expect(await color(sideNav(page).getByRole('link', { name: 'ジョブ' }))).toBe('rgb(26, 37, 48)')
    expect(await color(sideNav(page).getByRole('link', { name: 'データソース' }))).toBe(
      'rgb(26, 37, 48)',
    )
    expect(await color(page.getByRole('navigation', { name: 'パンくず' }).getByRole('link'))).toBe(
      'rgb(29, 91, 135)',
    )

    await page.goto('no/such/page')
    expect(await color(page.getByRole('link', { name: 'ダッシュボードへ戻る' }))).toBe(
      'rgb(29, 91, 135)',
    )
  })

  test('本文中のリンクの色は、class が v- で始まる Vuetify の部品の <a> には及ばず、独自 class(nav-link・dev-link)には付く', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    const colors = await page.evaluate(() => {
      const colorOf = (className: string | null) => {
        const link = document.createElement('a')
        link.href = '#'
        if (className !== null) link.className = className
        document.body.append(link)
        return getComputedStyle(link).color
      }
      return {
        plain: colorOf(null),
        navLink: colorOf('nav-link'),
        devLink: colorOf('dev-link'),
        prevLink: colorOf('prev-link'),
        vuetify: colorOf('v-list-item'),
        vuetifySecond: colorOf('foo v-tab'),
      }
    })

    const primary = 'rgb(29, 91, 135)'
    expect(toRgb(colors.plain)).toBe(primary)
    expect(toRgb(colors.navLink)).toBe(primary)
    expect(toRgb(colors.devLink)).toBe(primary)
    expect(toRgb(colors.prevLink)).toBe(primary)
    expect(toRgb(colors.vuetify)).not.toBe(primary)
    expect(toRgb(colors.vuetifySecond)).not.toBe(primary)
  })

  test('main.ts が vuetify/styles と global.css を読み込んでいる(本文フォント・sr-only・本文色)', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())
    await page.goto('sources')

    const styles = await page.evaluate(() => {
      const app = getComputedStyle(document.querySelector('.v-application') as Element)
      const hidden = document.createElement('span')
      hidden.className = 'sr-only'
      hidden.textContent = 'x'
      document.body.append(hidden)
      const rect = hidden.getBoundingClientRect()
      return {
        font: app.fontFamily,
        size: app.fontSize,
        color: app.color,
        hiddenWidth: rect.width,
        titleSize: getComputedStyle(document.querySelector('h1') as Element).fontSize,
      }
    })

    // global.css(Vuetify の後): 本文 14px・高強調の不透明度 1(本文色 #1A2530)・sr-only・見出し 20px
    expect(styles.size).toBe('14px')
    expect(toRgb(styles.color)).toBe('rgb(26, 37, 48)')
    expect(styles.hiddenWidth).toBeLessThanOrEqual(1)
    expect(styles.titleSize).toBe('20px')
    // システムフォント(Roboto ではない)
    expect(styles.font).toContain('Hiragino Sans')
    expect(styles.font).not.toContain('Roboto')
  })
})
