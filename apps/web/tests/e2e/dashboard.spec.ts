// D1 ダッシュボードの E2E(API はモック。dashboard 画面仕様・E 5.5・FARC-U-8)。
// 正常・異常・判定不能・取得失敗(データなし・前回データあり=降格)・読み込み中、30 秒のポーリング(Playwright の時計)・
// 手動更新・自動更新のオン/オフ・外部リンク(AF-20)・進行バーの reduced-motion・レスポンシブ・キーボード。
import type { Page } from '@playwright/test'

import type { MetaResponse } from '@/admin/api'

import { apiErrorResponse, hangResponse, jsonResponse } from '../support/apiErrors'
import { expect, test } from '../support/e2eTest'
import { dashboard } from '../support/fixtures/dashboard'
import { meta } from '../support/fixtures/meta'
import { opensearch } from '../support/fixtures/opensearch'
import { mockApi, type MockApi } from '../support/mockApi'

const PRIMARY_RGB = 'rgb(29, 91, 135)'
const ON_SURFACE_RGB = 'rgb(26, 37, 48)'

/** D1 を開く(シェルの `GET /meta` もモックする)。応答は固定・関数・呼び出し回数ごとの列。 */
async function openDashboard(
  page: Page,
  responses: Parameters<MockApi['respond']>[1] = jsonResponse(dashboard.allNormal()),
  metaBody: MetaResponse = meta.noDashboards(),
): Promise<MockApi> {
  const api = await mockApi(page, {
    'GET /meta': jsonResponse(metaBody),
    'GET /dashboard': responses,
  })
  await page.goto('./')
  return api
}

const lastSuccess = (page: Page) =>
  page.locator('.dashboard-page__toolbar > span').filter({ hasText: '最終取得成功' })
const summary = (page: Page) => page.getByTestId('d1-summary')
const tile = (page: Page, id: string) => page.getByTestId(`d1-tile-${id}`)
const switchControl = (page: Page) => page.getByRole('switch', { name: '自動更新(30 秒ごと)' })
const updateButton = (page: Page) => page.getByRole('button', { name: '更新', exact: true })

/** 「前回の構成と同じ全 8 タイル」を、定義表の順に確かめる。 */
const ALL_IDS = [
  'crawler',
  'indexer',
  'opensearch',
  'api',
  'web',
  'opensearch-dashboards',
  'embedding',
  'llm',
]

test.describe('通常の表示', () => {
  test('見出し・説明・概況・必須 5 と任意 3 のタイル・「この表示について」。見出しの階層は h1 → h2 → h3', async ({
    page,
  }) => {
    await openDashboard(page)

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('ダッシュボード')
    await expect(
      page.getByText('各コンポーネントが起動して応答できるかを確認します。'),
    ).toBeVisible()
    await expect(summary(page)).toContainText('すべてのコンポーネントが正常です')
    await expect(page.getByRole('heading', { level: 2 })).toHaveText([
      'コンポーネント',
      '任意のコンポーネント',
      'この表示について',
    ])
    await expect(page.getByRole('heading', { level: 3 })).toHaveText(ALL_IDS)
    await expect(
      page.getByRole('list', { name: 'コンポーネントの状態', exact: true }),
    ).toBeVisible()
    await expect(page.getByRole('list', { name: '任意のコンポーネントの状態' })).toBeVisible()
    await expect(tile(page, 'crawler')).toContainText('正常')
    await expect(tile(page, 'embedding')).toContainText('未設定')
    await expect(tile(page, 'embedding')).toContainText('設定されていません(任意)。')
  })

  test('最終取得成功の日時(ブラウザのローカル時刻)と、タイルの「確認 hh:mm:ss」を出す', async ({
    page,
  }) => {
    // 時計は取得の間も進む(数秒)ので、秒は固定せず、日付と分までを確かめる
    await page.clock.install({ time: new Date('2026-11-27T01:00:05Z') })
    await openDashboard(page)

    await expect(lastSuccess(page)).toContainText(/最終取得成功 2026-11-27 10:00:\d{2}/)
    // fixtures の checked_at は 2026-11-22T01:00:00Z(JST 10:00:00)
    await expect(tile(page, 'crawler')).toContainText('応答しています · 確認 10:00:00')
  })

  test('導線: opensearch のタイルから O1 へ移れる(ナビの現在地も移る)', async ({ page }) => {
    await openDashboard(page)
    await mockApi(page, { 'GET /opensearch/cluster': jsonResponse(opensearch.green()) })

    await tile(page, 'opensearch').getByRole('link', { name: 'OpenSearch の詳細' }).click()

    await expect(page).toHaveURL(/\/admin\/opensearch$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('OpenSearch')
  })

  test('導線のリンクがあるのは crawler・indexer・opensearch だけ。リンクの色は primary(実描画)', async ({
    page,
  }) => {
    await openDashboard(page)

    await expect(
      tile(page, 'crawler').getByRole('link', { name: 'ジョブの状態を確認' }),
    ).toHaveAttribute('href', '/admin/jobs')
    await expect(
      tile(page, 'indexer').getByRole('link', { name: 'ジョブの状態を確認' }),
    ).toHaveAttribute('href', '/admin/jobs')
    for (const id of ['api', 'web', 'opensearch-dashboards', 'embedding', 'llm']) {
      await expect(tile(page, id).getByRole('link')).toHaveCount(0)
    }
    await expect(tile(page, 'crawler').getByRole('link')).toHaveCSS('color', PRIMARY_RGB)
  })

  test('サイドバーのナビのリンクの色は本文色(v-list-item の <a> は primary にならない)', async ({
    page,
  }) => {
    await openDashboard(page)

    await expect(
      page
        .getByRole('navigation', { name: 'メインメニュー' })
        .getByRole('link', { name: 'データソース' }),
    ).toHaveCSS('color', ON_SURFACE_RGB)
  })
})

test.describe('異常・判定不能・未設定', () => {
  test('異常あり: 概況は error。異常のタイルは「応答がありません。…」(タグ「異常」)', async ({
    page,
  }) => {
    await openDashboard(page, jsonResponse(dashboard.abnormal()))

    await expect(summary(page)).toContainText('異常のコンポーネントがあります(1 件)')
    await expect(summary(page)).toContainText('異常: crawler')
    await expect(tile(page, 'crawler')).toContainText('異常')
    await expect(tile(page, 'crawler')).toContainText(
      '応答がありません。コンテナが停止している可能性があります。',
    )
    await expect(tile(page, 'indexer')).toContainText('正常')
  })

  test('判定不能あり: 概況は warning。タイルは理由つき(時間内に応答がありませんでした)', async ({
    page,
  }) => {
    await openDashboard(page, jsonResponse(dashboard.undetermined()))

    await expect(summary(page)).toContainText('状態を確認できないコンポーネントがあります(1 件)')
    await expect(tile(page, 'indexer')).toContainText('判定不能')
    await expect(tile(page, 'indexer')).toContainText(
      '状態を取得できませんでした(時間内に応答がありませんでした)。',
    )
  })

  test('異常と判定不能の両方: 異常を優先し、件数行に両方を並べる', async ({ page }) => {
    await openDashboard(page, jsonResponse(dashboard.mixed()))

    await expect(summary(page)).toContainText('異常のコンポーネントがあります(1 件)')
    await expect(summary(page)).toContainText('異常: crawler')
    await expect(summary(page)).toContainText('判定不能: indexer')
  })

  test('任意のコンポーネントがすべて設定済み: 正常 8・未設定 0', async ({ page }) => {
    await openDashboard(page, jsonResponse(dashboard.allConfigured()))

    await expect(summary(page)).toContainText('正常 8')
    await expect(summary(page)).toContainText('未設定 0')
  })

  test('未知の reason は一般的な文言だけ(判定不能は「状態を取得できませんでした。」。異常は固定の文)', async ({
    page,
  }) => {
    await openDashboard(page, jsonResponse(dashboard.unknownReason()))

    await expect(tile(page, 'indexer')).toContainText('状態を取得できませんでした。')
    await expect(tile(page, 'indexer')).not.toContainText('(')
    await expect(tile(page, 'crawler')).toContainText(
      '応答がありません。コンテナが停止している可能性があります。',
    )
  })

  test('必須がすべて判定不能: 概況は warning「状態を確認できないコンポーネントがあります(5 件)」', async ({
    page,
  }) => {
    await openDashboard(page, jsonResponse(dashboard.allUndetermined()))

    await expect(summary(page)).toContainText('状態を確認できないコンポーネントがあります(5 件)')
    await expect(summary(page)).toContainText('判定不能: crawler、indexer、opensearch、api、web')
    await expect(summary(page)).toContainText('異常 0')
  })

  test('タイルの実 CSS: 異常は左 4px の error の帯、判定不能は warning の帯、未設定は破線', async ({
    page,
  }) => {
    await openDashboard(page, jsonResponse(dashboard.mixed()))

    const abnormal = tile(page, 'crawler')
    await expect(abnormal).toHaveCSS('border-left-width', '4px')
    await expect(abnormal).toHaveCSS('border-left-color', 'rgb(179, 38, 30)')
    const undetermined = tile(page, 'indexer')
    await expect(undetermined).toHaveCSS('border-left-width', '4px')
    await expect(undetermined).toHaveCSS('border-left-color', 'rgb(143, 90, 0)')
    const notConfigured = tile(page, 'embedding')
    await expect(notConfigured).toHaveCSS('border-top-style', 'dashed')
    await expect(notConfigured).toHaveCSS('border-left-width', '1px')
    // 正常のタイルは実線・1px
    await expect(tile(page, 'opensearch')).toHaveCSS('border-top-style', 'solid')
  })
})

test.describe('読み込み中・初回の取得失敗', () => {
  test('読み込み中: 見出しと操作行は先に出し、概況とタイルはスケルトン(aria-busy・読み上げ用の「読み込み中」)', async ({
    page,
  }) => {
    await openDashboard(page, hangResponse())

    await expect(page.getByRole('heading', { level: 1, name: 'ダッシュボード' })).toBeVisible()
    await expect(switchControl(page)).toBeVisible()
    await expect(updateButton(page)).toBeVisible()
    const loading = page.getByTestId('d1-state-loading')
    await expect(loading).toHaveAttribute('aria-busy', 'true')
    await expect(loading.getByRole('status')).toHaveText('コンポーネントの状態を読み込み中')
    await expect(summary(page)).toHaveCount(0)
    await expect(lastSuccess(page)).toHaveCount(0)
  })

  test('初回から取得できない: エラーブロック(role=alert)+「再試行」。通知は出さない。再試行で復帰する', async ({
    page,
  }) => {
    const api = await openDashboard(page, [
      apiErrorResponse(500, 'internal_error'),
      jsonResponse(dashboard.allNormal()),
    ])

    const error = page.getByTestId('d1-state-error')
    await expect(error).toHaveAttribute('role', 'alert')
    await expect(
      error.getByRole('heading', { name: 'コンポーネントの状態を取得できません' }),
    ).toBeVisible()
    await expect(error).toContainText('api コンテナが起動しているかを確認してください。')
    await expect(page.locator('.v-snackbar')).toHaveCount(0)

    await error.getByRole('button', { name: '再試行' }).click()

    await expect(summary(page)).toBeVisible()
    await expect(error).toHaveCount(0)
    expect(api.callCount('GET /dashboard')).toBe(2)
  })
})

test.describe('取得失敗(前回データあり)。タイルを判定不能に降格する', () => {
  async function openAndFail(page: Page, first = dashboard.allNormal()) {
    await page.clock.install({ time: new Date('2026-11-27T01:44:30Z') })
    const api = await openDashboard(page, [
      jsonResponse(first),
      apiErrorResponse(500, 'internal_error'),
    ])
    await expect(summary(page)).toBeVisible()
    await updateButton(page).click()
    return api
  }

  test('警告のアラート(role=alert)「最新の状態を取得できませんでした」+「再読み込み」。概況は「現在の状態を確認できません」', async ({
    page,
  }) => {
    await openAndFail(page)

    const alert = page.locator('.page-alert[role="alert"]')
    await expect(alert).toContainText('最新の状態を取得できませんでした')
    await expect(alert).toContainText(
      'Admin API に接続できないため、どのコンポーネントの現在の状態も確認できません。',
    )
    await expect(alert.getByRole('button', { name: '再読み込み' })).toBeVisible()
    await expect(summary(page)).toContainText('現在の状態を確認できません')
    await expect(summary(page)).toContainText('判定不能 5')
    await expect(summary(page)).toContainText('未設定 3(前回取得時の設定)')
    await expect(summary(page)).toContainText('前回の構成と同じ 8 件')
  })

  test('stale のアラートと概況バーの間隔は 16px(他のブロックの間隔と同じ。実測)', async ({
    page,
  }) => {
    await openAndFail(page)
    await expect(page.locator('.page-alert[role="alert"]')).toBeVisible()

    const gap = await page.evaluate(() => {
      const alert = document.querySelector('.page-alert[role="alert"]')!.getBoundingClientRect()
      const band = document.querySelector('[data-testid="d1-summary"]')!.getBoundingClientRect()
      return Math.round(band.top - alert.bottom)
    })
    expect(gap).toBe(16)
  })

  test('前回「正常」「異常」だったタイルは判定不能(前回の状態を添える)。未設定は維持。全 8 タイル・任意の節も出す。通知は出さない', async ({
    page,
  }) => {
    await openAndFail(page, dashboard.abnormal())

    await expect(page.locator('.page-alert[role="alert"]')).toBeVisible()
    await expect(page.getByRole('heading', { level: 3 })).toHaveText(ALL_IDS)
    await expect(tile(page, 'crawler')).toContainText('判定不能')
    await expect(tile(page, 'crawler')).toContainText('前回の状態: 異常(')
    await expect(tile(page, 'indexer')).toContainText('前回の状態: 正常(')
    await expect(tile(page, 'embedding')).toContainText('未設定')
    await expect(tile(page, 'embedding')).toContainText(
      '前回取得時は、設定されていませんでした(任意)。',
    )
    await expect(
      page.getByRole('heading', { level: 2, name: '任意のコンポーネント' }),
    ).toBeVisible()
    // 前回の「正常」を、いまの状態として見せない
    await expect(page.getByTestId('d1-summary')).not.toContainText(
      'すべてのコンポーネントが正常です',
    )
    await expect(page.locator('.v-snackbar')).toHaveCount(0)
  })

  test('最終取得成功の日時は、失敗が続いても最後の成功のまま。自動更新は続き、成功すれば通常の表示に戻る(更新される)', async ({
    page,
  }) => {
    await page.clock.install({ time: new Date('2026-11-27T01:44:30Z') })
    const api = await openDashboard(page, [
      jsonResponse(dashboard.allNormal()),
      apiErrorResponse(500, 'internal_error'),
      apiErrorResponse(500, 'internal_error'),
      jsonResponse(dashboard.allNormal()),
    ])
    const lastSuccessText = lastSuccess(page)
    await expect(lastSuccessText).toContainText(/最終取得成功 2026-11-27 10:44:\d{2}/)
    const firstSuccess = await lastSuccessText.textContent()

    await page.clock.fastForward(31_000) // 1 回目の自動更新(失敗)
    await expect(page.locator('.page-alert[role="alert"]')).toBeVisible()
    await page.clock.fastForward(30_000) // 2 回目(失敗)
    await expect.poll(() => api.callCount('GET /dashboard')).toBe(3)
    await expect(lastSuccessText).toHaveText(firstSuccess ?? '')

    await page.clock.fastForward(30_000) // 3 回目(成功)
    await expect(page.locator('.page-alert[role="alert"]')).toHaveCount(0)
    await expect(summary(page)).toContainText('すべてのコンポーネントが正常です')
    await expect(tile(page, 'crawler')).toContainText('正常')
    await expect(lastSuccessText).not.toHaveText(firstSuccess ?? '')
  })

  test('「再読み込み」で取り直し、成功すれば通常の表示に戻る', async ({ page }) => {
    const api = await openAndFail(page)
    api.respond('GET /dashboard', jsonResponse(dashboard.allNormal()))

    await page.getByRole('button', { name: '再読み込み' }).click()

    await expect(page.locator('.page-alert[role="alert"]')).toHaveCount(0)
    await expect(tile(page, 'crawler')).toContainText('正常')
  })
})

test.describe('更新(Playwright の時計。FARC-U-8)', () => {
  test('30 秒ごとに取り直す(29 秒ではまだ。31 秒で 2 回目)', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-11-27T01:00:00Z') })
    const api = await openDashboard(page)
    await expect(summary(page)).toBeVisible()
    expect(api.callCount('GET /dashboard')).toBe(1)

    await page.clock.fastForward(29_000)
    await page.evaluate(() => 0)
    expect(api.callCount('GET /dashboard')).toBe(1)

    await page.clock.fastForward(2_000)
    await expect.poll(() => api.callCount('GET /dashboard')).toBe(2)
    // 次の定期更新のタイマーは、直前の取得が終わってから作り直される。進めた時点でまだ無いことがあるので、
    // 「30 秒進める → 取得が増えたか」を繰り返して確かめる(増えるまでに進めた量は 30 秒単位)。
    await expect
      .poll(
        async () => {
          await page.clock.fastForward(30_000)
          return api.callCount('GET /dashboard')
        },
        { intervals: [200] },
      )
      .toBeGreaterThanOrEqual(3)
  })

  test('スイッチをオフにすると止まり、「自動更新は停止中です」を出す。オンに戻すと再開する。保存はしない(再読み込みで入)', async ({
    page,
  }) => {
    await page.clock.install({ time: new Date('2026-11-27T01:00:00Z') })
    const api = await openDashboard(page)
    await expect(summary(page)).toBeVisible()
    await expect(switchControl(page)).toBeChecked()

    await switchControl(page).click()
    await expect(switchControl(page)).not.toBeChecked()
    await expect(
      page.getByText('自動更新は停止中です。「更新」で最新の状態を取得します。'),
    ).toBeVisible()
    await page.clock.fastForward(120_000)
    await page.evaluate(() => 0)
    expect(api.callCount('GET /dashboard')).toBe(1)

    // 「入」に戻すと、次の定期更新(最大 30 秒後)を待たずにすぐ取り直す
    await switchControl(page).click()
    await expect(page.getByText('自動更新は停止中です')).toHaveCount(0)
    await expect.poll(() => api.callCount('GET /dashboard')).toBe(2)
    // 次の定期更新のタイマーは、直前の取得が終わってから作り直される(進めた時点で無いことがある)ので、増えるまで 30 秒ずつ進める
    await expect
      .poll(
        async () => {
          await page.clock.fastForward(30_000)
          return api.callCount('GET /dashboard')
        },
        { intervals: [200] },
      )
      .toBeGreaterThanOrEqual(3)

    // 保存しない: 切って再読み込みすると、既定の「入」に戻る
    await switchControl(page).click()
    await page.reload()
    await expect(switchControl(page)).toBeChecked()
  })

  test('「更新」で取り直す(オフでも)。直後だけ、隠した role=status に「更新しました。異常 N 件、判定不能 M 件」', async ({
    page,
  }) => {
    const api = await openDashboard(page, [
      jsonResponse(dashboard.allNormal()),
      jsonResponse(dashboard.mixed()),
    ])
    await expect(summary(page)).toBeVisible()
    await switchControl(page).click() // オフ
    const status = page.getByRole('status').filter({ hasText: /^更新しました/ })
    await expect(status).toHaveCount(0)

    await updateButton(page).click()

    await expect(summary(page)).toContainText('異常のコンポーネントがあります(1 件)')
    await expect(status).toHaveText('更新しました。異常 1 件、判定不能 1 件')
    await expect(status).toHaveClass(/sr-only/)
    expect(api.callCount('GET /dashboard')).toBe(2)
  })

  test('自動更新の結果は読み上げない(手動の通知は次の取得で消える)。概況は role=status ではない', async ({
    page,
  }) => {
    await page.clock.install({ time: new Date('2026-11-27T01:00:00Z') })
    await openDashboard(page, [
      jsonResponse(dashboard.allNormal()),
      jsonResponse(dashboard.mixed()),
    ])
    await expect(summary(page)).toBeVisible()
    await expect(summary(page)).not.toHaveAttribute('role', /./)

    await page.clock.fastForward(31_000)

    await expect(summary(page)).toContainText('異常のコンポーネントがあります(1 件)')
    await expect(page.getByRole('status').filter({ hasText: /^更新しました/ })).toHaveCount(0)
  })

  test('タブが見えない間は止める(refetchIntervalInBackground: false)。見えるようになったら再開する', async ({
    page,
  }) => {
    await page.clock.install({ time: new Date('2026-11-27T01:00:00Z') })
    const api = await openDashboard(page)
    await expect(summary(page)).toBeVisible()

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await page.clock.fastForward(95_000)
    await page.evaluate(() => 0)
    expect(api.callCount('GET /dashboard')).toBe(1)

    await page.evaluate(() => {
      Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' })
      document.dispatchEvent(new Event('visibilitychange'))
    })
    await page.clock.fastForward(31_000)
    await expect.poll(() => api.callCount('GET /dashboard')).toBeGreaterThan(1)
  })

  test('更新中も表示は消えず、カード上端に進行バー(更新中)を出す', async ({ page }) => {
    await openDashboard(page, [jsonResponse(dashboard.allNormal()), hangResponse()])
    await expect(summary(page)).toBeVisible()

    await updateButton(page).click()

    await expect(page.getByRole('progressbar', { name: '更新中' })).toBeVisible()
    await expect(summary(page)).toBeVisible()
    await expect(tile(page, 'crawler')).toBeVisible()
  })

  test('進行バーは prefers-reduced-motion: reduce で動きを止める(実コンポーネントの animation-name)', async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    await openDashboard(page, [jsonResponse(dashboard.allNormal()), hangResponse()])
    await expect(summary(page)).toBeVisible()
    await updateButton(page).click()
    const bar = page.locator('.top-progress__bar')
    await expect(bar).toHaveCSS('animation-name', 'progress-slide')

    await page.emulateMedia({ reducedMotion: 'reduce' })

    await expect(bar).toHaveCSS('animation-name', 'none')
    await expect(bar).toHaveCSS('width', /^[1-9]/)
  })

  test('読み込み中のスケルトンも、reduced-motion では光沢を止める', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await openDashboard(page, hangResponse())

    await expect(page.getByTestId('d1-state-loading').locator('.skeleton-line').first()).toHaveCSS(
      'animation-name',
      'none',
    )
  })
})

test.describe('外部リンク(AF-20)', () => {
  test('/meta の URL があれば、サイドバーの下端に別タブのリンクを出す。D1 のタイルにはリンクを置かない', async ({
    page,
  }) => {
    await openDashboard(page, undefined, meta.normal())

    const link = page
      .getByRole('navigation', { name: 'メインメニュー' })
      .getByRole('link', { name: /OpenSearch Dashboards/ })
    await expect(link).toHaveAttribute('href', 'http://localhost:5601')
    await expect(link).toHaveAttribute('target', '_blank')
    await expect(tile(page, 'opensearch-dashboards').getByRole('link')).toHaveCount(0)
  })

  test('未設定なら、領域ごと出さない(タイルは「未設定」のまま)', async ({ page }) => {
    await openDashboard(page, undefined, meta.noDashboards())

    await expect(summary(page)).toBeVisible()
    await expect(page.getByRole('link', { name: /OpenSearch Dashboards/ })).toHaveCount(0)
  })
})

test.describe('レスポンシブ・キーボード', () => {
  for (const [width, columns] of [
    [1280, 3],
    [1024, 2],
    [840, 2],
    [768, 2],
    [375, 1],
    [320, 1],
  ] as const) {
    test(`幅 ${width}px: タイルは ${columns} 列(最小幅 240px の auto-fill。画面仕様 7 章の 2〜3 列・1 列)。横スクロールなし`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: 900 })
      await openDashboard(page)
      await expect(summary(page)).toBeVisible()

      const xs = await page
        .getByRole('list', { name: 'コンポーネントの状態', exact: true })
        .getByRole('listitem')
        .evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().left)))
      expect(new Set(xs).size).toBe(columns)
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      )
      expect(overflow).toBeLessThanOrEqual(0)
    })
  }

  test('幅 375px: ボタンとスイッチの操作領域は高さ 44px 以上', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 900 })
    await openDashboard(page)
    await expect(summary(page)).toBeVisible()

    const update = await updateButton(page).boundingBox()
    const control = await page.locator('.auto-refresh-switch__control').boundingBox()
    expect(update?.height).toBeGreaterThanOrEqual(44)
    expect(control?.height).toBeGreaterThanOrEqual(44)
  })

  test('キーボード: スイッチ → 更新 の順にフォーカスでき、Space でスイッチを切り替える', async ({
    page,
  }) => {
    await openDashboard(page)
    await expect(summary(page)).toBeVisible()

    await switchControl(page).focus()
    await page.keyboard.press('Space')
    await expect(switchControl(page)).not.toBeChecked()
    await page.keyboard.press('Space')
    await expect(switchControl(page)).toBeChecked()
    await page.keyboard.press('Tab')
    await expect(updateButton(page)).toBeFocused()
  })

  test('フォーカスの順序(タイル内のリンク): crawler → indexer → opensearch(定義表の順)', async ({
    page,
  }) => {
    await openDashboard(page)
    await expect(summary(page)).toBeVisible()

    await updateButton(page).focus()
    await page.keyboard.press('Tab')
    await expect(tile(page, 'crawler').getByRole('link')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(tile(page, 'indexer').getByRole('link')).toBeFocused()
    await page.keyboard.press('Tab')
    await expect(tile(page, 'opensearch').getByRole('link')).toBeFocused()
  })
})
