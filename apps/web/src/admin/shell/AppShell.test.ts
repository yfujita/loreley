import { flushPromises } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import { navGroups } from '@/admin/router/navGroups'
import { routes } from '@/admin/router/routes'
import { useSnackbar } from '@/shared/ui/useSnackbar'

import { jsonResponse } from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { meta } from '../../../tests/support/fixtures/meta'
import { mountInLayout } from '../../../tests/support/mount'
import AppShell from './AppShell.vue'

const stub = useFetchStub()
const originalWidth = window.innerWidth
afterEach(() => {
  window.innerWidth = originalWidth
})

// 本番の route 定義(ページ本体はスタブページ)で、シェルをマウントする。
async function mountShell(path: string, width: number) {
  window.innerWidth = width
  stub.respondWith(jsonResponse(meta.normal()))
  const mounted = await mountInLayout(AppShell, {
    props: { navGroups },
    routes,
    initialPath: path,
  })
  await flushPromises()
  return mounted
}

const drawer = (wrapper: Awaited<ReturnType<typeof mountShell>>['wrapper']) =>
  wrapper.find('.v-navigation-drawer')

describe('AppShell(DS 5.1。FARC-U-14: mobileBreakpoint・permanent)', () => {
  it('幅 840px 以上: サイドバーは常時表示で、上部バー(VAppBar)は置かない', async () => {
    const { wrapper } = await mountShell('/sources', 840)

    expect(wrapper.find('.mobile-app-bar').exists()).toBe(false)
    expect(drawer(wrapper).classes()).not.toContain('v-navigation-drawer--temporary')
    expect(drawer(wrapper).classes()).toContain('v-navigation-drawer--active')
  })

  it('幅 839px 以下: 上部バーを置き、サイドバーは一時表示(閉じている)。境は 840px(mobileBreakpoint: md)', async () => {
    const { wrapper } = await mountShell('/sources', 839)

    expect(wrapper.find('.mobile-app-bar').exists()).toBe(true)
    expect(drawer(wrapper).classes()).toContain('v-navigation-drawer--temporary')
    expect(drawer(wrapper).classes()).not.toContain('v-navigation-drawer--active')
  })

  it('840〜1144px でも、サイドバーは常時表示(既定の mobileBreakpoint(lg=1145px)のままなら、ここで一時表示になる)', async () => {
    for (const width of [840, 1024, 1144]) {
      const { wrapper } = await mountShell('/sources', width)

      expect(wrapper.find('.mobile-app-bar').exists(), `${width}px`).toBe(false)
      expect(drawer(wrapper).classes(), `${width}px`).toContain('v-navigation-drawer--active')
    }
  })

  it('メニューのボタンでドロワーを開閉し、aria-expanded に反映する(幅 839px 以下)', async () => {
    const { wrapper } = await mountShell('/sources', 700)
    const button = () => wrapper.find('button[aria-label="メニューを開く"]')
    expect(button().attributes('aria-expanded')).toBe('false')

    await button().trigger('click')
    await nextTick()
    expect(button().attributes('aria-expanded')).toBe('true')
    expect(drawer(wrapper).classes()).toContain('v-navigation-drawer--active')

    await button().trigger('click')
    await nextTick()
    expect(button().attributes('aria-expanded')).toBe('false')
    expect(drawer(wrapper).classes()).not.toContain('v-navigation-drawer--active')
  })

  it('ドロワーのナビは aria-label「メインメニュー」、本文は main(id=main)で 1 つ、スキップリンクが先頭にある', async () => {
    const { wrapper } = await mountShell('/sources', 1280)

    expect(drawer(wrapper).element.tagName).toBe('NAV')
    expect(drawer(wrapper).attributes('aria-label')).toBe('メインメニュー')
    expect(wrapper.findAll('main')).toHaveLength(1)
    expect(wrapper.find('main').attributes('id')).toBe('main')
    expect(wrapper.find('.v-application__wrap').element.firstElementChild?.textContent).toBe(
      'メインコンテンツへ移動',
    )
  })

  it('h1 はページごとに 1 つ(テンプレートの PageHeader)', async () => {
    const { wrapper } = await mountShell('/sources', 1280)

    expect(wrapper.findAll('h1')).toHaveLength(1)
    expect(wrapper.find('h1').text()).toBe('データソース')
    expect(wrapper.find('h1').attributes('tabindex')).toBe('-1')
  })

  it('パンくずを provide し、2 階層以上の画面だけ、ページ見出しの上に出す', async () => {
    const top = await mountShell('/sources', 1280)
    const detail = await mountShell('/sources/demo-handbook', 1280)

    expect(top.wrapper.find('nav[aria-label="パンくず"]').exists()).toBe(false)
    const crumbs = detail.wrapper.find('nav[aria-label="パンくず"]')
    expect(crumbs.text()).toContain('データソース')
    expect(crumbs.text()).toContain('demo-handbook')
    expect(crumbs.find('a').attributes('href')).toBe('/sources')
    expect(crumbs.find('[aria-current="page"]').text()).toBe('demo-handbook')
  })

  it('スナックバーはシェルが 1 つだけ持つ(useSnackbar の通知を出す)', async () => {
    await mountShell('/sources', 1280)

    useSnackbar().show('クロールを受け付けました')
    await nextTick()
    await new Promise((resolve) => window.setTimeout(resolve, 50))

    expect(document.querySelectorAll('.v-snackbar')).toHaveLength(1)
    expect(document.querySelector('.v-snackbar')?.textContent).toContain('クロールを受け付けました')
  })

  it('Esc で閉じ、フォーカスをメニューのボタンへ戻す(VNavigationDrawer は Esc を扱わない。DS 8)', async () => {
    const { wrapper } = await mountShell('/sources', 700)
    const button = wrapper.find<HTMLButtonElement>('button[aria-label="メニューを開く"]')
    await button.trigger('click')
    await nextTick()
    expect(drawer(wrapper).classes()).toContain('v-navigation-drawer--active')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()

    expect(drawer(wrapper).classes()).not.toContain('v-navigation-drawer--active')
    expect(button.attributes('aria-expanded')).toBe('false')
    expect(document.activeElement).toBe(button.element)
  })

  it('Esc は、ドロワーが閉じているとき・常時表示のとき(幅 840px 以上)は何もしない', async () => {
    const closed = await mountShell('/sources', 700)
    const closedButton = closed.wrapper.find<HTMLButtonElement>(
      'button[aria-label="メニューを開く"]',
    )
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(document.activeElement).not.toBe(closedButton.element)

    const wide = await mountShell('/sources', 1000)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(drawer(wide.wrapper).classes()).toContain('v-navigation-drawer--active')
  })

  it('一時表示のドロワーは、ナビの項目を選んで画面が変わると閉じる', async () => {
    const { wrapper, router } = await mountShell('/sources', 700)
    await wrapper.find('button[aria-label="メニューを開く"]').trigger('click')
    await nextTick()

    await router.push('/jobs')
    await flushPromises()

    expect(drawer(wrapper).classes()).not.toContain('v-navigation-drawer--active')
  })
})
