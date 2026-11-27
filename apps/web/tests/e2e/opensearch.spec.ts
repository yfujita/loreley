// O1 OpenSearch の E2E(API はモック。opensearch 画面仕様・E 5.6)。
// 1 ページの列数(実ブラウザでカードの幅から決まる。FMOD-U-6)・ページ送り・絞り込みの URL 同期(replace)・stale・
// truncated・未知の状態値・読み込み中・エラー・空・一致 0 件・進行バーの reduced-motion・キーボード。
import type { Page } from '@playwright/test'

import { apiErrorResponse, hangResponse, jsonResponse } from '../support/apiErrors'
import { expect, test } from '../support/e2eTest'
import { dashboard } from '../support/fixtures/dashboard'
import { meta } from '../support/fixtures/meta'
import { opensearch } from '../support/fixtures/opensearch'
import { mockApi, type MockApi } from '../support/mockApi'

/** O1 を開く(シェルの `GET /meta` もモックする)。`path` は `opensearch` 以降(クエリ可)。 */
async function openOpenSearch(
  page: Page,
  responses: Parameters<MockApi['respond']>[1] = jsonResponse(opensearch.many()),
  path = 'opensearch',
): Promise<MockApi> {
  const api = await mockApi(page, {
    'GET /meta': jsonResponse(meta.noDashboards()),
    'GET /opensearch/cluster': responses,
    'GET /dashboard': jsonResponse(dashboard.allNormal()),
  })
  await page.goto(path)
  return api
}

const card = (page: Page) => page.getByTestId('o1-cluster')
const matrix = (page: Page) => page.getByTestId('o1-shards')
const count = (page: Page) => page.getByTestId('o1-count')
const columnHeaders = (page: Page) => matrix(page).locator('thead th.shard-matrix__index')
const nameBox = (page: Page) => page.getByRole('textbox', { name: 'インデックス名' })
const stateCheck = (page: Page, name: string) => page.getByRole('checkbox', { name })
const clearButton = (page: Page) => page.getByRole('button', { name: '条件を解除' })
const pager = (page: Page) => page.getByRole('group', { name: 'シャードの配置のページ送り' })
/** ページ選択(ボタンの aria-label にも「ページ」を含むので、完全一致で選ぶ) */
const pageSelect = (page: Page) => pager(page).getByLabel('ページ', { exact: true })
const updateButton = (page: Page) => page.getByRole('button', { name: '更新', exact: true })

/** クエリ文字列(`q`・`state`)。ページ位置(`page`)は URL に入れない。 */
const search = (page: Page) => new URL(page.url()).search

test.describe('通常の表示(1 カード「クラスタ状態」)', () => {
  test('h1「OpenSearch」とカード(h2「クラスタ状態」)。カードの中は 概況 → 絞り込みフォーム → マトリクスの順', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('OpenSearch')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText('クラスタ状態')
    await expect(card(page)).toHaveAccessibleName('クラスタ状態')
    const order = await card(page).evaluate((element) =>
      ['o1-summary', 'o1-filter', 'o1-shards'].map((id) =>
        element.innerHTML.indexOf(`data-testid="${id}"`),
      ),
    )
    expect(order).toEqual([...order].sort((a, b) => a - b))
    expect(order.every((position) => position >= 0)).toBe(true)
    await expect(page.getByTestId('o1-summary')).toContainText('yellow(注意)')
    await expect(page.getByTestId('o1-summary')).toContainText('うち移動中 1')
  })

  test('最終更新の日時と「更新」は、見出しの右に出す。「更新」は手動のみで、ポーリングはしない', async ({
    page,
  }) => {
    await page.clock.install({ time: new Date('2026-11-27T01:00:00Z') })
    const api = await openOpenSearch(page)
    await expect(count(page)).toBeVisible()
    await expect(page.locator('.o1-page__acts')).toContainText(/最終更新 2026-11-27 10:00:\d{2}/)

    await page.clock.fastForward(300_000)
    await page.evaluate(() => 0)
    expect(api.callCount('GET /opensearch/cluster')).toBe(1)

    await updateButton(page).click()
    await expect.poll(() => api.callCount('GET /opensearch/cluster')).toBe(2)
    expect(api.requests.every((request) => request.searchParams.size === 0)).toBe(true)
  })

  test('red: ページ上部に error のアラート(role=status)と、該当のインデックス・シャード番号。赤の点線のチップ', async ({
    page,
  }) => {
    await openOpenSearch(page, jsonResponse(opensearch.red()))

    const alert = page.locator('.page-alert[role="status"]')
    await expect(alert).toContainText('未割り当てのプライマリシャードがあります')
    await expect(alert).toContainText('demo-docs-000001 のプライマリシャード(P0)')
    // 凡例の見本のチップと区別するため、表の中(tbody)だけを数える
    await expect(matrix(page).locator('tbody .shard-chip--unassigned-primary')).toHaveCount(1)
    await expect(matrix(page).getByTestId('o1-count-demo-docs-000001')).toContainText('—')
    await expect(matrix(page).getByText('見出しの「—」は件数を取得できません。')).toBeVisible()
  })

  test('red のアラートは絞り込みの対象外(red のインデックスを除外する条件でも残る)', async ({
    page,
  }) => {
    await openOpenSearch(page, jsonResponse(opensearch.red()))
    const alert = page.locator('.page-alert[role="status"]')
    await expect(alert).toContainText('demo-docs-000001 のプライマリシャード(P0)')

    await nameBox(page).fill('store')
    await expect(count(page)).toContainText('絞り込み後 2 件')
    await expect(columnHeaders(page).locator('.shard-matrix__index-name')).toHaveText([
      'demo-store-jobs',
      'demo-store-sources',
    ])
    await expect(alert).toContainText('demo-docs-000001 のプライマリシャード(P0)')
  })

  test('yellow: アラートは出さず、カード内の説明だけ', async ({ page }) => {
    await openOpenSearch(page, jsonResponse(opensearch.yellow()))

    await expect(page.getByTestId('o1-summary')).toContainText('通常 yellow になります')
    await expect(page.locator('.page-alert')).toHaveCount(0)
  })

  test('2 ノード・未割り当て・移動中・初期化中: 最下部に「未割り当て」の行、凡例は 5 項目', async ({
    page,
  }) => {
    await openOpenSearch(page, jsonResponse(opensearch.unassignedAndMoving()))

    await expect(matrix(page).locator('tbody tr')).toHaveCount(3)
    await expect(matrix(page).locator('tbody tr').last()).toContainText('未割り当て')
    await expect(page.getByTestId('o1-summary')).toContainText('アクティブ')
    await expect(page.getByRole('list', { name: '凡例' }).getByRole('listitem')).toHaveText([
      /プライマリ/,
      /レプリカ/,
      /未割り当てのレプリカ/,
      /初期化中・移動中/,
    ])
    // 初期化中と移動中は見た目が同じ。読み上げだけが違う
    await expect(matrix(page).locator('.shard-chip--relocating .sr-only')).toHaveText(
      '(プライマリ。移動中)',
    )
    await expect(matrix(page).locator('.shard-chip--initializing .sr-only')).toHaveText(
      '(レプリカ。初期化中)',
    )
  })

  test('未知の状態値: 中立のタグ・チップで値をそのまま出し、画面は壊れない', async ({ page }) => {
    await openOpenSearch(page, jsonResponse(opensearch.unknownValues()))

    await expect(page.getByTestId('o1-summary').locator('.status-tag')).toHaveText('purple')
    await expect(columnHeaders(page).locator('.status-tag')).toHaveText('purple')
    await expect(matrix(page).locator('.shard-chip--unknown')).toHaveCount(1)
    await expect(matrix(page).locator('.shard-chip--unknown .sr-only')).toHaveText(
      '(witness。moving)',
    )
  })

  test('状態・件数が null のインデックス: 「—」(件数の読み上げは「取得できません」)', async ({
    page,
  }) => {
    await openOpenSearch(page, jsonResponse(opensearch.nullIndexValues()))

    await expect(matrix(page).getByTestId('o1-count-closed-index')).toContainText(
      'ドキュメント件数を取得できません',
    )
    await expect(columnHeaders(page)).toContainText('状態を取得できません')
  })

  test('truncated=true: カード上部に warning の注記(先頭 1,000 件・全 1,500 件)。ほかは通常どおり', async ({
    page,
  }) => {
    await openOpenSearch(page, jsonResponse(opensearch.truncated()))

    await expect(card(page).locator('.o1-page__truncated')).toHaveText(
      'インデックスが多いため先頭 1,000 件だけを表示しています(全 1,500 件)。',
    )
    await expect(count(page)).toContainText('1–7 / 全 1,000 件のインデックス')
  })

  test('空(インデックス 0 件): 概況は出し、フォームは出さず、マトリクスの領域に「インデックスがありません」', async ({
    page,
  }) => {
    await openOpenSearch(page, jsonResponse(opensearch.empty()))

    await expect(page.getByTestId('o1-summary')).toBeVisible()
    await expect(page.getByTestId('o1-state-empty')).toContainText('インデックスがありません')
    await expect(page.getByTestId('o1-filter')).toHaveCount(0)
    await expect(matrix(page)).toHaveCount(0)
  })
})

test.describe('1 ページの列数(カードの幅から。実ブラウザ。FMOD-U-6)', () => {
  // opensearch 3.4 の検算表: viewport → 1 ページの列数
  for (const [width, columns] of [
    [1280, 7],
    [1145, 6],
    [1024, 5],
    [840, 3],
    [768, 5],
    [375, 2],
    [320, 1],
  ] as const) {
    test(`幅 ${width}px: 1 ページ ${columns} 列。ページ全体・表内に横スクロールが出ない`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await openOpenSearch(page)
      await expect(columnHeaders(page)).toHaveCount(columns)

      const overflow = await page.evaluate(() => ({
        page: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        scroller: (() => {
          const element = document.querySelector('.shard-matrix__scroll')
          return element === null ? 0 : element.scrollWidth - element.clientWidth
        })(),
      }))
      expect(overflow.page).toBeLessThanOrEqual(0)
      expect(overflow.scroller).toBeLessThanOrEqual(0)
      // 収まっているので、スクロール領域に tabindex・role は付かない
      await expect(page.locator('.shard-matrix__scroll')).not.toHaveAttribute('tabindex', /.*/)
      await expect(count(page)).toContainText(
        columns === 1 ? '1 / 全 25 件のインデックス' : `1–${columns} / 全 25 件のインデックス`,
      )
    })
  }

  // 行見出し列の幅 H は viewport 600px で 152px → 112px に切り替わる(DS 4.15)。W(約 565px)では、
  // H=152 なら 3 列、H=112 なら 4 列。同じ幅の差 1px で列数が変わることを実ブラウザで確かめる。
  for (const [width, columns] of [
    [600, 3],
    [599, 4],
  ] as const) {
    test(`幅 ${width}px(行見出し列の境界): 1 ページ ${columns} 列`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await openOpenSearch(page)

      await expect(columnHeaders(page)).toHaveCount(columns)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow).toBeLessThanOrEqual(0)
    })
  }

  test('ウィンドウ幅を変えると列数が追随し、表示中の先頭のインデックスを含むページになる', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await openOpenSearch(page)
    await pageSelect(page).selectOption('2')
    const head = await columnHeaders(page)
      .first()
      .locator('.shard-matrix__index-name')
      .textContent()

    await page.setViewportSize({ width: 1024, height: 900 })

    await expect(columnHeaders(page)).toHaveCount(5)
    await expect(count(page)).toContainText('6–10 /')
    await expect
      .poll(() => columnHeaders(page).locator('.shard-matrix__index-name').allTextContents())
      .toContain(head)
  })

  test('列幅は全ページ同じ。最終ページの列が少なくても、幅は変わらない', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await openOpenSearch(page)
    const widthOf = () =>
      columnHeaders(page)
        .first()
        .evaluate((element) => Math.round(element.getBoundingClientRect().width))
    const firstPage = await widthOf()

    await pageSelect(page).selectOption('4')

    await expect(columnHeaders(page)).toHaveCount(4)
    expect(await widthOf()).toBe(firstPage)
  })

  test('1 ページに収まるときは、ページ送りを出さない(インデックス 3 件・1280px)。375px では 3 件でもページ送りが出る', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await openOpenSearch(page, jsonResponse(opensearch.multiNode()))
    await expect(count(page)).toHaveText('3 件のインデックス')
    await expect(pager(page)).toHaveCount(0)

    await page.setViewportSize({ width: 375, height: 900 })

    await expect(columnHeaders(page)).toHaveCount(2)
    await expect(pager(page)).toBeVisible()
  })
})

test.describe('ページ送り', () => {
  test('前へ・次へ・ページ選択で列を切り替える。フォーカスは押したボタンに残り、ページ位置は URL に入れない', async ({
    page,
  }) => {
    await openOpenSearch(page)
    const next = pager(page).getByRole('button', { name: /^次へ/ })
    const prev = pager(page).getByRole('button', { name: /^前へ/ })
    await expect(prev).toHaveAttribute('aria-disabled', 'true')

    await next.click()

    await expect(count(page)).toContainText('8–14 / 全 25 件のインデックス')
    await expect(next).toBeFocused()
    await expect(prev).toHaveAttribute('aria-disabled', 'false')
    expect(search(page)).toBe('')

    await pageSelect(page).selectOption('4')
    await expect(count(page)).toContainText('22–25 /')
    await expect(next).toHaveAttribute('aria-disabled', 'true')
    // 使えない端のボタンは、押しても何も起きず、フォーカスを失わない
    // (Playwright は aria-disabled のボタンを押さないので、force で押して「何も起きない」を確かめる)
    await next.focus()
    await next.click({ force: true })
    await expect(count(page)).toContainText('22–25 /')
    await expect(next).toBeFocused()
  })

  test('件数表示は role=status(aria-live=polite・aria-atomic)。ページが変わったときだけ書き換わる', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await expect(count(page)).toHaveAttribute('role', 'status')
    await expect(count(page)).toHaveAttribute('aria-live', 'polite')
    await expect(count(page)).toHaveAttribute('aria-atomic', 'true')
    await expect(count(page)).toHaveText('1–7 / 全 25 件のインデックス(ページ 1 / 4)')
  })

  test('ページ送りの 3 部品は 1 つの group。ボタンの名前は見える文字を含む', async ({ page }) => {
    await openOpenSearch(page)

    await expect(
      pager(page).getByRole('button', { name: '前へ。シャードの配置の前のページ' }),
    ).toBeVisible()
    await expect(
      pager(page).getByRole('button', { name: '次へ。シャードの配置の次のページ' }),
    ).toBeVisible()
    await expect(pageSelect(page)).toHaveValue('1')
  })

  test('幅 320px でも、前へ・ページ選択・次へが 1 行に収まる(各 44px)', async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 900 })
    await openOpenSearch(page)

    const boxes = await Promise.all(
      [
        pager(page).getByRole('button', { name: /^前へ/ }),
        pageSelect(page),
        pager(page).getByRole('button', { name: /^次へ/ }),
      ].map((locator) => locator.boundingBox()),
    )
    const tops = boxes.map((box) => Math.round(box?.y ?? -1))
    expect(new Set(tops).size).toBe(1)
    expect(boxes.every((box) => (box?.height ?? 0) >= 44)).toBe(true)
  })
})

test.describe('絞り込み(URL の q・state。replace)', () => {
  test('名前: 入力から少し待って URL(q)へ反映し、一致したインデックスだけを列にする(大文字小文字を区別しない)', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await nameBox(page).fill('DOCS')

    await expect(count(page)).toHaveText('絞り込み後 3 件のインデックス(全 25 件中)')
    expect(search(page)).toBe('?q=DOCS')
    await expect(columnHeaders(page).locator('.shard-matrix__index-name')).toHaveText([
      'demo-docs-000003',
      'demo-docs-000001',
      'demo-docs-000002',
    ])
    await expect(matrix(page).getByText('適用中の条件: 名前に「DOCS」を含む。')).toBeVisible()
    // 概況は絞り込みの対象外(クラスタ全体のまま)
    await expect(page.getByTestId('o1-summary')).toContainText('yellow(注意)')
    await expect(pager(page)).toHaveCount(0)
  })

  test('状態: チェックの切替ですぐ反映(state=カンマ区切り)。yellow だけ、yellow か green(OR)', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await stateCheck(page, 'yellow').check()
    await expect(count(page)).toHaveText('絞り込み後 2 件のインデックス(全 25 件中)')
    expect(search(page)).toBe('?state=yellow')

    await stateCheck(page, 'green').check()
    await expect(count(page)).toContainText('絞り込み後 25 件のインデックス')
    expect(search(page)).toBe('?state=yellow,green')
  })

  test('3 つとも選ぶと「すべて」と同じ(絞り込み前の文言・解除は無効のまま)。チェックの表示は 3 つのまま', async ({
    page,
  }) => {
    await openOpenSearch(page)

    for (const name of ['red', 'yellow', 'green']) await stateCheck(page, name).check()

    await expect(count(page)).toHaveText('1–7 / 全 25 件のインデックス(ページ 1 / 4)')
    for (const name of ['red', 'yellow', 'green'])
      await expect(stateCheck(page, name)).toBeChecked()
    await expect(clearButton(page)).toHaveAttribute('aria-disabled', 'true')
  })

  test('URL の条件で開くと、入力・チェック・絞り込みを復元する(再読み込み・共有で再現)', async ({
    page,
  }) => {
    await openOpenSearch(page, undefined, 'opensearch?q=logs&state=yellow,green')

    await expect(nameBox(page)).toHaveValue('logs')
    await expect(stateCheck(page, 'yellow')).toBeChecked()
    await expect(stateCheck(page, 'green')).toBeChecked()
    await expect(stateCheck(page, 'red')).not.toBeChecked()
    await expect(count(page)).toHaveText(
      '1–7 / 絞り込み後 16 件のインデックス(全 25 件中)(ページ 1 / 3)',
    )

    await page.reload()
    await expect(nameBox(page)).toHaveValue('logs')
    await expect(count(page)).toContainText('絞り込み後 16 件のインデックス')
  })

  test('不正な URL(未知の state・空白だけの q)は正規化して replace する', async ({ page }) => {
    await openOpenSearch(page, undefined, 'opensearch?q=%20&state=purple,red')

    await expect.poll(() => search(page)).toBe('?state=red')
  })

  test('条件の変更は履歴を増やさない(replace)。「戻る」で O1 を開く前の画面に戻る', async ({
    page,
  }) => {
    await mockApi(page, { 'GET /dashboard': jsonResponse(dashboard.allNormal()) })
    await openOpenSearch(page)
    await page
      .getByRole('navigation', { name: 'メインメニュー' })
      .getByRole('link', { name: 'ダッシュボード' })
      .click()
    await page
      .getByRole('navigation', { name: 'メインメニュー' })
      .getByRole('link', { name: 'OpenSearch' })
      .click()
    await nameBox(page).fill('logs')
    await expect(count(page)).toContainText('絞り込み後 16 件')
    await stateCheck(page, 'green').check()
    await expect(count(page)).toContainText('絞り込み後 15 件')

    await page.goBack()

    await expect(page).toHaveURL(/\/admin\/$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')
  })

  test('条件を変えると 1 ページ目に戻る。条件が変わらない入力(空白だけ)では、ページを保つ', async ({
    page,
  }) => {
    // debounce(250ms)は時計で進める(「何も起きない」を実時間の待ちで確かめない)
    await page.clock.install()
    await openOpenSearch(page)
    await pageSelect(page).selectOption('3')
    await expect(count(page)).toContainText('15–21 /')

    await nameBox(page).fill('   ')
    await page.clock.fastForward(400)
    await expect(count(page)).toContainText('15–21 /')
    expect(search(page)).toBe('')

    await nameBox(page).fill('logs')
    await page.clock.fastForward(400)
    await expect(count(page)).toHaveText(
      '1–7 / 絞り込み後 16 件のインデックス(全 25 件中)(ページ 1 / 3)',
    )
  })

  test('絞り込み後の行見出し「シャード n」・凡例・未割り当ての行は、絞り込み後のインデックスで数える', async ({
    page,
  }) => {
    await openOpenSearch(page)
    await expect(matrix(page).locator('.shard-matrix__unassigned')).toBeVisible()

    await nameBox(page).fill('docs-000001')

    await expect(count(page)).toHaveText('絞り込み後 1 件のインデックス(全 25 件中)')
    await expect(matrix(page).locator('.shard-matrix__unassigned')).toHaveCount(0)
    await expect(page.getByRole('list', { name: '凡例' }).getByRole('listitem')).toHaveCount(2)
    await expect(matrix(page).locator('tbody th').first()).toContainText(
      '(絞り込み後のインデックスの合計)',
    )
  })

  test('一致 0 件: 件数表示は「絞り込み後 0 件のインデックス(全 25 件中)」。ブロックには解除ボタンを置かず、フォームの「条件を解除」は 1 つだけ', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await nameBox(page).fill('zzz')

    await expect(count(page)).toHaveText('絞り込み後 0 件のインデックス(全 25 件中)')
    const nomatch = page.getByTestId('o1-state-nomatch')
    await expect(nomatch).toContainText('条件に合うインデックスがありません')
    await expect(nomatch.getByRole('button')).toHaveCount(0)
    await expect(clearButton(page)).toHaveCount(1)
    await expect(matrix(page).locator('table')).toHaveCount(0)
    await expect(page.getByRole('list', { name: '凡例' })).toHaveCount(0)
    await expect(pager(page)).toHaveCount(0)
    await expect(page.getByTestId('o1-summary')).toBeVisible()
  })

  test('「条件を解除」: すべての条件を外し、名前の入力欄へフォーカスを移す。条件がないときは何も起きない', async ({
    page,
  }) => {
    await openOpenSearch(page, undefined, 'opensearch?q=logs&state=yellow')
    await expect(clearButton(page)).toHaveAttribute('aria-disabled', 'false')

    await clearButton(page).click()

    await expect(nameBox(page)).toBeFocused()
    await expect(nameBox(page)).toHaveValue('')
    await expect(stateCheck(page, 'yellow')).not.toBeChecked()
    await expect(clearButton(page)).toHaveAttribute('aria-disabled', 'true')
    await expect.poll(() => search(page)).toBe('')

    // 条件がないときは aria-disabled。Playwright は無効なボタンを押さないので、force で押して「何も起きない」を確かめる
    await clearButton(page).focus()
    await clearButton(page).click({ force: true })
    await expect(clearButton(page)).toBeFocused()
    expect(search(page)).toBe('')
  })

  test('絞り込みでは API を取り直さない(絞り込みは画面側。クエリも送らない)', async ({ page }) => {
    const api = await openOpenSearch(page)
    await expect(count(page)).toBeVisible()

    await nameBox(page).fill('logs')
    await stateCheck(page, 'yellow').check()
    await expect(count(page)).toContainText('絞り込み後')

    expect(api.callCount('GET /opensearch/cluster')).toBe(1)
  })

  test('「更新」で再取得しても、条件・入力を保つ(ページ位置は、先頭のインデックスを含むページ)', async ({
    page,
  }) => {
    const api = await openOpenSearch(page)
    await nameBox(page).fill('logs')
    await expect(count(page)).toContainText('絞り込み後 16 件')
    await pageSelect(page).selectOption('2')
    await expect(count(page)).toContainText('8–14 /')

    await updateButton(page).click()
    await expect.poll(() => api.callCount('GET /opensearch/cluster')).toBe(2)

    await expect(nameBox(page)).toHaveValue('logs')
    await expect(count(page)).toContainText('8–14 / 絞り込み後 16 件のインデックス')
  })
})

test.describe('キーボード・アクセシビリティ', () => {
  test('Tab の順は 名前 → 状態(red・yellow・green)→ 条件を解除 → 前へ → ページ選択 → 次へ。Space でチェックを切り替える', async ({
    page,
  }) => {
    await openOpenSearch(page)
    await nameBox(page).focus()

    await page.keyboard.press('Tab')
    await expect(stateCheck(page, 'red')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(stateCheck(page, 'yellow')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(stateCheck(page, 'green')).toBeFocused()
    await page.keyboard.press('Space')
    await expect(stateCheck(page, 'green')).toBeChecked()
    await page.keyboard.press('Tab')
    await expect(clearButton(page)).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(pager(page).getByRole('button', { name: /^前へ/ })).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(pageSelect(page)).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(pager(page).getByRole('button', { name: /^次へ/ })).toBeFocused()
  })

  test('チェックボックスにキーボードでフォーカスすると、ボックスの周囲に 2px のフォーカスリング(#0B57D0)が出る。12% の重ねは消える(DS 2.6)', async ({
    page,
  }) => {
    await openOpenSearch(page)
    await nameBox(page).focus()
    await page.keyboard.press('Tab')
    await expect(stateCheck(page, 'red')).toBeFocused()

    const box = page
      .locator('.index-filter__check')
      .first()
      .locator('.v-selection-control__input > .v-icon')
    await expect(box).toHaveCSS('outline-style', 'solid')
    await expect(box).toHaveCSS('outline-width', '2px')
    await expect(box).toHaveCSS('outline-color', 'rgb(11, 87, 208)')
    const overlay = await page.evaluate(
      () =>
        getComputedStyle(
          document.querySelector('.index-filter__check .v-selection-control__input')!,
          '::before',
        ).opacity,
    )
    expect(overlay).toBe('0')

    // フォーカスが移ったら、リングは消える
    await page.keyboard.press('Tab')
    await expect(box).toHaveCSS('outline-style', 'none')
  })

  test('名前の入力で Enter はすぐ絞り込む(ページは移動しない)', async ({ page }) => {
    await openOpenSearch(page)
    await nameBox(page).fill('logs')
    await nameBox(page).press('Enter')

    await expect(count(page)).toContainText('絞り込み後 16 件')
    await expect(page).toHaveURL(/\/admin\/opensearch\?q=logs$/)
  })

  test('絞り込みフォームは検索のランドマーク(role=search)、状態は fieldset+legend', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await expect(page.getByRole('search', { name: 'インデックスの絞り込み' })).toBeVisible()
    await expect(
      page.getByRole('group', { name: '状態(複数選択できます。選ばなければすべて)' }),
    ).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(1)
    await expect(page.getByRole('columnheader').first()).toHaveText('ノード')
    await expect(page.getByRole('rowheader').first()).toContainText('シャード')
  })

  test('表の読み上げ(Chromium のアクセシビリティツリー): 列見出しは 名前 → 件数 → 状態、行見出しは ノード名+シャード数、セルはチップの文字+状態(FMOD-U-6)', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await expect(page.getByRole('columnheader').nth(1)).toHaveAccessibleName(
      'demo-docs-000003 ドキュメント 8,402,117 件 yellow',
    )
    await expect(page.getByRole('rowheader').first()).toHaveAccessibleName(
      /^node-1 シャード \d+ \(全インデックスの合計\)$/,
    )
    await expect(page.getByRole('cell').first()).toHaveAccessibleName(
      /^(P0 \(プライマリ。割り当て済み\)|— シャードなし)$/,
    )
    // 件数が取得できない列(3 ページ目)は「ドキュメント件数を取得できません」
    await pageSelect(page).selectOption('3')
    await expect(
      page.getByRole('columnheader', { name: /^demo-logs-2026\.11\.16 / }),
    ).toHaveAccessibleName('demo-logs-2026.11.16 — ドキュメント件数を取得できません green')
  })

  test('行見出し(ノード)は固定(sticky)。タグ・チップは色だけに頼らず文字・アイコンを持つ', async ({
    page,
  }) => {
    await openOpenSearch(page)

    await expect(matrix(page).locator('tbody th').first()).toHaveCSS('position', 'sticky')
    // 角(thead の「ノード」)も固定(行見出しと一緒に動く)
    await expect(matrix(page).locator('thead th.shard-matrix__corner')).toHaveCSS(
      'position',
      'sticky',
    )
    await expect(matrix(page).locator('tbody .shard-chip--unassigned-replica .v-icon')).toHaveCount(
      2,
    )
    await expect(columnHeaders(page).first().locator('.status-tag')).toContainText('yellow')
  })
})

test.describe('読み込み中・エラー・取得失敗(前回データあり)', () => {
  test('読み込み中: 見出し・更新・カードの見出しは先に出し、カードの中はスケルトン。URL の条件を無効のフォームに表示する', async ({
    page,
  }) => {
    await openOpenSearch(page, hangResponse(), 'opensearch?q=logs&state=yellow')

    await expect(card(page).getByRole('heading', { level: 2, name: 'クラスタ状態' })).toBeVisible()
    await expect(card(page)).toHaveAttribute('aria-busy', 'true')
    await expect(page.getByTestId('o1-state-loading')).toHaveText('OpenSearch の状態を読み込み中')
    await expect(updateButton(page)).toBeVisible()
    await expect(page.locator('.o1-page__acts')).not.toContainText('最終更新')
    await expect(nameBox(page)).toBeDisabled()
    await expect(nameBox(page)).toHaveValue('logs')
    await expect(stateCheck(page, 'yellow')).toBeChecked()
    await expect(stateCheck(page, 'yellow')).toBeDisabled()
    await expect(page.getByTestId('o1-summary')).toHaveCount(0)
  })

  test('エラー(データなし): カードは残し、中にエラーブロック(role=alert)+再試行+「ダッシュボードを開く」。再試行で復帰する', async ({
    page,
  }) => {
    const api = await openOpenSearch(page, [
      apiErrorResponse(500, 'internal_error'),
      jsonResponse(opensearch.many()),
    ])

    const error = page.getByTestId('o1-state-error')
    await expect(error).toHaveAttribute('role', 'alert')
    await expect(card(page).getByRole('heading', { level: 2, name: 'クラスタ状態' })).toBeVisible()
    await expect(
      error.getByRole('heading', { name: 'OpenSearch の状態を取得できません' }),
    ).toBeVisible()
    await expect(error).toContainText('試行時刻')
    await expect(error.getByRole('link', { name: 'ダッシュボードを開く' })).toHaveAttribute(
      'href',
      '/admin/',
    )
    await expect(page.locator('.v-snackbar')).toHaveCount(0)

    await error.getByRole('button', { name: '再試行' }).click()

    await expect(count(page)).toBeVisible()
    await expect(error).toHaveCount(0)
    expect(api.callCount('GET /opensearch/cluster')).toBe(2)
  })

  test('「ダッシュボードを開く」で D1 へ移る', async ({ page }) => {
    await openOpenSearch(page, apiErrorResponse(500, 'internal_error'))

    await page
      .getByTestId('o1-state-error')
      .getByRole('link', { name: 'ダッシュボードを開く' })
      .click()

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')
  })

  async function openAndFail(page: Page, path = 'opensearch') {
    const api = await openOpenSearch(
      page,
      [jsonResponse(opensearch.many()), apiErrorResponse(500, 'internal_error')],
      path,
    )
    await expect(count(page)).toBeVisible()
    await updateButton(page).click()
    return api
  }

  test('前回データあり(stale): ページ上部に warning のアラート(role=alert)。カード全体を前回の値のまま出し、見出し行の右に注記(o1-state-stale)', async ({
    page,
  }) => {
    await openAndFail(page)

    const alert = page.locator('.page-alert[role="alert"]')
    await expect(alert).toContainText('最新の状態を取得できませんでした')
    await expect(alert).toContainText('クラスタの現在の状態と異なる可能性があります。')
    await expect(page.getByTestId('o1-state-stale')).toContainText(
      '前回取得時の値 · 最終更新(成功)',
    )
    await expect(card(page)).toHaveAccessibleName('クラスタ状態')
    await expect(page.getByTestId('o1-summary')).toContainText('前回取得時の値です。')
    await expect(matrix(page).locator('table')).toBeVisible()
    await expect(page.locator('.v-snackbar')).toHaveCount(0)
  })

  test('stale でも絞り込める(条件・入力は保つ)。「再読み込み」で復帰する', async ({ page }) => {
    const api = await openAndFail(page)
    await nameBox(page).fill('docs')
    await expect(count(page)).toContainText('絞り込み後 3 件')

    api.respond('GET /opensearch/cluster', jsonResponse(opensearch.many()))
    await page.getByRole('button', { name: '再読み込み' }).click()

    await expect(page.locator('.page-alert[role="alert"]')).toHaveCount(0)
    await expect(page.getByTestId('o1-state-stale')).toHaveCount(0)
    await expect(nameBox(page)).toHaveValue('docs')
    await expect(count(page)).toContainText('絞り込み後 3 件')
  })

  test('再取得中: 表示は消えず、カード上端に進行バー(更新中)。reduced-motion では動きを止める', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await openOpenSearch(page, [jsonResponse(opensearch.many()), hangResponse()])
    await expect(count(page)).toBeVisible()

    await updateButton(page).click()

    const bar = card(page).locator('.top-progress__bar')
    await expect(card(page).getByRole('progressbar', { name: '更新中' })).toBeVisible()
    await expect(matrix(page).locator('table')).toBeVisible()
    await expect(bar).toHaveCSS('animation-name', 'progress-slide')

    await page.emulateMedia({ reducedMotion: 'reduce' })

    await expect(bar).toHaveCSS('animation-name', 'none')
  })
})

test.describe('縦の増加・見た目の確認(幅 375px)', () => {
  test('幅 375px: 絞り込みフォームは縦に積む。入力・チェックのラベル・解除は 44px 以上', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 900 })
    await openOpenSearch(page)
    await expect(count(page)).toBeVisible()

    // 状態のチェックは、ラベル全体を押せる(チェックボックスの行 = .index-filter__check)
    const boxes = await Promise.all([
      nameBox(page).boundingBox(),
      page.locator('.index-filter__check').first().boundingBox(),
      page.locator('.index-filter__check').last().boundingBox(),
      clearButton(page).boundingBox(),
    ])
    for (const box of boxes) expect(box?.height).toBeGreaterThanOrEqual(44)
    // 縦に積む(名前の入力 → 状態 → 解除の順に、上から下)
    expect(boxes[0]!.y).toBeLessThan(boxes[1]!.y)
    expect(boxes[1]!.y).toBeLessThan(boxes[3]!.y)
  })
})
