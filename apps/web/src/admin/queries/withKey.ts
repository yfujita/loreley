// 生成 Options の key を差し替える(E 5.4・F 3.4。FARC-U-22 の (4)・(6))。
//
// `{ ...xxxOptions(…), queryKey: keys.… }` をそのまま `useQuery` に渡すと型検査が通らない(TS2769)。
// `queryFn` の型が、生成された key の型に結びついているため。key の型を合わせるキャストを、ここ 1 か所に閉じ込める。
//
// 実行時: 生成された `queryFn` は `xxxOptions` の引数(クロージャ)から URL を作り、key から作らない。
// このため key を差し替えても、正しい URL へ送られる(withKey.test.ts で確認)。
// この方式は Hey API の内部実装(上記)に依存する。依存が重くなったときの代替は、SDK 関数から独自の Options を
// 組み立てる方式(E の FARC-U-22 の (6))。
//
// 戻り値の `TError` は `unknown` にする。生成型は `error` を `ErrorResponse` と見せるが、実行時の値は型と食い違う
// (E 5.3)ため、`error` を読むには `isApiError`(または `describeError`)を通す必要がある。
import type { QueryKey, UseQueryOptions } from '@tanstack/vue-query'

export function withKey<
  TData,
  TGeneratedError,
  TGeneratedKey extends QueryKey,
  TKey extends QueryKey,
>(
  options: UseQueryOptions<TData, TGeneratedError, TData, TData, TGeneratedKey>,
  queryKey: TKey,
): UseQueryOptions<TData, unknown, TData, TData, TKey> & { queryKey: TKey } {
  return { ...options, queryKey } as unknown as UseQueryOptions<
    TData,
    unknown,
    TData,
    TData,
    TKey
  > & {
    queryKey: TKey
  }
}
