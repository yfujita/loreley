import { describe, expect, it } from 'vitest'

import type { ClusterSummary } from '@/admin/api'

import { mountInLayout } from '../../../../tests/support/mount'
import ClusterSummaryView from './ClusterSummary.vue'

const CLUSTER: ClusterSummary = {
  name: 'demo-cluster',
  status: 'yellow',
  node_count: 3,
  active_shards: 53,
  relocating_shards: 1,
  initializing_shards: 0,
  unassigned_shards: 3,
}

async function mountSummary(overrides: Partial<ClusterSummary> = {}, stale = false) {
  const { wrapper } = await mountInLayout(ClusterSummaryView, {
    props: { cluster: { ...CLUSTER, ...overrides }, stale },
  })
  return wrapper
}

/** 件数 4 項目(ラベル → 値のテキスト) */
function stats(wrapper: Awaited<ReturnType<typeof mountSummary>>) {
  return wrapper
    .findAll('.cluster-summary__stats > div')
    .map((item) => [item.find('dt').text(), item.find('dd').text().replace(/\s+/g, ' ')])
}

describe('ClusterSummary(概況。opensearch 3.0・3.1)', () => {
  it('クラスタ名(等幅)・状態タグ・説明・件数 4 項目(ノード / アクティブ(うち移動中)/ 未割り当て / 初期化中)', async () => {
    const wrapper = await mountSummary()

    expect(wrapper.find('[data-testid="o1-summary"]').exists()).toBe(true)
    expect(wrapper.find('.cluster-summary__head').text()).toContain('demo-cluster')
    expect(wrapper.find('.cluster-summary__head .status-tag').text()).toBe('yellow(注意)')
    expect(stats(wrapper)).toEqual([
      ['ノード', '3'],
      ['アクティブ', '53 うち移動中 1'],
      ['未割り当て', '3'],
      ['初期化中', '0'],
    ])
  })

  it('件数は 3 桁区切り。0 でも「0」を出す', async () => {
    const wrapper = await mountSummary({ active_shards: 12_345, relocating_shards: 0 })

    expect(stats(wrapper)[1]).toEqual(['アクティブ', '12,345 うち移動中 0'])
  })

  it.each([
    ['green', 'green(正常)', 'すべてのシャードが割り当てられています。'],
    [
      'yellow',
      'yellow(注意)',
      'プライマリシャードはすべて割り当てられていますが、一部のレプリカシャードが割り当てられていません。単一ノードでレプリカが 1 以上のインデックスは、通常 yellow になります。',
    ],
    [
      'red',
      'red(異常)',
      '一部のプライマリシャードが割り当てられていません。該当するインデックスの検索や登録に影響する可能性があります。',
    ],
  ])('%s: タグ「%s」と状態の説明', async (status, tag, description) => {
    const wrapper = await mountSummary({ status })

    expect(wrapper.find('.status-tag').text()).toBe(tag)
    expect(wrapper.find('.cluster-summary__description').text()).toBe(description)
  })

  it('未知の状態値: 中立のタグで値をそのまま出し、説明は出さない', async () => {
    const wrapper = await mountSummary({ status: 'purple' })

    expect(wrapper.find('.status-tag').text()).toBe('purple')
    expect(wrapper.find('.cluster-summary__description').exists()).toBe(false)
  })

  it('前回データ(stale)のときは、説明に「前回取得時の値です。」を添える。未知の状態値でもその一文だけ出す', async () => {
    const green = await mountSummary({ status: 'green' }, true)
    expect(green.find('.cluster-summary__description').text()).toBe(
      'すべてのシャードが割り当てられています。 前回取得時の値です。',
    )

    const unknown = await mountSummary({ status: 'purple' }, true)
    expect(unknown.find('.cluster-summary__description').text()).toBe('前回取得時の値です。')
  })

  it('クラスタ名・件数は <dl> の dt / dd の対', async () => {
    const wrapper = await mountSummary()

    expect(wrapper.findAll('dl')).toHaveLength(2)
    expect(wrapper.findAll('dt').map((el) => el.text())).toEqual([
      'クラスタ名',
      '状態',
      'ノード',
      'アクティブ',
      '未割り当て',
      '初期化中',
    ])
  })
})
