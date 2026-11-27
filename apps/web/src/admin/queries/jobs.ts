// EP-09 `GET /jobs`・EP-10 `GET /jobs/{job_id}`(J1・J2)。
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { getJobOptions, isValidPathId, listJobsOptions, type JobListResponse } from '@/admin/api'
import { keys } from '@/admin/queries/keys'
import { jobsScopeOf, type JobsQuery } from '@/admin/queries/params'
import { jobDetailRefetchInterval } from '@/admin/queries/polling'
import { keepPreviousWithinScope } from '@/admin/queries/placeholder'
import { withKey } from '@/admin/queries/withKey'

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
        placeholderData: keepPreviousWithinScope<JobListResponse, typeof key>(key, jobsScopeOf),
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
