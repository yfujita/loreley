import { describe, expect, it } from 'vitest'

import type { JobStatus } from '@/admin/api'

import {
  DASHBOARD_POLL_INTERVAL_MS,
  JOB_POLL_INTERVAL_MS,
  dashboardRefetchInterval,
  jobDetailRefetchInterval,
} from './polling'

const queryWith = (status: JobStatus | null | undefined, error: unknown = null) => ({
  state: { data: status === undefined ? undefined : { status }, error },
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

  describe('再取得が失敗したとき(前回のデータは保たれる)', () => {
    const apiError = (code: string, status: number, retryable = false) => ({
      kind: 'api' as const,
      status,
      code,
      retryable,
      outcomeUnknown: false,
    })

    it.each([
      ['404 job_not_found(ジョブが存在しない)', apiError('job_not_found', 404)],
      ['404 not_found(`/` を含む ID)', apiError('not_found', 404)],
      ['400 invalid_request(ID の形式違反)', apiError('invalid_request', 400)],
    ])('%s なら、前回 running でも止める', (_name, error) => {
      expect(jobDetailRefetchInterval(queryWith('running', error))).toBe(false)
      expect(jobDetailRefetchInterval(queryWith('queued', error))).toBe(false)
    })

    it.each([
      ['通信断(network)', { kind: 'network' }],
      ['タイムアウト', { kind: 'timeout' }],
      ['503 unavailable', apiError('unavailable', 503, true)],
      ['500 internal_error', apiError('internal_error', 500)],
      ['Nginx の HTML の 502', { kind: 'invalid_response', status: 502 }],
      ['ApiError でない値', new Error('boom')],
    ])('一時的な失敗(%s)では、回復を待って続ける', (_name, error) => {
      expect(jobDetailRefetchInterval(queryWith('running', error))).toBe(10_000)
    })

    it('エラーがなければ(null・undefined)、これまでどおり status で決める', () => {
      expect(jobDetailRefetchInterval(queryWith('running', null))).toBe(10_000)
      expect(jobDetailRefetchInterval({ state: { data: { status: 'running' } } })).toBe(10_000)
    })
  })
})
