import { describe, expect, it } from 'vitest'

import type { Unavailable } from '@/admin/api'

import { documents } from '../../../tests/support/fixtures/documents'
import { jobList } from '../../../tests/support/fixtures/jobs'
import { sourceDetails, sourceList } from '../../../tests/support/fixtures/sources'
import {
  cellState,
  rowCell,
  rowUnavailableReason,
  topCell,
  topUnavailableReason,
  UNAVAILABLE_PATH,
} from './unavailable'

const EXPECTED = { expected: true }
const OPTIONAL = { expected: false }

describe('cellState(E 5.9 の 4 状態)', () => {
  it('値があれば value(0・false・空文字も値)', () => {
    expect(cellState({}, 'x', 12, EXPECTED)).toEqual({ kind: 'value', value: 12 })
    expect(cellState({}, 'x', 0, EXPECTED)).toEqual({ kind: 'value', value: 0 })
    expect(cellState({}, 'x', false, EXPECTED)).toEqual({ kind: 'value', value: false })
    expect(cellState({}, 'x', '', EXPECTED)).toEqual({ kind: 'value', value: '' })
  })

  it('値があれば、同じパスが unavailable にあっても value(値を優先する)', () => {
    expect(cellState({ x: 'timeout' }, 'x', 5, EXPECTED)).toEqual({ kind: 'value', value: 5 })
  })

  it('null で unavailable にキーがあれば、取得できなかった(理由コードを持つ)', () => {
    expect(cellState({ x: 'store_unavailable' }, 'x', null, EXPECTED)).toEqual({
      kind: 'unavailable',
      reason: 'store_unavailable',
    })
    expect(cellState({ x: 'timeout' }, 'x', undefined, OPTIONAL)).toEqual({
      kind: 'unavailable',
      reason: 'timeout',
    })
  })

  it('null でキーがなく、値があるはずの項目なら、読み取れない(unreadable)', () => {
    expect(cellState({}, 'x', null, EXPECTED)).toEqual({ kind: 'unreadable' })
  })

  it('null でキーがなく、値があるはずでない項目なら、値がない(none)', () => {
    expect(cellState({}, 'x', null, OPTIONAL)).toEqual({ kind: 'none' })
  })

  it('別のパスのキーは影響しない', () => {
    const unavailable: Unavailable = { y: 'timeout' }

    expect(cellState(unavailable, 'x', null, EXPECTED)).toEqual({ kind: 'unreadable' })
  })

  it('プロトタイプのキー(constructor・toString)を取得失敗と誤判定しない', () => {
    expect(cellState({}, 'constructor', null, OPTIONAL)).toEqual({ kind: 'none' })
    expect(cellState({}, 'toString', null, OPTIONAL)).toEqual({ kind: 'none' })
  })
})

describe('unavailable が欠落しても落とさない(生成型を信用しない。E 5.3)', () => {
  it('cellState: unavailable が undefined・null のとき、キーなしと同じに扱う', () => {
    expect(cellState(undefined, 'x', null, EXPECTED)).toEqual({ kind: 'unreadable' })
    expect(cellState(null, 'x', null, OPTIONAL)).toEqual({ kind: 'none' })
    expect(cellState(undefined, 'x', 3, EXPECTED)).toEqual({ kind: 'value', value: 3 })
  })

  it('行・最上位の参照も、unavailable がない応答で undefined を返す', () => {
    const missing = {} as { unavailable: Unavailable }

    expect(rowUnavailableReason(missing, 'document_count')).toBeUndefined()
    expect(topUnavailableReason(missing, 'lock')).toBeUndefined()
    expect(rowCell(missing, 'document_count', null, OPTIONAL)).toEqual({ kind: 'none' })
    expect(topCell(missing, 'lock', null, EXPECTED)).toEqual({ kind: 'unreadable' })
  })

  it('unavailable がオブジェクトでない(文字列など)ときも、キーなしと同じ', () => {
    expect(cellState('oops' as never, 'x', null, OPTIONAL)).toEqual({ kind: 'none' })
  })
})

describe('行の unavailable(一覧の EP。EP-01・09・11)', () => {
  it('source-a の未実行(キーなし)と source-b の読み取り失敗(キーあり)を区別する', () => {
    const [sourceA, sourceB] = sourceList.neverCrawledAndFailedMixed().items

    expect(sourceA?.last_crawl).toBeNull()
    expect(sourceB?.last_crawl).toBeNull()
    // 2 行とも last_crawl は null。行の unavailable で区別できる。
    expect(
      rowCell(sourceA!, UNAVAILABLE_PATH.sourceRow.lastCrawl, sourceA!.last_crawl, OPTIONAL),
    ).toEqual({ kind: 'none' })
    expect(
      rowCell(sourceB!, UNAVAILABLE_PATH.sourceRow.lastCrawl, sourceB!.last_crawl, OPTIONAL),
    ).toEqual({ kind: 'unavailable', reason: 'store_unavailable' })
  })

  it('全行の失敗(全行に同じキー)は、すべての行が取得失敗になる', () => {
    const rows = sourceList.allRowsUnavailable().items

    const states = rows.map((row) =>
      rowCell(row, UNAVAILABLE_PATH.sourceRow.documentCount, row.document_count, OPTIONAL),
    )

    expect(states).toEqual([
      { kind: 'unavailable', reason: 'search_index_unavailable' },
      { kind: 'unavailable', reason: 'search_index_unavailable' },
    ])
  })

  it('1 行だけの失敗は、他の行に影響しない', () => {
    const [ok, failed] = sourceList.oneRowUnavailable().items

    expect(
      rowCell(ok!, UNAVAILABLE_PATH.sourceRow.documentCount, ok!.document_count, OPTIONAL),
    ).toEqual({ kind: 'value', value: 1284 })
    expect(
      rowCell(failed!, UNAVAILABLE_PATH.sourceRow.documentCount, failed!.document_count, OPTIONAL),
    ).toEqual({ kind: 'unavailable', reason: 'timeout' })
  })

  it('入れ子の stalled は行内の相対パス(last_crawl.stalled)で引く', () => {
    const [row] = sourceList.lastCrawlStalledUnavailable().items

    expect(rowUnavailableReason(row!, UNAVAILABLE_PATH.sourceRow.lastCrawlStalled)).toBe(
      'store_unavailable',
    )
    expect(rowUnavailableReason(row!, UNAVAILABLE_PATH.sourceRow.deleteJobStalled)).toBeUndefined()
  })

  it('EP-09 の行の stalled・EP-11 の行の existence', () => {
    const [unknownLease, ok] = jobList.oneRowStalledUnavailable().items
    const [skipped] = documents.skippedExistenceUnavailable().items

    expect(rowUnavailableReason(unknownLease!, UNAVAILABLE_PATH.jobRow.stalled)).toBe(
      'store_unavailable',
    )
    expect(rowUnavailableReason(ok!, UNAVAILABLE_PATH.jobRow.stalled)).toBeUndefined()
    expect(rowUnavailableReason(skipped!, UNAVAILABLE_PATH.documentRow.existence)).toBe(
      'search_index_unavailable',
    )
  })

  it('最上位ではなく行を引く(行の unavailable を最上位のパスで引かない)', () => {
    const [row] = sourceList.oneRowUnavailable().items.slice(1)

    expect(rowUnavailableReason(row!, 'items[1].document_count')).toBeUndefined()
  })
})

describe('最上位の unavailable(EP-02・10・11)', () => {
  it('EP-02: ロックの取得失敗は正式なパス(lock)', () => {
    const detail = sourceDetails.lockUnavailable()

    expect(topUnavailableReason(detail, UNAVAILABLE_PATH.sourceDetail.lock)).toBe(
      'store_unavailable',
    )
    expect(topCell(detail, UNAVAILABLE_PATH.sourceDetail.lock, detail.lock, OPTIONAL)).toEqual({
      kind: 'unavailable',
      reason: 'store_unavailable',
    })
  })

  it('EP-02: index.document_count は入れ子の正式なパス', () => {
    const detail = sourceDetails.documentCountUnavailable()

    expect(
      topCell(
        detail,
        UNAVAILABLE_PATH.sourceDetail.indexDocumentCount,
        detail.index.document_count,
        OPTIONAL,
      ),
    ).toEqual({ kind: 'unavailable', reason: 'search_index_unavailable' })
  })

  it('EP-02: 設定の項目が読めないとき、理由は malformed(S4 だけ扱いが違う)', () => {
    const detail = sourceDetails.malformedSettings()

    expect(topUnavailableReason(detail, 'ttl_seconds')).toBe('malformed')
    expect(topCell(detail, 'ttl_seconds', detail.ttl_seconds, EXPECTED)).toEqual({
      kind: 'unavailable',
      reason: 'malformed',
    })
  })

  it('EP-11: 行に属さない項目だけ(tab_counts.<タブ>・document_count)', () => {
    const response = documents.countsUnavailable()

    expect(
      topCell(
        response,
        UNAVAILABLE_PATH.documentList.tabCount('summary_pending'),
        response.tab_counts.summary_pending,
        OPTIONAL,
      ),
    ).toEqual({ kind: 'unavailable', reason: 'search_index_unavailable' })
    expect(
      topCell(
        response,
        UNAVAILABLE_PATH.documentList.documentCount,
        response.document_count,
        OPTIONAL,
      ),
    ).toEqual({ kind: 'unavailable', reason: 'search_index_unavailable' })
    expect(
      topCell(
        response,
        UNAVAILABLE_PATH.documentList.tabCount('skipped'),
        response.tab_counts.skipped,
        OPTIONAL,
      ),
    ).toEqual({ kind: 'value', value: 2 })
  })

  it('値が null でキーなし: 値があるはずなら unreadable、なければ none(S2 の last_crawl の未実行)', () => {
    const detail = sourceDetails.neverCrawled()

    expect(
      topCell(detail, UNAVAILABLE_PATH.sourceDetail.lastCrawl, detail.last_crawl, OPTIONAL),
    ).toEqual({
      kind: 'none',
    })
    expect(topCell(detail, 'connector_type', null, EXPECTED)).toEqual({ kind: 'unreadable' })
  })
})
