import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createApp, defineComponent, h, type FunctionalComponent } from 'vue'
import { createMemoryHistory, RouterView, type Router } from 'vue-router'

import { createAdminRouter } from './index'

let host: HTMLElement | null = null
let app: ReturnType<typeof createApp> | null = null

/** 本番のルーター(ガード込み)を、`main` に `h1` を持つ最小のアプリで動かす(ページ本体の実装には依存しない)。 */
async function startRouter(initialPath: string): Promise<Router> {
  const router = createAdminRouter(createMemoryHistory())
  // ページを、h1 だけの軽い部品に差し替える(スタブページ・テンプレートの重さに依存しない)。
  for (const route of router.getRoutes()) {
    const name = String(route.name)
    route.components = {
      default: defineComponent({ render: () => h('h1', { tabindex: -1 }, `page:${name}`) }),
    }
  }
  const Root: FunctionalComponent = () =>
    h('main', null, [h('a', { id: 'skip', href: '#' }, 'skip'), h(RouterView)])
  host = document.createElement('div')
  document.body.append(host)
  app = createApp(Root)
  app.use(router)
  app.mount(host)
  await router.push(initialPath)
  await router.isReady()
  await settle()
  return router
}

async function settle(): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, 0))
}

beforeEach(() => {
  document.title = ''
  document.body.focus()
})
afterEach(() => {
  app?.unmount()
  host?.remove()
  app = null
  host = null
})

describe('遷移後の処理(E 4.5・DS 8。FMOD-U-10)', () => {
  it('document.title を「title - Loreley 管理」にする', async () => {
    const router = await startRouter('/sources')
    expect(document.title).toBe('データソース - Loreley 管理')

    await router.push('/jobs')
    expect(document.title).toBe('ジョブ - Loreley 管理')
  })

  it('動的な meta.title(識別子)も、遷移後の document.title に反映する(復号済みの値)', async () => {
    const router = await startRouter('/sources')

    await router.push('/sources/demo-handbook')
    expect(document.title).toBe('demo-handbook - Loreley 管理')

    await router.push('/jobs/job%2F0001')
    expect(document.title).toBe('job/0001 - Loreley 管理')
  })

  it('SPA 内の 404 のタイトル', async () => {
    await startRouter('/no/such/page')

    expect(document.title).toBe('ページが見つかりません - Loreley 管理')
  })

  it('パス(route の name または params)が変わったら、フォーカスを main 内の h1 に移す', async () => {
    const router = await startRouter('/sources')

    await router.push('/jobs')
    await settle()

    expect(document.activeElement?.tagName).toBe('H1')
    expect(document.activeElement?.textContent).toBe('page:jobs')
  })

  it('同じ route で params だけが変わる遷移(詳細 a → b)でも、フォーカスを移す', async () => {
    const router = await startRouter('/sources/a')
    document.getElementById('skip')?.focus()

    await router.push('/sources/b')
    await settle()

    expect(document.activeElement?.tagName).toBe('H1')
  })

  it('クエリだけの変化(ページ・タブ・並べ替え)では、フォーカスを動かさない', async () => {
    const router = await startRouter('/jobs')
    const skip = document.getElementById('skip')
    skip?.focus()

    await router.push('/jobs?page=2')
    await settle()
    await router.push('/jobs?page=2&sort=-queued_at')
    await settle()

    expect(document.activeElement).toBe(skip)
  })

  it('最初の表示では、フォーカスを動かさない(スキップリンクが先頭のまま)。タイトルは更新する', async () => {
    await startRouter('/sources')

    expect(document.activeElement).toBe(document.body)
    expect(document.title).toBe('データソース - Loreley 管理')
  })

  it('遷移が失敗(同じ場所への移動・キャンセル)したときは、何もしない', async () => {
    const router = await startRouter('/jobs')
    document.title = 'unchanged'

    const failure = await router.push('/jobs')

    expect(failure).toBeDefined()
    expect(document.title).toBe('unchanged')
  })
})
