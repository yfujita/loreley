import { matchQuery } from '@tanstack/vue-query'
import { describe, expect, it } from 'vitest'

import { keys } from './keys'

describe('key factory(E 5.4 の表)', () => {
  it('メタ・ダッシュボード・OpenSearch', () => {
    expect(keys.meta()).toEqual(['meta'])
    expect(keys.dashboard()).toEqual(['dashboard'])
    expect(keys.opensearch.cluster()).toEqual(['opensearch', 'cluster'])
  })

  it('データソース: 一覧・詳細・編集(詳細と編集は別の key)', () => {
    expect(keys.sources.list()).toEqual(['sources', 'list'])
    expect(keys.sources.detail('demo')).toEqual(['sources', 'detail', 'demo'])
    expect(keys.sources.edit('demo')).toEqual(['sources', 'edit', 'demo'])
    expect(keys.sources.detail('demo')).not.toEqual(keys.sources.edit('demo'))
  })

  it('ジョブ・文書は条件(params)を key に含める', () => {
    const jobsParams = {
      page: 2,
      itemsPerPage: 50,
      sort: '-queued_at',
      sourceId: 'demo',
      status: 'active',
    } as const
    const documentsParams = { tab: 'skipped', page: 1, itemsPerPage: 25, sort: null } as const

    expect(keys.jobs.list(jobsParams)).toEqual(['jobs', 'list', jobsParams])
    expect(keys.jobs.detail('job-1')).toEqual(['jobs', 'detail', 'job-1'])
    expect(keys.documents.list('demo', documentsParams)).toEqual([
      'documents',
      'demo',
      documentsParams,
    ])
    expect(keys.documents.list(null, documentsParams)[1]).toBeNull()
  })

  it('invalidate の prefix は、その領域のすべての key に一致する(他の領域には一致しない)', () => {
    const sourceKeys = [keys.sources.list(), keys.sources.detail('a'), keys.sources.edit('a')]
    const otherKeys = [
      keys.meta(),
      keys.dashboard(),
      keys.jobs.detail('a'),
      keys.opensearch.cluster(),
    ]

    for (const key of sourceKeys) {
      expect(matchQuery({ queryKey: keys.sources.all }, { queryKey: key } as never)).toBe(true)
    }
    for (const key of otherKeys) {
      expect(matchQuery({ queryKey: keys.sources.all }, { queryKey: key } as never)).toBe(false)
    }
  })
})
