// Query・mutation を、Vue のコンポーネントなしで実際に走らせるテスト用の道具。
import { QueryClient, type MutationOptions } from '@tanstack/vue-query'

/** テストごとに新しく作る QueryClient。再試行しない(E 10.1)。 */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } },
  })
}

/**
 * 生成の `{fn}Mutation()` の mutationFn を、QueryClient の mutation として実行する。
 * 生成の戻り値は Vue 用の `UseMutationOptions`(`MaybeRef` を許す)だが、`{fn}Mutation()` が返す値は
 * 素のオブジェクトなので、`MutationOptions` として扱ってよい。
 */
export function runMutation<TData, TError, TVariables>(
  queryClient: QueryClient,
  options: unknown,
  variables: TVariables,
): Promise<TData> {
  return queryClient
    .getMutationCache()
    .build(queryClient, options as MutationOptions<TData, TError, TVariables>)
    .execute(variables)
}
