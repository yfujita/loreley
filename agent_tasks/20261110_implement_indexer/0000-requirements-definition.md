# 20261110_implement_indexer

## 要件

Indexerを実装する。

ディレクトリ構成は以下を参考にするs。

```
loreley/
├── apps/
│   ├── api/                   # Search API / Admin API / MCP
│   │   ├── src/
│   │   │   ├── search/
│   │   │   ├── admin/
│   │   │   ├── mcp/
│   │   │   └── shared/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   ├── crawler/               # クロール・ジョブ管理
│   │   ├── src/
│   │   │   ├── connectors/
│   │   │   │   └── local_fs/
│   │   │   ├── jobs/
│   │   │   ├── scheduler/
│   │   │   └── clients/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   ├── indexer/               # 抽出・登録・削除・要約
│   │   ├── src/
│   │   │   ├── extraction/
│   │   │   ├── indexing/
│   │   │   ├── deletion/
│   │   │   ├── summarization/
│   │   │   └── storage/
│   │   ├── tests/
│   │   └── Dockerfile
│   │
│   └── web/                   # Search View / Admin View
│       ├── src/
│       │   ├── search/
│       │   ├── admin/
│       │   └── shared/
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
  - docs/v0.x/system-design/opensearch/loreley-deletions-v0.9.md
  - docs/v0.x/system-design/opensearch/search-index-v0.9.md

