import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import vuetify from 'vite-plugin-vuetify'

// 既定の転送先は compose の web コンテナの公開ポート(WEB_HOST_PORT の既定値)。
// web コンテナの追加前は何も待ち受けていないため、api を直接指す場合は LORELEY_DEV_API_TARGET で上書きする。
// VITE_ を付けないのは、クライアントのコードに露出させない dev 専用の値だから。
const devApiTarget = process.env.LORELEY_DEV_API_TARGET || 'http://127.0.0.1:8090'

export default defineConfig({
  base: '/admin/',
  plugins: [
    vue(),
    vuetify({
      autoImport: true,
      styles: { configFile: 'src/shared/theme/settings.scss' },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': { target: devApiTarget },
    },
  },
})
