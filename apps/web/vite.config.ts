import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'
import vuetify from 'vite-plugin-vuetify'

// 既定の転送先は compose の web コンテナの公開ポート(WEB_HOST_PORT の既定値)。
// 使う前に compose で web を起動しておく。api はホストに公開されないので、WEB_HOST_PORT を変えたときなどは
// LORELEY_DEV_API_TARGET で上書きする。
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
  test: {
    environment: 'jsdom',
    setupFiles: ['tests/support/setup.ts'],
    include: ['src/**/*.test.ts', 'tests/support/**/*.test.ts'],
    // ブラウザのローカル時刻の表示を再現可能にする(DS 4.9)。プロセスの開始後に変えても効かないので、起動時の環境変数にする。
    env: { TZ: 'Asia/Tokyo' },
    // vuetify の部品(.js)を Vite の変換に通す(vite-plugin-vuetify が CSS・SASS の import を書き換えるため)。
    server: { deps: { inline: ['vuetify'] } },
    // 既定の true だと、2 回目以降の実行で `virtual:plugin-vuetify:…` を読めず全テストが落ちる。
    // vite-plugin-vuetify は、仮想モジュールの中身を resolveId の時にメモリへ置き load で返すため、
    // キャッシュ済みの変換結果では resolveId が呼ばれず、中身が空になる(Vitest 5・vite-plugin-vuetify 2.1.3 で確認)。
    fsModuleCache: false,
    // vi.stubGlobal(fetchStub など)を、テストごとに元へ戻す。後始末の漏れでテスト間に fetch の差し替えが残らないように。
    unstubGlobals: true,
  },
})
