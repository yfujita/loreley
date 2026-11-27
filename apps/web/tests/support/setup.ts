// Vitest の setup(単体テストだけ。E2E では読み込まない)。
import { enableAutoUnmount } from '@vue/test-utils'
import { afterEach } from 'vitest'

// 相対 `baseUrl` の生成クライアントは、jsdom 環境の `Request` が相対 URL を解決しないため、
// そのままでは `TypeError` を黙って返す(FARC-U-9)。テストの間だけ絶対 URL に差し替える。
// 本番用の `client.ts` にはテスト用の形を持たせない。
// 公開口(`@/admin/api`)が `client` を再 export したら、そこからの import に切り替え、この disable を外す(フェーズ 2)。
// eslint-disable-next-line no-restricted-imports -- 公開口が client を再 export するまでの暫定(R2)
import { client } from '../../src/admin/api/generated/client.gen'

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
