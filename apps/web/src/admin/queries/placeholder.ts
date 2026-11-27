// 取得中の前回データ(`placeholderData`。E 5.6・F 3.4)。
//
// **同じスコープ**(同じ絞り込み・同じデータソース・同じタブ)の、ページ・並べ替えの変更だけ前回データを見せる。
// 絞り込み・タブ・データソース・件数が変わったときは、別の条件の行を「古いデータ」として見せないよう、スケルトンにする。
import type { QueryKey } from '@tanstack/vue-query'

/**
 * `placeholderData` の関数を作る。`scopeOf` は key から「ページ・並べ替え以外」の部分を取り出す。
 * 前回の key と次の key の scope が同じときだけ、前回のデータを返す。
 */
export function keepPreviousWithinScope<TData, TKey extends QueryKey>(
  nextKey: TKey,
  scopeOf: (key: TKey) => unknown,
) {
  const nextScope = JSON.stringify(scopeOf(nextKey))
  return (
    previousData: TData | undefined,
    previousQuery: { queryKey: TKey } | undefined,
  ): TData | undefined => {
    if (previousQuery === undefined) return undefined
    return JSON.stringify(scopeOf(previousQuery.queryKey)) === nextScope ? previousData : undefined
  }
}

/**
 * 前回データを表示している間(`isPlaceholderData` が true)は、行単位の更新操作(J1 の取消など)を無効にする。
 * URL・ページネーションは次のページなのに、表の行が前のページのものである間に、意図しないジョブを操作しないため。
 * 取得が終われば有効になる。X1・O1 のような読み取りだけの表には関係しない。
 */
export function rowActionsDisabled(isPlaceholderData: boolean): boolean {
  return isPlaceholderData
}
