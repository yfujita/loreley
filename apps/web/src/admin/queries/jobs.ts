// EP-09 `GET /jobs`・EP-10 `GET /jobs/{job_id}`(J1・J2)。
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  getJobOptions,
  isValidPathId,
  listJobsOptions,
  type JobListResponse,
  type JobStatus,
} from '@/admin/api'
import type { ItemsPerPage } from '@/admin/lib/pagination'
import { keys } from '@/admin/queries/keys'
import { jobDetailRefetchInterval } from '@/admin/queries/polling'
import { keepPreviousWithinScope } from '@/admin/queries/placeholder'
import { withKey } from '@/admin/queries/withKey'

/** EP-09 の `sort`。OpenAPI では素の string のため、画面側で union を持つ(許容は `queued_at`・`-queued_at`)。 */
export type JobsSort = 'queued_at' | '-queued_at'

/** `status` の絞り込み。保存上の状態に、画面の「実行待ち・実行中」の複合値 `active` を加えたもの(E 5.6)。 */
export type JobsStatusFilter = JobStatus | 'active'

/** J1 の条件(URL から正規化した型付きの条件。key になる。E 5.6)。 */
export type JobsQuery = {
  page: number
  itemsPerPage: ItemsPerPage
  /** `null` は指定なし(API の既定の並び `-queued_at`) */
  sort: JobsSort | null
  /** データソースの絞り込み。`null` はすべて */
  sourceId: string | null
  /** `null` はすべて */
  status: JobsStatusFilter | null
}

/** ページ・並べ替え以外(同じスコープかの判定)。 */
function scopeOf(key: readonly [string, string, JobsQuery]) {
  const { sourceId, status, itemsPerPage } = key[2]
  return { sourceId, status, itemsPerPage }
}

/**
 * ジョブの一覧(J1)。同じスコープのページ・並べ替えの変更だけ前回データを保つ
 * (保っている間 `isPlaceholderData` が true。行の操作は無効にする)。
 */
export function useJobsListQuery(params: MaybeRefOrGetter<JobsQuery>) {
  return useQuery(
    computed(() => {
      const current = toValue(params)
      const key = keys.jobs.list(current)
      return {
        ...withKey(
          listJobsOptions({
            query: {
              page: current.page,
              items_per_page: current.itemsPerPage,
              ...(current.sort !== null && { sort: current.sort }),
              ...(current.sourceId !== null && { source_id: current.sourceId }),
              ...(current.status !== null && { status: current.status }),
            },
          }),
          key,
        ),
        placeholderData: keepPreviousWithinScope<JobListResponse, typeof key>(key, scopeOf),
      }
    }),
  )
}

/**
 * ジョブの詳細(J2)。`jobId` が `isValidPathId` で不正なら取得しない。
 * 実行待ち・実行中のときだけ 10 秒ごとに更新し、終端で止まる。
 */
export function useJobDetailQuery(jobId: MaybeRefOrGetter<string>) {
  return useQuery(
    computed(() => {
      const id = toValue(jobId)
      return {
        ...withKey(getJobOptions({ path: { job_id: id } }), keys.jobs.detail(id)),
        enabled: isValidPathId(id),
        refetchInterval: jobDetailRefetchInterval,
      }
    }),
  )
}
