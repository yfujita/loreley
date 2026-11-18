# 20261116_create_it_for_crawler

## 背景・目的

Crawlerを実装したのでIntegration Testを実装したい。

## 要件

### 現状(As-Is)

単体テストはあるがIntegration Testがない

### あるべき姿(To-Be)

CrawlerがComposeで起動でき、Integration Testを実行できる。また、テストが成功する。

### 具体的にやること

- 不足しているスキーマ等の準備
- Composeの作成
- テストの作成
- テストを実施し、失敗があればCrawlerまたはテストを修正し、テストを成功させる。

## 対象範囲

- apps/cawler
- infra
- deploy
- tests

## 完了条件

- [ ] Integration Testが成功する

## 成果物

- Compose
- Schemaなど
- Test
- (必要があれば)修正したCrawler

