import { describe, expect, it } from 'vitest'

import { ROUTE_NAMES } from './routeNames'

describe('ROUTE_NAMES(admin-view 4.2 の route の name)', () => {
  it('route の name と一致し、重複がない', () => {
    expect(Object.values(ROUTE_NAMES).sort()).toEqual(
      [
        'dashboard',
        'sources',
        'source-new',
        'source-detail',
        'source-edit',
        'jobs',
        'job-detail',
        'documents',
        'opensearch',
        'not-found',
      ].sort(),
    )
    expect(new Set(Object.values(ROUTE_NAMES)).size).toBe(Object.values(ROUTE_NAMES).length)
  })
})
