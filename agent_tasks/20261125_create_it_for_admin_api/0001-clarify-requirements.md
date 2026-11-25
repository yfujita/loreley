# 0001 要件確認

日付: 2026-11-25

`requirements-clarifier` で要件確認を実施(2回)。ユーザーは Q1〜Q3 とも推奨案を選択した。最終 STATUS: `REQUIREMENTS_READY`。

## 目的

Admin API・Crawler・Indexer・OpenSearch を Compose で起動し、実際の Admin API を HTTP で呼ぶ Integration Test(IT)を作って成功させる。単体テストで足りる内容は重複させず、実コンポーネント間の連携を中心に検証する(0000)。

## 確定した回答(ユーザー選択)

### Q1: 検証範囲(案1)

- 対象:
  - 0000 の主要ユースケース 5 群(データソースの登録・更新・一覧・詳細/クロールの状態遷移・ジョブ一覧と詳細・ロック状態/文書一覧・件数・集計・並べ替え・ページング/取消・ロック解放・データソース削除/コンポーネント停止時のエラー・部分失敗と復旧後の動作)
  - 実機でしか確認できない申し送り(0021 B):
    - EP-07: 実行中ジョブの取消
    - EP-08: 実ロックの解放
    - EP-06: `lock_held`・`lock_in_use` の 409 と、実行中の `lock_state`
    - EP-05・06: `force_delete=true`
    - AAA-U-1: 複数ソース・複数ジョブでの並べ替え順、`terms` の `size`、`top_hits`
    - AAA-U-2: `mget`・`msearch` の実応答と `ids` クエリ
- 未検証事項として記録するもの: AAA-U-7、AAA-U-10、10,000 件のページング窓、一部シャード障害、複数ノードの `cat.*`・`relocating`、`ClientDisconnect`、入れ子マウントと `root_path`(BAPI-U-2)、`stalled=true`・`lease_expired`、AAPI-U-7(`skipped` 行の `existence`)

### Q2: api の Compose 構成(案1)

- `deploy/compose/compose.yaml` に `api` サービスを追加し、HO-34・35 を解消する(設計 `api-base-design-v0.1.md` 8章 236-241 行に従う)。
  - ビルドは `apps/api`、公開は `127.0.0.1:${API_HOST_PORT:-8080}:8080`
  - `depends_on` は `opensearch`(healthy)と `opensearch-init`(正常終了)のみ。`crawler`・`indexer` は待たない
  - healthcheck は `/healthz`、`restart: unless-stopped`、検索対象ディレクトリは mount しない
- 索引名は共通変数から渡す: `sources`・`jobs` は Crawler と同じ変数、`deletions` は Indexer と同じ変数、検索エイリアスは `opensearch-init` の `SEARCH_INDEX_ALIAS` と Indexer の `LORELEY_INDEXER_SEARCH_INDEX_NAME` と同じ変数。Indexer にまだ渡していない検索・削除記録の索引名もここでそろえる。
- cron のタイムゾーン(`LORELEY_CRAWLER_TIMEZONE` / `LORELEY_API_CRON_TIMEZONE`)と受付途中の猶予(`LORELEY_CRAWLER_ADMITTING_LOCK_GRACE_SECONDS` / `LORELEY_API_ADMITTING_LOCK_GRACE_SECONDS`)は、1 つの変数から Crawler と api の両方へ渡す(HO-43・44)。
- Web の成果物(HO-36・37)はスコープ外。
- テストだけに必要な差分は `tests/integration/api/compose.test.yaml` に置く。

### Q3: 障害系の方式(案1)

- pytest から `docker compose -p loreley-it stop/start <サービス>` を呼ぶ。
- 操作可能なのはプロジェクト名 `loreley-it` と許可リストのサービスのみ。
- `finally` で必ず `start` し、期限つきで healthy まで待つ。
- 障害系は最後のファイル(例: `test_90_*`)にまとめる。

## 推奨案で決めた事項(ユーザー確認不要と判断。プラン承認時に確認される)

1. 実行中ジョブの作り方: `compose.test.yaml` で Crawler の `LORELEY_CRAWLER_POLLING_INTERVAL_SECONDS` を Crawler IT(2 秒)より長くし、ロックが残る窓を広げる。値・文書数での補完はプランで決める。条件は「観測・操作の窓が数秒より十分長い」「IT 全体の時間を過度に延ばさない」。
2. Indexer の停止も障害系に含める(対象は crawler・indexer・opensearch)。EP-13 で `indexer` が `abnormal`、Crawler・OpenSearch 経由の EP は影響なし、復旧後に正常に戻ることを確認する。停止中に始めたクロールの結果は Crawler の業務ロジックなので網羅せず、観測結果を記録し、ジョブ終了まで期限つきで待つ。
3. README・`.env.example` の追従: `deploy/compose/README.md`・`.env.example` に `api` サービス、`API_HOST_PORT`、共通変数、公開範囲の注意(認証なし・127.0.0.1 限定。HO-40・41)を追記。`compose.yaml` 冒頭コメントも更新。`tests/integration/api/README.md` と `docs/v0.x/test-results/admin-api-integration.md` を新規作成。Crawler・Indexer IT の README には「同時に実行できない」の注記を追加する程度。
4. `OPENAPI_ENABLED`: `compose.yaml` では既定(無効)のまま、IT でも有効にしない(0018 で確認済み、無効時 404 は単体テストで確認済み)。
5. EP-13 の `web`: テスト用上書きで `index.html` だけを置いたディレクトリを `LORELEY_API_WEB_DIST_DIR` に mount して `normal` にする。

## 前提

- プロジェクト名は既存 IT と同じ `loreley-it`。ポートは 9200・8000・8001・8080 固定、すべて 127.0.0.1。既存 IT と同時に実行できない。
- 実行スクリプトは `scripts/run-api-integration-test.sh`(既存 2 本にならう)。起動前に残ったコンテナ・ボリューム・空でない data/・使用中ポートを確認し、見つかれば何も消さず中止。`up -d` 後に自前でポーリング(`--wait` は使わない)。終了時は `down -v --remove-orphans` と data/ 削除、`--keep` で残す。待機上限は `LORELEY_IT_WAIT_TIMEOUT_SECS`、終了コードは既存と同じ体系。
- テストデータ分離: 文書は `tests/integration/api/data/`(`.gitignore`、サンプルは複製)。`source_id` はテストごとに一意(`it-` 始まり)。他プロジェクトのコンテナは止めない(9200 を Fess などが使っていれば中止し相手を表示)。
- 非同期の待ちは間隔と上限を明示したポーリング。判定は Admin API の応答で行い、必要なら OpenSearch を直接読んで裏付ける。
- IT の依存は uv 専用プロジェクト(pytest・httpx)、`uv.lock` で固定。
- 実機の挙動が設計と違ったら、テストを実機に合わせず発見事項として記録する。設計書改訂はユーザー判断。
- 退行確認: 変更したアプリの単体テスト・ruff、`compose.yaml` を変えるので既存 Crawler・Indexer IT の再実行、既存スクリプトへの影響がないことの確認。

## 完了条件

0000 のとおり(5 項目)。

## 未解決事項

- ユーザー判断が必要なものはなし。
- プランで決める: Crawler ポーリング間隔の具体値、シナリオ ID 体系(例 `AIT-nn`)とファイル分割、`compose.yaml` の変数名。
- 据え置き(0021 C): `apps/api/Dockerfile` 11 行目の古いコメントは、Dockerfile に触れる場合のみ修正。

## 次のアクション

planner で作業プランを作成(0002)し、ユーザーの承認を得る。
