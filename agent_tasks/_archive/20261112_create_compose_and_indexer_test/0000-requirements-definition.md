# 20261112_create_compose_and_indexer_test

## 背景・目的

Indexerを実施したので動作確認を実施する。
そのため、Indexerだけある状態でcomposeに着手する。


## 要件

### 現状(As-Is)

compose設定が存在しない。

### あるべき姿(To-Be)

composeでindexerとopensearchが起動する。

### 具体的にやること

- composeの作成。indexerとopensearchのみ。他のモジュールは後で実装後に追加していく。
- composeでindexerとopensearchを起動する。
- indexerの動作確認手順（コード等の資材も）の作成
- indexerの動作確認の実施

## 対象範囲

- apps/indexer
- deploy
- tests

## スコープ外

- indexer以外のモジュールのcompose

## 制約・前提条件

- 結合テストコードはコメントをリッチにして何をテストしているのかがわかるようにする。

## 完了条件

- [ ] composeを利用したテストが成功

## 成果物

- compose設定ファイル
- テストコード

## 補足・参考情報

### 全体のディレクトリ構成案（参考）

```
loreley/
├── apps/
│   ├── api/                   # Search API / Admin API / MCP
│   │   ├── src/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   ├── crawler/               # クロール・ジョブ管理
│   │   ├── src/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   ├── indexer/               # 抽出・登録・削除・要約
│   │   ├── src/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   └── web/                   # Search View / Admin View
│       ├── src/
│       └── Dockerfile
│
├── packages/
│   └── contracts/             # 共有APIスキーマ・型定義
│
├── infra/
│   └── opensearch/
│       ├── Dockerfile         # 日本語解析プラグイン等
│       ├── config/
│       └── schema/
│           ├── search-index.json
│           └── deletions.json
│
├── deploy/
│   └── compose/
│       ├── compose.yaml
│       ├── compose.dev.yaml
│       ├── .env.example
│       ├── config/
│       └── README.md
│
├── tests/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   └── v0.x/                  # 既存の設計書
│
├── scripts/
│   ├── build-images.sh
│   ├── package-release.sh
│   └── smoke-test.sh
│
├── Makefile
└── README.md
```


## 仕様

- Product Design
  - docs/v0.x/product-design/product-design
- System Design
  - docs/v0.x/system-design/indexer/indexer-api
  - docs/v0.x/system-design/indexer/indexer-architecture
  - docs/v0.x/system-design/indexer/indexer-module-structure
  - docs/v0.x/system-design/opensearch/loreley-deletions
  - docs/v0.x/system-design/opensearch/search-index
