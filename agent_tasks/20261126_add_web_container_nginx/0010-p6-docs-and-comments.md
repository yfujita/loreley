# 0010 P6: README・コメントの仕上げ

- 日付: 2026-11-26
- 実施: code-implementer(ドキュメントとコメントのみ)→ メインエージェントが grep・差分を確認

## 変更ファイル

- `deploy/compose/README.md`: 構成表(`api` はホスト公開なし、`web` `127.0.0.1:8090`)、前提のポート、`API_HOST_PORT` → `WEB_HOST_PORT`(既定 8090)、起動手順(`curl -I http://127.0.0.1:8090/admin/`・`docker compose logs web api`・`docker compose exec api python -c ...` での `/healthz`)、新節「`web` サービス」、`api` の節(`web` は待たない・`LORELEY_API_WEB_URL`・「`web` が abnormal に見える(既知)」の削除と「`web` を止めると EP-13 で abnormal(`name_not_resolved`)」)、公開範囲(HO-40・41 を `web` に適用)、トラブルシュート(HTML の 502、`web` のビルド失敗(想定・未確認))、確認状況(0009 の実機確認の内容)。`--no-deps` の手順は載せず、compose v2.3.3 で `api` も起動してしまう注意を 1 文書いた
- `apps/api/README.md`: Web UI の配信は `web` コンテナの役割、必須環境変数を 4 つに、`WEB_URL` の行を追加(確認先 `{WEB_URL}/admin/`)、`WEB_DIST_DIR`・`/app/web`・「`web` は異常と表示される」を撤去、compose では `api` を publish しない旨と確認方法
- `apps/web/README.md`: dev サーバーの `/api` の転送先を B+C 後の状態に(既定 `http://127.0.0.1:8090`・先に compose で `web` を起動・`LORELEY_DEV_API_TARGET` で上書き・`api` は非公開で 8080 は指定できない)、「`web` コンテナ(Docker ビルド)」の短い節を追加
- `apps/web/vite.config.ts`: 冒頭コメントのみ(コードは不変。`git diff` で確認)

## 検証

- `grep -rIn "web_dist|WebDist|WEB_DIST|/app/web" apps deploy tests scripts`(`.venv`・`node_modules`・`__pycache__`・`results` を除く): **0 件**(メインエージェントも再実行)
- `API_HOST_PORT` の残り: IT の上書き(`tests/integration/api/compose.test.yaml`)・`scripts/run-api-integration-test.sh`・`tests/integration/api/README.md`・`deploy/compose/README.md`(「IT 用で本番用の compose にはない」の説明 1 文)

## 未対応・次の作業

- レビュー(code-reviewer・test-reviewer を並列)→ 指摘対応 → task-reviewer
- `docs/` の設計書・IT 結果文書(`docs/v0.x/test-results/admin-api-integration.md`。IT README 冒頭の「23 passed」の確認状況を含む)の追従は別タスク(申し送り)
