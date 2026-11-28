// 操作ダイアログ(DLG-1〜5・削除の再実行)の共通の状態機械(E 7.4・6.3・F 3.8)。
//
// 実行 → mutation(`isPending` の間は実行ボタン・入力を無効にして二重送信を防ぐ)
//   → 成功: 閉じる+スナックバー(通知があるとき)+呼び出し側の `onSuccess`(遷移など)
//   → 失敗: **開いたまま**、`describeError` の結果をダイアログ内アラートに出す(消えない。DS 4.7)
//
// 状態ごとの見せ方(拒否の variant・既存ジョブ・結果不明の導線)は、ダイアログの `error`(`describeError` の結果)を読む
// ダイアログごとの純関数(`refusal.ts` など)が担う。ここは「開閉・実行中・失敗の保持」だけを持つ。
import { readonly, ref } from 'vue'

import { describeError, type ErrorDescription, type WriteOperation } from '@/admin/api'
import { useSnackbar, type SnackbarAction } from '@/shared/ui/useSnackbar'

export type SuccessNotice = { text: string; action?: SnackbarAction }

export type OperationDialogOptions<TInput, TResult> = {
  /** `describeError` の文脈(mutation の名前) */
  operation: WriteOperation
  /** 操作の実行(mutation の `mutateAsync`)。失敗は throw する */
  execute: (input: TInput) => Promise<TResult>
  /** 成功時のスナックバー。null・省略なら出さない(`released=false` は成功の通知にしない。E 6.3) */
  successNotice?: (result: TResult, input: TInput) => SuccessNotice | null
  /** 成功時の呼び出し側の処理(遷移など)。ダイアログを閉じた後に呼ぶ */
  onSuccess?: (result: TResult, input: TInput) => void
  /**
   * 失敗のうち、`describeError` が成功扱いにするもの(`target === 'success'`。取消の 409 `job_already_finished`)。
   * ダイアログを閉じてから呼ぶ(スナックバーは呼び出し側が出す)。省略すると、閉じるだけ。
   */
  onAlreadyDone?: (description: ErrorDescription) => void
}

export function useOperationDialog<TInput, TResult>(
  options: OperationDialogOptions<TInput, TResult>,
) {
  const { show } = useSnackbar()

  const isOpen = ref(false)
  const isPending = ref(false)
  const error = ref<ErrorDescription | null>(null)

  function open(): void {
    // 前回の失敗を残さない。
    error.value = null
    isOpen.value = true
  }

  /** 実行中は閉じない(失敗のアラートを見逃さない。二重送信の途中で状態を失わない)。 */
  function close(): void {
    if (isPending.value) return
    isOpen.value = false
  }

  async function run(input: TInput): Promise<void> {
    // 二重送信を防ぐ(ボタンの無効化が間に合わない連打も)。
    if (isPending.value) return
    isPending.value = true
    error.value = null

    let result: TResult
    try {
      result = await options.execute(input)
    } catch (thrown) {
      const description = describeError(thrown, { operation: options.operation })
      if (description.target === 'success') {
        isOpen.value = false
        options.onAlreadyDone?.(description)
      } else {
        error.value = description
      }
      return
    } finally {
      isPending.value = false
    }

    // 成功の後始末(スナックバー・遷移)は、操作の失敗と区別する(ここで投げても、操作の失敗として扱わない)。
    isOpen.value = false
    const notice = options.successNotice?.(result, input) ?? null
    if (notice !== null) show(notice.text, notice.action ? { action: notice.action } : {})
    options.onSuccess?.(result, input)
  }

  return { isOpen, isPending: readonly(isPending), error: readonly(error), open, close, run }
}
