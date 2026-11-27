// ポーリング(E 5.5・F 3.4)。`refetchInterval` に渡す値と関数。
import type { JobStatus } from '@/admin/api'

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
 */
export function jobDetailRefetchInterval(query: {
  state: { data: { status: JobStatus | null } | undefined }
}): number | false {
  const status = query.state.data?.status
  return status === 'queued' || status === 'running' ? JOB_POLL_INTERVAL_MS : false
}
