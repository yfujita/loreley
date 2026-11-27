// debounce した ref(F 3.1)。O1 の絞り込み(`q`)の入力など、入力のたびに URL・再計算をしないため。
import { onScopeDispose, readonly, ref, watch, type Ref } from 'vue'

/**
 * `source` の変更から `delayMs` ミリ秒、変更がなかったときに値を反映する読み取り専用の ref。
 * 最初の値はそのまま入る。スコープ(コンポーネント)の破棄でタイマーを止める。
 */
export function useDebouncedRef<T>(source: Readonly<Ref<T>>, delayMs: number): Readonly<Ref<T>> {
  const debounced = ref(source.value) as Ref<T>
  let timer: number | undefined

  const clearTimer = () => {
    if (timer !== undefined) window.clearTimeout(timer)
    timer = undefined
  }

  watch(source, (value) => {
    clearTimer()
    timer = window.setTimeout(() => {
      debounced.value = value
      timer = undefined
    }, delayMs)
  })
  onScopeDispose(clearTimer)

  return readonly(debounced) as Readonly<Ref<T>>
}
