# 20261111_implement_indexer

## 背景・目的

全体構成の中でまずIndexerを実装する。

## 要件

### 現状(As-Is)

未実装

### あるべき姿(To-Be)

Indexerの実装が完了

### 具体的にやること

- 仕様の確認
- Indexerの実装
- 単体テスト

## 対象範囲

- Indexer

## スコープ外

- Indexer以外のモジュールの実装はスコープ外

## 制約・前提条件

- 

## 完了条件

- [ ] (完了と判断できる条件)

## 成果物

- (作成・変更するもの)

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
  - docs/v0.x/product-design/product-design-v0.17.md
- System Design
  - docs/v0.x/system-design/indexer/indexer-api-v0.9.md
  - docs/v0.x/system-design/indexer/indexer-architecture-v0.9.md
  - docs/v0.x/system-design/indexer/indexer-module-structure-v0.3.md
  - docs/v0.x/system-design/opensearch/loreley-deletions-v0.9.md
  - docs/v0.x/system-design/opensearch/search-index-v0.9.md
