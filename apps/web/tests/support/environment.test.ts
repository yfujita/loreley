// テスト基盤の前提(FARC-U-9)を固定するテスト。jsdom で Vuetify の部品が動くこと、
// 相対 `baseUrl` の `Request` が解決されないこと(setup が絶対 URL に差し替える理由)、TZ。
import { describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { VDataTableServer, VDialog, VNavigationDrawer } from 'vuetify/components'

import { getMetaOptions } from '@/admin/api'

import { jsonResponse } from './apiErrors'
import { useFetchStub } from './fetchStub'
import { mountInLayout } from './mount'
import { createTestQueryClient } from './queryTesting'

describe('jsdom 上の Vuetify', () => {
  it('VDataTableServer がマウントでき、@update:options が初期に 1 回発火する', async () => {
    const onUpdateOptions = vi.fn()
    const { wrapper } = await mountInLayout(VDataTableServer, {
      props: {
        headers: [{ title: 'ID', key: 'id' }],
        items: [{ id: 'source-a' }, { id: 'source-b' }],
        itemsLength: 2,
        itemsPerPage: 25,
        page: 1,
        'onUpdate:options': onUpdateOptions,
      },
    })

    expect(wrapper.find('table').exists()).toBe(true)
    expect(wrapper.text()).toContain('source-b')
    expect(onUpdateOptions).toHaveBeenCalledTimes(1)
    expect(onUpdateOptions).toHaveBeenCalledWith(
      expect.objectContaining({ page: 1, itemsPerPage: 25 }),
    )
  })

  it('VDialog が body にテレポートして描画される', async () => {
    await mountInLayout(VDialog, {
      props: { modelValue: true },
      slots: { default: () => h('p', { 'data-testid': 'dialog-body' }, '本文') },
    })

    expect(document.body.querySelector('[role="dialog"]')).not.toBeNull()
    expect(document.body.querySelector('[data-testid="dialog-body"]')?.textContent).toBe('本文')
  })

  it('VNavigationDrawer が VLayout の中でマウントできる', async () => {
    const { wrapper } = await mountInLayout(VNavigationDrawer, {
      slots: { default: () => 'ナビ' },
    })

    expect(wrapper.find('nav').text()).toBe('ナビ')
  })

  // html() は js-beautify を使う。overrides で glob 14・minimatch 11 に上げた依存が壊れていないことの確認。
  it('wrapper.html() が使える', async () => {
    const { wrapper } = await mountInLayout(VNavigationDrawer, {
      slots: { default: () => 'ナビ' },
    })

    expect(wrapper.html()).toContain('ナビ')
  })
})

describe('相対 baseUrl', () => {
  const stub = useFetchStub()

  it('jsdom 環境でも Request は Node(undici)のもので、相対 URL を解決しない(setup が絶対 URL に差し替える理由)', () => {
    expect(() => new Request('/api/admin/v1/meta')).toThrow(TypeError)
  })

  it('生成クライアントの baseUrl は /api/admin/v1(setup の差し替え前の値)', async () => {
    // setup が差し替えたクライアントとは別の、生成直後のインスタンスを読み込む。
    vi.resetModules()
    // 生成直後のインスタンスが要るため、公開口(client を出さない設計。F 3.3)ではなく直接読む(R2 の例外)。
    // eslint-disable-next-line no-restricted-syntax -- 上記の理由
    const { client: freshClient } = await import('../../src/admin/api/generated/client.gen')

    expect(freshClient.getConfig().baseUrl).toBe('/api/admin/v1')
  })

  it('setup 後の生成クライアントは絶対 URL で Request を作れる(公開口の Options → fetch の差し替え先まで届く)', async () => {
    stub.respondWith(jsonResponse({ cron_timezone: null, dashboards_url: null }))

    await createTestQueryClient().fetchQuery(getMetaOptions())

    expect(stub.requests.map((request) => request.url)).toEqual([
      'http://localhost/api/admin/v1/meta',
    ])
  })
})

describe('時刻', () => {
  it('TZ は Asia/Tokyo(UTC の 0 時が JST の 9 時)', () => {
    expect(new Date('2026-01-01T00:00:00Z').getHours()).toBe(9)
  })
})
