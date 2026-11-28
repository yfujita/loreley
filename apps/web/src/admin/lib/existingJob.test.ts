import { describe, expect, it } from 'vitest'

import { existingJob } from '../../../tests/support/fixtures/jobs'
import { canLinkToJob } from './existingJob'

describe('canLinkToJob(「ジョブを表示」(J2)へ導けるか。FARC-P-35)', () => {
  it.each([
    ['running の crawl', { status: 'running', job_type: 'crawl' }],
    ['queued の crawl', { status: 'queued', job_type: 'crawl' }],
    ['running の source_delete', { status: 'running', job_type: 'source_delete' }],
    ['終端(failed)', { status: 'failed', job_type: 'crawl' }],
  ] as const)('導ける: %s', (_name, overrides) => {
    expect(canLinkToJob(existingJob(overrides))).toBe(true)
  })

  it.each([
    ['status が null(ジョブ記録がない・読めない)', { status: null }],
    ['job_type が null', { job_type: null }],
    ['どちらも null(孤児ロック)', { status: null, job_type: null }],
  ] as const)('導かない: %s', (_name, overrides) => {
    expect(canLinkToJob(existingJob(overrides))).toBe(false)
  })

  it.each([
    ['未知の status', { status: 'paused' }],
    ['未知の job_type', { job_type: 'reindex' }],
    ['プロトタイプのキー', { status: 'constructor' }],
    ['空文字', { status: '' }],
  ])('導かない(Crawler の文字列をそのまま通すため未知の値がありうる): %s', (_name, overrides) => {
    expect(canLinkToJob({ ...existingJob(), ...overrides } as never)).toBe(false)
  })

  it('既存ジョブがない(null・undefined)・job_id がない・空のときは導かない', () => {
    expect(canLinkToJob(null)).toBe(false)
    expect(canLinkToJob(undefined)).toBe(false)
    expect(canLinkToJob(existingJob({ job_id: '' }))).toBe(false)
    expect(canLinkToJob({ ...existingJob(), job_id: undefined } as never)).toBe(false)
  })
})
