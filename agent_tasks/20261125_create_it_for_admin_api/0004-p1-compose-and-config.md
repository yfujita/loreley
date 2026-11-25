# 0004 P1: compose・設定・既存スクリプト

日付: 2026-11-25
担当: code-implementer(実装)、メインエージェント(差分と `docker compose config` の再確認)

## 実施内容

- `deploy/compose/compose.yaml` に `api` サービスを追加(build `../../apps/api`、`LORELEY_API_*`、`127.0.0.1:${API_HOST_PORT:-8080}:8080`、`depends_on` は opensearch(healthy)と opensearch-init(completed)のみ、`restart: unless-stopped`、検索対象の mount なし、`OPENAPI_ENABLED` なし)
- 共通変数を配線: `opensearch-init`(`DELETIONS_INDEX_NAME`・`SEARCH_INDEX_ALIAS`)、`indexer`(`LORELEY_INDEXER_DELETIONS_INDEX_NAME`・`..._SEARCH_INDEX_NAME`=エイリアス)、`crawler`(`LORELEY_CRAWLER_TIMEZONE`・`..._ADMITTING_LOCK_GRACE_SECONDS`)。init の実体名 `SEARCH_INDEX_NAME` は Indexer・api に渡さない
- 冒頭コメントの構成・公開範囲・同値定義(新設「Crawler と api の同値定義」)を更新
- `.env.example` に `API_HOST_PORT`・`API_LOG_LEVEL`・`LORELEY_DELETIONS_INDEX_NAME`・`LORELEY_SEARCH_INDEX_ALIAS`・`LORELEY_CRON_TIMEZONE`・`LORELEY_ADMITTING_LOCK_GRACE_SECONDS` を追記
- `deploy/compose/README.md`: 構成表・変数表・「`api` サービス」節・`web` が abnormal に見える注記(コードと Dockerfile の読解による。実機は未確認と明記)・HO-45 の起動直後の見え方・公開範囲の注意(HO-40・41)・3 スクリプトの同時実行不可
- `scripts/run-crawler-integration-test.sh`・`run-indexer-integration-test.sh`: 新索引名 2 変数の既定値 export を追加、同時実行不可コメントに api IT を追加(Indexer 側は jobs・sources の固定がもともとなく、新 2 変数のみ)
- `tests/integration/crawler/README.md`・`indexer/README.md`: api IT と同時に実行できない旨を追記

## 変更したファイル

`deploy/compose/compose.yaml`、`deploy/compose/.env.example`、`deploy/compose/README.md`、`scripts/run-crawler-integration-test.sh`、`scripts/run-indexer-integration-test.sh`、`tests/integration/crawler/README.md`、`tests/integration/indexer/README.md`(7 ファイル、+130/-18)

## 検証

- `docker compose -p loreley-it -f deploy/compose/compose.yaml config`(`.env` なし)rc=0。api の環境変数が既定値で展開(索引名 4 つ、`CRON_TIMEZONE=UTC`、猶予 60、`LOG_LEVEL=INFO`)、api の ports は `host_ip 127.0.0.1`・`published 8080`。init・indexer・crawler の共通変数も展開。実体名は api・indexer に渡っていない。`OPENAPI_ENABLED` は展開結果に出ない(メインエージェントも再確認)
- 変数上書き(`API_HOST_PORT=18080` ほか)で api が `127.0.0.1` のまま、共通変数が渡し先すべてに反映されることを確認。`API_LOG_LEVEL` は api のみに反映
- `--env-file deploy/compose/.env.example` での config と、crawler・indexer の `compose.test.yaml` との重ね合わせも rc=0
- 既存 2 スクリプトの `up -d --build` 行は未変更で、起動対象は不変(api は他サービスの依存先でないため起動しない)
- `bash -n` OK。shellcheck は未インストールのため未実施
- docker のコンテナ起動・停止・削除は一切行っていない

## 判断・設計上の理由

- 設計書(api-base-design 8章・9.2)との食い違いなし。HO-34・35・43・44 の要求を満たす
- README に `tests/integration/api`・`scripts/run-api-integration-test.sh` を「作成中」と注記して参照している(P2 で作成)

## 未対応事項・次にやること

- 実際に api が healthy になるか、EP-13 の値などの起動確認は P2 以降
- shellcheck 未実施
- 申し送り: api-base-design 9.2 の HO-34・35・40・41・43・44 の状態更新(設計書追従改訂タスクへ)
- 据え置き: `apps/api/Dockerfile` 11 行目の古いコメント
- 次: P2(`tests/integration/api` の土台、`scripts/run-api-integration-test.sh`、`test_01_startup.py`)
