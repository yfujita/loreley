# Loreley

## プロダクト概要

社内ドキュメントをクロール・索引化し、Web UIやAIエージェント(MCP)から検索できるようにするサービス。

## アーキテクチャ

MVPは単一ホスト・単一Crawler・単一Indexer・直列実行・認証なしを前提とする(将来キュー化・複数化・認証追加を見据えた疎結合構成)。

- **Crawler**(`crawler`): 社内ドキュメントソースを巡回して原本を取得する。ジョブ・ロック・リースの管理、Indexerへの開始・終了通知を行う
- **Indexer**(`indexer`): 抽出・正規化・要約生成を行い、検索インデックスとStore層に登録する。削除の判断・実行(Deletion Manager)も担当する唯一のコンポーネント
- **Search API / Admin API / MCP Server**(`api`): 検索・管理操作の窓口。MCP ServerはAIエージェント向けインターフェース(Streamable HTTP)
- **Web UI**(`web`): 利用者向けSearch Viewと管理者向けAdmin View
- **OpenSearch**(`opensearch`): 検索インデックスと、Store層(設定・ジョブ・削除記録・抽出済みテキストなどのKVS)のバックエンドを兼ねる。Repositoryインターフェース経由のため将来差し替え可能

CrawlerとIndexerは別コンテナで、メッセージブローカーを介さずHTTPで直接通信する。バックエンドはPython。

## 参照先

- プロダクト設計: `docs/v0.x/product-design/`(版番号が最大のファイルが最新。改訂履歴は各文書の冒頭を参照)
- システム設計: `docs/v0.x/system-design/`(同上。実装レベルの詳細はこちら)
- タスク管理: `agent_tasks/`(新規タスクは `scripts/new-task.sh` で作成する)
- 作業ワークフロー: `.claude/rules/task-workflow.md`

## 開発ルール

- 既存の設計・実装との整合性を優先する。プロダクト設計・システム設計の決定事項と矛盾する実装をしない
- 要件にない機能を追加しない
- 変更に対応する検証(ビルド・テスト・リントなど)を実施する
