// EP-01 `GET /sources`・EP-02 `GET /sources/{source_id}`(S1〜S4・J1・X1)。
import { useQuery } from '@tanstack/vue-query'
import { computed, toValue, type MaybeRefOrGetter } from 'vue'

import { getSourceOptions, isValidPathId, listSourcesOptions } from '@/admin/api'
import { keys } from '@/admin/queries/keys'
import { withKey } from '@/admin/queries/withKey'

/**
 * データソースの一覧。S1・J1(選択肢)・X1(選択肢)で共有する。
 * EP-01 は検索ベースで反映が遅れうる(EP-02 は ID 指定で即時)。登録・削除の直後に、新規のソースが見えない・
 * 消えたソースが残ることがある(E 5.4。FARC-U-23)。
 */
export function useSourcesListQuery() {
  return useQuery(withKey(listSourcesOptions(), keys.sources.list()))
}

/**
 * データソースの詳細(S2)。`sourceId` は route のパラメータ。
 * `isValidPathId` が偽なら取得せず(`enabled: false`)、画面は「見つかりません」にする(E 5.3 の二重の保証の 1 つ目)。
 */
export function useSourceDetailQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery(
    computed(() => {
      const id = toValue(sourceId)
      return {
        ...withKey(getSourceOptions({ path: { source_id: id } }), keys.sources.detail(id)),
        enabled: isValidPathId(id),
      }
    }),
  )
}

/**
 * データソースの編集用の取得(S4。FARC-P-12)。S2 と**別の key**で、同じ EP-02 を使う。
 * 画面を開くたびに必ず取得し(`refetchOnMount: 'always'`・`gcTime: 0`)、取得結果でフォームを 1 度だけ初期化する。
 * 取得後は差し替えない(`staleTime: Infinity`。編集中にバックグラウンドで値が差し替わらない。
 * フォーカス・再接続の再取得は QueryClient の既定で無効)。
 */
export function useSourceEditQuery(sourceId: MaybeRefOrGetter<string>) {
  return useQuery(
    computed(() => {
      const id = toValue(sourceId)
      return {
        ...withKey(getSourceOptions({ path: { source_id: id } }), keys.sources.edit(id)),
        enabled: isValidPathId(id),
        gcTime: 0,
        staleTime: Infinity,
        refetchOnMount: 'always' as const,
      }
    }),
  )
}
