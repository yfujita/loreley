// vite-plugin-vuetify はコンポーネント単位の CSS しか入れないため、
// リセット CSS・タイポグラフィ・ユーティリティはここで読み込む(必須)。
import 'vuetify/styles'

import { createApp } from 'vue'
import { createVuetify } from 'vuetify'

import App from '@/admin/app/App.vue'
import { router } from '@/admin/router'

createApp(App).use(createVuetify()).use(router).mount('#app')
