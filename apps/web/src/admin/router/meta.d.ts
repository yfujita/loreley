// `RouteMeta` の型(E 4.3・DS 5.3)。ナビ項目・パンくず・タイトル・テンプレートの定義は route `meta` にだけ持つ。
import type { RouteTitleSource } from '@/admin/composables/routeTitle'
import type { RouteName } from '@/admin/lib/routeNames'

declare module 'vue-router' {
  interface RouteMeta {
    /** ページ見出し・パンくず・`document.title`(「title - Loreley 管理」)。動的な見出し(識別子など)は route を受ける関数(I-83) */
    title: string | ((route: RouteTitleSource) => string)
    /** 使うページテンプレート(DS 6) */
    template: 'list' | 'detail' | 'form' | 'dashboard'
    /** パンくずの親(route 名) */
    parent?: RouteName
    /** ある場合だけナビに出る。`icon` は `@mdi/js` のアイコン(SVG パス) */
    nav?: { label: string; icon: string; group: string; order: number }
    /** `/meta` 由来のフラグ名。評価はナビ(`SideNav`・外部リンク領域)だけ(E 4.5。I-89) */
    featureFlag?: string
  }
}
