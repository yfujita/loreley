// ロック状態の写像(E 5.10・F 3.5。FARC-P-34)。S2 のロック状態カード・J2 のロックカード・DLG-1 の拒否表示が共有する。
//
// `lock.state`(B 2.9。7 値)を、画面仕様の 6 種(sources 1.5)+「確認できません」+取得失敗に対応づける。
// リース切れかどうかは `lock.state`(J2 では `stalled`)に従い、画面で再計算しない。
import type { ExistingJob, Lock, LockState } from '@/admin/api'
import { canLinkToJob } from '@/admin/lib/existingJob'

export type LockCardKind =
  | 'none'
  | 'held-running'
  | 'held-queued'
  | 'held-delete'
  | 'lease-expired'
  | 'orphan'
  | 'just-acquired'
  | 'unknown'
  | 'unavailable'

/** カードの操作。`show-job`=「ジョブを表示」(J2)、`release-lock`=「ロックを解放…」(DLG-5)、`reload`=「再読み込み」。 */
export type LockCardAction = 'show-job' | 'release-lock' | 'reload'

export type LockStateView = {
  kind: LockCardKind
  /** StatusTag に出す状態(実行待ち・実行中・削除中)。出さないとき null */
  tag: 'queued' | 'running' | 'deleting' | null
  /** warning アラートで見せるか(止まったロックが残っている) */
  warning: boolean
  actions: readonly LockCardAction[]
}

const VIEW_BY_STATE: Record<
  Exclude<LockState, 'held_crawl'>,
  Omit<LockStateView, 'actions'> & { actions: readonly LockCardAction[] }
> = {
  none: { kind: 'none', tag: null, warning: false, actions: [] },
  // 削除ジョブが保持(リース期限内)。リース期限内は解放できない。完了を待つ
  held_delete: { kind: 'held-delete', tag: 'deleting', warning: false, actions: [] },
  lease_expired: {
    kind: 'lease-expired',
    tag: null,
    warning: true,
    actions: ['release-lock', 'show-job'],
  },
  orphan: { kind: 'orphan', tag: null, warning: true, actions: ['release-lock'] },
  // 受付の途中の可能性があるので解放できない
  just_acquired: { kind: 'just-acquired', tag: null, warning: false, actions: ['reload'] },
  // 理由を断定しない。解放は出さない(sources 1.5 にない。I-87)
  unknown: { kind: 'unknown', tag: null, warning: false, actions: ['reload'] },
}

function withoutShowJobUnlessLinkable(
  view: LockStateView,
  job: (Pick<ExistingJob, 'job_id'> & { status: string | null; job_type: string | null }) | null,
): LockStateView {
  if (canLinkToJob(job)) return view
  // `job_type`・`status` が null(ジョブ記録がない・読めない)のときは、「ジョブを表示」を出さない(FARC-P-35)。
  return { ...view, actions: view.actions.filter((action) => action !== 'show-job') }
}

/**
 * ロック状態カードの表示を決める。
 * @param lock EP-02 の `lock`(取得失敗・読めないときは null)
 * @param lockUnavailable 最上位の `unavailable` に `lock` のキーがあるか(取得失敗。「取得できません」)
 */
export function lockStateView(
  lock: Pick<Lock, 'state' | 'job'> | null,
  lockUnavailable: boolean,
): LockStateView {
  if (lock === null) {
    return {
      kind: lockUnavailable ? 'unavailable' : 'unknown',
      tag: null,
      warning: false,
      actions: ['reload'],
    }
  }

  if (lock.state === 'held_crawl') {
    // held_* は実行待ちを含む(B 2.9)。画面仕様は実行中だけを書くため、実行待ちは同じ構成でタグだけ変える(案)。
    const isQueued = lock.job?.status === 'queued'
    const view: LockStateView = {
      kind: isQueued ? 'held-queued' : 'held-running',
      tag: isQueued ? 'queued' : 'running',
      warning: false,
      actions: ['show-job'],
    }
    return withoutShowJobUnlessLinkable(view, lock.job)
  }

  const view = VIEW_BY_STATE[lock.state]
  return withoutShowJobUnlessLinkable(view, lock.job)
}
