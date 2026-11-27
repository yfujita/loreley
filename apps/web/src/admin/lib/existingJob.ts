// 409 `lock_held`・`lock_in_use` の `details.existing_job` の判定(E 6.3・F 3.5。FARC-P-35)。
// DLG-1・DLG-4・DLG-5 が共有する。
import type { ExistingJob, JobStatus, JobType } from '@/admin/api'

// 既知の値。生成型の `JobStatus`・`JobType` と過不足なく一致することを型で検査する(`Record` の網羅)。
const KNOWN_JOB_STATUSES: Readonly<Record<JobStatus, true>> = {
  queued: true,
  running: true,
  succeeded: true,
  partially_succeeded: true,
  failed: true,
  cancelled: true,
}
const KNOWN_JOB_TYPES: Readonly<Record<JobType, true>> = { crawl: true, source_delete: true }

function isKnownJobStatus(value: unknown): value is JobStatus {
  return typeof value === 'string' && Object.hasOwn(KNOWN_JOB_STATUSES, value)
}

function isKnownJobType(value: unknown): value is JobType {
  return typeof value === 'string' && Object.hasOwn(KNOWN_JOB_TYPES, value)
}

/**
 * 「ジョブを表示」(J2)へ導けるか。`status`・`job_type` が `null`(ジョブ記録がない・読めない)、
 * または既知の値でない(未知の文字列)ときは導かない。EP-10 が 404 になりうるため。
 * 孤児ロックの解放の入口は S2 のロック状態カードだけ(sources 1.5)。
 *
 * OpenAPI の型は列挙だが、実装は Crawler の文字列をそのまま通すため、未知の値がありうる。
 */
export function canLinkToJob(
  job:
    | (Pick<ExistingJob, 'job_id'> & { status: string | null; job_type: string | null })
    | null
    | undefined,
): boolean {
  if (job === null || job === undefined) return false
  if (typeof job.job_id !== 'string' || job.job_id === '') return false
  return isKnownJobStatus(job.status) && isKnownJobType(job.job_type)
}
