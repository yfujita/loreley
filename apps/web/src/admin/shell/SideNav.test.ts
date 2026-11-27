import { flushPromises } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { routes } from '@/admin/router/routes'
import { navGroups } from '@/admin/router/navGroups'

import {
  apiErrorResponse,
  jsonResponse,
  networkErrorResponse,
} from '../../../tests/support/apiErrors'
import { useFetchStub } from '../../../tests/support/fetchStub'
import { meta } from '../../../tests/support/fixtures/meta'
import { mountInLayout } from '../../../tests/support/mount'
import SideNav from './SideNav.vue'

const stub = useFetchStub()

async function mountNav(path: string) {
  const mounted = await mountInLayout(SideNav, {
    props: { navGroups },
    routes,
    initialPath: path,
  })
  await flushPromises()
  return mounted
}

describe('SideNav(DS 5.1・5.3)', () => {
  it('route の meta.nav から、ダッシュボード | データソース・ジョブ | 文書の確認・OpenSearch の 3 グループを描く(区切り線 2 本)', async () => {
    stub.respondWith(jsonResponse(meta.noDashboards()))
    const { wrapper } = await mountNav('/')

    const groups = wrapper.findAll('ul.side-nav__group')
    expect(groups.map((group) => group.findAll('a').map((a) => a.text()))).toEqual([
      ['ダッシュボード'],
      ['データソース', 'ジョブ'],
      ['文書の確認', 'OpenSearch'],
    ])
    expect(wrapper.findAll('hr')).toHaveLength(2)
    // グループの見出し文字は MVP では出さない(読み上げ用の aria-label だけ)
    expect(groups.map((group) => group.attributes('aria-label'))).toEqual(['全体', '運用', '確認'])
  })

  it('各項目は route 名から作る data-testid(nav-{route 名})を持ち、リンク先は route の path', async () => {
    stub.respondWith(jsonResponse(meta.noDashboards()))
    const { wrapper } = await mountNav('/')

    const hrefs = Object.fromEntries(
      wrapper
        .findAll('a[data-testid^="nav-"]')
        .map((a) => [a.attributes('data-testid'), a.attributes('href')]),
    )
    expect(hrefs).toEqual({
      'nav-dashboard': '/',
      'nav-sources': '/sources',
      'nav-jobs': '/jobs',
      'nav-documents': '/documents',
      'nav-opensearch': '/opensearch',
    })
  })

  it('現在地は aria-current="page"(面が白・左の帯)。ほかの項目には付けない', async () => {
    stub.respondWith(jsonResponse(meta.noDashboards()))
    const { wrapper } = await mountNav('/jobs')

    const current = wrapper.findAll('a[aria-current]')
    expect(current.map((a) => a.attributes('data-testid'))).toEqual(['nav-jobs'])
    expect(current[0]?.attributes('aria-current')).toBe('page')
    expect(current[0]?.classes()).toContain('side-nav__item--current')
  })

  it('詳細・編集の画面でも、親のナビ項目を強調する(S2・S4 → データソース、J2 → ジョブ)', async () => {
    stub.respondWith(jsonResponse(meta.noDashboards()))

    const edit = await mountNav('/sources/demo-handbook/edit')
    const job = await mountNav('/jobs/job-0001')

    expect(edit.wrapper.findAll('a[aria-current]').map((a) => a.attributes('data-testid'))).toEqual(
      ['nav-sources'],
    )
    expect(job.wrapper.findAll('a[aria-current]').map((a) => a.attributes('data-testid'))).toEqual([
      'nav-jobs',
    ])
  })

  it('SPA 内の 404 では、どの項目も強調しない', async () => {
    stub.respondWith(jsonResponse(meta.noDashboards()))
    const { wrapper } = await mountNav('/no/such/page')

    expect(wrapper.findAll('a[aria-current]')).toHaveLength(0)
  })

  describe('外部リンク領域(AF-20)', () => {
    it('Dashboards が設定されていれば、「OpenSearch Dashboards」を target=_blank rel=noopener で出し、「(別タブで開く)」を視覚的に隠して添える', async () => {
      stub.respondWith(jsonResponse(meta.normal()))
      const { wrapper } = await mountNav('/')

      const link = wrapper.find('a[href="http://localhost:5601"]')
      expect(link.exists()).toBe(true)
      expect(link.text()).toContain('OpenSearch Dashboards')
      expect(link.attributes('target')).toBe('_blank')
      expect(link.attributes('rel')).toBe('noopener')
      expect(link.find('.sr-only').text()).toBe('(別タブで開く)')
    })

    it('未設定(null)なら、領域ごと出さない', async () => {
      stub.respondWith(jsonResponse(meta.noDashboards()))
      const { wrapper } = await mountNav('/')

      expect(wrapper.find('.external-links').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('OpenSearch Dashboards')
    })

    it.each([
      ['EP-14 が 503', () => apiErrorResponse(503, 'unavailable', { retryable: false })],
      ['EP-14 が通信断', () => networkErrorResponse()],
    ])('%s のときも、領域を出さず、ナビは止めない', async (_name, response) => {
      stub.respondWith(response())
      const { wrapper } = await mountNav('/')

      expect(wrapper.find('.external-links').exists()).toBe(false)
      expect(wrapper.findAll('ul.side-nav__group a')).toHaveLength(5)
    })

    it('http・https 以外の URL(javascript: など)は、リンクにしない', async () => {
      stub.respondWith(
        jsonResponse({ cron_timezone: 'Asia/Tokyo', dashboards_url: 'javascript:alert(1)' }),
      )
      const { wrapper } = await mountNav('/')

      expect(wrapper.find('.external-links').exists()).toBe(false)
    })
  })
})
