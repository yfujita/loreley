// invalidate の表(E 5.8・F 3.4): 操作 → invalidate する prefix。mutation が成功したときに呼ぶ。
import {
  useMutation,
  useQueryClient,
  type QueryClient,
  type QueryKey,
  type UseMutationOptions,
} from '@tanstack/vue-query'

import { describeError, type WriteOperation } from '@/admin/api'
import { keys } from '@/admin/queries/keys'

export const INVALIDATION_TABLE: Readonly<Record<WriteOperation, readonly QueryKey[]>> = {
  // DLG-1・DLG-4(クロール起動・再実行)
  startCrawl: [keys.sources.all, keys.jobs.all],
  // DLG-2・削除の再実行。S2 のロック状態カードは invalidate 後の EP-02 で即時に `held_delete` になる。
  // S1 の行は「削除中」にならないことがある(受付の時点では設定の status は active のまま。E 5.8)
  startSourceDelete: [keys.sources.all, keys.jobs.all],
  // DLG-3(取消)。409 `job_already_finished`(成功扱い)も同じ(useInvalidatingMutation が onError で呼ぶ)
  cancelJob: [keys.jobs.all, keys.sources.all],
  // DLG-5(ロック解放)。`released=false` でも実態に追従させるために同じ
  releaseLock: [keys.sources.all, keys.jobs.all],
  // S3(登録)。編集用の key は `gcTime: 0` で残らない
  registerSource: [keys.sources.all],
  // S4(保存)
  updateSource: [keys.sources.all],
}

export function invalidateAfter(queryClient: QueryClient, operation: WriteOperation): void {
  for (const queryKey of INVALIDATION_TABLE[operation]) {
    // 再取得の完了は待たない(ダイアログを閉じる・遷移を、再取得のネットワーク待ちで遅らせない)。
    void queryClient.invalidateQueries({ queryKey })
  }
}

/**
 * 生成の `{fn}Mutation()` を `useMutation` に渡し、成功したら invalidate の表で無効化する。
 * 成功後の遷移・スナックバー・ダイアログの開閉は呼び出し側が決める。
 *
 * 失敗でも、`describeError` が成功扱い(`target === 'success'`。取消の 409 `job_already_finished`)と判断したものは、
 * 成功と同じく invalidate する(終端済みのジョブが J1・J2 で `running` のまま残らないように。E 5.8・6.3)。
 *
 * `error` は `unknown` として扱う(生成型は `ErrorResponse` と見せるが、実行時の値は型と食い違う。E 5.3)。
 * 呼び出し側は `describeError` を通して読む。
 */
export function useInvalidatingMutation<TData, TGeneratedError, TVariables>(
  options: UseMutationOptions<TData, TGeneratedError, TVariables>,
  operation: WriteOperation,
) {
  const queryClient = useQueryClient()
  return useMutation<TData, unknown, TVariables>({
    ...(options as UseMutationOptions<TData, unknown, TVariables>),
    onSuccess: () => invalidateAfter(queryClient, operation),
    onError: (error) => {
      if (describeError(error, { operation }).target === 'success') {
        invalidateAfter(queryClient, operation)
      }
    },
  })
}
