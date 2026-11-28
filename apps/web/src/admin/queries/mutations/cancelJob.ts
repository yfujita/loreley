// ジョブの取消(EP-07 `cancelJob`)。409 `job_already_finished` は成功扱い(呼び出し側が `describeError` で判断する)。
import { cancelJobMutation } from '@/admin/api'
import { useInvalidatingMutation } from '@/admin/queries/invalidation'

export function useCancelJobMutation() {
  return useInvalidatingMutation(cancelJobMutation(), 'cancelJob')
}
