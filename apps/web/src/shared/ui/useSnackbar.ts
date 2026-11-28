// スナックバーの呼び出し口(DS 4.7・E 8 章)。アプリで 1 つだけ(`AppSnackbar`)、同時に 1 つ、新しい通知で置き換える。
// 状態はモジュール内の `ref` で、永続化しない。使うのは操作の「受付・保存の成功」だけ(失敗には使わない)。
import { readonly, ref } from 'vue'

export type SnackbarAction = {
  label: string
  onClick: () => void
}

export type SnackbarMessage = {
  /** 新しい通知で置き換えたとき、表示と 6 秒のタイマーをやり直すためのキー */
  id: number
  text: string
  action: SnackbarAction | null
}

const current = ref<SnackbarMessage | null>(null)
let nextId = 1

export function useSnackbar() {
  /** 通知を出す。表示中なら置き換える。 */
  function show(text: string, options: { action?: SnackbarAction } = {}): void {
    current.value = { id: nextId++, text, action: options.action ?? null }
  }

  function close(): void {
    current.value = null
  }

  return { message: readonly(current), show, close }
}
