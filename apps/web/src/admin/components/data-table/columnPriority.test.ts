import { describe, expect, it } from 'vitest'

import { COLUMN_PRIORITY, filterColumnsByPriority } from './columnPriority'

describe('COLUMN_PRIORITY(DS 4.3: 識別子 > 状態 > 日時 > 件数 > 操作 > 種別・起動・周期・終了日時)', () => {
  it('高い順に 1 から並ぶ', () => {
    expect(Object.entries(COLUMN_PRIORITY)).toEqual([
      ['id', 1],
      ['status', 2],
      ['date', 3],
      ['count', 4],
      ['action', 5],
      ['other', 6],
    ])
  })
})

describe('filterColumnsByPriority', () => {
  const columns = [
    { key: 'job_id', priority: COLUMN_PRIORITY.id },
    { key: 'source', priority: COLUMN_PRIORITY.other },
    { key: 'status', priority: COLUMN_PRIORITY.status },
    { key: 'started_at', priority: COLUMN_PRIORITY.date },
    { key: 'finished_at', priority: COLUMN_PRIORITY.other },
    { key: 'actions', priority: COLUMN_PRIORITY.action },
  ]

  it('優先順位が低い(数字が大きい)列から隠す。元の並びを保つ', () => {
    expect(filterColumnsByPriority(columns, COLUMN_PRIORITY.action).map((c) => c.key)).toEqual([
      'job_id',
      'status',
      'started_at',
      'actions',
    ])
    expect(filterColumnsByPriority(columns, COLUMN_PRIORITY.date).map((c) => c.key)).toEqual([
      'job_id',
      'status',
      'started_at',
    ])
    expect(filterColumnsByPriority(columns, COLUMN_PRIORITY.id).map((c) => c.key)).toEqual([
      'job_id',
    ])
  })

  it('最大(other)なら全列を残す', () => {
    expect(filterColumnsByPriority(columns, COLUMN_PRIORITY.other)).toHaveLength(6)
  })

  it('優先順位のない列は、常に残す', () => {
    expect(filterColumnsByPriority([{ key: 'a' }, { key: 'b', priority: 6 }], 1)).toEqual([
      { key: 'a' },
    ])
  })
})
