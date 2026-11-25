# 20261125_create_it_for_admin_api

## 背景・目的

Admin APIの実装が完了したため、Admin画面の実装に先立ちIntegration Testを実装する。
実際のCrawler・Indexer・OpenSearchとの連携を検証し、コンポーネント間の契約の不整合や将来の変更による退行を検出できるようにする。

## 要件

### 現状(As-Is)

- Admin API(EP-01〜14)は実装済み。
- 単体テストおよび手動スモークテストは実施済みだが、自動化されたIntegration Testは存在しない。
- Crawler・IndexerのIntegration Testは実装済み。

### あるべき姿(To-Be)

Admin API・Crawler・Indexer・OpenSearchをComposeで起動し、実際のAdmin APIをHTTP経由で呼び出すIntegration Testを実行できる。また、テストが成功する。

既存の単体テストで十分に検証できる内容は重複して検証せず、実コンポーネント間の連携を中心に検証する。

### 具体的にやること

- Admin APIの設計書・実装・既存テスト、および手動スモークテストの結果と結合テストへの申し送りを確認する。
- 既存のCrawler・IndexerのIntegration Testを参考に、テスト用Composeと実行スクリプトを作成する。必要に応じて既存のComposeを更新する。
- 以下を中心に、主要なユースケースのIntegration Testを作成する。
  - データソースの登録・更新・一覧・詳細取得
  - クロール起動から完了までの状態遷移、ジョブ一覧・詳細、ロック状態の取得
  - 文書一覧・件数・集計・並べ替え・ページングなど、実OpenSearchに対するクエリの妥当性
  - クロール取消・ロック解放・データソース削除
  - コンポーネントの死活・停止時のエラーや部分失敗・復旧後の動作
- テストデータを通常の実行環境から分離し、テスト終了後にテスト用のリソースを安全に後始末できるようにする。非同期処理の完了待ちには期限を設ける。
- テストを実施し、失敗があれば原因を調査して必要な修正を行い、テストを成功させる。
- 実行方法とテスト結果を記録する。

## 対象範囲

- tests/integration/api/
- scripts/
- deploy/compose/
- docs/v0.x/test-results/
- 必要に応じてapps/api/、apps/crawler/、apps/indexer/、infra/

## スコープ外

- Admin画面の実装およびブラウザを用いたE2E Test
- 単体テストで検証済みの全入力パターン・エラーコードの網羅的な再検証
- Crawler・Indexer固有の業務ロジックの網羅的な再検証
- 大規模な負荷試験・複数ノード構成での障害試験
- Admin APIの新機能追加、認証・CSRF対策、テスト実装に直接関係しない設計変更

## 完了条件

- [ ] 実コンポーネントを用いたAdmin APIのIntegration Testが実行できる。
- [ ] 主要なユースケースについてIntegration Testが成功する。
- [ ] テスト実行後にテスト用のリソースが安全に後始末される。
- [ ] 既存の単体テストに退行がない。
- [ ] テストの実行方法・実行結果・未検証事項が記録されている。

## 成果物

- Integration Test用Compose設定
- Integration Test実行スクリプト
- Admin APIのIntegration Test
- テストのREADMEおよび実行結果
- 必要に応じた既存実装の修正

## 補足・参考情報

- Admin API設計: docs/v0.x/system-design/api/admin/
- Admin API実装: apps/api/
- 既存Integration Test: tests/integration/crawler/、tests/integration/indexer/
- Admin API実装タスク: agent_tasks/20261123_implement_admin_api/
  - 0018-p7-manual-smoke.md
  - 0021-task-review-and-handoff.md（B. 結合テストのタスクへの申し送り）
- 具体的なテストシナリオおよび未検証事項のうち今回対応する範囲は、要件確認・作業プラン作成時に決定する。