// アプリの入口(E 4.1・F 2.4)。起動の順序はここで決める。
// 0. `configureApiClient()`: API クライアントの設定。1〜4 より前に 1 回だけ呼ぶ(冪等。interceptor は二重に登録されない)
// 1. Vuetify(`setupVuetify`)。`vuetify/styles` は必須: vite-plugin-vuetify はコンポーネント単位の CSS しか入れないため、
//    リセット CSS・タイポグラフィ・ユーティリティはここで読み込む。続けて、アプリ共通の CSS(Vuetify の後)
// 2. Router(`setupRouter`)
// 3. Vue Query(`setupQuery`)
// 4. マウント
import 'vuetify/styles'
import '@/shared/theme/global.css'

import { createApp } from 'vue'

import { configureApiClient } from '@/admin/api'
import App from '@/admin/app/App.vue'
import { setupQuery } from '@/admin/app/setupQuery'
import { setupRouter } from '@/admin/app/setupRouter'
import { setupVuetify } from '@/admin/app/setupVuetify'

configureApiClient()

const app = createApp(App)
app.use(setupVuetify())
setupRouter(app)
setupQuery(app)
app.mount('#app')
