# 0004 P0: 事前確認とベースライン

- 日付: 2026-11-26
- 承認: ユーザーが 0003 のプランを承認(2026-11-26)

## 結果

- 比較基準の SHA: `656999348dbfc4fe956e8003af3e33917ccfbe29`(main。作業ツリーの未コミット分は agent_tasks のみ)
- `docker compose version`: v2.3.3(→ 上書きファイルから `ports` を消せない。0003 P-2 のとおり)
- 実行中のコンテナ: なし。ネットワークは `opensearch_default` のみ(触らない)
- ポート 8090・8080・8000・8001・9200: すべて空き(8090 は使用中でない。既定値のまま)
- 変更前 OpenAPI: scratchpad の `openapi-before.json`(102533 bytes)に書き出し済み
- `apps/api` のベースライン: `ruff check` OK、`ruff format --check` 249 files OK、`pytest` **3429 passed**(約 2 分)

## 次
P1(`web` イメージ。code-implementer)と P2(`api` の `web` 判定置換。code-implementer)を並行して依頼済み。
