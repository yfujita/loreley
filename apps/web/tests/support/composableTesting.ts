// composable を、本番に近い土台(Router・QueryClient・Vuetify)の中で走らせるテスト用の道具。
// `useQuery`・`useRoute` など、コンポーネントの `setup` の中でしか呼べないものを検証するため。
import { defineComponent } from 'vue'

import { mountInLayout } from './mount'

type MountOptions = NonNullable<Parameters<typeof mountInLayout>[1]>

/** `setup` を実行して、その戻り値(composable の結果)と、マウントの結果を返す。 */
export async function runComposable<T>(setup: () => T, options: MountOptions = {}) {
  let result: T | undefined
  const host = defineComponent({
    setup() {
      result = setup()
      return () => null
    },
  })
  const mounted = await mountInLayout(host, options)
  return { ...mounted, result: result as T }
}
