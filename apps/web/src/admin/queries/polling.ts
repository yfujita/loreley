// ポーリング(E 5.5・F 3.4)。`refetchInterval` に渡す値と関数。
import { describeError, type JobStatus } from '@/admin/api'

/** D1 の定期更新(30 秒。承認済み(ゲート C。#26))。 */
export const DASHBOARD_POLL_INTERVAL_MS = 30_000
/** J2 の定期更新(10 秒。#8)。 */
export const JOB_POLL_INTERVAL_MS = 10_000

/** D1: 自動更新のスイッチが入のときだけ 30 秒ごと。 */
export function dashboardRefetchInterval(autoRefresh: boolean): number | false {
  return autoRefresh ? DASHBOARD_POLL_INTERVAL_MS : false
}

/**
 * J2: 直近のデータの `status` が `queued`・`running` のときだけ 10 秒ごと。終端(`succeeded` など)で止める。
 * 取消を要求した後も、終端になるまで続ける。`stalled`(保存上は `running` でリース切れ)も `running` のため続く。
 * データがまだない・`status=null`(読めない値)のときは続けない(確認できない状態でポーリングし続けない)。
 *
 * 再取得が失敗したとき: TanStack Query は前回のデータを保つので、`status` だけ見ると、ジョブが消えた(404 `job_not_found`)後も
 * 続けてしまう。「見つかりません」(ジョブが存在しない)なら止める。一時的な通信障害(network・timeout・5xx)では、
 * 回復を待つために続ける。
 */
export function jobDetailRefetchInterval(query: {
  state: { data: { status: JobStatus | null } | undefined; error?: unknown }
}): number | false {
  const { data, error } = query.state
  if (
    error !== null &&
    error !== undefined &&
    describeError(error, { operation: 'read' }).notFound
  ) {
    return false
  }
  return data?.status === 'queued' || data?.status === 'running' ? JOB_POLL_INTERVAL_MS : false
}
