// シェル・ルーティングの E2E(API はモック。E 10.2・F 7.2「router・shell」): ナビ、840px の境のサイドバー、
// SPA 内の 404、遷移後の h1 へのフォーカスとタイトル、スキップリンク、外部リンク領域の表示・非表示。
// 各画面の中身は後続のフェーズ(いまはスタブページ)。
import type { Page } from '@playwright/test'

import type { MetaResponse } from '@/admin/api'

import { apiErrorResponse, jsonResponse } from '../support/apiErrors'
import { expect, test } from '../support/e2eTest'
import { meta } from '../support/fixtures/meta'
import { mockApi } from '../support/mockApi'

/** シェルは `GET /meta`(EP-14)を取る。外部リンク領域の出し分けを、テストごとに決める。 */
async function mockMeta(page: Page, body: MetaResponse | null = null) {
  await mockApi(page, {
    'GET /meta': body === null ? apiErrorResponse(503, 'unavailable') : jsonResponse(body),
  })
}

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

      await page.keyboard.press('Escape')
      await expectDrawerClosed(page)
      // 閉じたら、フォーカスはメニューのボタンへ戻る(DS 8)
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

  test('全 route(D1・S1〜S4・J1・J2・X1・O1)が開く', async ({ page }) => {
    await mockMeta(page, meta.noDashboards())
    const cases: [string, string][] = [
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
    for (const [path, heading] of cases) {
      await page.goto(path)

      await expect(page.getByRole('heading', { level: 1 }), path).toHaveText(heading)
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)
    }
  })
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
    const api = await mockApi(page, { 'GET /meta': jsonResponse(meta.normal()) })
    await page.goto('./')
    await expect(sideNav(page).getByRole('link', { name: /OpenSearch Dashboards/ })).toBeVisible()

    await sideNav(page).getByRole('link', { name: 'ジョブ' }).click()
    await sideNav(page).getByRole('link', { name: 'データソース' }).click()

    expect(api.callCount('GET /meta')).toBe(1)
  })
})

test.describe('外部通信と相対パス', () => {
  test('同一オリジン以外への要求は 0 件(外部フォント・CDN を使わない。DS 3.1)', async ({
    page,
  }) => {
    const external: string[] = []
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (!['localhost:15173'].includes(url.host) && url.protocol.startsWith('http')) {
        external.push(request.url())
      }
    })
    await mockMeta(page, meta.normal())

    for (const path of ['./', 'sources', 'jobs/job-0001', 'no/such/page']) await page.goto(path)

    expect(external).toEqual([])
  })

  test('FARC-U-8: 先頭にスラッシュのない相対パスの goto は、baseURL(/admin/)の下に解決される', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    await page.goto('sources')

    expect(page.url()).toBe('http://localhost:15173/admin/sources')
  })

  test('FARC-U-8: スラッシュで始まるパスは、/admin を落として origin 直下に解決される(使わない)', async ({
    page,
  }) => {
    await mockMeta(page, meta.noDashboards())

    const response = await page.goto('/sources')

    expect(page.url()).toBe('http://localhost:15173/sources')
    // dev サーバーは /admin/ の外を配信しない(Vite の base)
    expect(response?.status()).not.toBe(200)
  })

  test('FARC-U-8: request フィクスチャの相対パスも、baseURL(/admin/)の下に解決される', async ({
    request,
  }) => {
    const response = await request.get('src/shared/theme/global.css')

    expect(response.url()).toBe('http://localhost:15173/admin/src/shared/theme/global.css')
    expect(response.status()).toBe(200)
  })
})
