# 20261126_create_admin_ui_system_design

## 背景・目的

Admin Viewの実装に向けて、フロントエンドのシステム設計を整備する。

既存のAdmin Viewの機能設計、UIデザイン設計、フロントエンド設計、および実装済みのAdmin APIを踏まえ、実装時に必要となる技術的な方針、モジュール構成、各モジュールの責務を明確にする。

## 要件

### 現状(As-Is)

- Admin Viewの機能設計およびUIデザイン設計は作成済み。
- フロントエンドのアーキテクチャ設計およびモジュール構成設計(v0.1)は作成済み。
- Admin APIの実装およびIntegration Testの作成は完了している。
- 既存のフロントエンド設計はAdmin APIの実装前に作成されており、実際のAPI実装との整合性が確認されていない。
- フロントエンド設計には未決事項および実装時の確認事項が残っている。
- Admin View自体は未実装である。

### あるべき姿(To-Be)

- Admin Viewの実装に必要なシステム設計が整備されている。
- 実装済みのAdmin APIとフロントエンド設計の整合性が取れている。
- フロントエンドのディレクトリ構成、モジュール構成、各モジュールの責務および依存関係が明確になっている。
- 各画面が利用するAPIおよびデータの取得・更新方法が明確になっている。
- Admin Viewのビルド、配信、テストの方針が明確になっている。
- 既存設計の未決事項が整理され、実装開始前に決定すべき事項が解消されている。
- 将来的な画面や機能の追加が容易な構成となっている。

### 具体的にやること

- 既存の機能設計、UIデザイン設計、フロントエンド設計およびAdmin APIの実装を確認する。
- 既存のフロントエンド設計とAdmin APIの実装との差異を調査する。
- フロントエンドのアーキテクチャ設計を見直す。
  - 技術スタックおよび依存ライブラリ
  - アプリケーション構成
  - ルーティング
  - 状態管理
  - APIクライアントおよびOpenAPIを利用した型・クライアントの生成
  - データ取得、キャッシュ、ポーリングおよび更新処理
  - エラーハンドリング
  - フォームおよびバリデーション
  - ビルドおよび静的ファイルの配信
  - 開発環境の構成
- フロントエンドのモジュール構成設計を見直す。
  - ディレクトリ構成
  - モジュールの分割方針
  - 各モジュールの責務
  - モジュール間の依存関係
  - コンポーネントの共通化方針
  - 画面・機能とモジュールの対応関係
  - Admin View固有の処理と将来的にSearch Viewと共有する処理の分離方針
- 各画面とAdmin APIの対応関係を確認する。
  - ダッシュボード
  - データソース管理
  - ジョブ管理
  - ドキュメント管理
  - OpenSearch管理
- テストおよび品質管理の方針を整理する。
  - Unit Test
  - コンポーネントテスト
  - E2E Test
  - 実際のAdmin APIとの接続確認
  - 型チェック、Lint、フォーマット
  - モジュール間の依存ルールの検証
- DockerおよびDocker ComposeにおけるAdmin Viewのビルド・配信方針を整理する。
- 既存設計に残されている未決事項および申し送り事項を確認する。
- Admin APIの実装やOpenAPIスキーマに修正が必要な事項がある場合は、その内容を整理する。
- 作成・更新した設計書のレビューを実施する。

## 対象範囲

- Admin Viewのフロントエンドに関するシステム設計
- `apps/web/` の構成設計
- Admin ViewとAdmin APIの連携設計
- Admin Viewのビルドおよび配信に関する設計
- Admin Viewのテストに関する設計

## スコープ外

- Admin Viewの本実装
- Admin API、Crawler、Indexerの実装変更
- Admin Viewの機能追加
- Admin ViewのUIデザインの再設計
- Search Viewの設計および実装
- Search APIおよびMCPの設計
- 認証・認可機能の新規設計および実装
- DockerfileおよびDocker Composeの実装変更
- テストコードの本実装

## 制約・前提条件

- 既存のProduct設計、System設計、Admin Viewの機能設計およびUIデザイン設計に準拠する。
- 既存のフロントエンド設計で承認済みの方針は、変更が必要な理由がない限り維持する。
- 技術スタックは既存設計に従い、以下を基本とする。
  - Vue 3
  - TypeScript
  - Vite
  - Vuetify
  - Vue Router
  - TanStack Vue Query
  - Hey API(OpenAPI TypeScript)
  - Vitest
  - Playwright
- Admin ViewからCrawler、Indexer、OpenSearchに直接アクセスせず、Admin APIを経由する構成とする。
- Admin APIが提供する業務ロジックや状態判定をフロントエンドで重複して実装しない。
- Admin Viewは `/admin/` 配下のSPAとし、既存設計に従ってAPIサーバーから静的配信する構成を基本とする。
  - 【2026-11-26 注記】ユーザー指示により、静的配信は API サーバーではなく `web` コンテナ(Nginx)が行い、`/api/` も Nginx がプロキシする構成に変更した(作業記録 0003・0007)。
- オンプレミスおよびローカル環境での利用を考慮し、外部CDN等への実行時の依存を持たない構成とする。
- 既存の公開範囲およびセキュリティに関する制約を維持する。
- 過度な抽象化や将来的な拡張を目的とした不要な設計は行わない。
- 技術的な確認に必要な最小限の検証コードの作成は許容するが、プロダクトの実装は行わない。
- 既存設計の変更が必要な場合は、変更理由および影響範囲を整理し、承認を得る。
- 実装時に確認すべき事項については、無理に本タスクで決定せず、申し送り事項として整理する。

## 完了条件

- [ ] Admin Viewのフロントエンドアーキテクチャ設計書が整備されている。
- [ ] Admin Viewのフロントエンドモジュール構成設計書が整備されている。
- [ ] 各モジュールの責務および依存関係が明確になっている。
- [ ] Admin Viewの各画面とAdmin APIの対応関係が明確になっている。
- [ ] Admin APIの実装およびOpenAPIスキーマとフロントエンド設計の整合性が確認されている。
- [ ] ビルド、配信、開発環境およびテストの方針が明確になっている。
- [ ] 既存設計との不整合、未決事項および申し送り事項が整理されている。
- [ ] 実装開始を妨げる未決事項が解消されているか、必要な前提タスクが明確になっている。
- [ ] 設計書のレビューが完了し、対応が必要な指摘事項が解消されている。

## 成果物

- フロントエンドアーキテクチャ設計書
  - `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-architecture-v0.2.md`
- フロントエンドモジュール構成設計書
  - `docs/v0.x/system-design/ui-admin/frontend/ui-admin-frontend-module-structure-v0.2.md`
- 既存設計との不整合、未決事項および申し送り事項の整理
- 必要に応じた関連設計書の追従改訂

## 補足・参考情報

- Product設計: `docs/v0.x/product-design/`
- Admin View機能設計: `docs/v0.x/system-design/ui-admin/ui-admin-functions-v0.1.md`
- Admin View UIデザイン仕様: `docs/v0.x/ui-design/admin-view-v0.1.md`
- デザインシステム: `docs/v0.x/ui-design/design-system-v0.1.md`
- 各画面のUIデザイン仕様: `docs/v0.x/ui-design/admin/`
- UIデザインモック: `docs/v0.x/ui-design/mockups/`
- 既存のフロントエンド設計: `docs/v0.x/system-design/ui-admin/frontend/`
- API共通基本設計: `docs/v0.x/system-design/api/api-base-design-v0.1.md`
- Admin API設計: `docs/v0.x/system-design/api/admin/`
- Admin API実装: `apps/api/`
- Admin API Integration Test: `tests/integration/api/`
- Admin API Integration Test結果: `docs/v0.x/test-results/admin-api-integration.md`
- Docker Compose: `deploy/compose/`
- Admin API実装時の申し送り: `agent_tasks/20261123_implement_admin_api/STATUS.md`
- Admin API Integration Test実装時の申し送り: `agent_tasks/20261125_create_it_for_admin_api/STATUS.md`