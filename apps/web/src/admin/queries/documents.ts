// EP-11 `GET /sources/{source_id}/documents`(X1)。
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { isValidPathId, listDocumentsOptions, type DocumentListResponse } from '@/admin/api'
import { keys } from '@/admin/queries/keys'
import { documentsScopeOf, type DocumentsQuery } from '@/admin/queries/params'
import { keepPreviousWithinScope } from '@/admin/queries/placeholder'
import { withKey } from '@/admin/queries/withKey'

/**
 * 文書の一覧(X1)。`source` が未選択(`null`)、または `isValidPathId` が偽のときは取得しない(`enabled: false`)。
 * `enabled: false` のとき `isPending` は true のままで取得は走らない。スケルトンは `isPending` ではなく
 * 取得中を表す `isLoading` で出す(FARC-U-26 の (4)。documents.test.ts で確認)。
 */
export function useDocumentsQuery(
  source: MaybeRefOrGetter<string | null>,
  params: MaybeRefOrGetter<DocumentsQuery>,
) {
  return useQuery(
    computed(() => {
      const sourceId = toValue(source)
      const current = toValue(params)
      const key = keys.documents.list(sourceId, current)
      return {
        ...withKey(
          listDocumentsOptions({
            // 未選択のときは取得しないので、path の値は使われない(型を満たすための空文字)。
            path: { source_id: sourceId ?? '' },
            query: {
              tab: current.tab,
              page: current.page,
              items_per_page: current.itemsPerPage,
              ...(current.sort !== null && { sort: current.sort }),
            },
          }),
          key,
        ),
        enabled: sourceId !== null && isValidPathId(sourceId),
        placeholderData: keepPreviousWithinScope<DocumentListResponse, typeof key>(
          key,
          documentsScopeOf,
        ),
      }
    }),
  )
}
