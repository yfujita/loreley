# 0001 要件確認の結果

日付: 2026-11-23

## 実施内容

`requirements-clarifier` で要件定義(0000)の不明点を洗い出し、スコープ境界3点をユーザーに確認した。

## ユーザー回答(確定)

| # | 質問 | 回答 |
|---|------|------|
| Q1 | 実装範囲 | 14本(EP-01〜14)すべてをこのタスクで実装し、フェーズに分ける(共通部品 → 読み取り系 → 書き込み系 → EP-13) |
| Q2 | 周辺範囲 | OpenAPI書き出し(`admin/openapi_export.py`)+`OPENAPI_ENABLED`、README更新(環境変数・HO-40/41の注意書き・README冒頭の古い記述の修正)を含める。`/admin/` 静的配信・SPAフォールバックと compose/Dockerfile への api サービス追加は含めない(別タスク。ただし EP-13 に必要な `WEB_DIST_DIR` 設定と probes/web_dist は含む) |
| Q3 | 検証方法 | 単体テスト+アーキテクチャテスト+手動スモーク確認。自動結合テストは作らない |

## 確定した要件(設計書由来・質問不要)

- 実装の正本は Admin API 設計(admin-api-v0.1 / architecture-v0.1 / module-structure-v0.1)と api-base-design-v0.1。ゲート3(2026-11-23)承認済み
- EP は14本(ベース `/api/admin/v1`)。Admin API は OpenSearch・Store層に書き込まない。書き込みは Crawler の固定6経路の中継のみ
- Indexer とのやり取りは EP-13 の `GET /healthz` のみ
- Crawler クライアントは urllib3。接続3秒・応答60秒(仮値)、再送なし
- 依存追加: `opensearch-py`・`urllib3`・`anyio`

## 前提として置く事項(プランで承認を得る)

- 対象範囲の `apps/api/src/admin/` は実在パッケージ `apps/api/src/loreley_api/admin/` と読み替える。組み込みに必要な `main.py`・`config.py`・`common/` の残り・`infrastructure/`・`tests/`・`pyproject.toml`・`uv.lock` も変更対象に含める(module-structure D 4.12(b))
- 完了条件「Admin API が存在している」は、①範囲内EPがB仕様どおり応答 ②`uv run pytest` と ruff が通る ③アーキテクチャテスト追加・通過 ④OpenAPI が生成できる、の4点で解釈する
- ブランチ: 現在 `main`(PR #17 マージ済み)。実装前に `feature/implement-admin-api` を切る
- 設計書と実装に食い違いが出た場合は設計書を直接直さず、作業記録で申し送る(別タスクで追従改訂)
- 実装時確認事項(AAPI-U・AAA-U・AAM-U)は、手動スモークで確認できたものだけ作業記録に残す

## 未対応事項

- プラン作成(planner)とユーザー承認
