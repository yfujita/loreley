import { describe, expect, it } from 'vitest'

import type { ComponentId, ComponentStatus, DashboardResponse } from '@/admin/api'

import { component, dashboard } from '../../../../../tests/support/fixtures/dashboard'
import { buildDashboardViewModel } from './dashboardViewModel'

const FRESH = { stale: false, lastSuccessAt: null } as const
// 2026-11-21 01:44:30Z = JST 10:44:30(TZ は Asia/Tokyo)
const LAST_SUCCESS_AT = Date.UTC(2026, 10, 21, 1, 44, 30)
const STALE = { stale: true, lastSuccessAt: LAST_SUCCESS_AT } as const

function allTiles(
  response: DashboardResponse,
  options = FRESH as Parameters<typeof buildDashboardViewModel>[1],
) {
  const model = buildDashboardViewModel(response, options)
  return [...model.required, ...model.optional]
}
function tile(
  response: DashboardResponse,
  id: ComponentId,
  options: Parameters<typeof buildDashboardViewModel>[1] = FRESH,
) {
  const found = allTiles(response, options).find((entry) => entry.id === id)
  if (found === undefined) throw new Error(`tile not found: ${id}`)
  return found
}

describe('dashboardViewModel: 通常(取得できている)', () => {
  it('必須 5・任意 3 のタイルを、定義表の順に作る', () => {
    const model = buildDashboardViewModel(dashboard.allNormal(), FRESH)

    expect(model.required.map((entry) => entry.id)).toEqual([
      'crawler',
      'indexer',
      'opensearch',
      'api',
      'web',
    ])
    expect(model.optional.map((entry) => entry.id)).toEqual([
      'opensearch-dashboards',
      'embedding',
      'llm',
    ])
  })

  it('正常: 「応答しています · 確認 hh:mm:ss」(ブラウザのローカル時刻)。役割と導線を持つ', () => {
    // component() の checked_at は 2026-11-22T01:00:00Z = JST 10:00:00
    expect(tile(dashboard.allNormal(), 'crawler')).toEqual({
      id: 'crawler',
      role: '文書の取得とジョブの実行',
      status: 'normal',
      detail: '応答しています · 確認 10:00:00',
      emphasized: false,
      link: { label: 'ジョブの状態を確認', routeName: 'jobs' },
    })
  })

  it('異常: 「応答がありません。コンテナが停止している可能性があります。確認 …」。本文色(emphasized)', () => {
    expect(tile(dashboard.abnormal(), 'crawler')).toMatchObject({
      status: 'abnormal',
      detail: '応答がありません。コンテナが停止している可能性があります。確認 10:00:00',
      emphasized: true,
    })
  })

  it.each([
    ['timeout', '状態を取得できませんでした(時間内に応答がありませんでした)。'],
    ['connection_error', '状態を取得できませんでした(接続できませんでした)。'],
    [null, '状態を取得できませんでした。'],
  ] as const)('判定不能(reason=%s): %s', (reason, detail) => {
    const response = dashboard.allNormal()
    response.components[1] = {
      ...component('indexer', 'undetermined'),
      reason: reason as ComponentStatus['reason'],
    }

    expect(tile(response, 'indexer')).toMatchObject({
      status: 'undetermined',
      detail,
      emphasized: true,
    })
  })

  it('未知の reason(フィクスチャ): 判定不能は「状態を取得できませんでした。」だけ、異常は reason によらず固定の文', () => {
    const response = dashboard.unknownReason()

    expect(tile(response, 'indexer').detail).toBe('状態を取得できませんでした。')
    expect(tile(response, 'crawler').detail).toBe(
      '応答がありません。コンテナが停止している可能性があります。確認 10:00:00',
    )
  })

  it('未設定: 「設定されていません(任意)。」。導線なし', () => {
    expect(tile(dashboard.allNormal(), 'embedding')).toMatchObject({
      status: 'not_configured',
      detail: '設定されていません(任意)。',
      emphasized: false,
      link: null,
    })
  })

  it('導線: crawler・indexer が J1、opensearch が O1、ほかにはない', () => {
    const links = allTiles(dashboard.allNormal()).map((entry) => [entry.id, entry.link?.routeName])

    expect(links).toEqual([
      ['crawler', 'jobs'],
      ['indexer', 'jobs'],
      ['opensearch', 'opensearch'],
      ['api', undefined],
      ['web', undefined],
      ['opensearch-dashboards', undefined],
      ['embedding', undefined],
      ['llm', undefined],
    ])
  })

  it('確認時刻が読めないときは、時刻を省く(落とさない)', () => {
    const response = dashboard.allNormal()
    response.components[0] = { ...component('crawler', 'normal'), checked_at: 'not a date' }

    expect(tile(response, 'crawler').detail).toBe('応答しています')
  })

  it('未知の state は判定不能、応答にないコンポーネントも判定不能(出さないと、落ちているのを見逃す)', () => {
    const response = dashboard.allNormal()
    response.components[0] = {
      ...component('crawler', 'normal'),
      state: 'brand_new_state' as ComponentStatus['state'],
    }
    response.components = response.components.filter((entry) => entry.id !== 'indexer')

    expect(tile(response, 'crawler').status).toBe('undetermined')
    expect(tile(response, 'indexer')).toMatchObject({
      status: 'undetermined',
      detail: '状態を取得できませんでした。',
    })
  })

  it('応答の並びが違っても、定義表の順・区分(必須・任意)でタイルを作る', () => {
    const response = dashboard.allConfigured()
    response.components.reverse()

    const model = buildDashboardViewModel(response, FRESH)

    expect(model.required.map((entry) => entry.id)).toEqual([
      'crawler',
      'indexer',
      'opensearch',
      'api',
      'web',
    ])
    expect(model.optional.map((entry) => entry.id)).toEqual([
      'opensearch-dashboards',
      'embedding',
      'llm',
    ])
  })

  it('定義表にない id は無視する(8 件のまま)', () => {
    const response = dashboard.allNormal()
    response.components.push({
      ...component('crawler', 'abnormal'),
      id: 'mystery' as ComponentId,
    })

    expect(allTiles(response)).toHaveLength(8)
  })
})

describe('dashboardViewModel: 概況(dashboard 3.4)', () => {
  it('すべて正常(任意は未設定を許す): success。「正常 5 · 異常 0 · 判定不能 0 · 未設定 3」', () => {
    const { summary, counts } = buildDashboardViewModel(dashboard.allNormal(), FRESH)

    expect(summary.tone).toBe('success')
    expect(summary.title).toBe('すべてのコンポーネントが正常です')
    expect(summary.items).toEqual([
      { key: 'normal', label: '正常', value: '5' },
      { key: 'abnormal', label: '異常', value: '0' },
      { key: 'undetermined', label: '判定不能', value: '0' },
      { key: 'not-configured', label: '未設定', value: '3' },
    ])
    expect(counts).toEqual({ normal: 5, abnormal: 0, undetermined: 0, not_configured: 3 })
  })

  it('任意がすべて設定済み: 正常 8・未設定 0', () => {
    const { counts } = buildDashboardViewModel(dashboard.allConfigured(), FRESH)

    expect(counts).toEqual({ normal: 8, abnormal: 0, undetermined: 0, not_configured: 0 })
  })

  it('異常あり: error。「異常のコンポーネントがあります(N 件)」+ 異常の名前を先頭に、正常・判定不能 0・未設定', () => {
    const { summary } = buildDashboardViewModel(dashboard.abnormal(), FRESH)

    expect(summary.tone).toBe('error')
    expect(summary.title).toBe('異常のコンポーネントがあります(1 件)')
    expect(summary.items).toEqual([
      { key: 'abnormal-names', label: '異常', names: ['crawler'] },
      { key: 'normal', label: '正常', value: '4' },
      { key: 'undetermined', label: '判定不能', value: '0' },
      { key: 'not-configured', label: '未設定', value: '3' },
    ])
  })

  it('異常なし・判定不能あり: warning。「状態を確認できないコンポーネントがあります(N 件)」+ 判定不能の名前', () => {
    const { summary } = buildDashboardViewModel(dashboard.undetermined(), FRESH)

    expect(summary.tone).toBe('warning')
    expect(summary.title).toBe('状態を確認できないコンポーネントがあります(1 件)')
    expect(summary.items).toEqual([
      { key: 'undetermined-names', label: '判定不能', names: ['indexer'] },
      { key: 'normal', label: '正常', value: '4' },
      { key: 'abnormal', label: '異常', value: '0' },
      { key: 'not-configured', label: '未設定', value: '3' },
    ])
  })

  it('必須がすべて判定不能(異常なし): warning「状態を確認できないコンポーネントがあります(5 件)」。名前は定義表の順', () => {
    const { summary, counts } = buildDashboardViewModel(dashboard.allUndetermined(), FRESH)

    expect(summary.tone).toBe('warning')
    expect(summary.title).toBe('状態を確認できないコンポーネントがあります(5 件)')
    expect(summary.items[0]).toEqual({
      key: 'undetermined-names',
      label: '判定不能',
      names: ['crawler', 'indexer', 'opensearch', 'api', 'web'],
    })
    expect(counts).toEqual({ normal: 0, abnormal: 0, undetermined: 5, not_configured: 3 })
  })

  it('異常と判定不能の両方: 異常を優先して表示し、件数行に両方を並べる', () => {
    const { summary } = buildDashboardViewModel(dashboard.mixed(), FRESH)

    expect(summary.tone).toBe('error')
    expect(summary.title).toBe('異常のコンポーネントがあります(1 件)')
    expect(summary.items.map((item) => [item.key, item.names ?? item.value])).toEqual([
      ['abnormal-names', ['crawler']],
      ['undetermined-names', ['indexer']],
      ['normal', '3'],
      ['not-configured', '3'],
    ])
  })

  it('複数の異常は、名前を定義表の順に並べる', () => {
    const response = dashboard.allNormal()
    response.components[3] = component('api', 'abnormal', 'unexpected_status')
    response.components[0] = component('crawler', 'abnormal', 'connection_refused')

    const { summary } = buildDashboardViewModel(response, FRESH)

    expect(summary.title).toBe('異常のコンポーネントがあります(2 件)')
    expect(summary.items[0]?.names).toEqual(['crawler', 'api'])
  })
})

describe('dashboardViewModel: 取得失敗時の降格(dashboard 4.3。#25)', () => {
  it('前回「正常」のタイルは判定不能にし、「前回の状態: 正常(hh:mm:ss 時点)」を添える。導線は出さない', () => {
    expect(tile(dashboard.allNormal(), 'crawler', STALE)).toEqual({
      id: 'crawler',
      role: '文書の取得とジョブの実行',
      status: 'undetermined',
      detail: '前回の状態: 正常(10:44:30 時点)',
      emphasized: false,
      link: null,
    })
  })

  it('前回「異常」のタイルも判定不能にする(前回の異常を、いまも異常と断定しない)', () => {
    expect(tile(dashboard.abnormal(), 'crawler', STALE)).toMatchObject({
      status: 'undetermined',
      detail: '前回の状態: 異常(10:44:30 時点)',
    })
  })

  it('前回「判定不能」のタイルは判定不能のまま、「前回の状態: 判定不能」', () => {
    expect(tile(dashboard.undetermined(), 'indexer', STALE)).toMatchObject({
      status: 'undetermined',
      detail: '前回の状態: 判定不能(10:44:30 時点)',
    })
  })

  it('前回「未設定」のタイルは未設定のまま(設定の有無は「正常」と断定する情報ではない)', () => {
    expect(tile(dashboard.allNormal(), 'embedding', STALE)).toMatchObject({
      status: 'not_configured',
      detail: '前回取得時は、設定されていませんでした(任意)。',
      emphasized: false,
      link: null,
    })
  })

  it('前回の構成と同じ全 8 タイルを出す(任意の節も省かない)', () => {
    const model = buildDashboardViewModel(dashboard.allNormal(), STALE)

    expect(model.required).toHaveLength(5)
    expect(model.optional).toHaveLength(3)
  })

  it('概況: warning「現在の状態を確認できません」。判定不能 5・未設定 3(前回取得時の設定)・前回の構成と同じ 8 件', () => {
    const { summary, counts } = buildDashboardViewModel(dashboard.allNormal(), STALE)

    expect(summary.tone).toBe('warning')
    expect(summary.title).toBe('現在の状態を確認できません')
    expect(summary.items).toEqual([
      { key: 'undetermined', label: '判定不能', value: '5' },
      { key: 'not-configured', label: '未設定', value: '3(前回取得時の設定)' },
      { key: 'total', label: '前回の構成と同じ', value: '8 件' },
    ])
    expect(counts).toEqual({ normal: 0, abnormal: 0, undetermined: 5, not_configured: 3 })
  })

  it('前回の異常があっても、概況は異常にしない(error の概況を出さない)', () => {
    const { summary } = buildDashboardViewModel(dashboard.abnormal(), STALE)

    expect(summary.tone).toBe('warning')
    expect(summary.items.some((item) => item.names !== undefined)).toBe(false)
  })

  it('前回の取得成功時刻がないときは、時刻を省く', () => {
    expect(
      tile(dashboard.allNormal(), 'crawler', { stale: true, lastSuccessAt: null }).detail,
    ).toBe('前回の状態: 正常')
  })

  it('降格は stale のときだけ(stale でなければ、正常は正常のまま)', () => {
    expect(tile(dashboard.allNormal(), 'crawler', FRESH).status).toBe('normal')
  })
})
