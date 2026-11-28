// S4 の保存(EP-04 `updateSource`)。設定の全置換。成功後の遷移・スナックバーは呼び出し側。
import { updateSourceMutation } from '@/admin/api'
import { useInvalidatingMutation } from '@/admin/queries/invalidation'

export function useUpdateSourceMutation() {
  return useInvalidatingMutation(updateSourceMutation(), 'updateSource')
}
