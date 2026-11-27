// EP-14 `GET /meta`(シェル。FARC-P-25)。クエリを付けない(E 5.3)。
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'

import { getMetaOptions } from '@/admin/api'
import { keys } from '@/admin/queries/keys'
import { withKey } from '@/admin/queries/withKey'

/** `Infinity`: 再読み込みまで取り直さない(Dashboards の URL・cron のタイムゾーンは運用中に変わらない)。 */
export function useMetaQuery() {
  return useQuery({
    ...withKey(getMetaOptions(), keys.meta()),
    staleTime: Infinity,
  })
}

/**
 * OpenSearch Dashboards の URL。`null`(未設定)と、EP-14 の失敗は同じ扱い(Dashboards リンクを出さない。AF-20)。
 * シェルは EP-14 が失敗しても止めない。
 */
export function useDashboardsUrl() {
  const meta = useMetaQuery()
  return computed(() => meta.data.value?.dashboards_url ?? null)
}

/** Crawler の cron が解釈されるタイムゾーン(UC-19)。`null` と EP-14 の失敗は同じ扱い(「取得できません」の警告)。 */
export function useCronTimezone() {
  const meta = useMetaQuery()
  return computed(() => meta.data.value?.cron_timezone ?? null)
}
