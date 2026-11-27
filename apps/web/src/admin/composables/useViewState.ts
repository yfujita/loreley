// Query の結果 + `describeError` の結果 → `viewState`(E 6.2・F 3.7。FMOD-P-27)。
// `features` の composable が呼び、`templates` は結果の `viewState` だけを props で受けて描く。
//
// 取得していない(`enabled: false`。データも取得中もエラーもない)ときは `empty` を返す。X1 のソース未選択のように、
// 取得しない理由が画面にある場合は、画面がそれを先に判定してから使う(`empty` の文言を出さない)。
// 入力は構造的な型で受ける(R4: `@tanstack/vue-query` の型に頼らない。`useQuery` の戻り値がそのまま渡せる)。
import { computed, toValue, type ComputedRef, type MaybeRefOrGetter, type Ref } from 'vue'

import { describeError } from '@/admin/api'
import { resolveViewState, type ViewState } from '@/admin/lib/viewState'

/** `useQuery` の戻り値のうち、状態の決定に使う部分。 */
export type QueryStateSource<TData> = {
  data: Readonly<Ref<TData | undefined>>
  /** `unknown` として扱う(生成型は `ErrorResponse` と見せるが、実行時の値は型と食い違う。E 5.3) */
  error: Readonly<Ref<unknown>>
  /** 取得中かつデータなし。`enabled: false` では false(`isPending` は true のまま。FARC-U-26 の (4)) */
  isLoading: Readonly<Ref<boolean>>
  isFetching: Readonly<Ref<boolean>>
  isLoadingError: Readonly<Ref<boolean>>
  isRefetchError: Readonly<Ref<boolean>>
  dataUpdatedAt: Readonly<Ref<number>>
}

export type UseViewStateOptions<TData> = {
  /** 成功したデータが 0 件か(一覧の `items.length === 0` など)。省略すると 0 件の状態を持たない */
  isEmpty?: (data: TData) => boolean
  /** route の ID が `isValidPathId` で不正なとき true。API を呼ばず「見つかりません」と同じにする(E 5.3) */
  invalidPathId?: MaybeRefOrGetter<boolean>
}

export function useViewState<TData>(
  query: QueryStateSource<TData>,
  options: UseViewStateOptions<TData> = {},
): ComputedRef<ViewState> {
  return computed(() => {
    const data = query.data.value
    const hasData = data !== undefined
    const error = query.error.value
    return resolveViewState({
      isLoading: query.isLoading.value,
      isFetching: query.isFetching.value,
      hasData,
      isEmpty: hasData && options.isEmpty?.(data) === true,
      isLoadingError: query.isLoadingError.value,
      isRefetchError: query.isRefetchError.value,
      dataUpdatedAt: query.dataUpdatedAt.value,
      error:
        error === null || error === undefined ? null : describeError(error, { operation: 'read' }),
      invalidPathId: toValue(options.invalidPathId) ?? false,
    })
  })
}
