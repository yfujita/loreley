import { describe, expect, it } from 'vitest'

import type { LockState } from '@/admin/api'

import { existingJob } from '../../../tests/support/fixtures/jobs'
import { lock } from '../../../tests/support/fixtures/sources'
import { lockStateView } from './lockStateView'

const ALL_STATES: LockState[] = [
  'none',
  'held_crawl',
  'held_delete',
  'lease_expired',
  'orphan',
  'just_acquired',
  'unknown',
]

describe('lockStateView(E 5.10 の写像)', () => {
  it('none → ロックなし(操作なし)', () => {
    expect(lockStateView(lock('none'), false)).toEqual({
      kind: 'none',
      tag: null,
      warning: false,
      actions: [],
    })
  })

  it('held_crawl(running)→ 実行中のジョブが保持。「ジョブを表示」(解放はできない旨と取消の案内)', () => {
    expect(lockStateView(lock('held_crawl'), false)).toEqual({
      kind: 'held-running',
      tag: 'running',
      warning: false,
      actions: ['show-job'],
    })
  })

  it('held_crawl(queued)→ 同じ構成でタグだけ「実行待ち」(案)', () => {
    const view = lockStateView(
      lock('held_crawl', { job: existingJob({ status: 'queued', lease_expires_at: null }) }),
      false,
    )

    expect(view).toEqual({
      kind: 'held-queued',
      tag: 'queued',
      warning: false,
      actions: ['show-job'],
    })
  })

  it('held_delete → 削除ジョブが保持。タグ「削除中」。操作なし(完了を待つ)', () => {
    expect(lockStateView(lock('held_delete'), false)).toEqual({
      kind: 'held-delete',
      tag: 'deleting',
      warning: false,
      actions: [],
    })
  })

  it('lease_expired → warning。「ロックを解放…」(DLG-5)と「ジョブを表示」', () => {
    expect(lockStateView(lock('lease_expired'), false)).toEqual({
      kind: 'lease-expired',
      tag: null,
      warning: true,
      actions: ['release-lock', 'show-job'],
    })
  })

  it('orphan → warning。「ロックを解放…」(DLG-5 孤児版)だけ', () => {
    expect(lockStateView(lock('orphan'), false)).toEqual({
      kind: 'orphan',
      tag: null,
      warning: true,
      actions: ['release-lock'],
    })
  })

  it('just_acquired → 「再読み込み」だけ(受付の途中の可能性。解放は出さない)', () => {
    expect(lockStateView(lock('just_acquired'), false)).toEqual({
      kind: 'just-acquired',
      tag: null,
      warning: false,
      actions: ['reload'],
    })
  })

  it('unknown → 「ロック状態を確認できません」(理由を断定しない。解放は出さない)', () => {
    expect(lockStateView(lock('unknown'), false)).toEqual({
      kind: 'unknown',
      tag: null,
      warning: false,
      actions: ['reload'],
    })
  })

  it('取得失敗(lock=null・unavailable に lock)→ 取得できません。「再読み込み」', () => {
    expect(lockStateView(null, true)).toEqual({
      kind: 'unavailable',
      tag: null,
      warning: false,
      actions: ['reload'],
    })
  })

  it('lock=null で取得失敗でもないときは、確認できない状態(unknown)', () => {
    expect(lockStateView(null, false)).toMatchObject({ kind: 'unknown', actions: ['reload'] })
  })

  it('7 値すべてに、解放を出す状態は lease_expired と orphan だけ', () => {
    const withRelease = ALL_STATES.filter((state) =>
      lockStateView(lock(state), false).actions.includes('release-lock'),
    )

    expect(withRelease).toEqual(['lease_expired', 'orphan'])
  })

  describe('lock.job の status・job_type が null・未知のとき、「ジョブを表示」を出さない(FARC-P-35)', () => {
    it('lease_expired でジョブ記録が読めない → 解放だけ', () => {
      const view = lockStateView(
        lock('lease_expired', { job: existingJob({ status: null, job_type: null }) }),
        false,
      )

      expect(view.actions).toEqual(['release-lock'])
    })

    it('held_crawl でジョブ記録が読めない → 操作なし', () => {
      const view = lockStateView(lock('held_crawl', { job: existingJob({ status: null }) }), false)

      expect(view.actions).toEqual([])
    })

    it('lease_expired で job が null → 解放だけ', () => {
      expect(lockStateView(lock('lease_expired', { job: null }), false).actions).toEqual([
        'release-lock',
      ])
    })

    it('未知の status → 「ジョブを表示」を出さない', () => {
      const view = lockStateView(
        lock('lease_expired', { job: { ...existingJob(), status: 'paused' as never } }),
        false,
      )

      expect(view.actions).not.toContain('show-job')
    })
  })
})
