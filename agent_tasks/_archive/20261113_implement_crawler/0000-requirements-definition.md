# 20261113_implement_crawler

## 背景・目的

Crawlerモジュールを実装する

## 要件

### 現状(As-Is)

設計書だけ存在している

### あるべき姿(To-Be)

Clawlerが実装されている

### 具体的にやること

- 設計書の内容の把握
- Crawlerモジュールの実装
  - ConnectorはFileSystemのみ実装。
- Crawlerモジュールの単体テスト

## 対象範囲

- apps/crawler
- docs/system-design/crawler

## スコープ外

- CrawlerのIntegration Test

## 完了条件

- [ ] Crawlerが実装され、単体テストが通っている。

## 成果物

- Crawlerのソースコード。

## 補足・参考情報

### 設計書

X部分はそれぞれ最新を参照する。

- docs/system-design/crawler/crawler-api-v0.X.md
- docs/system-design/crawler/crawler-architecture-v0.x.md
- docs/system-design/crawler/crawler-design-decisions-v0.X.md
- docs/system-design/crawler/crawler-module-structure-v0.X.md
- docs/system-design/crawler/connector/connector-interface-v0.X.md
- docs/system-design/crawler/connector/connector-file-system-v0.X.md