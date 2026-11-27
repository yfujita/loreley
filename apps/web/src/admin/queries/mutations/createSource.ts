// S3 の保存(EP-03 `registerSource`)。成功後の遷移・スナックバーは呼び出し側。
import { registerSourceMutation } from '@/admin/api'
import { useInvalidatingMutation } from '@/admin/queries/invalidation'

export function useCreateSourceMutation() {
  return useInvalidatingMutation(registerSourceMutation(), 'registerSource')
}
