// データソースの削除ジョブの起動(EP-05 `startSourceDelete`)。DLG-2 と削除の再実行が共有する。本文なし。
import { startSourceDeleteMutation } from '@/admin/api'
import { useInvalidatingMutation } from '@/admin/queries/invalidation'

export function useDeleteSourceMutation() {
  return useInvalidatingMutation(startSourceDeleteMutation(), 'startSourceDelete')
}
