// ロックの解放(EP-08 `releaseLock`)。200 でも `released=false` は成功の文言にしない(呼び出し側が判断する)。
import { releaseLockMutation } from '@/admin/api'
import { useInvalidatingMutation } from '@/admin/queries/invalidation'

export function useReleaseLockMutation() {
  return useInvalidatingMutation(releaseLockMutation(), 'releaseLock')
}
