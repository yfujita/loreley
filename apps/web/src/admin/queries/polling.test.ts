import { describe, expect, it } from 'vitest'

import type { JobStatus } from '@/admin/api'

import {
  DASHBOARD_POLL_INTERVAL_MS,
  JOB_POLL_INTERVAL_MS,
  dashboardRefetchInterval,
  jobDetailRefetchInterval,
} from './polling'

const queryWith = (status: JobStatus | null | undefined) => ({
  state: { data: status === undefined ? undefined : { status } },
})

describe('dashboardRefetchInterval(D1。30 秒+スイッチ)', () => {
  it('自動更新が入のときだけ 30 秒', () => {
    expect(DASHBOARD_POLL_INTERVAL_MS).toBe(30_000)
    expect(dashboardRefetchInterval(true)).toBe(30_000)
  })

  it('自動更新が切のときは更新しない', () => {
    expect(dashboardRefetchInterval(false)).toBe(false)
  })
})

describe('jobDetailRefetchInterval(J2。実行待ち・実行中のときだけ 10 秒)', () => {
  it.each(['queued', 'running'] as const)('%s は 10 秒', (status) => {
    expect(JOB_POLL_INTERVAL_MS).toBe(10_000)
    expect(jobDetailRefetchInterval(queryWith(status))).toBe(10_000)
  })

  it.each(['succeeded', 'partially_succeeded', 'failed', 'cancelled'] as const)(
    '終端(%s)で止まる',
    (status) => {
      expect(jobDetailRefetchInterval(queryWith(status))).toBe(false)
    },
  )

  it('データがない・status が null(読めない値)のときは続けない', () => {
    expect(jobDetailRefetchInterval(queryWith(undefined))).toBe(false)
    expect(jobDetailRefetchInterval(queryWith(null))).toBe(false)
  })
})
