import { describe, expect, it } from 'vitest'

import { findStatusEntry, statusMaps, type StatusKind } from './statusMaps'

const kinds = Object.keys(statusMaps) as StatusKind[]

describe('statusMaps(DS 4.1)', () => {
  it.each(kinds)('%s のすべての行が、アイコン(SVG パス)・文言・色を持つ', (kind) => {
    const entries = Object.entries(statusMaps[kind])

    expect(entries.length).toBeGreaterThan(0)
    for (const [, entry] of entries) {
      // `@mdi/js` のアイコンは SVG パス(`M` で始まる)。文言のないアイコンだけのタグは作らない。
      expect(entry.icon).toMatch(/^M/)
      expect(entry.label).not.toBe('')
      expect(['secondary', 'info', 'success', 'warning', 'error']).toContain(entry.tone)
    }
  })

  it('ジョブの状態は DS 4.1 の 8 値(リース切れ・ロック解放済みを含む)', () => {
    expect(Object.keys(statusMaps.job)).toEqual([
      'queued',
      'running',
      'succeeded',
      'partially_succeeded',
      'failed',
      'cancelled',
      'failed_lease_expired',
      'failed_lock_released',
    ])
  })

  it('色・形(アイコン)・文言の対応: 一部成功は琥珀の三角、失敗は赤の八角形、リース切れは赤の鍵', () => {
    expect(statusMaps.job.partially_succeeded).toMatchObject({ tone: 'warning', label: '一部成功' })
    expect(statusMaps.job.failed).toMatchObject({ tone: 'error', label: '失敗' })
    expect(statusMaps.job.failed_lease_expired).toMatchObject({
      tone: 'error',
      label: '失敗(リース切れ)',
    })
    // 形で区別する: 三角(一部成功)・八角形(失敗)・鍵(リース切れ)は、同じアイコンでない。
    const icons = [
      statusMaps.job.partially_succeeded.icon,
      statusMaps.job.failed.icon,
      statusMaps.job.failed_lease_expired.icon,
    ]
    expect(new Set(icons).size).toBe(3)
  })

  it('塗りなし(枠線のみ)は「失敗(ロック解放済み)」と「未設定」', () => {
    const outlined = kinds.flatMap((kind) =>
      Object.entries(statusMaps[kind])
        .filter(([, entry]) => 'outlined' in entry && entry.outlined === true)
        .map(([value]) => `${kind}:${value}`),
    )

    expect(outlined).toEqual(['job:failed_lock_released', 'health:not_configured'])
  })

  it('findStatusEntry: 登録済みは行を返し、未登録(継承されたプロパティ名を含む)は null', () => {
    expect(findStatusEntry('job', 'running')?.label).toBe('実行中')
    expect(findStatusEntry('job', 'unknown_status')).toBeNull()
    expect(findStatusEntry('job', 'toString')).toBeNull()
    expect(findStatusEntry('cluster', 'green')?.label).toBe('green(正常)')
  })
})
