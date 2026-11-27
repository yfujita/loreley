// Vuetify の組み立て(E 4.1 の 1。DS 3 章)。`createVuetify` を呼ぶのはこのファイルだけ(R13)。
// 設定の値は `shared/theme` が持ち(Search View と共有できる)、ここは読んで組み立てるだけ。
// `import 'vuetify/styles'` は main.ts の責務(必須。vite-plugin-vuetify はコンポーネント単位の CSS しか入れない)。
import { createVuetify, type VuetifyOptions } from 'vuetify'
import { ja } from 'vuetify/locale'

import { vuetifyDefaults } from '@/shared/theme/defaults'
import { displayOptions } from '@/shared/theme/display'
import { iconOptions } from '@/shared/theme/icons'
import { DEFAULT_THEME_NAME, lightTheme } from '@/shared/theme/tokens'

/** `VuetifyOptions` は本番とテスト(`tests/support/mount.ts`)で共有する。 */
export const vuetifyOptions: VuetifyOptions = {
  // 既定は `system` で、OS がダークだと別配色になる。ライトだけを定義し、明示する(DS 3.1)。
  theme: { defaultTheme: DEFAULT_THEME_NAME, themes: { [DEFAULT_THEME_NAME]: lightTheme } },
  defaults: vuetifyDefaults,
  display: displayOptions,
  icons: iconOptions,
  // 部品の内部の文言(ページ送りの aria-label など)を日本語にする(日本語のみ。前提 3)。
  locale: { locale: 'ja', fallback: 'ja', messages: { ja } },
}

export function setupVuetify() {
  return createVuetify(vuetifyOptions)
}
