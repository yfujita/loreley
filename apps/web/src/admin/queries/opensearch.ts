// EP-12 `GET /opensearch/cluster`(O1)。クエリを付けない(E 5.3)。応答に `unavailable` はない。
// 絞り込み(`q`・`state`)は画面側で行い、API に渡さない(E 5.6)。
import { useQuery } from '@tanstack/vue-query'

import { getClusterOptions } from '@/admin/api'
import { keys } from '@/admin/queries/keys'
import { withKey } from '@/admin/queries/withKey'

export function useOpenSearchClusterQuery() {
  return useQuery(withKey(getClusterOptions(), keys.opensearch.cluster()))
}
