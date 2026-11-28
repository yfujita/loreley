// Vitest の setup(単体テストだけ。E2E では読み込まない)。
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach } from 'vitest'

import { configureApiClient } from '@/admin/api'
import { useSnackbar } from '@/shared/ui/useSnackbar'
// 生成クライアントの `client` は公開口に出さない設計(F 3.3。SDK 関数・client は Query・mutation 経由だけ)。
// テストの setup だけが、下の baseUrl の差し替えのために直接 import する(R2 の例外)。
// eslint-disable-next-line no-restricted-imports -- テスト基盤の例外。公開口に client を足さない
import { client } from '../../src/admin/api/generated/client.gen'

// 本番と同じ設定(タイムアウト付き fetch・interceptor 2 つ。E 5.3)。冪等で、`baseUrl` は変えない。
configureApiClient()

// 相対 `baseUrl` の生成クライアントは、jsdom 環境の `Request` が相対 URL を解決しないため、
// そのままでは `TypeError` を黙って返す(FARC-U-9)。テストの間だけ絶対 URL に差し替える。
// `configureApiClient()` は `baseUrl` に触れないので、呼ぶ順序によらず衝突しない。
// 本番の相対 `baseUrl`(`/api/admin/v1`)は client.test.ts・environment.test.ts が別に固定する。
client.setConfig({ baseUrl: 'http://localhost/api/admin/v1' })

// jsdom に無い API(Vuetify が参照する)の最小のスタブ。
// node 環境のテスト(dependencyRules.test.ts など)でも setup は読み込まれるので、jsdom のときだけ置く。
if (typeof window !== 'undefined') {
  class ResizeObserverStub implements ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  globalThis.ResizeObserver = ResizeObserverStub

  // jsdom は `window.scrollTo` を実装していない(呼ぶと「Not implemented」のノイズが出る)。vue-router の scrollBehavior が呼ぶ。
  window.scrollTo = () => {}

  // VOverlay(VDialog など)が位置の計算で `visualViewport` を読む。
  Object.defineProperty(window, 'visualViewport', {
    configurable: true,
    value: {
      width: window.innerWidth,
      height: window.innerHeight,
      offsetLeft: 0,
      offsetTop: 0,
      pageLeft: 0,
      pageTop: 0,
      scale: 1,
      addEventListener: () => {},
      removeEventListener: () => {},
    },
  })
}

// VDialog などは body にテレポートするので、テストごとに必ず外す。
enableAutoUnmount(afterEach)

// スナックバーの状態はモジュール内の `ref`(アプリで 1 つ)。テストの間に通知を持ち越さない。
afterEach(() => useSnackbar().close())
