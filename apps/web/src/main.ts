// vite-plugin-vuetify はコンポーネント単位の CSS しか入れないため、
// リセット CSS・タイポグラフィ・ユーティリティはここで読み込む(必須)。
import 'vuetify/styles'

import { createApp } from 'vue'
/* eslint-disable no-restricted-imports --
  フェーズ 3 で main.ts を作り直す(E 4.1)までの暫定。スキャフォールドのままでは R13・R15 に反する。 */
import { createVuetify } from 'vuetify'

import App from '@/admin/app/App.vue'
import { router } from '@/admin/router'
/* eslint-enable no-restricted-imports */

createApp(App).use(createVuetify()).use(router).mount('#app')
