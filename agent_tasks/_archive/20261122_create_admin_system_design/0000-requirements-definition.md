# 20261122_create_admin_system_design

## 背景・目的

admin画面のsystem_designを作成する。

## 要件

### 現状(As-Is)

admin画面の機能設計およびデザイン設計は存在するが詳細設計が存在しない。

### あるべき姿(To-Be)

以下のadmin画面の設計が存在する。

- admin api設計
- admin ui設計

### 具体的にやること

- APIを設計する
  - APIの技術スタックはindexerやcrawlerと揃える
- UIを設計する

## 技術スタック案

- Vue3
- Vite
- Vuetify
- Vue Router
- TanStack Vue Query
- Playwright

## 対象範囲

- docs/v0.x/system-design/ui-admins

## スコープ外

- Admin画面の実装

## 完了条件

- [ ] Admin画面の設計が存在する

## 成果物

- API仕様書: docs/v0.x/system-design/ui-admins/api/ui-admin-api-design-v0.x.md
- APIアーキテクチャ: docs/v0.x/system-design/ui-admins/api/ui-admin-api-architecture-v0.x.md
- APIモジュール構成: docs/v0.x/system-design/ui-admins/api/ui-admin-api-module-structure-v0.x.md
- フロントエンドアーキテクチャ: docs/v0.x/system-design/ui-admins/frontend/ui-admin-frontend-architecture-v0.x.md
- フロントエンドモジュール構成: docs/v0.x/system-design/ui-admins/frontend/ui-admin-frontend-module-structure-v0.x.md

## 補足・参考情報

- Admin画面機能設計: docs/v0.x/system-design/ui-admins/ui-admin-functions-v0.1.md
- Admin画面デザイン: docs/v0.x/ui-design/
- Admin画面画面仕様: docs/v0.x/ui-design/admin/
- Admin画面デザインモック: docs/v0.x/ui-design/mockups
- Product設計: `docs/v0.x/product-design`
- Crawler設計: `docs/v0.x/system-design/crawler`
- Indexer設計: `docs/v0.x/system-design/indexer`
