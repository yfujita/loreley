// ShardMatrix(DS 4.15・opensearch 3.3・3.4)。1 ページの列数は、観測している要素の幅から決まる。
// jsdom にはレイアウトがないので、`ResizeObserver` の偽物の `resize()` で幅を駆動する(FMOD-U-6)。実ブラウザの列数は E2E。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, reactive } from 'vue'

import type { ShardEntry } from '@/admin/api'
import { buildMatrixModel } from '@/admin/features/opensearch/models/matrixModel'

import { opensearch } from '../../../../tests/support/fixtures/opensearch'
import { mountInLayout } from '../../../../tests/support/mount'
import { useResizeObserverStub } from '../../../../tests/support/resizeObserverStub'
import ShardMatrix from './ShardMatrix.vue'
import type { MatrixModel } from './types'

const stub = useResizeObserverStub()
const REGION = '[data-testid="o1-shards"]'

type Props = {
  model: MatrixModel
  totalIndexCount: number
  filtered: boolean
  conditionText: string
  resetKey: string
}

const originalInnerWidth = window.innerWidth
beforeEach(() => {
  window.innerWidth = 1280
})
afterEach(() => {
  window.innerWidth = originalInnerWidth
})

function propsOf(response = opensearch.many(), overrides: Partial<Props> = {}): Props {
  return {
    model: buildMatrixModel(response, response.indices),
    totalIndexCount: response.indices.length,
    filtered: false,
    conditionText: '',
    resetKey: '',
    ...overrides,
  }
}

/** props を後から差し替えられる土台(更新・条件の変更を再現する)。 */
async function mountMatrix(props: Props, width?: number) {
  const state = reactive({ ...props })
  const Host = defineComponent({ setup: () => () => h(ShardMatrix, { ...state }) })
  const mounted = await mountInLayout(Host)
  if (width !== undefined) {
    stub.resize(REGION, width)
    await nextTick()
  }
  const { wrapper } = mounted
  return {
    ...mounted,
    state,
    async resize(next: number) {
      stub.resize(REGION, next)
      await nextTick()
    },
    names: () => wrapper.findAll('.shard-matrix__index-name').map((el) => el.text()),
    count: () => wrapper.find('[data-testid="o1-count"]').text(),
    note: () => wrapper.find('.shard-matrix__note').text(),
    legendItems: () => wrapper.findAll('.shard-legend li').map((el) => el.text()),
    prev: () => wrapper.find('button[aria-label^="前へ"]'),
    next: () => wrapper.find('button[aria-label^="次へ"]'),
    select: () => wrapper.find('select'),
  }
}

describe('ShardMatrix: 1 ページの列数(ResizeObserver の幅から決める)', () => {
  // viewport → W(カード幅 − 枠 2px)→ 列数。opensearch 3.4 の検算表
  it.each([
    [1280, 982, 7],
    [1145, 847, 6],
    [1024, 742, 5],
    [840, 558, 3],
    [768, 734, 5],
  ])('viewport %ipx(W=%ipx)は 1 ページ %i 列', async (viewport, width, columns) => {
    window.innerWidth = viewport
    const view = await mountMatrix(propsOf(), width)

    expect(view.names()).toHaveLength(columns)
  })

  it.each([
    [375, 341, 2],
    [320, 286, 1],
  ])(
    'viewport %ipx(600px 未満。行見出し列 112px)は 1 ページ %i 列',
    async (viewport, width, columns) => {
      window.innerWidth = viewport
      const view = await mountMatrix(propsOf(), width)

      expect(view.names()).toHaveLength(columns)
    },
  )

  it('幅が変わると、列数が変わる(ResizeObserver の通知に追随する)', async () => {
    const view = await mountMatrix(propsOf(), 982)
    expect(view.names()).toHaveLength(7)

    await view.resize(742)
    expect(view.names()).toHaveLength(5)
  })

  it('幅が未計測(0)の間は 1 列。クラッシュしない', async () => {
    const view = await mountMatrix(propsOf())

    expect(view.names()).toHaveLength(1)
  })

  it('列幅は全ページ同じ floor((W − H) ÷ 列数)。表の幅 = H + 列数 × 列幅(最終ページの列が少なくても変えない)', async () => {
    const view = await mountMatrix(propsOf(), 982)
    const widthsOf = () => view.wrapper.findAll('col').map((col) => col.attributes('style'))

    expect(widthsOf()).toEqual(['width: 152px;', ...Array(7).fill('width: 118px;')])
    expect(view.wrapper.find('table').attributes('style')).toContain('width: 978px')
    await view.select().setValue('4')
    expect(widthsOf()).toEqual(['width: 152px;', ...Array(4).fill('width: 118px;')])
  })

  it('1 ページに収まるときは、ページ送りを出さない。列幅は余りを分け、200px が上限', async () => {
    const response = opensearch.multiNode()
    const view = await mountMatrix(propsOf(response), 982)

    expect(
      view.wrapper.find('[role="group"][aria-label="シャードの配置のページ送り"]').exists(),
    ).toBe(false)
    expect(view.wrapper.findAll('col').map((col) => col.attributes('style'))).toEqual([
      'width: 152px;',
      'width: 200px;',
      'width: 200px;',
      'width: 200px;',
    ])
  })

  it('375px・320px では、インデックスが 3 件でもページ送りが出る(列が 2・1 のため。意図した動き)', async () => {
    window.innerWidth = 375
    const view = await mountMatrix(propsOf(opensearch.multiNode()), 341)

    expect(view.names()).toHaveLength(2)
    expect(view.select().findAll('option')).toHaveLength(2)
  })
})

describe('ShardMatrix: 境界', () => {
  const firstN = (n: number) => {
    const response = opensearch.many()
    return propsOf(response, {
      model: buildMatrixModel(response, response.indices.slice(0, n)),
      totalIndexCount: n,
    })
  }

  it('インデックスがちょうど 1 ページ分(7 列・幅 982)なら、ページ送りを出さず「7 件のインデックス」', async () => {
    const view = await mountMatrix(firstN(7), 982)

    expect(view.names()).toHaveLength(7)
    expect(
      view.wrapper.find('[role="group"][aria-label="シャードの配置のページ送り"]').exists(),
    ).toBe(false)
    expect(view.count()).toBe('7 件のインデックス')
  })

  it('8 列分(1 つ超える)なら、ページ送りが出て「1–7 / 全 8 件のインデックス」', async () => {
    const view = await mountMatrix(firstN(8), 982)

    expect(view.names()).toHaveLength(7)
    expect(view.select().findAll('option')).toHaveLength(2)
    expect(view.count()).toBe('1–7 / 全 8 件のインデックス(ページ 1 / 2)')
  })

  it('行見出し列の幅 H は viewport 600px で切り替わる: W=590 は 600px(wide)で 3 列、599px(narrow)で 4 列', async () => {
    window.innerWidth = 600
    const wide = await mountMatrix(propsOf(), 590)
    expect(wide.names()).toHaveLength(3)

    window.innerWidth = 599
    const narrow = await mountMatrix(propsOf(), 590)
    expect(narrow.names()).toHaveLength(4)
  })
})

describe('ShardMatrix: 同じ役割・番号のチップの重複', () => {
  const INDEX = 'loreley-documents-000001'
  const replica: ShardEntry = {
    index: INDEX,
    shard: 1,
    role: 'replica',
    state: 'started',
    node: 'node-1',
  }
  const withShards = (shards: ShardEntry[]) => {
    const response = opensearch.green()
    response.shards = shards
    return propsOf(response)
  }

  it('同じセル・未割り当て行に同じ役割・番号が 2 つあっても、2 つとも描き、更新(差分の描画)で key の重複警告を出さない', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      // 先に別のシャードを描き、重複のある内容へ差し替える(Vue が key の重複を調べるのは、差分が複雑な更新のとき)
      const view = await mountMatrix(
        withShards([
          { ...replica, shard: 9 },
          { ...replica, shard: 9, state: 'unassigned', node: null },
        ]),
        982,
      )

      view.state.model = withShards([
        replica,
        { ...replica },
        { ...replica, state: 'unassigned', node: null },
        { ...replica, state: 'unassigned', node: null },
      ]).model
      await nextTick()

      const rows = view.wrapper.findAll('tbody tr')
      expect(rows[0]!.findAll('.shard-chip')).toHaveLength(2)
      expect(rows[1]!.findAll('.shard-chip')).toHaveLength(2)
      const duplicateKeyWarnings = warn.mock.calls.filter((call) =>
        String(call[0]).includes('Duplicate keys'),
      )
      expect(duplicateKeyWarnings).toEqual([])
    } finally {
      warn.mockRestore()
    }
  })
})

describe('ShardMatrix: ページ送り', () => {
  it('次へ・前へ・ページ選択で列を切り替える。件数表示は「a–b / 全 N 件のインデックス」', async () => {
    const view = await mountMatrix(propsOf(), 982)
    expect(view.count()).toBe('1–7 / 全 25 件のインデックス(ページ 1 / 4)')
    const firstPage = view.names()

    await view.next().trigger('click')
    expect(view.count()).toBe('8–14 / 全 25 件のインデックス(ページ 2 / 4)')
    expect(view.names()).not.toEqual(firstPage)

    await view.select().setValue('4')
    expect(view.count()).toBe('22–25 / 全 25 件のインデックス(ページ 4 / 4)')
    expect(view.names()).toHaveLength(4)

    await view.prev().trigger('click')
    expect(view.count()).toBe('15–21 / 全 25 件のインデックス(ページ 3 / 4)')
  })

  it('1 ページ目の「前へ」・最終ページの「次へ」は aria-disabled=true で、押しても動かない', async () => {
    const view = await mountMatrix(propsOf(), 982)
    expect(view.prev().attributes('aria-disabled')).toBe('true')

    await view.prev().trigger('click')
    expect(view.count()).toContain('1–7 /')

    await view.select().setValue('4')
    expect(view.next().attributes('aria-disabled')).toBe('true')
    await view.next().trigger('click')
    expect(view.count()).toContain('22–25 /')
  })

  it('表示範囲が 1 件のときは「25 / 全 25 件のインデックス」(「25–25」にしない)', async () => {
    window.innerWidth = 375
    const view = await mountMatrix(propsOf(opensearch.many()), 286)
    await view.select().setValue('25')

    expect(view.count()).toBe('25 / 全 25 件のインデックス(ページ 25 / 25)')
  })

  it('件数は 3 桁区切り(切り詰め後の 1,000 件: 「1–7 / 全 1,000 件のインデックス(ページ 1 / 143)」)', async () => {
    const response = opensearch.truncated()
    const view = await mountMatrix(propsOf(response), 982)

    expect(view.count()).toBe('1–7 / 全 1,000 件のインデックス(ページ 1 / 143)')
    await view.select().setValue('143')
    expect(view.count()).toBe('995–1,000 / 全 1,000 件のインデックス(ページ 143 / 143)')
  })

  it('ページ送りでは、凡例は変わらない(全ページ分のデータで決める)', async () => {
    const view = await mountMatrix(propsOf(), 982)
    const first = view.legendItems()

    await view.select().setValue('4')

    expect(view.legendItems()).toEqual(first)
    expect(first.join('|')).toContain('未割り当てのレプリカ(点線)')
    expect(first.join('|')).toContain('初期化中・移動中')
  })

  it('幅の変化で列数が変わったとき、表示中の先頭のインデックスを含むページにする', async () => {
    const view = await mountMatrix(propsOf(), 982)
    await view.select().setValue('2') // 8〜14 件目。先頭は 8 件目
    const head = view.names()[0]

    await view.resize(742) // 5 列。8 件目(位置 7)は 2 ページ目(6〜10 件目)
    expect(view.count()).toContain('6–10 /')
    expect(view.names()).toContain(head)
  })

  it('更新(model の差し替え)でも、先頭のインデックスを含むページを保つ。なくなっていれば最終ページに丸める', async () => {
    const view = await mountMatrix(propsOf(), 982)
    await view.select().setValue('3') // 15〜21 件目
    const head = view.names()[0]

    // 同じインデックスのまま更新
    view.state.model = propsOf().model
    await nextTick()
    expect(view.count()).toContain('15–21 /')
    expect(view.names()[0]).toBe(head)

    // 先頭のインデックスがなくなった(全件の先頭 20 件だけに)
    const response = opensearch.many()
    const kept = response.indices.slice(0, 20)
    view.state.model = buildMatrixModel(response, kept)
    await nextTick()
    expect(view.count()).toBe('15–20 / 全 20 件のインデックス(ページ 3 / 3)')
  })

  it('resetKey が変わったら 1 ページ目に戻る。同じ resetKey のままなら、ページを保つ', async () => {
    const view = await mountMatrix(propsOf(), 982)
    await view.select().setValue('3')

    view.state.resetKey = '' // 同じ
    await nextTick()
    expect(view.count()).toContain('15–21 /')

    view.state.resetKey = 'changed'
    await nextTick()
    expect(view.count()).toContain('1–7 /')
  })
})

describe('ShardMatrix: 列見出し(名前 → ドキュメント件数 → 状態タグ)', () => {
  it('DOM の順は 名前 → 件数 → 状態。件数は「12,846 件」(3 桁区切り・単位「件」)', async () => {
    const view = await mountMatrix(propsOf(opensearch.multiNode()), 982)

    const header = view.wrapper.find('thead th.shard-matrix__index')
    const parts = header.findAll('.shard-matrix__index-inner > *').map((el) => el.classes()[0])
    expect(parts[0]).toBe('shard-matrix__index-name')
    expect(parts[1]).toBe('shard-matrix__doc-count')
    expect(header.find('.shard-matrix__index-inner > :nth-child(3)').text()).toBe('green')
    expect(header.text()).toBe('demo-docs-000001ドキュメント 12,846 件green')
    expect(header.attributes('scope')).toBe('col')
  })

  it('件数: 0 件は「0 件」、10 桁は「1,234,567,890 件」。数字は折り返さない(nowrap の要素)', async () => {
    const response = opensearch.many()
    const view = await mountMatrix(propsOf(response), 2000)

    const text = (name: string) =>
      view.wrapper.find(`[data-testid="o1-count-${name}"]`).text().replace(/\s+/g, ' ')
    expect(text('demo-logs-2026.11.01')).toBe('ドキュメント 1,234,567,890 件')
    expect(
      view.wrapper
        .find('[data-testid="o1-count-demo-logs-2026.11.01"] .shard-matrix__doc-number')
        .exists(),
    ).toBe(true)
  })

  it('件数が 0 のインデックスは「0 件」(取得不能の「—」と区別する)', async () => {
    const response = opensearch.green()
    response.indices[0]!.document_count = 0
    const view = await mountMatrix(propsOf(response), 982)

    expect(view.wrapper.find('[data-testid^="o1-count-"]').text()).toContain('0 件')
  })

  it('件数が取得できない(null)は「—」+視覚的に隠した「ドキュメント件数を取得できません」。補足に「見出しの「—」は…」を足す', async () => {
    const response = opensearch.red()
    const view = await mountMatrix(propsOf(response), 982)

    const count = view.wrapper.find('[data-testid="o1-count-demo-docs-000001"]')
    expect(count.text()).toBe('—ドキュメント件数を取得できません')
    expect(count.find('.sr-only').text()).toBe('ドキュメント件数を取得できません')
    expect(view.note()).toContain('見出しの「—」は件数を取得できません。')
  })

  it('補足の「—」の文は、現在の表示列に件数「—」があるときだけ(ページを送ると消える)', async () => {
    const view = await mountMatrix(propsOf(), 982)
    // demo-logs-2026.11.16(件数 null)は、並びの 21 番目(3 ページ目)
    expect(view.note()).not.toContain('見出しの「—」')

    await view.select().setValue('3')
    expect(view.note()).toContain('見出しの「—」は件数を取得できません。')
  })

  it('補足(インデックス名の下の数はドキュメント件数・並び順)は、ページングの有無にかかわらず常に出す', async () => {
    const paged = await mountMatrix(propsOf(), 982)
    const single = await mountMatrix(propsOf(opensearch.multiNode()), 982)

    for (const view of [paged, single]) {
      expect(view.note()).toContain('インデックス名の下の数はドキュメント件数。')
      expect(view.note()).toContain('状態の悪い順(同じ状態は名前の昇順)。')
    }
  })

  it('状態タグは green / yellow / red。未知の値は中立のタグで値をそのまま出す。null は「—」+読み上げ', async () => {
    const unknown = await mountMatrix(propsOf(opensearch.unknownValues()), 982)
    expect(unknown.wrapper.find('thead .status-tag').text()).toBe('purple')

    const nullStatus = await mountMatrix(propsOf(opensearch.nullIndexValues()), 982)
    expect(nullStatus.wrapper.find('thead').text()).toContain('状態を取得できません')
    expect(nullStatus.wrapper.find('thead .status-tag').exists()).toBe(false)
  })
})

describe('ShardMatrix: 行・セル', () => {
  it('行見出しはノード名+「シャード n」(視覚的に隠した「(全インデックスの合計)」)。<th scope="row">', async () => {
    const response = opensearch.multiNode()
    const view = await mountMatrix(propsOf(response), 982)

    const rows = view.wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    const header = rows[0]!.find('th')
    expect(header.attributes('scope')).toBe('row')
    expect(header.text()).toBe('node-1シャード 3(全インデックスの合計)')
  })

  it('セル: シャードのチップ(プライマリ → レプリカ)。シャードがないセルは「—」+視覚的に隠した「シャードなし」', async () => {
    const response = opensearch.yellow()
    response.nodes.push({ name: 'node-2' })
    const view = await mountMatrix(propsOf(response), 982)

    const rows = view.wrapper.findAll('tbody tr')
    expect(rows[0]!.find('td').text()).toContain('P0')
    expect(rows[1]!.find('td').text()).toBe('—シャードなし')
  })

  it('未割り当てのシャードがあるときだけ、最下部に「未割り当て」の行(点線のチップ)。なければ出さない', async () => {
    const yellow = await mountMatrix(propsOf(opensearch.yellow()), 982)
    const rows = yellow.wrapper.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[1]!.classes()).toContain('shard-matrix__unassigned')
    expect(rows[1]!.find('th').text()).toBe('未割り当て シャード 1(全インデックスの合計)')
    expect(rows[1]!.find('.shard-chip--unassigned-replica').exists()).toBe(true)

    const green = await mountMatrix(propsOf(opensearch.multiNode()), 982)
    expect(green.wrapper.find('.shard-matrix__unassigned').exists()).toBe(false)
  })

  it('現在のページに未割り当てのシャードがなくても、行は残る(セルは「—」。ページで行の構成を変えない)', async () => {
    const view = await mountMatrix(propsOf(), 982)
    await view.select().setValue('4')

    const row = view.wrapper.find('.shard-matrix__unassigned')
    expect(row.exists()).toBe(true)
    expect(row.find('th').text()).toContain('シャード 2')
  })

  it('絞り込み中の行見出しは「(絞り込み後のインデックスの合計)」', async () => {
    const view = await mountMatrix(
      propsOf(opensearch.multiNode(), { filtered: true, conditionText: '状態が green' }),
      982,
    )

    expect(view.wrapper.find('tbody th').text()).toContain('(絞り込み後のインデックスの合計)')
  })

  it('表の caption(視覚的に隠す)に、向き・件数・表示範囲・並びを書く。aria-sort は付けない', async () => {
    const view = await mountMatrix(propsOf(), 982)

    expect(view.wrapper.find('caption').classes()).toContain('sr-only')
    expect(view.wrapper.find('caption').text()).toBe(
      'シャードの配置。行はノードと未割り当て、列はインデックス(列見出しにインデックス名・ドキュメント件数・状態)。全 25 件のうち 1〜7 件目を表示中(ページ 1 / 4)。状態の悪い順、同じ状態は名前の昇順。',
    )
    expect(view.wrapper.find('[aria-sort]').exists()).toBe(false)
  })

  it('角(thead の「ノード」)は <th scope=col>。左端の行見出しの sticky は CSS なので E2E で測る', async () => {
    const view = await mountMatrix(propsOf(), 982)

    expect(view.wrapper.find('thead th.shard-matrix__corner').text()).toBe('ノード')
    expect(view.wrapper.find('thead th.shard-matrix__corner').attributes('scope')).toBe('col')
  })
})

describe('ShardMatrix: 凡例', () => {
  it('プライマリ・レプリカは常に。ほかは、表示対象にあるときだけ', async () => {
    const view = await mountMatrix(propsOf(opensearch.multiNode()), 982)

    expect(view.legendItems()).toEqual(['P0 プライマリ', 'R0 レプリカ'])
  })

  it('model.legend のとおりに出す(未割り当てのプライマリ・初期化中/移動中)', async () => {
    const view = await mountMatrix(propsOf(opensearch.unassignedAndMoving()), 982)

    expect(view.legendItems().map((text) => text.replace(/^[PR]0 /, ''))).toEqual([
      'プライマリ',
      'レプリカ',
      '未割り当てのレプリカ(点線)',
      '初期化中・移動中',
    ])
  })
})

describe('ShardMatrix: 絞り込みの件数表示と一致 0 件', () => {
  it('件数表示(role=status・aria-live=polite・aria-atomic)の文: 絞り込み前', async () => {
    const view = await mountMatrix(propsOf(opensearch.multiNode()), 982)

    const status = view.wrapper.find('[data-testid="o1-count"]')
    expect(status.attributes('role')).toBe('status')
    expect(status.attributes('aria-live')).toBe('polite')
    expect(status.attributes('aria-atomic')).toBe('true')
    expect(status.text()).toBe('3 件のインデックス')
  })

  it('絞り込み後(1 ページ): 「絞り込み後 N 件のインデックス(全 M 件中)」+補足に「適用中の条件: …」', async () => {
    const response = opensearch.many()
    const view = await mountMatrix(
      propsOf(response, {
        model: buildMatrixModel(response, response.indices.slice(0, 3)),
        totalIndexCount: 25,
        filtered: true,
        conditionText: '名前に「docs」を含む',
      }),
      982,
    )

    expect(view.count()).toBe('絞り込み後 3 件のインデックス(全 25 件中)')
    expect(view.note()).toContain(
      '適用中の条件: 名前に「docs」を含む。概況はクラスタ全体の値で、絞り込みの対象外。',
    )
    // 「(全 M 件中)」は 1 つの塊として折り返さない
    expect(view.wrapper.findAll('.shard-matrix__nb').map((el) => el.text())).toEqual([
      '絞り込み後 3 件のインデックス',
      '(全 25 件中)',
    ])
  })

  it('絞り込み後も複数ページ: 「a–b / 絞り込み後 N 件のインデックス(全 M 件中)」', async () => {
    const response = opensearch.many()
    const view = await mountMatrix(
      propsOf(response, {
        model: buildMatrixModel(response, response.indices.slice(0, 16)),
        totalIndexCount: 25,
        filtered: true,
        conditionText: '名前に「logs」を含む',
      }),
      982,
    )

    expect(view.count()).toBe('1–7 / 絞り込み後 16 件のインデックス(全 25 件中)(ページ 1 / 3)')
  })

  it('一致 0 件: 件数表示は「絞り込み後 0 件のインデックス(全 M 件中)」(要素は消さない)。凡例・ページ送り・表は出さず、ブロックを出す', async () => {
    const response = opensearch.many()
    const view = await mountMatrix(
      propsOf(response, {
        model: buildMatrixModel(response, []),
        totalIndexCount: 25,
        filtered: true,
        conditionText: '名前に「zzz」を含む',
      }),
      982,
    )

    expect(view.count()).toBe('絞り込み後 0 件のインデックス(全 25 件中)')
    expect(view.note()).toBe(
      '適用中の条件: 名前に「zzz」を含む。概況はクラスタ全体の値で、絞り込みの対象外。',
    )
    expect(view.wrapper.find('.shard-legend').exists()).toBe(false)
    expect(view.wrapper.find('table').exists()).toBe(false)
    expect(view.wrapper.find('select').exists()).toBe(false)
    const block = view.wrapper.find('[data-testid="o1-state-nomatch"]')
    expect(block.find('h3').text()).toBe('条件に合うインデックスがありません')
    expect(block.text()).toContain('「条件を解除」')
    // 解除のボタンはフォームの 1 つだけ(ブロックには置かない)
    expect(block.find('button').exists()).toBe(false)
  })
})

describe('ShardMatrix: 領域・横スクロール', () => {
  it('role=group(シャードの配置(行はノード、列はインデックス))・testid o1-shards', async () => {
    const view = await mountMatrix(propsOf(), 982)

    const region = view.wrapper.find(REGION)
    expect(region.attributes('role')).toBe('group')
    expect(region.attributes('aria-label')).toBe('シャードの配置(行はノード、列はインデックス)')
  })

  it('収まっている通常時は、スクロール領域に tabindex・role を付けない', async () => {
    const view = await mountMatrix(propsOf(), 982)

    const scroller = view.wrapper.find('.shard-matrix__scroll')
    expect(scroller.attributes('tabindex')).toBeUndefined()
    expect(scroller.attributes('role')).toBeUndefined()
  })

  it('収まらずスクロールできるときだけ、tabindex=0・role=region・aria-label を付ける(拡大時の保険)', async () => {
    vi.spyOn(Element.prototype, 'scrollWidth', 'get').mockReturnValue(2000)
    vi.spyOn(Element.prototype, 'clientWidth', 'get').mockReturnValue(1000)
    try {
      const view = await mountMatrix(propsOf(), 982)
      await view.resize(900)
      await nextTick()
      await nextTick()

      const scroller = view.wrapper.find('.shard-matrix__scroll')
      expect(scroller.attributes('tabindex')).toBe('0')
      expect(scroller.attributes('role')).toBe('region')
      expect(scroller.attributes('aria-label')).toBe('シャードの配置(横にスクロールできます)')
    } finally {
      vi.restoreAllMocks()
    }
  })
})
