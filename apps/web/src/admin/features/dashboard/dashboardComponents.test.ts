import { describe, expect, it } from 'vitest'

import { ROUTE_NAMES } from '@/admin/lib/routeNames'

import { dashboard } from '../../../../tests/support/fixtures/dashboard'
import { dashboardComponents } from './dashboardComponents'

describe('dashboardComponents(dashboard 3.2)', () => {
  it('必須 5 つ・任意 3 つが、API の固定の順(B 8.1)で並ぶ', () => {
    expect(dashboardComponents.map((entry) => [entry.id, entry.group])).toEqual([
      ['crawler', 'required'],
      ['indexer', 'required'],
      ['opensearch', 'required'],
      ['api', 'required'],
      ['web', 'required'],
      ['opensearch-dashboards', 'optional'],
      ['embedding', 'optional'],
      ['llm', 'optional'],
    ])
    expect(dashboardComponents.map((entry) => entry.id)).toEqual(
      dashboard.allNormal().components.map((component) => component.id),
    )
  })

  it('導線(#28)は crawler・indexer が J1、opensearch が O1。ほかにはない', () => {
    expect(dashboardComponents.map((entry) => [entry.id, entry.link?.routeName ?? null])).toEqual([
      ['crawler', ROUTE_NAMES.jobs],
      ['indexer', ROUTE_NAMES.jobs],
      ['opensearch', ROUTE_NAMES.opensearch],
      ['api', null],
      ['web', null],
      ['opensearch-dashboards', null],
      ['embedding', null],
      ['llm', null],
    ])
    expect(dashboardComponents[0]?.link?.label).toBe('ジョブの状態を確認')
    expect(dashboardComponents[2]?.link?.label).toBe('OpenSearch の詳細')
  })

  it('役割(12px の補足)をすべて持つ', () => {
    expect(dashboardComponents.every((entry) => entry.role !== '')).toBe(true)
  })
})
