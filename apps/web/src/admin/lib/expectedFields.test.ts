import { describe, expect, it } from 'vitest'

import { documents } from '../../../tests/support/fixtures/documents'
import { jobBrief, jobDetails } from '../../../tests/support/fixtures/jobs'
import { sourceDetail, sourceListItem } from '../../../tests/support/fixtures/sources'
import {
  EXPECTED_FIELDS,
  expectedFor,
  expectedKindForDocumentTab,
  isExpectedField,
  type ExpectedFieldsKind,
} from './expectedFields'
import { rowCell } from './unavailable'

describe('値があるはずの項目の表(FMOD-U-13)', () => {
  it('JobBrief・EP-10 の最上位: status・job_type・trigger・queued_at(started_at・finished_at・failure_reason は含めない)', () => {
    expect(EXPECTED_FIELDS.jobBrief).toEqual(['status', 'job_type', 'trigger', 'queued_at'])
    expect(EXPECTED_FIELDS.jobDetail).toEqual(['status', 'job_type', 'trigger', 'queued_at'])
    for (const field of ['started_at', 'finished_at', 'failure_reason', 'force_delete']) {
      expect(isExpectedField('jobBrief', field)).toBe(false)
    }
  })

  it('registration: 件数・partial・phase', () => {
    expect(EXPECTED_FIELDS.registration).toContain('created_count')
    expect(EXPECTED_FIELDS.registration).toContain('partial')
    expect(EXPECTED_FIELDS.registration).toContain('phase')
    expect(EXPECTED_FIELDS.registration).toHaveLength(10)
  })

  it('EP-01 の行: status だけ(connector_type・last_completed_at は S1 で使わない)', () => {
    expect(EXPECTED_FIELDS.sourceListRow).toEqual(['status'])
  })

  it('EP-02 の設定項目: ttl_days(割り切れない null)・schedule_cron(手動のみの null)は含めない', () => {
    expect(isExpectedField('sourceDetail', 'ttl_seconds')).toBe(true)
    expect(isExpectedField('sourceDetail', 'ttl_days')).toBe(false)
    expect(isExpectedField('sourceDetail', 'schedule_cron')).toBe(false)
  })

  describe('EP-11 の行型(B 6.1 の項目表から導く)', () => {
    it.each([
      ['skippedDocument', 'document_id', true],
      ['skippedDocument', 'last_job_id', true],
      ['skippedDocument', 'stage', true],
      ['extractFailedDocument', 'title', false],
      ['extractFailedDocument', 'last_seen_at', true],
      ['extractFailedDocument', 'mime_type', true],
      ['oversizeDocument', 'size', false],
      ['oversizeDocument', 'detected_by', true],
      ['oversizeDocument', 'last_detected_at', true],
      ['summaryPendingDocument', 'title', false],
      ['summaryPendingDocument', 'indexed_at', true],
    ] as const)('%s の %s は expected=%s', (kind, field, expected) => {
      expect(isExpectedField(kind, field)).toBe(expected)
    })

    it('他の行型にある項目は、その行型では expected にならない(判別のキーが行型ごとに違う)', () => {
      expect(isExpectedField('skippedDocument', 'last_seen_at')).toBe(false)
      expect(isExpectedField('extractFailedDocument', 'detected_by')).toBe(false)
      expect(isExpectedField('oversizeDocument', 'indexed_at')).toBe(false)
      expect(isExpectedField('summaryPendingDocument', 'last_seen_at')).toBe(false)
    })

    it('tab から行型の表を引ける(4 つのタブすべて)', () => {
      expect(expectedKindForDocumentTab('skipped')).toBe('skippedDocument')
      expect(expectedKindForDocumentTab('extract_failed')).toBe('extractFailedDocument')
      expect(expectedKindForDocumentTab('oversize')).toBe('oversizeDocument')
      expect(expectedKindForDocumentTab('summary_pending')).toBe('summaryPendingDocument')
    })

    it('フィクスチャの正常な行は、expected の項目がすべて値を持つ(表が実際の行型と合っている)', () => {
      const rows = {
        skippedDocument: documents.skipped().items[0],
        extractFailedDocument: documents.extractFailed().items[0],
        oversizeDocument: documents.oversize().items[0],
        summaryPendingDocument: documents.summaryPending().items[0],
      } as const
      for (const [kind, row] of Object.entries(rows)) {
        for (const field of EXPECTED_FIELDS[kind as keyof typeof rows]) {
          expect((row as Record<string, unknown>)[field], `${kind}.${field} が null`).not.toBeNull()
        }
      }
    })
  })

  it('表のすべての項目名が、対応する型のキーである(typo は型検査で落ちる。実際のフィクスチャでも確認)', () => {
    const samples: Record<ExpectedFieldsKind, Record<string, unknown>> = {
      jobBrief: jobBrief(),
      jobDetail: jobDetails.succeeded(),
      registration: jobDetails.succeeded().registration!,
      sourceListRow: sourceListItem(),
      sourceDetail: sourceDetail(),
      skippedDocument: documents.skipped().items[0] as Record<string, unknown>,
      extractFailedDocument: documents.extractFailed().items[0] as Record<string, unknown>,
      oversizeDocument: documents.oversize().items[0] as Record<string, unknown>,
      summaryPendingDocument: documents.summaryPending().items[0] as Record<string, unknown>,
    }
    for (const [kind, sample] of Object.entries(samples)) {
      for (const field of EXPECTED_FIELDS[kind as ExpectedFieldsKind]) {
        expect(sample, `${kind}.${field}`).toHaveProperty(field)
      }
    }
  })
})

describe('cellState との組み合わせ(status=null の行は「読めない値」として扱う)', () => {
  it('EP-01 の status=null は unreadable(取得失敗ではない)', () => {
    const row = sourceListItem({ status: null })

    expect(rowCell(row, 'status', row.status, expectedFor('sourceListRow', 'status'))).toEqual({
      kind: 'unreadable',
    })
  })

  it('JobBrief の finished_at が null なら none(実行中は終了していないだけ)', () => {
    const job = jobBrief({ status: 'running', finished_at: null })
    const row = { unavailable: {} }

    expect(
      rowCell(row, 'finished_at', job.finished_at, expectedFor('jobBrief', 'finished_at')),
    ).toEqual({
      kind: 'none',
    })
    expect(rowCell(row, 'job_type', null, expectedFor('jobBrief', 'job_type'))).toEqual({
      kind: 'unreadable',
    })
  })
})
