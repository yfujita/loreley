// EP-11 `GET /sources/{source_id}/documents`(X1)。
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import {
  isValidPathId,
  listDocumentsOptions,
  type DocumentListResponse,
  type DocumentTab,
} from '@/admin/api'
import type { ItemsPerPage } from '@/admin/lib/pagination'
import { keys } from '@/admin/queries/keys'
import { keepPreviousWithinScope } from '@/admin/queries/placeholder'
import { withKey } from '@/admin/queries/withKey'

/**
 * X1 の条件(URL から正規化した型付きの条件。key になる。E 5.6)。
 * `tab` は API の値(snake_case)。URL の kebab-case との対応は features 側の定義表(documentTabs)が持つ。
 */
export type DocumentsQuery = {
  tab: DocumentTab
  page: number
  itemsPerPage: ItemsPerPage
  /** タブごとの項目の昇順・降順。`null` は指定なし(タブごとの既定の並び) */
  sort: string | null
}

/** ページ・並べ替え以外(同じスコープかの判定)。データソースは key の 2 番目なので別に比べる。 */
function scopeOf(key: readonly [string, string | null, DocumentsQuery]) {
  const { tab, itemsPerPage } = key[2]
  return { sourceId: key[1], tab, itemsPerPage }
}

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
        placeholderData: keepPreviousWithinScope<DocumentListResponse, typeof key>(key, scopeOf),
      }
    }),
  )
}
