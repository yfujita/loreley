# 20261113_create_crawler_design

## 背景・目的

Indexerの実装が一旦完了したので、次にCrawlerを実装する。
そのための設計書を作成する。

## 要件

### 現状(As-Is)

Crawlerの設計書が存在しない。全体のSDは存在する。

### あるべき姿(To-Be)

Crawlerの設計書が存在する。

### 具体的にやること

- system-design/crawler/crawler-architecture-v0.X.md (アーキテクチャ設計)
- system-design/crawler/crawler-api-v0.X.md (API設計)
- system-design/crawler/crawler-module-structure-v0.X.md (モジュール構成設計)
- system-design/crawler/connector/connector-interface-v0.X.md (コネクタの共通インタフェース設計)
- system-design/crawler/connector/connector-file-system-v0.X.md （ファイルシステムコネクタ設計）
- system-design/crawler/connector/connector-web-v0.X.md （Webコネクタ設計）

※ Xはマイナーバージョン番号で1から始める

#### 設計書を記載するときの方針

- ArchitectureにはIndexerとの連携を含める
- Connector Interfaceは独立して設計する価値がある
- Web Connectorの詳細設計は後でよい。外枠だけ大まかに埋めて共通インターフェースと齟齬が起きないかを確認する。
- crawler-module-structureは他の設計が固まった後に最後に作成する。

## 対象範囲

- system-design/crawler配下の設計書

## スコープ外

- Crawlerの実装
- Web Connectorの詳細設計

## 制約・前提条件

- system-design-v0.X.mdは廃止予定のため、Crawlerの設計に合わせてメンテナンスする必要はない。Crawlerの設計はcrawler設計で完結させる。
- Indexerの既存設計・実装と整合すること。
  - 特にIndexer API、ジョブのライフサイクル、ロック・リース、文書ID、再クロール時の削除処理について整合性を確認すること。
  - Indexerの既存設計と矛盾する場合は独自に仕様変更せず、課題として記録すること。

## 完了条件

- [ ] 指定した6つの設計書が作成されている
- [ ] CrawlerとIndexerの連携仕様が整合している
- [ ] 各設計書の責務が明確で、設計内容に矛盾や不要な重複がない
- [ ] Connectorの共通インターフェースがFileSystemとWebの両方に適用可能である
- [ ] FileSystem Connectorは実装に着手できる粒度まで設計されている
- [ ] Web Connectorは概要設計にとどめ、詳細設計が必要な箇所を明示している
- [ ] 未決定事項や既存設計との不整合があれば一覧化されている

## 成果物

- system-design/crawler/crawler-architecture-v0.X.md (アーキテクチャ設計)
- system-design/crawler/crawler-api-v0.X.md (API設計)
- system-design/crawler/crawler-module-structure-v0.X.md (モジュール構成設計)
- system-design/crawler/connector/connector-interface-v0.X.md (コネクタの共通インタフェース設計)
- system-design/crawler/connector/connector-file-system-v0.X.md （ファイルシステムコネクタ設計）
- system-design/crawler/connector/connector-web-v0.X.md （Webコネクタ設計）

