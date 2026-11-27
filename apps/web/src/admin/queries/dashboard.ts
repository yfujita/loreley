// EP-13 `GET /dashboard`(D1)。クエリを付けない(E 5.3)。応答に `unavailable` はない。
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { getDashboardOptions } from '@/admin/api'
import { keys } from '@/admin/queries/keys'
import { dashboardRefetchInterval } from '@/admin/queries/polling'
import { withKey } from '@/admin/queries/withKey'

/** `autoRefresh`: D1 の自動更新スイッチ。入のときだけ 30 秒ごとに更新する(タブが見えない間は止める)。 */
export function useDashboardQuery(autoRefresh: MaybeRefOrGetter<boolean>) {
  return useQuery(
    computed(() => ({
      ...withKey(getDashboardOptions(), keys.dashboard()),
      refetchInterval: dashboardRefetchInterval(toValue(autoRefresh)),
      refetchIntervalInBackground: false,
    })),
  )
}
